"""The submission-moderation lifecycle — the second spec, chosen to stress the
engine in ways the invoice lifecycle never did.

What's deliberately different here:

- **A system-fired transition.** `expire` is driven by a scheduled job, not a
  person — its only permitted actor is the synthetic `SYSTEM` role. This probes
  the engine's "every edge has a role" assumption (it holds: SYSTEM is just a
  role no human can hold).
- **An age-based guard** rather than an amount-based one. The guard reads
  `age_days` from the entity snapshot, which the service derives from
  `created_at`. Guards stay pure (no clock inside them), exactly as the invoice
  guard reads `amount`.
- **A back-and-forth** (`request_info` ⇄ `provide_info`) and a third terminal
  (`expired`) alongside `approved`/`rejected`.

The engine itself is imported unchanged — this module is pure data.
"""

from __future__ import annotations

from typing import Mapping

from app.roles import REVIEWER, SYSTEM
from app.statespec.core import Invariant, StateSpec, Transition

__all__ = ["SUBMISSION_SPEC", "STALE_AFTER_DAYS"]

# A pending/awaiting-info submission older than this is auto-expired by the
# scheduled job. The threshold is enforced by a guard, not left to convention.
STALE_AFTER_DAYS = 30


def _is_stale(entity: Mapping[str, object]) -> bool:
    age = entity.get("age_days", 0)
    return isinstance(age, (int, float)) and age >= STALE_AFTER_DAYS


def _status_declared(e: Mapping[str, object]) -> bool:
    return e.get("status") in _STATES


_STATES = {
    "pending": "Submitted and awaiting moderation.",
    "needs_info": "Returned to the submitter for more information.",
    "approved": "Accepted and published.",
    "rejected": "Declined by a moderator.",
    "expired": "Auto-closed after going stale with no decision.",
}


SUBMISSION_SPEC = StateSpec(
    name="submission",
    title="Submission moderation lifecycle",
    states=_STATES,
    initial="pending",
    terminal=frozenset({"approved", "rejected", "expired"}),
    guards={"is_stale": _is_stale},
    transitions=(
        Transition(
            name="request_info",
            sources=("pending",),
            dest="needs_info",
            roles=frozenset({REVIEWER}),
            label="Ask the submitter for more information.",
        ),
        Transition(
            name="provide_info",
            sources=("needs_info",),
            dest="pending",
            roles=frozenset({REVIEWER}),
            label="Record that the requested information arrived; back to the queue.",
        ),
        Transition(
            name="approve",
            sources=("pending",),
            dest="approved",
            roles=frozenset({REVIEWER}),
            label="Accept and publish the submission.",
        ),
        Transition(
            name="reject",
            sources=("pending",),
            dest="rejected",
            roles=frozenset({REVIEWER}),
            label="Decline the submission (final).",
        ),
        Transition(
            name="expire",
            sources=("pending", "needs_info"),
            dest="expired",
            # System-only: a scheduled job fires this; no human role can.
            roles=frozenset({SYSTEM}),
            guard="is_stale",
            label="Auto-close a stale submission (scheduled job, not a person).",
        ),
    ),
    invariants=(
        Invariant(
            "status_declared",
            _status_declared,
            "The status is always one of the declared states.",
        ),
    ),
)
