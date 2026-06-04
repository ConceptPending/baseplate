from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class InvoiceCreate(BaseModel):
    # Each field carries a manifest validation_predicate so the promotion
    # verifier can resolve it against this schema:
    #   required (no default) · gt 0 · format date · one_of currencies
    supplier_name: str
    invoice_date: date
    invoice_number: str
    amount: float = Field(gt=0)
    currency: Literal["GBP", "EUR", "USD"] = "GBP"

    @field_validator("invoice_date")
    @classmethod
    def _not_in_future(cls, v: date) -> date:
        # The manifest's `not_in_future` predicate. (The verifier can't
        # introspect a custom validator, so it reports this one as a WARN —
        # which is honest: it's implemented, just not statically provable.)
        if v > date.today():
            raise ValueError("invoice_date must not be in the future")
        return v


class InvoiceResponse(BaseModel):
    id: UUID
    supplier_name: str
    invoice_date: date
    invoice_number: str
    amount: float
    currency: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
