# Policy fixtures + semantic-diff corpus

Concrete artifacts for integrating an external consumer (a control plane /
policy-review GitHub App) against the kernel's output — without running the
application. See [`../design/policy-artifact-contract.md`](../design/policy-artifact-contract.md).

- **`submission.baseline.policy.json`** — a real policy artifact (the
  `submission` lifecycle): the versioned envelope (`schema_version`,
  `spec_version`, `semantic_digest`, `presentation_digest`) around the canonical
  spec.
- **`expected-diffs.json`** — a corpus of `scenario → semantic-diff lines`: what
  `identity.diff(baseline, mutated)` produces for representative changes (widen a
  guard threshold, add a role, add an invariant). This is the human-renderable
  output a control plane shows an approver.

Both are generated from the engine and pinned by
`backend/tests/test_policy_corpus.py`, so they can't drift from what the kernel
emits. A consumer can treat these as the fixture contract for its diff-rendering
and approval-routing logic.
