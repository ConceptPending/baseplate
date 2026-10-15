# Recipe: concurrency-safe state transitions

The [lifecycle state machine](lifecycle-state-machine.md) recipe makes illegal
transitions *structurally impossible* — but only against a single actor at a
time. It says so itself ("Not a concurrency control… add an optimistic-lock
`version` column and a separate test"). This recipe is that hand-off, written
out.

The state machine sits **above** your persistence layer. It decides whether a
transition is legal given a snapshot of the entity; it does not stop two actors
from each reading that snapshot and both acting on it. When transitions move
money, allocate inventory, or assign work, that gap is where the real defects
live — the boring lifecycle bugs are gone, so what's left is the race. Use this
recipe when an entity's transitions are contended: two admins on the same queue,
an admin racing the expiry job, or any transition that writes more than just
`status`.

## The race, concretely

`SubmissionService.transition()` is a read-modify-write:

1. **read** — load the row; build a snapshot (`status` + the guard's inputs);
2. **decide** — `statespec.apply(...)` judges the transition legal *for that snapshot*;
3. **write** — persist the new state.

Between (1) and (3) another transaction can commit a change to the same row. With
a naive `submission.status = new_state; await db.commit()` you get one of two
classic defects:

- **Lost update** — two admins both load `pending`, one approves, the other
  rejects; the second write silently overwrites the first. The audit trail shows
  one decision; the database holds the other.
- **Stale-fact decision** — the guard read `balance >= amount`, but another
  transaction drew the balance down between the read and the write. The
  transition was legal against a snapshot that no longer exists. (This is the
  "money at the seams" class — see *Scope* at the end.)

## What you'll add

Three tiers, smallest first. Most slices need only Tier 1 or 2.

| Tier | Mechanism | Schema change | Testable on SQLite | When |
| --- | --- | --- | --- | --- |
| **1** | Compare-and-set on `status` | none | yes | The transition's only write is `status`, and every guard input is immutable or derived from `status`/`created_at`. **The reference already does this.** |
| **2** | `version` column (optimistic lock) | one column | yes | The transition writes other columns (a payload), or a guard reads a *mutable* non-`status` field. The general default. |
| **3** | `SELECT … FOR UPDATE` (pessimistic) | none | **no** (Postgres-only) | Conflicts are frequent, or the critical section is expensive to recompute, or it spans multiple rows. |

## Tier 1 — status compare-and-set (you already have this)

Look at the reference `SubmissionService.transition()` on the
`example/state-machine` branch — it is **not** a naive setter:

```python
result = await db.execute(
    update(Submission)
    .where(Submission.id == submission.id, Submission.status == old_state)
    .values(status=new_state)
    .execution_options(synchronize_session=False)
)
if result.rowcount == 0:
    await db.rollback()
    raise IllegalTransition(
        f"{action!r}: submission left state {old_state!r} concurrently"
    )
await db.commit()
```

The `Submission.status == old_state` clause is the lock. Two admins both load
`pending`; the first commits `approved`; the second's `UPDATE … WHERE status =
'pending'` now matches **zero rows**, so `rowcount == 0` and it's refused instead
of clobbering. No schema change, no extra column — the state you're leaving *is*
the version token.

**This is enough when** the only thing the transition mutates is `status`, and
every guard input is immutable-once-set or derived from immutable data. The
submission slice qualifies: the `is_stale` guard reads `age_days`, derived from
`created_at`, which never changes. Don't add Tier 2 ceremony you don't need.

**It is not enough when** either of these is true:

- **The transition writes a payload.** `apply(..., post_overrides={...})` lets a
  transition set `reviewed_by`, `decision_note`, `amount`. A self-loop that keeps
  `status` the same (e.g. an `add_note` edge `pending → pending`) passes the
  `status == old_state` check for *both* racing writers — lost update. And even on
  a real flip, status-CAS guards only `status`; a separate un-versioned edit
  endpoint writing `amount` is invisible to it.
- **A guard reads a mutable non-`status` field** (`error_count`, `balance`,
  `assignee`). Status-CAS detects that the *status* changed, not that the *fact*
  the decision rested on changed. The write commits against stale facts.

For either, move to Tier 2.

## Tier 2 — a `version` column (optimistic lock)

A monotonic `version` integer guards the **whole row**. Every transition reads
the version at decision time and writes conditioned on it; any committed change
to the row in between bumps the version, so the stale writer matches zero rows.

### 1. Model

```python
from sqlalchemy import Integer

class Submission(Base, TimestampMixin):
    ...
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
```

### 2. Migration

`make migrate-new msg="add version to submissions"`, then confirm it reads like
this (NOT NULL with a server default, matching the house rule that columns the
model treats as always-present are `nullable=False` in the migration too):

```python
def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

def downgrade() -> None:
    op.drop_column("submissions", "version")
```

### 3. A distinct conflict error

Add to `app/statespec/core.py` (and export it from `app/statespec/__init__.py`),
**separate** from `IllegalTransition`:

```python
class ConcurrencyConflict(TransitionError):
    """The row was modified between the decision and the write. The action may
    still be legal — the caller should re-read and retry, not give up."""
```

The distinction is the point: `IllegalTransition` means *don't retry this* (the
action isn't legal from that state); `ConcurrencyConflict` means *the row moved
under you — re-read and decide again*. Conflating them sends the wrong signal to
both the client and the retry loop below.

### 4. Service: version compare-and-set

```python
@staticmethod
async def transition(db, submission, action, actor_roles, *, overrides=None):
    overrides = overrides or {}
    expected = submission.version            # the version the decision is made against
    new_state = apply(
        SUBMISSION_SPEC, action, submission.status, actor_roles,
        SubmissionService._snapshot(submission), post_overrides=overrides,
    )
    result = await db.execute(
        update(Submission)
        .where(Submission.id == submission.id, Submission.version == expected)
        .values(status=new_state, version=expected + 1, **overrides)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        await db.rollback()
        raise ConcurrencyConflict(
            f"submission {submission.id} changed under {action!r}; re-read and retry"
        )
    await db.commit()
    await db.refresh(submission)             # bulk UPDATE leaves the object stale
    return submission
```

The load (in your route or job) and this write must share one transaction — the
session must not `commit` between them, or the window reopens. The reference
loads via `get_by_id` (a `SELECT`, no commit) and writes here, so they do.

> **The one invariant that makes this work:** *every* write path to the row must
> bump `version`. A transition that writes through `apply` does; an ad-hoc edit
> endpoint that does `submission.field = x; await db.commit()` does **not**, and
> it will slip a lost update straight past the lock. Either route every write
> through a version-bumping path, or use SQLAlchemy's native
> [`version_id_col`](https://docs.sqlalchemy.org/en/20/orm/versioning.html), which
> enforces the bump on ORM flush. This codebase writes with explicit `update()`
> statements (not ORM dirty-flush), so the manual CAS above is the honest fit —
> but if you adopt `version_id_col`, let it own the bump and drop the manual
> `version=expected + 1`.

### 5. Map the conflict to HTTP 409

In `app/api/submissions.py`, alongside the existing engine-error mapping:

```python
except ConcurrencyConflict:
    raise HTTPException(status_code=409, detail="Submission was modified; please retry")
```

409 (Conflict) tells a client the request was well-formed but raced — retry after
re-fetching. Don't reuse the 4xx you map `IllegalTransition` to; a client that
retries an illegal transition loops forever, and a client that gives up on a
conflict drops a legitimate action.

### 6. Retry where a retry is safe

System jobs and idempotent server-side callers should re-read and retry — but
re-read *every* attempt; reusing the stale object just re-raises:

```python
async def transition_with_retry(db, sid, action, roles, *, attempts=3):
    for _ in range(attempts):
        submission = await SubmissionService.get_by_id(db, sid)   # fresh read each time
        if submission is None:
            return None
        try:
            return await SubmissionService.transition(db, submission, action, roles)
        except ConcurrencyConflict:
            continue
    raise ConcurrencyConflict(f"{action!r} on {sid} lost {attempts} races")
```

`SubmissionService.expire_stale` already re-fetches each row before transitioning
— give it this loop and a contended submission gets expired on the next pass
instead of being abandoned. **Don't** auto-retry a *human* action: surface the
409 so the reviewer re-reads what changed before re-deciding.

## Tier 3 — `SELECT … FOR UPDATE` (pessimistic), Postgres only

When conflicts are frequent enough that optimistic retries thrash, or the
critical section is expensive, or it touches several rows, take the row lock up
front:

```python
result = await db.execute(
    select(Submission).where(Submission.id == sid).with_for_update()
)
submission = result.scalar_one()
# ... decide and write; concurrent actors block here until this tx commits
await db.commit()                            # releases the lock
```

Concurrent transactions **block** on the locked row instead of racing, so there's
nothing to retry. The cost: held locks, and the risk of deadlock if two paths
lock multiple rows in different orders (always lock in a consistent order).

**SQLite caveat (read this):** the test engine is `aiosqlite`, which **ignores
`FOR UPDATE`** — there are no row locks, so this path is silently a no-op under
`make test-backend` and cannot be tested there (see the SQLite gotcha in
`CLAUDE.md`). Gate it on the dialect and keep an optimistic fallback so the
SQLite path is still correct:

```python
stmt = select(Submission).where(Submission.id == sid)
if db.get_bind().dialect.name == "postgresql":
    stmt = stmt.with_for_update()
```

Test the locking behaviour against a real Postgres in CI, not SQLite. **Default
to Tier 2** — it's lower-contention, holds no locks, and is fully testable on
SQLite. Reach for Tier 3 only when you've measured that you need it.

## Tests

Force the race deterministically — no threads. Two sessions read the same row at
the same version; the second writer must lose:

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.roles import REVIEWER            # whatever roles your spec's edges require
from app.services.submissions import SubmissionService
from app.statespec import ConcurrencyConflict

REVIEWER_ROLES = frozenset({REVIEWER})   # actor_roles is a frozenset, not a bare string


@pytest.mark.asyncio
async def test_concurrent_transitions_one_wins(db_engine):
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as s0:
        created = await SubmissionService.create(s0, _payload())
        sid, base_version = created.id, created.version

    # Two readers load the same row at the same version — the race window.
    async with factory() as s1, factory() as s2:
        a = await SubmissionService.get_by_id(s1, sid)
        b = await SubmissionService.get_by_id(s2, sid)
        assert a.version == b.version == base_version

        # First writer commits and bumps the version.
        await SubmissionService.transition(s1, a, "approve", REVIEWER_ROLES)

        # Second writer's CAS no longer matches — refused, not a silent clobber.
        with pytest.raises(ConcurrencyConflict):
            await SubmissionService.transition(s2, b, "request_info", REVIEWER_ROLES)

    # The surviving state is the winner's, bumped exactly once.
    async with factory() as s3:
        final = await SubmissionService.get_by_id(s3, sid)
        assert final.status == "approved"
        assert final.version == base_version + 1
```

Add a second test that the retry helper *succeeds* once the row settles
(`transition_with_retry` returns the winner after one conflict), and one that a
human-facing 409 is returned by the route (drive it through `client`, mirroring
`tests/test_submission_lifecycle_api.py`).

This is deterministic because optimistic locking doesn't need a true wall-clock
race to exercise — a stale version is a stale version however it got that way.

## What to skip

- **Distributed / cross-process locks** (Redis, Postgres advisory locks) — within
  one database, the row lock or the version column already serialises. Reach for
  these only when the critical section spans systems, and only after measuring.
- **Raising the isolation level to `SERIALIZABLE`** globally — it converts races
  into transaction-retry errors you'd handle the same way, at a throughput cost
  on every transaction. Per-row optimistic locking is cheaper and more targeted.
- **Field-level merge / operational transforms** — overkill for status workflows.
  A conflict here means "re-read and re-decide," not "auto-merge two intents."

## Scope (the honest boundary)

This closes the **single-row** race on the transition path: one entity, one
database, read-decide-write in one transaction. It does **not** address
consistency *across systems* — a transition here plus a charge in a payment
processor, or a write to a second service. Those can't be locked together; they
need **reconciliation** (a periodic job that detects and repairs divergence),
which is a different control and out of scope here. The state machine raised the
floor on structural correctness and pushed the residual risk down into
concurrency and the seams; Tier 1–3 cover the concurrency half. The seams are
still yours.
