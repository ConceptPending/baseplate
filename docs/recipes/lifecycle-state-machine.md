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
  "who-may-do-what" table, and the guarantees that always hold. A domain owner,
  reviewer, or auditor signs off on *that* — without reading Python. It's
  generated and CI-checked, so it can never drift from the behaviour.
- **Machines (correctness).** Every transition goes through one function,
  `statespec.apply`. A Hypothesis `RuleBasedStateMachine` drives it over
  thousands of random action/role sequences and asserts the lifecycle's
  invariants hold after *every* step. The documented workflow and the tested
  workflow are the same object.

That's a concrete, demonstrable control: "the system mechanically enforces the
documented approval workflow and separation of duties, and proves it on every
CI run." It maps cleanly onto the access-control / change-management evidence a
SOC 2 (or similar) reviewer asks for — an executable control, not a screenshot
of a policy doc.

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
| `tests/test_<entity>_statespec.py` | Static checks + the Hypothesis state machine (the proof). |
| `scripts/statespec.py` | `check` (CI gate) and `render` (regenerate docs). Register new specs in `SPECS`. |

## Steps

1. **Copy the engine.** Bring `app/statespec/{core,render,__init__}.py` and
   `scripts/statespec.py` across from the `example/state-machine` branch. They
   are domain-free.

2. **Write the spec.** Create `app/statespec/<entity>_spec.py`. Declare your
   `states`, the `initial` state, the `terminal` (sink) states, and each
   `Transition(name, sources, dest, roles, guard?, label)`. Put guard
   predicates and `Invariant`s next to it — pure functions over an entity
   snapshot the service supplies (so guards never reach for a clock or the DB).

   ```python
   BATCH_SPEC = StateSpec(
       name="batch", title="Batch review lifecycle",
       states={"pending": "...", "approved": "...", "rejected": "..."},
       initial="pending", terminal=frozenset({"approved", "rejected"}),
       guards={"no_unresolved_errors": lambda e: int(e.get("error_count", 0)) == 0},
       transitions=(
           Transition("approve", ("pending",), "approved",
                      roles=frozenset({APPROVER}), guard="no_unresolved_errors"),
           Transition("reject", ("pending",), "rejected",
                      roles=frozenset({REVIEWER, APPROVER})),
       ),
       invariants=(...),
   )
   ```

3. **Register + validate.** Add the spec to `SPECS` in `scripts/statespec.py`
   and run `make spec-check`. It refuses unreachable states, traps (a
   non-terminal state that can't reach a terminal), dead edges (no roles), and
   dangling guard references — so a malformed lifecycle can't reach production.

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

7. **Write the proof.** Copy a `test_<entity>_statespec.py`: assert
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
  won't catch two actors firing conflicting transitions at once. If that
  matters, add an optimistic-lock (`version`) column and a separate test.
- **Not a workflow *engine*.** No timers, no async orchestration, no
  persistence of in-flight processes beyond the entity's own row. It's a small,
  checkable contract — keep it that way.
- **Note on the proof.** Hypothesis proves the code *obeys the spec*; it does
  not prove the spec is the right business rule. The generated doc is how a
  human verifies intent — machine checks conformance, human checks correctness.
