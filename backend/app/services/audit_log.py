from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class AuditLogService:
    @staticmethod
    async def record(
        db: AsyncSession,
        *,
        user_id: UUID,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Single entry point for audit writes. Every callsite uses the same
        shape so log entries are queryable consistently."""
        entry = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            extra=extra or {},
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return entry

    @staticmethod
    async def list_recent(db: AsyncSession, limit: int = 100) -> list[AuditLog]:
        result = await db.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
