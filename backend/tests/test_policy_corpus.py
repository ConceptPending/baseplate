"""Semantic-diff corpus: a pinned set of policy-change scenarios and the exact
diff each produces. This is the contract an external control plane integrates
against — it consumes `policy-artifact-contract.md` artifacts and renders these
diffs for approval. If the diff output changes, this test (and the committed
fixtures under docs/policy-fixtures/) must be updated deliberately.
"""

import json
from dataclasses import replace
from pathlib import Path

from app.statespec import core, identity
from app.statespec.expr import any_, field
from app.statespec.submission_spec import SUBMISSION_SPEC

FIXTURES = Path(__file__).resolve().parents[2] / "docs" / "policy-fixtures"


def _with(spec, **changes):
    return replace(spec, **changes)


def _transition_replaced(spec, name, **changes):
    ts = tuple(replace(t, **changes) if t.name == name else t for t in spec.transitions)
    return replace(spec, transitions=ts, version=spec.version + 1)


# The scenarios: (label, mutated spec, expected diff lines).
def _scenarios():
    base = SUBMISSION_SPEC
    return {
        "widen-expire-guard": (
            _transition_replaced(base, "expire", guard=field("age_days").ge(60)),
            ["version: 1 → 2",
             "transition expire: guard age_days ≥ 30 → age_days ≥ 60"],
        ),
        "add-role-to-approve": (
            _transition_replaced(base, "approve", roles=frozenset({"reviewer", "approver"})),
            ["version: 1 → 2",
             "transition approve: roles ['reviewer'] → ['approver', 'reviewer']"],
        ),
        "add-invariant": (
            _with(
                base,
                version=2,
                invariants=base.invariants + (
                    core.Invariant(
                        "needs_info_implies_open",
                        any_(field("status").ne("needs_info"),
                             field("age_days").ge(0)),
                        "needs_info items are still open",
                        control_id="SUB-INV-OPEN",
                    ),
                ),
            ),
            ["version: 1 → 2", "+ invariant SUB-INV-OPEN"],
        ),
    }


def test_semantic_diff_corpus_is_stable():
    base = identity.canonical(SUBMISSION_SPEC)
    for name, (mutated, expected) in _scenarios().items():
        got = identity.diff(base, identity.canonical(mutated))
        assert got == expected, f"{name}: {got}"
        # the semantic digest must move for every behavioural change
        assert identity.semantic_digest(SUBMISSION_SPEC) != identity.semantic_digest(mutated), name


def test_committed_fixtures_match():
    """The committed corpus under docs/policy-fixtures/ matches what the engine
    produces — so an external consumer integrating against the files sees the
    same artifacts the kernel emits."""
    baseline = json.loads((FIXTURES / "submission.baseline.policy.json").read_text())
    assert baseline == identity.policy_record(SUBMISSION_SPEC)
    expected = json.loads((FIXTURES / "expected-diffs.json").read_text())
    base_canon = identity.canonical(SUBMISSION_SPEC)
    for name, (mutated, _exp) in _scenarios().items():
        assert identity.diff(base_canon, identity.canonical(mutated)) == expected[name]
