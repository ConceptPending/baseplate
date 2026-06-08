"""Submission moderation routes (admin-side).

Scoped to the lifecycle: create, fire a transition, read the spec. Kept
admin-gated to keep this slice focused on the state-machine generality test;
making `create` a public unauthenticated endpoint (with CSRF exemption + a
tight rate limit) is the public-submission recipe's job and composes cleanly.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_admin, roles_for
from app.models.user import User
from app.schemas.submission import (
    LifecycleSpecResponse,
    SubmissionCreate,
    SubmissionResponse,
    SubmissionTransition,
)
from app.services.submissions import SubmissionService
from app.statespec import (
    IllegalTransition,
    PermissionDenied,
    TransitionError,
    UnknownAction,
)
from app.statespec.render import to_dict
from app.statespec.submission_spec import SUBMISSION_SPEC

router = APIRouter(
    prefix="/api/admin/submissions",
    tags=["submissions"],
    dependencies=[Depends(get_current_admin)],
)

_ERROR_STATUS: dict[type[TransitionError], int] = {
    UnknownAction: 422,
    IllegalTransition: 409,
    PermissionDenied: 403,
}


@router.get("", response_model=list[SubmissionResponse])
async def list_submissions(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select

    from app.models.submission import Submission

    result = await db.execute(select(Submission).order_by(Submission.created_at.desc()))
    return list(result.scalars().all())


@router.post("", response_model=SubmissionResponse, status_code=201)
async def create_submission(
    data: SubmissionCreate, db: AsyncSession = Depends(get_db)
):
    return await SubmissionService.create(db, data)


@router.get("/lifecycle", response_model=LifecycleSpecResponse)
async def get_lifecycle():
    return to_dict(SUBMISSION_SPEC)


@router.post("/{submission_id}/transition", response_model=SubmissionResponse)
async def transition_submission(
    submission_id: uuid.UUID,
    data: SubmissionTransition,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    submission = await SubmissionService.get_by_id(db, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    try:
        return await SubmissionService.transition(
            db, submission, data.action, roles_for(admin)
        )
    except TransitionError as exc:
        raise HTTPException(
            status_code=_ERROR_STATUS.get(type(exc), 409), detail=str(exc)
        ) from exc
