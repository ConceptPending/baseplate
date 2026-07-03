# Design: declarative guard/invariant expressions for StateSpec

> **Authoritative home moved (2026-07-03):** the kernel (and this doc's
> authoritative copy) now live in
> [`ConceptPending/statespec`](https://github.com/ConceptPending/statespec)
> as of `statespec-v0.4.0`. This in-tree copy is frozen at `statespec-v0.3.0`
> alongside the reference example.

**Status:** implemented — `backend/app/statespec/expr.py`, used by the
submission spec. **Scope decision:** minimal comparators
(field/literal comparisons + boolean combinators); anything richer is an opaque,
flagged escape hatch. **Decisions locked:** typed field schema = yes; runtime
invariant enforcement = yes; per-spec content hash = deferred to the identity
layer.

## 1. Why

Guards and invariants are currently arbitrary Python functions referenced by
name. The complete `StateSpec` is therefore not serialisable: `to_dict()` can
expose a guard's *name* but not the condition it evaluates. A developer (or an
agent) could change `error_count == 0` to `error_count <= 5` with the guard name
and rendered doc byte-for-byte unchanged — the policy changes silently.

Making conditions **pure data** (a small expression tree) fixes this at the
root: the same object evaluates at runtime, renders into the generated doc,
serialises to JSON, and diffs structurally. The rendered policy then *is* the
enforced policy, and a change to it shows up in the doc and in a semantic diff.

## 2. The expression model (`app/statespec/expr.py`)

Two kinds of node:

- **Operands** resolve to a value: `Field`, `Literal`.
- **Conditions** resolve to `bool`: `Compare`, `All`, `Any`, `Not`, `Opaque`.

```python
# Operands ------------------------------------------------------------------
@dataclass(frozen=True)
class Field:
    name: str
    def resolve(self, ctx: Mapping[str, object]) -> object: ...   # ctx[name]

@dataclass(frozen=True)
class Literal:
    value: int | Decimal | str | bool | None | tuple
    def resolve(self, ctx) -> object: return self.value

Operand = Field | Literal

# Conditions ----------------------------------------------------------------
CompareOp = Literal["eq", "ne", "lt", "le", "gt", "ge", "in", "not_in"]

@dataclass(frozen=True)
class Compare:
    op: CompareOp
    left: Operand
    right: Operand

@dataclass(frozen=True)
class All:                      # conjunction (empty = True)
    terms: tuple["Expr", ...]

@dataclass(frozen=True)
class Any:                      # disjunction (empty = False)
    terms: tuple["Expr", ...]

@dataclass(frozen=True)
class Not:
    term: "Expr"

@dataclass(frozen=True)
class Opaque:                   # escape hatch — see §11
    name: str                   # stable id, e.g. "within_supplier_credit"
    version: int                # bump to change behaviour (diff-visible); see §11
    label: str                  # human description

Expr = Compare | All | Any | Not | Opaque
```

Every condition implements:

- `evaluate(ctx: Mapping[str, object]) -> bool`
- `to_dict() -> dict` / `from_dict(d) -> Expr` (round-trippable)
- `render() -> str` (human-readable)
- `fields() -> frozenset[str]` (field names referenced; for `validate` + viewer)

The grammar is deliberately closed at compare + boolean. **No arithmetic, no
aggregates, no path traversal, no function calls.** Anything that needs them is
either pre-materialised into a context field by the service, or `Opaque`.

## 3. Evaluation semantics

- **Field resolution:** `ctx[name]`. A missing field **raises `ExpressionError`**
  (not silently False). The typed field schema (§6) plus `validate` guarantee
  presence, so a miss is a service/spec contract bug and should fail loud, not
  masquerade as a policy decision.
- **`eq` / `ne`:** Python `==` / `!=` (handles `Decimal`/`int`/`str`).
- **`lt` / `le` / `gt` / `ge`:** Python ordering; both operands must be
  order-comparable (numeric or date). Incomparable types raise `ExpressionError`
  (caught earlier by `validate`'s type check).
- **`in` / `not_in`:** right operand is a `Literal` collection; `left in right`.
- **Money** is `Decimal`; numeric literals for money fields are `Decimal`, never
  `float`.
- **Short-circuit:** `All`/`Any` short-circuit; an empty `All` is `True`, empty
  `Any` is `False`.
- `Opaque.evaluate` looks its callable up in the opaque registry (§11).

## 4. Serialisation (JSON)

`to_dict()` emits a tagged tree; `from_dict()` reverses it. `Literal` carries a
type tag so `Decimal` survives a round-trip.

```jsonc
// field("amount").le(Decimal("10000"))
{"kind": "compare", "op": "le",
 "left":  {"kind": "field", "name": "amount"},
 "right": {"kind": "literal", "type": "decimal", "value": "10000"}}

// any_(field("status").ne("approved"), field("error_count").eq(0))
{"kind": "any", "terms": [
  {"kind":"compare","op":"ne","left":{"kind":"field","name":"status"},
   "right":{"kind":"literal","type":"str","value":"approved"}},
  {"kind":"compare","op":"eq","left":{"kind":"field","name":"error_count"},
   "right":{"kind":"literal","type":"int","value":0}}]}

// opaque("within_supplier_credit", "Within the supplier's live credit limit")
{"kind": "opaque", "name": "within_supplier_credit",
 "label": "Within the supplier's live credit limit", "review_required": true}
```

This is the diffable form. (A canonical digest over it is the seam for the
identity layer — **deferred**, but the serialisation is designed so a hash drops
in later without changing the tree shape.)

## 5. Rendering (human strings)

`render()` produces what shows in the generated doc's **Condition** column —
the actual policy, not a name:

| Node | Renders as |
| --- | --- |
| `Compare(le, amount, 10000)` | `amount ≤ 10000` |
| `Compare(eq, error_count, 0)` | `error_count = 0` |
| `Any([...])` | `(status ≠ "approved" or error_count = 0)` |
| `Opaque(...)` | `«within_supplier_credit» — custom code (requires technical review)` |

Op symbols: `= ≠ < ≤ > ≥ ∈ ∉`.

## 6. Typed field schema (the context contract)

`StateSpec` gains `fields: Mapping[str, str]` — every name the conditions may
reference, mapped to a type tag. This is the contract the service's snapshot
must satisfy, the basis for `validate`'s field/type checks, and the schema a
future viewer reads.

Type tags (v1): `"int"`, `"decimal"`, `"str"`, `"bool"`, `"uuid"`, `"date"`.

Order comparators (`lt/le/gt/ge`) are legal only on `int | decimal | date`.

## 7. Revised `StateSpec` / `Transition` / `Invariant`

```python
@dataclass(frozen=True)
class Transition:
    name: str
    sources: tuple[str, ...]
    dest: str
    roles: frozenset[str]
    guard: Expr | None = None        # was: str (name into spec.guards)
    label: str = ""

@dataclass(frozen=True)
class Invariant:
    name: str
    condition: Expr                  # was: predicate: Callable
    label: str = ""

@dataclass(frozen=True)
class StateSpec:
    name: str
    title: str
    states: Mapping[str, str]
    fields: Mapping[str, str]        # NEW — context contract (name -> type tag)
    initial: str
    terminal: frozenset[str]
    transitions: tuple[Transition, ...]
    invariants: tuple[Invariant, ...] = ()
    # `guards` registry REMOVED — guards are inline Expr; Opaque has its own
    # registry for the escape hatch.
```

Breaking change to the authoring API (guards/invariants go from callables to
`Expr`). Touches the three spec files + the engine in both repos + the recipe —
that's rollout, out of scope for this doc.

## 8. Runtime invariant enforcement

`apply` evaluates the spec's invariants against the **proposed post-state** and
refuses the transition if any fails.

```python
def apply(spec, action, current_state, actor_roles, context,
          *, post_overrides=None) -> str:
    decision = can_fire(spec, action, current_state, actor_roles, context)
    if not decision.allowed:
        raise decision.error(decision.reason)
    dest = decision.dest
    # Always merge onto the default — a partial override can't silently drop or
    # stale a field (the post_context foot-gun, per the review).
    post = {**context, "status": dest, **(post_overrides or {})}
    _require_fields(spec, post)                  # post.keys() ⊇ spec.fields
    violated = [inv for inv in spec.invariants if not inv.condition.evaluate(post)]
    if violated:
        raise InvariantViolation(dest, [i.name for i in violated])
    return dest
```

`post_overrides` (merge-only) replaces the original `post_context` (full
snapshot): a transition that sets a derived field passes just that field, and
the default keys can never be dropped. `_require_fields` asserts the post-state
satisfies the field contract.

- **Default post-state** is `{**context, "status": dest}`. For the current specs
  every invariant reads only `status` + a field unchanged by the transition
  (`error_count`, `age_days`), so the default suffices with **no service change**.
- **Derived-field case:** if a transition *sets* a field an invariant reads
  (e.g. an `approved_at` that an `paid ⇒ approved` invariant checks), the service
  passes `post_context=` with that field set to its post-transition value. The
  service already builds this snapshot.
- **`InvariantViolation`** is a *backstop*, not a user error. If guards are
  correct it can only fire from a guard/spec bug or out-of-band mutation. It is
  raised **before commit** (transaction rolls back), logged at error level via
  the observability seam, and mapped to **HTTP 500** (it is an internal breach of
  a stated guarantee, not a client mistake). Contrast with a guard refusal, which
  is the user-facing 409/403.
- **Residual gap (unchanged, documented):** a mutation made entirely outside the
  transition path (`batch.error_count = 0` in a script) is not caught by any
  engine check. That is the database-constraint domain — out of v1.

## 9. `validate()` additions

On top of the current checks (and the recently added duplicate-name +
role-catalogue checks):

- Every `Field` referenced by any guard/invariant is in `spec.fields`.
- Order comparators (`lt/le/gt/ge`) only on `int|decimal|date` operands;
  `Literal` type must be compatible with the compared `Field`'s declared type.
- Every `Opaque.name` is present in the opaque registry.
- (Optional, debug-time) `apply` asserts the passed `context` provides every key
  in `spec.fields` — catches service/spec drift at the source.

## 10. Migration of the live guards (concrete)

All current guards and invariants become declarative — **no `Opaque` needed.**

**Batch** (`batch_spec.py`):

```python
fields = {"status": "str", "error_count": "int"}

# approve guard:
guard = field("error_count").eq(0)

# invariants:
Invariant("status_declared",
          field("status").is_in(tuple(STATES)),
          "Status is always a declared state.")
Invariant("approved_implies_clean",
          any_(field("status").ne("approved"), field("error_count").eq(0)),
          "An approved batch has no unresolved validation errors.")
```

**Submission** (`submission_spec.py`):

```python
fields = {"status": "str", "age_days": "decimal"}

# expire guard (was the opaque is_stale — now declarative, because age_days is
# a service-supplied snapshot field, not now() inside the guard):
guard = field("age_days").ge(30)

Invariant("status_declared", field("status").is_in(tuple(STATES)), "...")
```

**Invoice** (illustrative; the slice is retired):
`within_approval_limit` → `field("amount").le(Decimal("10000"))`.

## 11. The opaque escape hatch

For a condition that genuinely cannot be a pure snapshot field — a *live*
cross-entity aggregate or external call evaluated at decision time:

```python
guard = opaque(
    "within_supplier_credit",
    "Within the supplier's live credit limit",
    lambda ctx: _check_credit(ctx["supplier_id"]),   # body lives in code
)
```

The tree stores only `name` + `label` + `review_required: true`; the callable is
held in a registry keyed by name. It renders as *"custom code (requires technical
review)"*, and a diff can see that an opaque's name/label changed but flags that
its **body** is code requiring review — i.e. opaque conditions are explicitly
*not* governed by the declarative diff, and are surfaced as such rather than
hidden. Prefer materialising a fact into a context field over reaching for this.

## 12. Authoring DSL

Readable constructors that compile to the tree:

```python
field("amount").le(10000)            # Compare(le, Field, Literal)
field("actor_id").ne(field("uploaded_by_id"))   # Field-vs-Field (see §13)
field("status").is_in(("approved", "paid"))
all_(a, b)   any_(a, b)   not_(a)
opaque(name, label, fn)
```

`field(x).<op>(y)` wraps a non-`Operand` `y` in `Literal`; pass `field(...)` to
compare two fields.

## 13. Bonus the grammar already reaches: actor-relative SoD

Because comparators allow **Field-vs-Field**, maker-checker separation of duties
is expressible *within minimal comparators* — provided the service puts actor
facts in the context:

```python
fields = {"status": "str", "error_count": "int",
          "actor_id": "uuid", "uploaded_by_id": "uuid"}

guard = all_(
    field("error_count").eq(0),
    field("actor_id").ne(field("uploaded_by_id")),   # uploader can't approve
)
```

This turns the review's "true separation of duties" gap from a new-language
problem into a *context-population* problem — the service already builds the
snapshot; it just adds `actor_id`/`uploaded_by_id`. (Not required for the
expression rollout; noted because it's the natural follow-on and validates the
"minimal" choice.)

## 14. What this unblocks / what's still deferred

Unblocks: the doc shows the real policy (silent-change hole closed); structural
**semantic diff** of two specs' conditions (the "an agent can't redefine the rule
unseen" control); **runtime invariant enforcement** (§8); the viewer's
"why denied" (read the failing clause).

Still deferred (later layers): per-spec content hash + version + stable control
IDs (identity layer); immutable transition/audit events; authoritative
cross-entity guards via materialised context fields; optimistic concurrency; the
viewer/simulator UI; arithmetic/aggregate expressions.

## 15. Rollout (not part of this design)

When approved: implement `expr.py` + the `StateSpec` changes + `apply`
invariant enforcement + `validate` additions in **both** the engine copies
(baseplate `example/state-machine`, `flatpack-invoice-review-example`), migrate
the three specs, update the recipe doc, regenerate `docs/specs/*`. One PR per
repo; the recipe's "guards are arbitrary Python" guidance is replaced with the
expression grammar + the opaque escape-hatch rule.

## 16. Incorporated review findings (gpt-5.1)

Deltas applied to the design above after an external review. Each is part of
the spec now; listed together so the rationale is traceable.

1. **Opaque versioning + locked registry (§2, §11).** `Opaque` carries a
   `version`; its identity is `name:version`. Changing an opaque body requires a
   version bump, which is diff-visible — otherwise the escape hatch would be a
   silent-change bypass (a body swap with no spec diff). The opaque registry is
   bound at engine init and immutable at runtime; a missing or duplicate
   `name:version` **fails startup**, not first-eval. `validate` and
   `Opaque.evaluate` resolve against the same registry instance.

2. **Type-compatibility matrix in `validate` (§9).** A defined matrix, not
   Python's defaults: `eq`/`ne` require the operand types to match (the only
   allowed coercion is `int`→`decimal`); `lt/le/gt/ge` require `int|decimal|date`
   on both sides; `in`/`not_in` require a homogeneous `Literal` collection whose
   element type matches the left field. This closes the silent vectors
   (`uuid == str` → `False`, `1 == True` → `True`). Field-vs-Field comparisons
   are type-checked on both sides. `uuid`/`date` literals have defined JSON
   string forms and are validated on construction.

3. **`post_overrides` replaces `post_context` (§8).** Merge-only, with a
   field-contract assertion. Resolves the foot-gun where a partial full-snapshot
   could drop required fields.

4. **Canonical serialization defined now (§4), hash still deferred.** Fixed key
   order per node; `terms` and `Literal` collections are ordered arrays and
   collection order **is** semantically significant; `Decimal` has a canonical
   string form (normalized, fixed handling of trailing zeros) validated on
   construction. A `to_canonical_bytes()` exists so the identity layer can hash
   without reshaping the tree.

5. **Evaluation + authoring safety (§3, §6, §12).** Every evaluation failure
   (incl. `in`/`not_in` on a non-collection, or an order op on incomparable
   types that slipped past `validate`) is wrapped in `ExpressionError` → HTTP
   500. `Literal` construction rejects non-primitive types (e.g. `datetime`);
   `date`/`uuid` must be built via explicit `literal(...)`. Empty `All`/`Any`
   are rejected by `validate` in authored specs. `context` must contain at least
   `spec.fields`; extra keys are ignored. `Opaque.label` changes are
   diff-visible governance events.

**Deliberately declined: the 409-vs-500 split for invariants.** The reviewer
proposed splitting invariants into client-facing (409) and internal (500). We
keep a single category mapped to **500**, because the design's load-bearing
distinction is *user-facing rules are guards; invariants are consequences of
guards (backstops)*. An invariant can only fire from a guard/spec bug or an
out-of-band mutation — a 500 that alarms is correct. `validate` cannot prove an
invariant is a true consequence, so this is enforced by convention and
documented: **any client-visible rule must be a guard, never a standalone
invariant.**

## 17. Identity & audit layers — notes from the second review

These landed after §16 (the identity layer, then audit), with two clarifications
worth recording:

- **`docs/specs/<name>.policy.json` is a *committed* baseline, not an *approved*
  one.** It is a declared, repository-level baseline (version + digest +
  canonical spec). An agent can still change the spec and the baseline in the
  same PR, so the digest alone does not mean "approved." It only becomes an
  approved policy once an **independent approval record** is tied to the exact
  digest — that belongs to the future approval-authority / GitHub-gate layer,
  not here.
- **Label changes are tracked, not policy-invalidating (split landed).**
  `canonical()` still carries labels/descriptions in full, but identity is now
  two digests: `semantic_digest` (states, transitions, roles, expressions,
  opaque-body hashes) and `presentation_digest` (title, descriptions, labels).
  Rewording "Batch must contain no unresolved errors" to "All validation errors
  must be resolved" moves `presentation_digest` only — `diff` names it, but the
  behavioural approval that binds to `semantic_digest` survives. The split was
  made pre-v1 (zero live approval bindings to migrate); deferring it past the
  control plane's first approvals would have made it a breaking re-binding. The
  routing test is `identity.change_kind` → `semantic | presentation | none`. See
  `policy-artifact-contract.md`.

**Audit layer (built):** every transition records an append-only
`LifecycleEvent` in the same transaction as the state change (atomic) —
who/what/prev-new-state, roles snapshotted as historical facts, the spec
version+digest, entity version before/after, and structured guard/invariant
evidence (control id, expression, result, and the *fields the expression read*,
not the whole entity). The engine primitive is `core.fire()`, which returns
`(dest, [Evaluation, ...])`; `apply()` is the dest-only wrapper. Denied attempts
are out of this pass (different transaction semantics — the main txn rolls back
while a denial record must still commit); the `outcome` field is in the schema
for when they're added. Worked example: the `flatpack-invoice-review-example`
repo's `ReviewBatch` (`GET /api/admin/batches/{id}/lifecycle-events`).
