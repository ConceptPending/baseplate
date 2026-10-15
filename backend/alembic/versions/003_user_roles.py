"""User lifecycle roles column

Adds `users.roles` — a sorted CSV of lifecycle roles (see app/roles.py) that
gates which state-machine transitions a user may fire. Orthogonal to is_admin.

Backfill: existing admins are granted every human role, so upgrading a live
deployment never strips power from people who already had it.

Revision ID: 003
Revises: 002
Create Date: 2026-06-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen literal — a historical record that must not shift if the role
# catalogue grows later. (Sorted human roles: approver, finance, reviewer.)
_ADMIN_BACKFILL = "approver,finance,reviewer"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("roles", sa.String(255), nullable=False, server_default=""),
    )
    users = sa.table(
        "users", sa.column("roles", sa.String), sa.column("is_admin", sa.Boolean)
    )
    op.execute(
        users.update().where(users.c.is_admin.is_(True)).values(roles=_ADMIN_BACKFILL)
    )


def downgrade() -> None:
    op.drop_column("users", "roles")
