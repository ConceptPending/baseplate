from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk
from app.statespec.submission_spec import SUBMISSION_SPEC


class Submission(Base, TimestampMixin):
    """A public-style submission moving through a moderation lifecycle. The
    legal states and transitions are governed by
    app/statespec/submission_spec.py; `status` is a plain string the engine
    keeps within the spec. `created_at` (from TimestampMixin) is what the
    `is_stale` guard reads via the service-computed age."""

    __tablename__ = "submissions"

    id = uuid_pk()
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)

    status: Mapped[str] = mapped_column(
        String(32),
        default=SUBMISSION_SPEC.initial,
        server_default=SUBMISSION_SPEC.initial,
        index=True,
    )
