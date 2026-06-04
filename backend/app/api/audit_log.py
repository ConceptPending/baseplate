from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_admin
from app.schemas.audit_log import AuditLogResponse
from app.services.audit_log import AuditLogService

router = APIRouter(
    prefix="/api/admin/audit-log",
    tags=["audit-log"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("", response_model=list[AuditLogResponse])
async def list_audit_log(db: AsyncSession = Depends(get_db)):
    return await AuditLogService.list_recent(db)
