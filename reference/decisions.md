# Promotion decisions — Supplier invoice cleaner → Baseplate

This file records the **INTERVIEW-REQUIRED** answers and **CODE-INFERRED**
choices made while promoting the Flatpack in `original-flatpack.html` (plan
skeleton in `promotion-plan.md`). `make verify-promotion` checks the
MANIFEST-ASSERTED claims against the built app; these notes cover what the
manifest could not.

## What carried over (MANIFEST-ASSERTED → verified)

- **Entity `Invoice`** → `app/models/invoice.py` (`invoices` table). Every
  manifest field maps to a column of compatible type.
- **Validation predicates** → `app/schemas/invoice.py` (`InvoiceCreate`):
  `required`, `amount > 0` (`Field(gt=0)`), `invoice_date` is a date,
  `currency` is one of GBP/EUR/USD (`Literal`). `invoice_number` `unique` is a
  DB constraint. Run `make verify-promotion` to see all of these resolve.
- **Exports** → `app/api/invoices.py`: `clean_csv` (`GET …/export`),
  `errors_csv` (`GET …/errors`), `summary_print` (`GET …/summary`).

## Decisions the manifest did not constrain

- **`not_in_future`** is implemented as a Pydantic `@field_validator` on
  `invoice_date`. The verifier reports it as a WARN, not an OK — correctly, as
  it cannot statically prove a custom validator. It *is* enforced (see
  `test_future_invoice_date_rejected`).
- **`invoice_number` uniqueness** is now **global** (a DB unique constraint),
  not per-file as in the Flatpack — this is the whole point of promotion
  (matches the promotion signal "stored centrally and de-duplicated across
  files"). A duplicate POST returns 409.
- **`currency` normalisation** (upper-case/trim) from the Flatpack is replaced
  by a strict `Literal` enum at the API boundary — invalid currencies are
  rejected (422) rather than coerced. Revisit if lenient import is needed.
- **Roles**: left as Baseplate's single admin role for this reference. The
  promotion signals ("multiple reviewers", "audit history") point at the
  `admin-users` and `audit-log` recipes — see the `example/admin-users`
  branch for those applied. Not layered here to keep the round-trip minimal.
- **The example `Item` slice was kept** alongside `Invoice` so the base's
  existing tests stay green. A real promotion would remove `Item`.

## Not done (out of scope for this reference)

- CSV *import* UI (the Flatpack's headline feature). Here invoices are created
  via the API/admin form; a bulk-import endpoint + a background job is the
  natural next step (manifest archetype `import-validate-store`).
- Supplier as its own entity / reference list (a promotion signal). Would be a
  second model + FK; tracked but not built.
