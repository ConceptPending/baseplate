"""Property-based proof for the second lifecycle, reusing the same engine.

The point of this file (beyond covering submissions) is the *generality test*:
the exact same `RuleBasedStateMachine` pattern as the invoice suite drives a
differently-shaped spec — a system-fired transition and an age guard — through
the unchanged engine. If the abstraction were invoice-shaped, this is where it
would break.
"""

import pytest
from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

from app.statespec import core, render
from app.statespec.submission_spec import STALE_AFTER_DAYS, SUBMISSION_SPEC

ROLES = sorted({r for t in SUBMISSION_SPEC.transitions for r in t.roles})
ACTIONS = [t.name for t in SUBMISSION_SPEC.transitions]
ALL_ROLES = frozenset(ROLES)


def test_spec_is_well_formed():
    assert core.validate(SUBMISSION_SPEC) == []


def test_system_edge_is_system_only():
    """`expire` is gated to SYSTEM — no human role can fire it."""
    expire = SUBMISSION_SPEC.transition("expire")
    assert expire.roles == frozenset({"system"})
    # A reviewer in the right state with a stale entity is still refused.
    with pytest.raises(core.PermissionDenied):
        core.apply(
            SUBMISSION_SPEC, "expire", "pending", frozenset({"reviewer"}),
            {"age_days": 999},
        )


def test_renders_show_system_actor():
    mermaid = render.to_mermaid(SUBMISSION_SPEC)
    assert "expire (system)" in mermaid


class SubmissionLifecycleMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.state = SUBMISSION_SPEC.initial
        self.age_days = 0

    @initialize(age=st.integers(min_value=0, max_value=2 * STALE_AFTER_DAYS))
    def set_age(self, age):
        self.age_days = age

    def _entity(self):
        return {"status": self.state, "age_days": self.age_days}

    @rule(action=st.sampled_from(ACTIONS), roles=st.sets(st.sampled_from(ROLES)))
    def fire(self, action, roles):
        roles = frozenset(roles)
        t = SUBMISSION_SPEC.transition(action)
        expected_ok = (
            self.state in t.sources
            and bool(roles & t.roles)
            and (t.guard is None or self.age_days >= STALE_AFTER_DAYS)
        )
        decision = core.can_fire(
            SUBMISSION_SPEC, action, self.state, roles, self._entity()
        )
        assert decision.allowed == expected_ok, (
            action, sorted(roles), self.state, decision.reason,
        )
        if expected_ok:
            self.state = core.apply(
                SUBMISSION_SPEC, action, self.state, roles, self._entity()
            )
            assert self.state == t.dest
        else:
            with pytest.raises(core.TransitionError):
                core.apply(SUBMISSION_SPEC, action, self.state, roles, self._entity())

    @invariant()
    def status_is_declared(self):
        assert self.state in SUBMISSION_SPEC.states

    @invariant()
    def terminals_are_sinks(self):
        if self.state in SUBMISSION_SPEC.terminal:
            assert (
                core.enabled_transitions(
                    SUBMISSION_SPEC, self.state, ALL_ROLES, self._entity()
                )
                == []
            )


TestSubmissionLifecycle = SubmissionLifecycleMachine.TestCase
TestSubmissionLifecycle.settings = settings(
    max_examples=200,
    stateful_step_count=12,
    deadline=None,
    suppress_health_check=[HealthCheck.filter_too_much],
)
