"use client";

import { useEffect, useMemo, useState } from "react";
import {
  addKbMember,
  createKb,
  deleteKb,
  listKb,
  listKbAuditLogs,
  listKbMembers,
  removeKbMember,
  updateKb,
  updateKbMemberRole,
} from "../../lib/api.js";

const inputClass = "fut-input";
const labelClass = "fut-label";
const btnPrimary = "fut-btn";
const btnSecondary = "fut-btn-ghost";
const ROLE_OPTIONS = ["owner", "editor", "viewer", "api_user"];

function compactDetail(details) {
  if (!details || typeof details !== "object") return "-";
  const pairs = Object.entries(details).slice(0, 4);
  if (pairs.length === 0) return "-";
  return pairs
    .map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join(" • ");
}

function formatTimestamp(value) {
  const d = new Date(value || "");
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function MembersPage() {
  const [kbs, setKbs] = useState([]);
  const [kbId, setKbId] = useState("");
  const [members, setMembers] = useState([]);
  const [email, setEmail] = useState("");
  const [newRole, setNewRole] = useState("viewer");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [savingUserId, setSavingUserId] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const [newKbName, setNewKbName] = useState("");
  const [newKbDescription, setNewKbDescription] = useState("");
  const [savingKb, setSavingKb] = useState(false);
  const [editingKbName, setEditingKbName] = useState("");
  const [editingKbDescription, setEditingKbDescription] = useState("");

  const [auditLogs, setAuditLogs] = useState([]);
  const [loadingAudit, setLoadingAudit] = useState(false);

  const activeKb = useMemo(() => kbs.find((kb) => String(kb.id) === kbId) || null, [kbs, kbId]);
  const activeKbRole = activeKb?.role || "";
  const isOwner = activeKbRole === "owner";

  const refreshKbList = async (preferredKbId) => {
    const data = await listKb();
    const rows = Array.isArray(data) ? data : [];
    setKbs(rows);
    if (rows.length === 0) {
      setKbId("");
      setMembers([]);
      setAuditLogs([]);
      return rows;
    }
    const preferred = preferredKbId != null ? String(preferredKbId) : kbId;
    const next = rows.some((kb) => String(kb.id) === preferred) ? preferred : String(rows[0].id);
    setKbId(next);
    return rows;
  };

  const refreshMembers = async (targetKbId = kbId) => {
    if (!targetKbId) return;
    setLoadingMembers(true);
    try {
      const data = await listKbMembers(parseInt(targetKbId, 10));
      setMembers(Array.isArray(data) ? data : []);
    } finally {
      setLoadingMembers(false);
    }
  };

  const refreshAuditLogs = async (targetKbId = kbId) => {
    if (!targetKbId || !isOwner) {
      setAuditLogs([]);
      return;
    }
    setLoadingAudit(true);
    try {
      const data = await listKbAuditLogs(parseInt(targetKbId, 10), { limit: 100 });
      setAuditLogs(Array.isArray(data) ? data : []);
    } finally {
      setLoadingAudit(false);
    }
  };

  useEffect(() => {
    refreshKbList()
      .catch((err) => {
        if (err?.status === 401) setError("Please log in to manage members.");
        else setError("Failed to load knowledge bases.");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!activeKb) {
      setEditingKbName("");
      setEditingKbDescription("");
      return;
    }
    setEditingKbName(activeKb.name || "");
    setEditingKbDescription(activeKb.description || "");
  }, [activeKb]);

  useEffect(() => {
    if (!kbId) return;
    setError("");
    refreshMembers(kbId)
      .catch((err) => {
        if (err?.status === 401) setError("Please log in to manage members.");
        else setError(err?.message || "Failed to load members.");
      });
  }, [kbId]);

  useEffect(() => {
    if (!kbId) return;
    if (!isOwner) {
      setAuditLogs([]);
      return;
    }
    setError("");
    refreshAuditLogs(kbId)
      .catch((err) => {
        if (err?.status === 401) setError("Please log in to access audit logs.");
        else setError(err?.message || "Failed to load audit logs.");
      });
  }, [kbId, isOwner]);

  const handleAddMember = async (e) => {
    e.preventDefault();
    if (!kbId || !email.trim()) return;
    setSubmitting(true);
    setError("");
    setMessage("");
    try {
      await addKbMember(parseInt(kbId, 10), { email: email.trim(), role: newRole });
      await refreshMembers(kbId);
      await refreshAuditLogs(kbId);
      setEmail("");
      setNewRole("viewer");
      setMessage("Member added or updated.");
    } catch (err) {
      setError(err?.message || "Failed to add member.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdateRole = async (memberUserId, role) => {
    if (!kbId) return;
    setSavingUserId(memberUserId);
    setError("");
    setMessage("");
    try {
      const updated = await updateKbMemberRole(parseInt(kbId, 10), memberUserId, role);
      setMembers((prev) =>
        prev.map((m) => (m.user_id === memberUserId ? { ...m, role: updated.role } : m)),
      );
      await refreshAuditLogs(kbId);
      setMessage("Role updated.");
    } catch (err) {
      setError(err?.message || "Failed to update role.");
    } finally {
      setSavingUserId(null);
    }
  };

  const handleRemove = async (memberUserId) => {
    if (!kbId) return;
    setSavingUserId(memberUserId);
    setError("");
    setMessage("");
    try {
      await removeKbMember(parseInt(kbId, 10), memberUserId);
      setMembers((prev) => prev.filter((m) => m.user_id !== memberUserId));
      await refreshAuditLogs(kbId);
      setMessage("Member removed.");
    } catch (err) {
      setError(err?.message || "Failed to remove member.");
    } finally {
      setSavingUserId(null);
    }
  };

  const handleCreateKb = async (e) => {
    e.preventDefault();
    if (!newKbName.trim()) return;
    setSavingKb(true);
    setError("");
    setMessage("");
    try {
      const created = await createKb({
        name: newKbName.trim(),
        description: newKbDescription.trim() || undefined,
      });
      await refreshKbList(created?.id);
      setNewKbName("");
      setNewKbDescription("");
      setMessage("Knowledge base created.");
    } catch (err) {
      setError(err?.message || "Failed to create knowledge base.");
    } finally {
      setSavingKb(false);
    }
  };

  const handleUpdateKb = async (e) => {
    e.preventDefault();
    if (!kbId) return;
    setSavingKb(true);
    setError("");
    setMessage("");
    try {
      await updateKb(parseInt(kbId, 10), {
        name: editingKbName,
        description: editingKbDescription,
      });
      await refreshKbList(kbId);
      await refreshAuditLogs(kbId);
      setMessage("Knowledge base updated.");
    } catch (err) {
      setError(err?.message || "Failed to update knowledge base.");
    } finally {
      setSavingKb(false);
    }
  };

  const handleDeleteKb = async () => {
    if (!kbId) return;
    const target = activeKb;
    const ok = window.confirm(
      `Delete "${target?.name || "this knowledge base"}"? Documents and chat history in this KB will be removed.`,
    );
    if (!ok) return;
    setSavingKb(true);
    setError("");
    setMessage("");
    try {
      await deleteKb(parseInt(kbId, 10));
      await refreshKbList();
      setMessage("Knowledge base deleted.");
    } catch (err) {
      setError(err?.message || "Failed to delete knowledge base.");
    } finally {
      setSavingKb(false);
    }
  };

  return (
    <div className="space-y-6">
      <section className="page-head">
        <p className="page-kicker">Access control</p>
        <h1 className="page-title">Knowledge base members</h1>
        <p className="page-subtitle">Manage knowledge bases, collaborators, and audit trails.</p>
      </section>

      <div className="ui-card space-y-4">
        <div>
          <label htmlFor="members-kb" className={labelClass}>
            Knowledge base
          </label>
          <select
            id="members-kb"
            value={kbId}
            onChange={(e) => setKbId(e.target.value)}
            className={inputClass}
            disabled={kbs.length === 0}
          >
            {kbs.map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name}
                {kb.role ? ` (${kb.role})` : ""}
              </option>
            ))}
          </select>
        </div>
        {!isOwner && kbId && (
          <p className="fut-alert-warn">
            You are not an owner on this knowledge base. Membership, lifecycle changes, and audit logs are owner-only.
          </p>
        )}
      </div>

      <div className="ui-card space-y-4">
        <h2 className="ui-card-title">Knowledge base lifecycle</h2>
        <form onSubmit={handleCreateKb} className="ui-grid-two">
          <div>
            <label htmlFor="new-kb-name" className={labelClass}>
              New KB name
            </label>
            <input
              id="new-kb-name"
              className={inputClass}
              value={newKbName}
              onChange={(e) => setNewKbName(e.target.value)}
              placeholder="Team KB"
              disabled={savingKb}
            />
          </div>
          <div>
            <label htmlFor="new-kb-description" className={labelClass}>
              New KB description
            </label>
            <input
              id="new-kb-description"
              className={inputClass}
              value={newKbDescription}
              onChange={(e) => setNewKbDescription(e.target.value)}
              placeholder="Optional description"
              disabled={savingKb}
            />
          </div>
          <div className="sm:col-span-2">
            <button
              type="submit"
              className={btnPrimary}
              disabled={savingKb || !newKbName.trim()}
            >
              {savingKb ? "Saving..." : "Create knowledge base"}
            </button>
          </div>
        </form>

        <form onSubmit={handleUpdateKb} className="ui-grid-two">
          <div>
            <label htmlFor="edit-kb-name" className={labelClass}>
              Selected KB name
            </label>
            <input
              id="edit-kb-name"
              className={inputClass}
              value={editingKbName}
              onChange={(e) => setEditingKbName(e.target.value)}
              disabled={!isOwner || !kbId || savingKb}
            />
          </div>
          <div>
            <label htmlFor="edit-kb-description" className={labelClass}>
              Selected KB description
            </label>
            <input
              id="edit-kb-description"
              className={inputClass}
              value={editingKbDescription}
              onChange={(e) => setEditingKbDescription(e.target.value)}
              disabled={!isOwner || !kbId || savingKb}
            />
          </div>
          <div className="sm:col-span-2 members-kb-actions">
            <button
              type="submit"
              className={btnSecondary}
              disabled={!isOwner || !kbId || savingKb || !editingKbName.trim()}
            >
              Update selected KB
            </button>
            <button
              type="button"
              className="fut-btn-danger"
              disabled={!isOwner || !kbId || savingKb}
              onClick={handleDeleteKb}
            >
              Delete selected KB
            </button>
          </div>
        </form>
      </div>

      <div className="ui-card space-y-4">
        <h2 className="ui-card-title">Members</h2>
        <form onSubmit={handleAddMember} className="ui-grid-two">
          <div className="sm:col-span-2">
            <label htmlFor="member-email" className={labelClass}>
              User email
            </label>
            <input
              id="member-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="teammate@example.com"
              className={inputClass}
              disabled={!isOwner || submitting || !kbId}
            />
          </div>
          <div>
            <label htmlFor="member-role" className={labelClass}>
              Role
            </label>
            <select
              id="member-role"
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
              className={inputClass}
              disabled={!isOwner || submitting || !kbId}
            >
              {ROLE_OPTIONS.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </div>
          <div className="sm:col-span-2">
            <button type="submit" className={btnPrimary} disabled={!isOwner || submitting || !email.trim() || !kbId}>
              {submitting ? "Saving..." : "Add or update member"}
            </button>
          </div>
        </form>
      </div>

      {error && (
        <div className="fut-alert-error">
          {error}
          {error.startsWith("Please log in") && (
            <>
              {" "}
              <a href="/login" className="font-medium underline text-slate-900">
                Log in
              </a>
            </>
          )}
        </div>
      )}
      {message && <div className="fut-alert-success">{message}</div>}

      <div className="ui-card">
        <h2 className="ui-card-title">Current members</h2>
        {loadingMembers ? (
          <p className="text-slate-600 mt-3">Loading members...</p>
        ) : members.length === 0 ? (
          <p className="text-slate-600 mt-3">No members found for this knowledge base.</p>
        ) : (
          <ul className="member-list">
            {members.map((m) => (
              <li key={`${m.user_id}-${m.email}`} className="member-row">
                <div className="flex flex-col gap-1">
                  <div>
                    <p className="font-medium text-slate-900">{m.email}</p>
                    <p className="text-xs text-slate-500">User ID: {m.user_id}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <select
                      value={m.role}
                      onChange={(e) =>
                        setMembers((prev) =>
                          prev.map((row) =>
                            row.user_id === m.user_id ? { ...row, role: e.target.value } : row,
                          ),
                        )
                      }
                      className="fut-input min-h-[2.5rem] px-3 py-1.5 sm:min-w-[140px]"
                      disabled={!isOwner || savingUserId === m.user_id}
                    >
                      {ROLE_OPTIONS.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className={btnSecondary}
                      disabled={!isOwner || savingUserId === m.user_id}
                      onClick={() => handleUpdateRole(m.user_id, m.role)}
                    >
                      Update
                    </button>
                    <button
                      type="button"
                      className="fut-btn-danger sm:min-w-[84px]"
                      disabled={!isOwner || savingUserId === m.user_id}
                      onClick={() => handleRemove(m.user_id)}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="ui-card">
        <div className="members-audit-head">
          <h2 className="ui-card-title">Audit log</h2>
          <button
            type="button"
            className="fut-btn-ghost"
            disabled={!isOwner || !kbId || loadingAudit}
            onClick={() => refreshAuditLogs(kbId).catch((err) => setError(err?.message || "Failed to load audit logs."))}
          >
            {loadingAudit ? "Refreshing..." : "Refresh"}
          </button>
        </div>
        {!kbId ? (
          <div className="fut-alert-info">Select a knowledge base to inspect audit logs.</div>
        ) : !isOwner ? (
          <div className="fut-alert-info">Owner role required to view audit logs.</div>
        ) : loadingAudit ? (
          <div className="fut-alert-info">Loading audit logs...</div>
        ) : auditLogs.length === 0 ? (
          <div className="fut-alert-info">No audit events yet.</div>
        ) : (
          <div className="members-audit-list">
            {auditLogs.map((row) => (
              <div key={row.id} className="members-audit-row">
                <div className="members-audit-meta">
                  <span>{formatTimestamp(row.created_at)}</span>
                  <span>{row.action}</span>
                  <span>{row.user_email || `User #${row.user_id || "unknown"}`}</span>
                </div>
                <p className="members-audit-details">{compactDetail(row.details)}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
