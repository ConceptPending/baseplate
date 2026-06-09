# The policy artifact: a versioned contract

`make spec-doc` writes `docs/specs/<name>.policy.json` for every lifecycle spec.
This file is the **stable, machine-readable contract** an external consumer (a
control plane, a policy-review GitHub App, an auditor tool) reads. This document
defines it so that contract can be relied on across repos and over time.

## Status of the artifact

It is a **committed / declared baseline** — the policy the repository currently
declares. It is **not** an *approved* policy. Approval is an independent record
(who authorised which `semantic_digest`, when) that lives in the control plane,
never in the repository. A repo can change the spec and its `.policy.json` in one commit;
that makes it the *candidate* policy, not the *authorised* one.

## Shape (schema_version 2)

```jsonc
{
  "schema_version": 2,                  // version of THIS envelope format (not the policy)
  "spec_version": 1,                    // the author-asserted policy version
  "semantic_digest": "c90feaf9c431…",   // sha256 over executable behaviour — what approval binds to
  "presentation_digest": "a5765188d595…", // sha256 over wording — tracked, non-invalidating
  "spec": {                             // the canonical, content-only spec
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

- **Two digests, both deterministic and content-only.** Each is `sha256` over a
  canonical serialisation (sorted keys, stable arrays, normalised `Decimal`).
  `semantic_digest` covers **executable behaviour** — states, transitions,
  roles, guard/invariant expressions, and **opaque-body** hashes; it is what
  approval binds to, and bumping `spec_version` is keyed to it. `presentation_digest`
  covers the **human-facing wording** — title, state descriptions, and
  transition/invariant labels. A copy-edit moves `presentation_digest` only, so
  a behavioural approval survives a reword; a behavioural change moves
  `semantic_digest` (and almost always both). Splitting them is what makes
  "wording vs behaviour" a mechanical check (`identity.change_kind`) instead of
  a human judgement on every diff.
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
  **`semantic_digest`** changes. `statespec.py diff <name>` warns if the
  semantic digest changed but the version did not; a wording-only change does
  not require a bump.
- The two are independent: a format migration doesn't touch policy versions, and
  a policy change doesn't touch the format version.

## Note on labels (the semantic/presentation split)

`spec` still includes labels/descriptions in full — a reword is never lost. But
identity is split: a reword moves `presentation_digest` only, leaving
`semantic_digest` (the digest approval binds to) untouched. So an editorial
change is **non-invalidating by default** — `diff` still names it ("transition
X: label changed") and a consumer routes it to the general policy owner for a
lightweight ack, rather than re-triggering control-owner approval. This was a
deliberate pre-v1 split, made while there were zero live approval bindings to
migrate; doing it after the control plane accumulated approvals would have been
a breaking re-binding. Mechanically: compare the two records with
`identity.change_kind` → `semantic` | `presentation` | `none`.
