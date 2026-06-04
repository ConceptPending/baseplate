"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import {
  createInvoice,
  getInvoiceSummary,
  listInvoices,
  type Invoice,
  type InvoiceSummary,
} from "@/lib/api";
import { errorMessage } from "@/lib/errors";

const CURRENCIES = ["GBP", "EUR", "USD"] as const;

export default function AdminInvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [summary, setSummary] = useState<InvoiceSummary | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState({
    supplier_name: "",
    invoice_date: "",
    invoice_number: "",
    amount: "",
    currency: "GBP" as (typeof CURRENCIES)[number],
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    listInvoices()
      .then(setInvoices)
      .catch((err) => setError(errorMessage(err, "Failed to load invoices")));
    getInvoiceSummary()
      .then(setSummary)
      .catch(() => {});
  };

  useEffect(() => {
    load();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await createInvoice({
        supplier_name: form.supplier_name,
        invoice_date: form.invoice_date,
        invoice_number: form.invoice_number,
        amount: Number(form.amount),
        currency: form.currency,
      });
      setForm({
        supplier_name: "",
        invoice_date: "",
        invoice_number: "",
        amount: "",
        currency: "GBP",
      });
      setModalOpen(false);
      load();
    } catch (err) {
      setError(errorMessage(err, "Failed to create invoice"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Invoices</h1>
        <Button onClick={() => setModalOpen(true)}>New invoice</Button>
      </div>

      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      {summary && summary.by_currency.length > 0 && (
        <Card className="mb-4">
          <div className="px-4 py-3 flex flex-wrap gap-6 text-sm">
            <span className="text-muted">
              {summary.count} invoice{summary.count === 1 ? "" : "s"}
            </span>
            {summary.by_currency.map((c) => (
              <span key={c.currency}>
                <span className="text-muted">{c.currency}</span>{" "}
                <span className="font-medium">{c.total.toFixed(2)}</span>
              </span>
            ))}
          </div>
        </Card>
      )}

      <Card>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted">
              <th className="px-4 py-3 font-medium">Supplier</th>
              <th className="px-4 py-3 font-medium">Date</th>
              <th className="px-4 py-3 font-medium">Number</th>
              <th className="px-4 py-3 font-medium text-right">Amount</th>
              <th className="px-4 py-3 font-medium">Currency</th>
            </tr>
          </thead>
          <tbody>
            {invoices.map((inv) => (
              <tr key={inv.id} className="border-b border-border last:border-0">
                <td className="px-4 py-3 font-medium">{inv.supplier_name}</td>
                <td className="px-4 py-3 text-muted">{inv.invoice_date}</td>
                <td className="px-4 py-3 text-muted">{inv.invoice_number}</td>
                <td className="px-4 py-3 text-right">{inv.amount.toFixed(2)}</td>
                <td className="px-4 py-3 text-muted">{inv.currency}</td>
              </tr>
            ))}
            {invoices.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted">
                  No invoices yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="New invoice"
      >
        <form onSubmit={handleCreate} className="space-y-4">
          <Input
            id="supplier_name"
            label="Supplier name"
            value={form.supplier_name}
            onChange={(e) => setForm({ ...form, supplier_name: e.target.value })}
            required
          />
          <Input
            id="invoice_date"
            label="Invoice date"
            type="date"
            value={form.invoice_date}
            onChange={(e) => setForm({ ...form, invoice_date: e.target.value })}
            required
          />
          <Input
            id="invoice_number"
            label="Invoice number"
            value={form.invoice_number}
            onChange={(e) => setForm({ ...form, invoice_number: e.target.value })}
            required
          />
          <Input
            id="amount"
            label="Amount"
            type="number"
            step="0.01"
            min="0.01"
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
            required
          />
          <div className="space-y-1.5">
            <label htmlFor="currency" className="block text-sm font-medium">
              Currency
            </label>
            <select
              id="currency"
              value={form.currency}
              onChange={(e) =>
                setForm({
                  ...form,
                  currency: e.target.value as (typeof CURRENCIES)[number],
                })
              }
              className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
            >
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              type="button"
              onClick={() => setModalOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? "Saving..." : "Create"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
