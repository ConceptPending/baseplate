from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice
from app.schemas.invoice import InvoiceCreate


class InvoiceService:
    @staticmethod
    async def list_all(db: AsyncSession) -> list[Invoice]:
        result = await db.execute(
            select(Invoice).order_by(Invoice.invoice_date.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_number(db: AsyncSession, invoice_number: str) -> Invoice | None:
        result = await db.execute(
            select(Invoice).where(Invoice.invoice_number == invoice_number)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data: InvoiceCreate) -> Invoice:
        invoice = Invoice(
            supplier_name=data.supplier_name,
            invoice_date=data.invoice_date,
            invoice_number=data.invoice_number,
            amount=data.amount,
            currency=data.currency,
        )
        db.add(invoice)
        await db.commit()
        await db.refresh(invoice)
        return invoice
