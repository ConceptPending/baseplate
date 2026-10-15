from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_admin
from app.models.user import User
from app.schemas.item import ItemCreate, ItemResponse, ItemUpdate
from app.services.audit_log import AuditLogService
from app.services.items import ItemService

# All routes in this router require an authenticated admin. The mutating routes
# take `user: User = Depends(get_current_admin)` so they can attribute the audit
# entry to the acting admin; the read routes only need the gate.
router = APIRouter(
    prefix="/api/admin/items",
    tags=["items"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("", response_model=list[ItemResponse])
async def list_items(db: AsyncSession = Depends(get_db)):
    return await ItemService.list_all(db)


@router.post("", response_model=ItemResponse, status_code=201)
async def create_item(
    data: ItemCreate,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    item = await ItemService.create(db, data)
    await AuditLogService.record(
        db,
        user_id=user.id,
        action="create",
        resource_type="item",
        resource_id=str(item.id),
        extra={"name": item.name},
    )
    return item


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(item_id: str, db: AsyncSession = Depends(get_db)):
    item = await ItemService.get_by_id(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.patch("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: str,
    data: ItemUpdate,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    item = await ItemService.update(db, item_id, data)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await AuditLogService.record(
        db,
        user_id=user.id,
        action="update",
        resource_type="item",
        resource_id=str(item.id),
        extra=data.model_dump(exclude_unset=True, mode="json"),
    )
    return item


@router.delete("/{item_id}", status_code=204)
async def delete_item(
    item_id: str,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    deleted = await ItemService.delete(db, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Item not found")
    await AuditLogService.record(
        db,
        user_id=user.id,
        action="delete",
        resource_type="item",
        resource_id=item_id,
    )
