"use client";

import { useEffect, useState } from "react";
import {
  addKbMember,
  listKb,
  listKbMembers,
  removeKbMember,
  updateKbMemberRole,
} from "../../lib/api.js";

const inputClass =
  "fut-input";
const labelClass = "fut-label";
const btnPrimary = "fut-btn";
const btnSecondary = "fut-btn-ghost";
const ROLE_OPTIONS = ["owner", "editor", "viewer"];

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

  const activeKbRole = kbs.find((kb) => String(kb.id) === kbId)?.role || "";
  const isOwner = activeKbRole === "owner";

  useEffect(() => {
    listKb()
      .then((data) => {
        setKbs(data);
        if (data.length > 0) setKbId(String(data[0].id));
      })
      .catch((err) => {
        if (err?.status === 401) setError("Please log in to manage members.");
        else setError("Failed to load knowledge bases.");
      });
  }, []);

  useEffect(() => {
    if (!kbId) return;
    setLoadingMembers(true);
    setError("");
    listKbMembers(parseInt(kbId, 10))
      .then((data) => setMembers(Array.isArray(data) ? data : []))
      .catch((err) => {
        if (err?.status === 401) setError("Please log in to manage members.");
        else setError(err?.message || "Failed to load members.");
      })
      .finally(() => setLoadingMembers(false));
  }, [kbId]);

  const handleAddMember = async (e) => {
    e.preventDefault();
    if (!kbId || !email.trim()) return;
    setSubmitting(true);
    setError("");
    setMessage("");
    try {
      await addKbMember(parseInt(kbId, 10), { email: email.trim(), role: newRole });
      const data = await listKbMembers(parseInt(kbId, 10));
      setMembers(Array.isArray(data) ? data : []);
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
      setMessage("Member removed.");
    } catch (err) {
      setError(err?.message || "Failed to remove member.");
    } finally {
      setSavingUserId(null);
    }
  };

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <p className="fut-kicker">Collaborative Governance</p>
        <h1 className="fut-title text-4xl sm:text-5xl flex items-end gap-3">
          <span className="fut-script text-6xl sm:text-7xl text-slate-900">Members</span>
          <span className="fut-title-gradient">Access Control</span>
        </h1>
        <p className="max-w-3xl text-slate-600">
          Invite collaborators and manage role-based permissions at the knowledge-base level.
        </p>
      </section>

      <div className="fut-panel max-w-5xl space-y-4 p-4 sm:p-5">
        <div>
          <label htmlFor="members-kb" className={labelClass}>
            Knowledge base
          </label>
          <select
            id="members-kb"
            value={kbId}
            onChange={(e) => setKbId(e.target.value)}
            className={inputClass}
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
            Only owners can add, remove, or change roles for this knowledge base.
          </p>
        )}

        <form onSubmit={handleAddMember} className="grid gap-3 sm:grid-cols-3">
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
              disabled={!isOwner || submitting}
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
              disabled={!isOwner || submitting}
            >
              {ROLE_OPTIONS.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </div>
          <div className="sm:col-span-3">
            <button type="submit" className={btnPrimary} disabled={!isOwner || submitting || !email.trim()}>
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
              <a href="/login" className="font-medium underline text-cyan-700 hover:text-cyan-800">
                Log in
              </a>
            </>
          )}
        </div>
      )}
      {message && <div className="fut-alert-success">{message}</div>}

      <div className="fut-panel max-w-5xl p-4 sm:p-5">
        <h2 className="mb-4 text-lg font-semibold text-slate-900">Current members</h2>
        {loadingMembers ? (
          <p className="text-slate-600">Loading members...</p>
        ) : members.length === 0 ? (
          <p className="text-slate-600">No members found for this knowledge base.</p>
        ) : (
          <ul className="space-y-3">
            {members.map((m) => (
              <li key={`${m.user_id}-${m.email}`} className="fut-card">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="font-medium text-slate-900">{m.email}</p>
                    <p className="text-sm text-slate-600">User ID: {m.user_id}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                    <select
                      value={m.role}
                      onChange={(e) =>
                        setMembers((prev) =>
                          prev.map((row) =>
                            row.user_id === m.user_id ? { ...row, role: e.target.value } : row,
                          ),
                        )
                      }
                      className="fut-input min-h-[2.62rem] px-4 py-1.5"
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
                      className="fut-btn-danger"
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
    </div>
  );
}
