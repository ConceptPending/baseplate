"""Submissions table (submission moderation lifecycle)

The lifecycle-state-machine recipe's worked example — a submission moving
through app/statespec/submission_spec.py. `status` is a plain string governed
by the spec (initial state: pending).

Revision ID: 004
Revises: 003
Create Date: 2026-06-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "submissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="pending"
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_submissions_status", "submissions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_submissions_status", table_name="submissions")
    op.drop_table("submissions")
