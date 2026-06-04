import pytest

from tests.conftest import TEST_ADMIN_EMAIL


async def _login(client) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": "testpass"},
    )
    assert resp.status_code == 200
    return resp.cookies["csrf_token"]


def _valid_payload(**over) -> dict:
    payload = {
        "supplier_name": "Acme Ltd",
        "invoice_date": "2020-01-15",
        "invoice_number": "INV-001",
        "amount": 123.45,
        "currency": "GBP",
    }
    payload.update(over)
    return payload


@pytest.mark.asyncio
async def test_create_invoice(client):
    csrf = await _login(client)
    resp = await client.post(
        "/api/admin/invoices",
        json=_valid_payload(),
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["invoice_number"] == "INV-001"
    assert body["currency"] == "GBP"


@pytest.mark.asyncio
async def test_amount_must_be_positive(client):
    csrf = await _login(client)
    resp = await client.post(
        "/api/admin/invoices",
        json=_valid_payload(amount=0, invoice_number="INV-ZERO"),
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422  # Pydantic gt=0 rejects it


@pytest.mark.asyncio
async def test_future_invoice_date_rejected(client):
    csrf = await _login(client)
    resp = await client.post(
        "/api/admin/invoices",
        json=_valid_payload(invoice_date="2999-12-31", invoice_number="INV-FUT"),
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422  # not_in_future validator


@pytest.mark.asyncio
async def test_duplicate_invoice_number_rejected(client):
    csrf = await _login(client)
    headers = {"X-CSRF-Token": csrf}
    first = await client.post(
        "/api/admin/invoices", json=_valid_payload(invoice_number="DUP-1"), headers=headers
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/admin/invoices",
        json=_valid_payload(invoice_number="DUP-1", supplier_name="Other"),
        headers=headers,
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_summary_totals_by_currency(client):
    csrf = await _login(client)
    headers = {"X-CSRF-Token": csrf}
    await client.post(
        "/api/admin/invoices",
        json=_valid_payload(invoice_number="S-1", amount=100, currency="GBP"),
        headers=headers,
    )
    await client.post(
        "/api/admin/invoices",
        json=_valid_payload(invoice_number="S-2", amount=50, currency="GBP"),
        headers=headers,
    )
    resp = await client.get("/api/admin/invoices/summary")
    assert resp.status_code == 200
    data = resp.json()
    gbp = next(r for r in data["by_currency"] if r["currency"] == "GBP")
    assert gbp["total"] == 150.0


@pytest.mark.asyncio
async def test_clean_export_is_csv(client):
    csrf = await _login(client)
    await client.post(
        "/api/admin/invoices",
        json=_valid_payload(invoice_number="EXP-1"),
        headers={"X-CSRF-Token": csrf},
    )
    resp = await client.get("/api/admin/invoices/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "invoice_number" in resp.text and "EXP-1" in resp.text
