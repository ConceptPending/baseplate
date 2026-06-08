"""Submission service. Mirrors the invoice service's shape — a thin
`transition()` that delegates all decisions to the generic engine — plus one
new thing: `expire_stale`, the entry point a scheduled job calls to fire the
system-only `expire` transition.
"""

import uuid as _uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.submission import Submission
from app.roles import SYSTEM
from app.schemas.submission import SubmissionCreate
from app.statespec import GuardRejected, apply
from app.statespec.submission_spec import SUBMISSION_SPEC

# The synthetic actor a scheduled job presents. Humans can never hold SYSTEM,
# so only this code path can fire system-only transitions.
_SYSTEM_ACTOR = frozenset({SYSTEM})


def _age_days(created_at: datetime) -> float:
    now = datetime.now(timezone.utc)
    ca = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    return (now - ca).total_seconds() / 86_400


class SubmissionService:
    @staticmethod
    async def create(db: AsyncSession, data: SubmissionCreate) -> Submission:
        submission = Submission(name=data.name, email=data.email, message=data.message)
        db.add(submission)
        await db.commit()
        await db.refresh(submission)
        return submission

    @staticmethod
    async def get_by_id(
        db: AsyncSession, submission_id: str | _uuid.UUID
    ) -> Submission | None:
        sid = (
            _uuid.UUID(submission_id)
            if isinstance(submission_id, str)
            else submission_id
        )
        result = await db.execute(select(Submission).where(Submission.id == sid))
        return result.scalar_one_or_none()

    @staticmethod
    def _snapshot(submission: Submission) -> dict:
        # The age the `is_stale` guard reads — derived here so the guard stays
        # pure (no clock inside the spec).
        return {
            "status": submission.status,
            "age_days": _age_days(submission.created_at),
        }

    @staticmethod
    async def transition(
        db: AsyncSession,
        submission: Submission,
        action: str,
        actor_roles: frozenset[str],
    ) -> Submission:
        new_state = apply(
            SUBMISSION_SPEC,
            action,
            submission.status,
            actor_roles,
            SubmissionService._snapshot(submission),
        )
        submission.status = new_state
        await db.commit()
        await db.refresh(submission)
        return submission

    @staticmethod
    async def expire_stale(db: AsyncSession) -> int:
        """Scheduled-job entry point: fire the system-only `expire` on every
        stale open submission. Staleness is decided by the spec's guard, not
        re-implemented here — fresh submissions are refused by the guard and
        skipped. Returns the number expired."""
        result = await db.execute(
            select(Submission).where(Submission.status.in_(("pending", "needs_info")))
        )
        expired = 0
        for submission in result.scalars().all():
            try:
                await SubmissionService.transition(
                    db, submission, "expire", _SYSTEM_ACTOR
                )
                expired += 1
            except GuardRejected:
                # Not stale yet — the guard is the single source of the rule.
                continue
        return expired
