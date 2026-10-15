"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { getAuditLog, type AuditLogEntry } from "@/lib/api";
import { errorMessage } from "@/lib/errors";

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleString();
}

export default function AdminAuditLogPage() {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAuditLog()
      .then(setEntries)
      .catch((err) => setError(errorMessage(err, "Failed to load audit log")));
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Audit log</h1>
      </div>

      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      <Card>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted">
              <th className="px-4 py-3 font-medium">When</th>
              <th className="px-4 py-3 font-medium">Action</th>
              <th className="px-4 py-3 font-medium">Resource</th>
              <th className="px-4 py-3 font-medium">Details</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id} className="border-b border-border last:border-0 align-top">
                <td className="px-4 py-3 text-muted whitespace-nowrap">
                  {relativeTime(e.created_at)}
                </td>
                <td className="px-4 py-3 font-medium">{e.action}</td>
                <td className="px-4 py-3 text-muted">
                  {e.resource_type}
                  {e.resource_id ? ` · ${e.resource_id.slice(0, 8)}` : ""}
                </td>
                <td className="px-4 py-3 text-muted">
                  {e.extra && Object.keys(e.extra).length > 0 ? (
                    <pre className="text-xs whitespace-pre-wrap">
                      {JSON.stringify(e.extra)}
                    </pre>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-muted">
                  No audit entries yet. Create, update, or delete an item to
                  record one.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
