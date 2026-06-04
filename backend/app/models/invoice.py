from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class Invoice(Base, TimestampMixin):
    """Promoted from the `Supplier invoice cleaner` Flatpack — see
    reference/original-flatpack.html. The columns mirror the manifest's
    `Invoice` entity so `make verify-promotion` can resolve every field."""

    __tablename__ = "invoices"

    id = uuid_pk()
    supplier_name: Mapped[str] = mapped_column(String(255))
    invoice_date: Mapped[date] = mapped_column(Date)
    # unique = the manifest's `invoice_number unique` predicate, now enforced
    # centrally (the Flatpack could only dedupe within a single file).
    invoice_number: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(
        String(3), default="GBP", server_default="GBP"
    )
