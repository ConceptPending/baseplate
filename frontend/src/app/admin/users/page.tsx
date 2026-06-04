"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { StatusPill } from "@/components/ui/StatusPill";
import {
  checkAuth,
  inviteUser,
  listUsers,
  setUserActive,
  setUserAdmin,
  type AdminUser,
} from "@/lib/api";
import { errorMessage } from "@/lib/errors";

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [meId, setMeId] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    listUsers()
      .then(setUsers)
      .catch((err) => setError(errorMessage(err, "Failed to load users")));

  useEffect(() => {
    checkAuth()
      .then((u) => setMeId(u.id))
      .catch(() => {});
    load();
  }, []);

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await inviteUser(email, true);
      setEmail("");
      setModalOpen(false);
      load();
    } catch (err) {
      setError(errorMessage(err, "Failed to invite user"));
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(u: AdminUser) {
    try {
      await setUserActive(u.id, !u.is_active);
      load();
    } catch (err) {
      setError(errorMessage(err, "Failed to update user"));
    }
  }

  async function toggleAdmin(u: AdminUser) {
    try {
      await setUserAdmin(u.id, !u.is_admin);
      load();
    } catch (err) {
      setError(errorMessage(err, "Failed to update user"));
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
        <Button onClick={() => setModalOpen(true)}>Invite admin</Button>
      </div>

      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      <Card>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted">
              <th className="px-4 py-3 font-medium">Email</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Admin</th>
              <th className="px-4 py-3 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const isSelf = u.id === meId;
              return (
                <tr key={u.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3 font-medium">
                    {u.email}
                    {isSelf && <span className="text-muted"> (you)</span>}
                  </td>
                  <td className="px-4 py-3">
                    <StatusPill status={u.is_active ? "active" : "inactive"} />
                  </td>
                  <td className="px-4 py-3 text-muted">
                    {u.is_admin ? "Yes" : "No"}
                  </td>
                  <td className="px-4 py-3 text-right space-x-2">
                    {/* The backend refuses self-deactivation and last-admin
                        changes anyway; hiding the buttons is UI hygiene. */}
                    {!isSelf && (
                      <>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => toggleAdmin(u)}
                        >
                          {u.is_admin ? "Revoke admin" : "Make admin"}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => toggleActive(u)}
                        >
                          {u.is_active ? "Deactivate" : "Activate"}
                        </Button>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
            {users.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-muted">
                  No users yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Invite admin"
      >
        <form onSubmit={handleInvite} className="space-y-4">
          <Input
            id="invite-email"
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <p className="text-xs text-muted">
            The user is created with a random initial password. Share a reset
            out-of-band, or have them sign in via SSO if that recipe is applied.
          </p>
          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              type="button"
              onClick={() => setModalOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? "Inviting..." : "Invite"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
