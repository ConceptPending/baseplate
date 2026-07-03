# Recipe: lifecycle entity with a verified state machine

Some entities aren't just rows you edit — they move through a **lifecycle**: a
submission is received, reviewed, approved or rejected; an invoice batch is
uploaded, then approved or rejected; a case is opened, triaged, closed. These
have rules a plain `status` column can't express:

- which transitions are legal (you can't approve a batch that was rejected);
- who may perform each one (the person who *reviews* isn't always the one who
  *approves* — separation of duties);
- conditions that gate a step (don't approve a batch with unresolved errors).

This recipe models that lifecycle as a **declarative spec** enforced by a small,
generic engine, so the same artifact is readable by a non-engineer *and*
provable by a machine. It replaces the free-form `entity.status = new_value`
setter — which silently allows any value from any state, by anyone — with a
single guarded transition path.

## Why bother (the two audiences)

- **Humans (fit-for-purpose).** `make spec-doc` renders the spec to
  `docs/specs/<entity>-lifecycle.md`: a state diagram, a plain-English
  "who-may-do-what" table, and the declared invariants. A domain owner,
  reviewer, or auditor signs off on *that* — without reading Python. It's
  generated and CI-checked, so it **can't drift from the declarative spec**.
- **Machines (correctness).** Every transition goes through one function,
  `statespec.apply`. At runtime it enforces the guard and the invariants
  against the proposed post-state; a Hypothesis `RuleBasedStateMachine` also
  drives it over random action/role sequences. So the application's *canonical
  transition path* is continuously checked against the declared spec.

That gives you a concrete, inspectable control: the documented workflow and the
enforced workflow are the same declarative object, and a change to it is visible
in the rendered doc and a structural diff. **Read the scope honestly, though**
— this checks that the app applies the declared rule on its transition path. It
does *not* by itself cover: a service that supplies wrong *facts* (runtime
context type-checking mitigates, doesn't eliminate, this); direct database
mutations; concurrency; `Opaque` custom code; audit/evidence of *who did what*
(a separate concern); or whether the human-approved policy is itself correct.
It's a strong ingredient for access-control / change-management evidence (SOC 2
and similar), not a turnkey control on its own.

## Worked examples

The full engine and two end-to-end applications already exist — copy from them
rather than retyping:

- **`example/state-machine` branch of this repo** — the engine plus a
  **submission moderation** lifecycle, including a *system-fired* transition
  (a scheduled job auto-expires stale submissions; no human actor) and the
  role-assignment endpoint. The canonical in-repo reference.
- **[`flatpack-invoice-review-example`](https://github.com/ConceptPending/flatpack-invoice-review-example)**
  — the recipe applied to a real promoted project: a `ReviewBatch` approval
  lifecycle, role-gated, with a guard that refuses to approve a batch holding
  unresolved validation errors.

## The pieces

| File | Role |
| --- | --- |
| `app/statespec/core.py` | Generic engine: `StateSpec`/`Transition` data model, `apply` (the single enforcement path), `validate` (well-formedness). Domain-free — copy verbatim. |
| `app/statespec/render.py` | Spec → Mermaid diagram / Markdown table / dict. Copy verbatim. |
| `app/statespec/<entity>_spec.py` | The domain spec: states, transitions, roles, guards, invariants. **Source of truth.** |
| `app/roles.py` | The role vocabulary; `HUMAN_ROLES` (grantable) vs the full engine set (which may include a synthetic `SYSTEM` actor). |
| `app/services/<entity>.py` | A thin `transition()` method that calls `apply` and persists. No other lifecycle logic. |
| `app/api/<entity>.py` | A `POST /{id}/transition` endpoint + `roles_for(user)`; maps engine refusals to HTTP codes. `GET /lifecycle` exposes the spec as data. |
| `tests/test_<entity>_statespec.py` | Static checks + the Hypothesis conformance machine. |
| `scripts/statespec.py` | `check` (CI gate) and `render` (regenerate docs). Register new specs in `SPECS`. |

## Steps

1. **Copy the engine.** Bring `app/statespec/{core,render,__init__}.py` and
   `scripts/statespec.py` across from the `example/state-machine` branch. They
   are domain-free.

2. **Write the spec.** Create `app/statespec/<entity>_spec.py`. Declare your
   `states`, a typed `fields` schema (the context contract — what the service
   snapshot must provide), the `initial` and `terminal` (sink) states, and each
   `Transition(name, sources, dest, roles, guard?, label)`. Guards and
   invariants are **declarative expressions** (`app/statespec/expr.py`), not
   Python functions: `field(...).eq/ne/lt/le/gt/ge/is_in(...)` combined with
   `all_/any_/not_`. Because they're pure data, the rendered doc shows the real
   condition and a change to it is diff-visible.

   ```python
   BATCH_SPEC = StateSpec(
       name="batch", title="Batch review lifecycle",
       states={"pending": "...", "approved": "...", "rejected": "..."},
       fields={"status": "str", "error_count": "int"},   # the context contract
       initial="pending", terminal=frozenset({"approved", "rejected"}),
       transitions=(
           Transition("approve", ("pending",), "approved",
                      roles=frozenset({APPROVER}),
                      guard=field("error_count").eq(0)),
           Transition("reject", ("pending",), "rejected",
                      roles=frozenset({REVIEWER, APPROVER})),
       ),
       invariants=(
           Invariant("approved_implies_clean",
                     any_(field("status").ne("approved"),
                          field("error_count").eq(0)), "..."),
       ),
   )
   ```

   The grammar is closed at comparison + boolean. A condition that genuinely
   can't be a context field (a live cross-entity lookup) uses a **versioned**
   `opaque("name", 1, "label", fn=...)` escape hatch — flagged "requires
   technical review" and registered. It is *identified and versioned*, so it's
   conspicuously excluded from declarative assurance; note the registry does
   not by itself detect a body swap made without a version bump (binding a
   source hash to the approved policy is the identity layer's job).

3. **Register + validate.** Add the spec to `SPECS` in `scripts/statespec.py`
   and run `make spec-check` (it passes the role catalogue). It refuses
   unreachable states, traps, dead edges, duplicate/un-catalogued roles, and
   **type-mismatched or unknown-field expressions** — so a malformed lifecycle
   (or a guard comparing a `uuid` to a `str`) can't reach production.

4. **Add the columns + migration.** A `status: Mapped[str]` defaulting to the
   spec's initial state (plain `String`, **not** a DB enum — the spec is the
   source of truth), plus any fields your invariants need. Write the migration
   by hand; `add_column` of a string + index is safe on SQLite and Postgres.

5. **Add the service method.** One `transition()` that builds a snapshot dict,
   calls `statespec.apply(SPEC, action, entity.status, actor_roles, snapshot)`,
   assigns the returned state, sets derived fields, and commits. Resist putting
   branching logic here — the engine owns the decisions.

6. **Add the endpoint.** `POST /{id}/transition` taking `{action}`. Supply
   roles via `roles_for(current_admin)` and translate `TransitionError`
   subclasses to status codes (`UnknownAction`→422, `IllegalTransition`→409,
   `PermissionDenied`→403, guard→409). Expose `GET /lifecycle` returning
   `render.to_dict(SPEC)` for the UI / a future viewer. (Declare `/lifecycle`
   before any `/{id}` route so the literal path isn't captured as an id.)

7. **Write the conformance test.** Copy a `test_<entity>_statespec.py`: assert
   `core.validate(SPEC) == []`, then a `RuleBasedStateMachine` whose one
   `@rule` fires a random `(action, roles)` and checks the engine's decision
   against an independently derived expectation, with your invariants as
   `@invariant` methods. Add focused async tests for the persistence + HTTP
   layer, including one that drives the service with a **non-privileged** role
   set to exercise permissions.

8. **Render the docs + wire CI.** `make spec-doc` writes
   `docs/specs/<entity>-lifecycle.md` (commit it). Add `spec-check` and a
   doc-freshness check to CI so the spec stays well-formed and the diagram
   stays in sync.

## Roles, and the SYSTEM actor

Roles are real and per-user: a `User.roles` CSV column (vocabulary in
`app/roles.py`) holds an admin's lifecycle roles; `roles_for(user)` returns
them. `is_admin` gates the admin area; `roles` gate which transitions an admin
may fire. Assign roles via `PUT /api/admin/users/{id}/roles` (guards: unknown
role → 422; removing the last admin holder of a role → 409).

For transitions performed by the system, not a person (a scheduled job
auto-expiring a stale item), gate the edge to a synthetic `SYSTEM` role. It is
in the engine vocabulary but **not** human-grantable, so the assignment
endpoint refuses to give it to a user, and only a job calling `apply` with
`frozenset({SYSTEM})` can fire it. See the submission lifecycle on the
`example/state-machine` branch.

## What this is not

- **Not for plain CRUD.** Reference/directory data (the `Item` slice) has no
  meaningful lifecycle; a spec there is pure ceremony. Opt in only for entities
  with real transition rules. (Unused machinery is worse than none — the same
  razor Baseplate applies to multi-tenancy.)
- **Not a concurrency control.** The Hypothesis model is single-threaded; it
  won't catch two actors firing conflicting transitions at once — the engine
  sits above your persistence layer. When transitions are contended (two admins
  on one queue, an admin racing the expiry job, or any transition that writes
  more than `status`), apply the companion
  [concurrency-safe transitions](concurrency-safe-transitions.md) recipe:
  status compare-and-set (which the reference service already does), a `version`
  optimistic lock, or `SELECT … FOR UPDATE`, with tests that force the race.
- **Not a workflow *engine*.** No timers, no async orchestration, no
  persistence of in-flight processes beyond the entity's own row. It's a small,
  checkable contract — keep it that way.
- **Note on the proof.** Hypothesis proves the code *obeys the spec*; it does
  not prove the spec is the right business rule. The generated doc is how a
  human verifies intent — machine checks conformance, human checks correctness.
- **What the expression layer buys you.** Because conditions are pure data:
  `apply` evaluates the spec's invariants against the proposed post-state and
  refuses the transition if any fails (a backstop — invariants are consequences
  of guards, so a violation is a 500, not a client 4xx); and a change to any
  *declarative* guard/invariant shows up in the rendered doc and in a structural
  diff, so it can't be redefined unseen (an `Opaque` body is the exception —
  see the note in step 2). Design details:
  [`docs/design/statespec-expressions.md`](../design/statespec-expressions.md)
  (on the `example/state-machine` branch alongside the engine).
