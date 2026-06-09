# Design: the approval-authority layer (external control plane)

**Status:** design only. **This layer does NOT belong in the application or the
example.** It is a separate product boundary — a control plane that governs
*production elevation* by recording who authorised which policy digest. The
application stays ordinary, standalone software; the control plane never becomes
its runtime.

## Why it's separate

The application knows: *"this is policy `batch-review`, version 3, digest
`abc123`."* The control plane knows: *"digest `abc123` was approved for
production by the authorised Finance Policy Owner, based on commit `def456`,
after these checks passed."* Keeping that split is what preserves the OSS value:
the resulting app is plain FastAPI you own and run anywhere.

Likely repo split:

```
baseplate                        OSS foundation + StateSpec kernel
flatpack-invoice-review-example  end-to-end reference implementation (frozen)
baseplate-control  (name TBD)    GitHub App + approval service + production gate
```

## The protocol (what crosses the boundary)

The control plane consumes **standard policy artifacts** (see
`policy-artifact-contract.md`) + GitHub events. It must NOT need to understand
the customer's models or run their code.

**Repository → control plane** (per change / per deploy):
repository identity · `spec_id` · `spec_version` · `semantic_digest` ·
`presentation_digest` · `control_id`s · the **semantic diff from the
currently-approved digest** · commit SHA · test/check results · optional preview
URL · (eventually) build/container digest.

**Control plane → repository / GitHub:**
control→owner mapping · required approvers · approval status · approval evidence ·
revocation/supersession · the production-elevation decision (a status check).

## Minimal data model (five concepts)

```text
Policy                # the continuing governed policy (not one version)
  organisation, repository, spec_id, display_name

PolicyRevision        # immutable once created
  policy_id, spec_version, semantic_digest, presentation_digest, canonical_spec,
  commit_sha, created_at, proposed_by   # approval binds to semantic_digest

ControlOwner          # control-specific ownership is the differentiator
  policy_id, control_id, owner_user_or_group, required_approvals,
  effective_from, effective_until        # a policy-wide fallback owner is useful

Approval              # append-only; a rejection is a decision record, not a mutation
  policy_revision_id, approver, approved_controls, decision, timestamp,
  comment, preview_reviewed

DeploymentAuthorization   # what the production gate evaluates
  policy_revision_id, commit_sha, artifact_digest, environment,
  required_approvals_satisfied, authorized_at, consumed_at, deployment_result
```

## Approval is *calculated from the semantic diff*

A change touching `INV-CLEAN-BATCH` + `INV-MAKER-CHECKER` resolves the owners of
*those* controls and computes the requirement. A pure wording change
(`presentation_digest` moves, `semantic_digest` stable) needs only the general
policy owner — and that's now a mechanical test (`identity.change_kind` returns
`presentation`), not a read of the diff. A change to finance authority / data
retention / sanctions handling can require separate Finance, Privacy, and
Financial-Crime approvals. That control-scoped routing —
driven by the `control_id`s in the diff — is what makes this more than a generic
"someone must approve production" button.

## Exact approval semantics

An approval applies to `semantic_digest + commit_sha + target_environment`
(eventually `+ built_artifact_digest`). Binding to the *semantic* digest is what
lets a later copy-edit ship without re-approval; a `presentation_digest`-only
move is recorded and acked, not re-approved. Two viable models:

- **Strict artifact approval** — any commit change invalidates approvals.
  Simplest/strongest; forces reapproval of harmless implementation fixes.
- **Split policy/implementation approval** — the policy owner approves the
  *digest*; engineering approves the *commit/artifact*; elevation requires the
  approved digest + a commit proven to implement it + green checks. Better
  long-term (separates "I approve this rule" from "I approve this code").

For v1, strict is easier — but **shape the records so the split is possible
later** (that's why `PolicyRevision` carries both digest and commit, and
`DeploymentAuthorization` carries digest, commit, and artifact separately).

## Rules v1 must enforce

- A proposer cannot approve their own change where separation is required.
- An approval applies to exactly one immutable `PolicyRevision`.
- A new policy change supersedes/invalidates prior pending approvals.
- Production cannot elevate an unapproved digest.
- Approval requirements are computed from the affected `control_id`s.
- Prior approvals stay historically visible; revocation never rewrites history.
- GitHub status checks clearly separate *technical success* from *policy
  approval*.
- **The authorised baseline is derived from approval history, not from whichever
  `.policy.json` is committed.** Once the control plane exists, the repo's
  artifact is a *candidate*; the control plane is the source of truth for what
  was authorised.

## First vertical slice (enough to test the premise)

1. Install the GitHub App. 2. Detect a StateSpec change (compare committed
`.policy.json` `semantic_digest` to the approved one). 3. Render the semantic diff. 4.
Determine the required owner(s) from the affected controls. 5. Collect an
approval in a thin web page. 6. Publish a GitHub check. 7. Permit/refuse
production elevation. 8. Retain the evidence record.

## Explicitly NOT in the first version

Visual workflow editor · natural-language authoring · cross-provider deploy ·
complex delegation trees · auditor portals · cryptographic ledgering ·
multi-stage enterprise approval orchestration · an internal application catalogue.

## The OSS / hosted boundary

| Open source (kernel + example) | Hosted product (control plane) |
| --- | --- |
| Define policy as a spec | Map controls → owners |
| Enforce it at runtime | Require + collect approvals |
| Test it (Hypothesis) | Compute requirements from the diff |
| Emit version + semantic/presentation digests | Record approval tied to the semantic digest |
| Append-only event evidence | Authorise production elevation |
| Render it for a domain owner | GitHub check + elevation gate |

The kernel proves the policy *works and is enforced*. The control plane answers
the commercial question: *will an organisation treat the approval record as
authoritative enough to gate production — and pay for that assurance?*
