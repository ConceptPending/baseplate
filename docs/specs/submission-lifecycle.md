# Submission moderation lifecycle

> **Generated file — do not edit by hand.** Regenerate with `make spec-doc`. The source of truth is the spec in `app/statespec/submission_spec.py`; this document is rendered from it so the picture can never drift from the enforced behaviour.

## Lifecycle

```mermaid
stateDiagram-v2
    %% Submission moderation lifecycle
    [*] --> pending
    pending --> needs_info: request_info (reviewer)
    needs_info --> pending: provide_info (reviewer)
    pending --> approved: approve (reviewer)
    pending --> rejected: reject (reviewer)
    pending --> expired: expire (system) [is_stale]
    needs_info --> expired: expire (system) [is_stale]
    approved --> [*]
    expired --> [*]
    rejected --> [*]
```

## States

| State | Meaning |
| --- | --- |
| `pending` _(start)_ | Submitted and awaiting moderation. |
| `needs_info` | Returned to the submitter for more information. |
| `approved` _(final)_ | Accepted and published. |
| `rejected` _(final)_ | Declined by a moderator. |
| `expired` _(final)_ | Auto-closed after going stale with no decision. |

## Transitions

| Action | From | To | Who may do it | Condition |
| --- | --- | --- | --- | --- |
| **request_info** — Ask the submitter for more information. | pending | needs_info | reviewer | — |
| **provide_info** — Record that the requested information arrived; back to the queue. | needs_info | pending | reviewer | — |
| **approve** — Accept and publish the submission. | pending | approved | reviewer | — |
| **reject** — Decline the submission (final). | pending | rejected | reviewer | — |
| **expire** — Auto-close a stale submission (scheduled job, not a person). | pending, needs_info | expired | system | is_stale |

## Guarantees that always hold

These invariants are checked after *every* transition by the property-based test suite (Hypothesis), across randomly generated sequences of actions:

- **status_declared** — The status is always one of the declared states.
