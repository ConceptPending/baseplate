import csv
import io
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_admin
from app.schemas.invoice import InvoiceCreate, InvoiceResponse
from app.services.invoices import InvoiceService

ALLOWED_CURRENCIES = {"GBP", "EUR", "USD"}

router = APIRouter(
    prefix="/api/admin/invoices",
    tags=["invoices"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("", response_model=list[InvoiceResponse])
async def list_invoices(db: AsyncSession = Depends(get_db)):
    return await InvoiceService.list_all(db)


@router.post("", response_model=InvoiceResponse, status_code=201)
async def create_invoice(data: InvoiceCreate, db: AsyncSession = Depends(get_db)):
    # Central de-duplication — the carry-over of the Flatpack's per-file
    # invoice_number uniqueness check, now enforced across all imports.
    if await InvoiceService.get_by_number(db, data.invoice_number):
        raise HTTPException(status_code=409, detail="Duplicate invoice_number")
    return await InvoiceService.create(db, data)


def _csv_response(rows: list[list[str]], header: list[str], filename: str) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_HEADER = ["supplier_name", "invoice_date", "invoice_number", "amount", "currency"]


def _row(inv) -> list[str]:
    return [
        inv.supplier_name,
        inv.invoice_date.isoformat(),
        inv.invoice_number,
        str(inv.amount),
        inv.currency,
    ]


# Promoted export: the Flatpack's `clean_csv`.
@router.get("/export")
async def export_clean_csv(db: AsyncSession = Depends(get_db)):
    invoices = await InvoiceService.list_all(db)
    return _csv_response([_row(i) for i in invoices], _HEADER, "invoices-clean.csv")


# Promoted export: the Flatpack's `errors_csv` — rows flagged for review (here,
# any with an out-of-policy currency that slipped in before the constraint).
@router.get("/errors")
async def export_errors_csv(db: AsyncSession = Depends(get_db)):
    invoices = await InvoiceService.list_all(db)
    flagged = [i for i in invoices if i.currency not in ALLOWED_CURRENCIES]
    return _csv_response([_row(i) for i in flagged], _HEADER, "invoices-errors.csv")


# Promoted export: the Flatpack's `summary_print` — per-currency totals, the
# recurring finance report named in the manifest's promotion signals.
@router.get("/summary")
async def summary(db: AsyncSession = Depends(get_db)):
    invoices = await InvoiceService.list_all(db)
    totals: dict[str, float] = defaultdict(float)
    for inv in invoices:
        totals[inv.currency] += float(inv.amount)
    return {
        "count": len(invoices),
        "by_currency": [
            {"currency": cur, "total": round(total, 2)}
            for cur, total in sorted(totals.items())
        ],
    }
