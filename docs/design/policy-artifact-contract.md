# The policy artifact: a versioned contract

`make spec-doc` writes `docs/specs/<name>.policy.json` for every lifecycle spec.
This file is the **stable, machine-readable contract** an external consumer (a
control plane, a policy-review GitHub App, an auditor tool) reads. This document
defines it so that contract can be relied on across repos and over time.

## Status of the artifact

It is a **committed / declared baseline** — the policy the repository currently
declares. It is **not** an *approved* policy. Approval is an independent record
(who authorised which digest, when) that lives in the control plane, never in
the repository. A repo can change the spec and its `.policy.json` in one commit;
that makes it the *candidate* policy, not the *authorised* one.

## Shape (schema_version 1)

```jsonc
{
  "schema_version": 1,          // version of THIS envelope format (not the policy)
  "spec_version": 1,            // the author-asserted policy version
  "digest": "006c626f9058…",    // sha256 over `spec` (the content identity)
  "spec": {                     // the canonical, content-only spec
    "name": "submission",
    "version": 1,
    "states": { "pending": "…", "approved": "…", … },
    "initial": "pending",
    "terminal": ["approved", "rejected", "expired"],
    "fields": { "status": "str", "age_days": "decimal" },
    "transitions": [
      {
        "id": "approve",                 // control_id, else the action name
        "name": "approve",
        "from": ["pending"], "to": "approved",
        "roles": ["reviewer"],
        "label": "…",
        "guard": { "kind": "compare", "op": "eq",
                   "left": {"kind":"field","name":"error_count"},
                   "right": {"kind":"literal","type":"int","value":0} },
        "opaque": {}                     // {name:version -> source-hash} for opaque guards
      }
    ],
    "invariants": [
      { "id": "status_declared", "name": "status_declared", "label": "…",
        "condition": { … expr tree … }, "opaque": {} }
    ]
  }
}
```

## Guarantees the contract makes

- **`digest` is deterministic and content-only.** It is `sha256` over a
  canonical serialisation of `spec` (sorted keys, stable arrays, normalised
  `Decimal`). The same policy always produces the same digest; any change to
  states, transitions, roles, guard/invariant expressions, **labels**, or an
  **opaque body** changes it.
- **Conditions are data, not code.** `guard`/`condition` are expression trees
  (compare + boolean), so a consumer can render, diff, and reason about them
  without executing the application. The grammar is closed (see
  `statespec-expressions.md`).
- **Opaque code is identified, not hidden.** A guard that escapes to Python
  appears as `{"kind":"opaque","name":…,"version":…}` and its source hash is in
  the transition/invariant's `opaque` map, so an opaque body change is visible
  in the digest.
- **Control IDs are stable.** Each transition/invariant carries an `id`
  (`control_id`, defaulting to the name) — the handle a control plane maps to an
  owner and an approval requirement. It survives a label reword.

## What a consumer should do, not do

- **Do**: read the artifact, compute/compare digests, diff two artifacts
  semantically (see `identity.diff`), map `control_id`s to owners, and gate on
  GitHub events.
- **Don't**: parse the application's models, import its code, or re-run the
  guard functions. The artifact + GitHub events are sufficient.

## Versioning

- `schema_version` versions the **envelope/format**. Bump it only when this
  shape changes; a consumer keys its parser off it.
- `spec_version` is the **policy's** author-asserted version. Bump it when the
  digest changes. `statespec.py diff <name>` warns if the digest changed but the
  version did not.
- The two are independent: a format migration doesn't touch policy versions, and
  a policy change doesn't touch the format version.

## Note on labels

`spec` includes labels/descriptions, so an editorial reword changes the digest.
That is deliberate (the approved human-facing wording changed). If that becomes
painful, the design allows a future split into a **semantic/execution digest**
(states, transitions, roles, expressions) and a **document digest** (adds
prose). Not split yet — documented in `statespec-expressions.md` §17.
