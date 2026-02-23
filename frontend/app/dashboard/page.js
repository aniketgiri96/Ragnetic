"use client";

import { useEffect, useMemo, useState } from "react";
import { listKb } from "../../lib/api.js";

export default function DashboardPage() {
  const [kbs, setKbs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let canceled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const data = await listKb();
        if (!canceled) setKbs(Array.isArray(data) ? data : []);
      } catch (err) {
        if (!canceled) setError(err?.status === 401 ? "Please log in to access dashboard." : "Failed to load knowledge bases.");
      } finally {
        if (!canceled) setLoading(false);
      }
    }
    load();
    return () => {
      canceled = true;
    };
  }, []);

  const roleCounts = useMemo(() => {
    const counts = { owner: 0, editor: 0, viewer: 0 };
    kbs.forEach((kb) => {
      const role = String(kb.role || "").toLowerCase();
      if (role in counts) counts[role] += 1;
    });
    return counts;
  }, [kbs]);

  const readiness = useMemo(() => {
    if (loading) return "Loading";
    if (kbs.length === 0) return "Setup needed";
    if (roleCounts.owner > 0) return "Ready";
    return "Review access";
  }, [kbs.length, loading, roleCounts.owner]);

  return (
    <div className="dash-clean space-y-5">
      <section className="dash-clean-hero">
        <div className="space-y-2">
          <p className="page-kicker">Workspace overview</p>
          <h1 className="page-title">Knowledge Operations</h1>
          <p className="page-subtitle">A cleaner command view for ingestion, retrieval, chat, and permissions.</p>
        </div>
        <div className="dash-clean-actions">
          <a href="/chat" className="fut-btn">
            Open chat
          </a>
          <a href="/upload" className="fut-btn-ghost">
            Upload files
          </a>
          <a href="/members" className="fut-btn-ghost">
            Manage access
          </a>
        </div>
      </section>

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

      <section className="dash-clean-metrics" aria-label="Workspace metrics">
        <article className="dash-clean-metric">
          <p className="dash-clean-metric-label">Knowledge bases</p>
          <p className="dash-clean-metric-value">{loading ? "--" : kbs.length}</p>
        </article>
        <article className="dash-clean-metric">
          <p className="dash-clean-metric-label">Owner access</p>
          <p className="dash-clean-metric-value">{loading ? "--" : roleCounts.owner}</p>
        </article>
        <article className="dash-clean-metric">
          <p className="dash-clean-metric-label">Collaborators</p>
          <p className="dash-clean-metric-value">{loading ? "--" : roleCounts.editor + roleCounts.viewer}</p>
        </article>
        <article className="dash-clean-metric">
          <p className="dash-clean-metric-label">Readiness</p>
          <p className="dash-clean-metric-value">{readiness}</p>
        </article>
      </section>

      <section className="dash-clean-grid">
        <article className="dash-clean-panel">
          <h2 className="dash-clean-panel-title">Core workflow</h2>
          <ol className="dash-clean-steps">
            <li>
              <span>1</span>
              <div>
                <p>Upload source docs</p>
                <small>Add PDFs, docs, or markdown files.</small>
              </div>
            </li>
            <li>
              <span>2</span>
              <div>
                <p>Validate retrieval</p>
                <small>Run search and inspect scoring signals.</small>
              </div>
            </li>
            <li>
              <span>3</span>
              <div>
                <p>Run grounded chat</p>
                <small>Ask questions and verify cited snippets.</small>
              </div>
            </li>
          </ol>
        </article>

        <article className="dash-clean-panel">
          <div className="dash-clean-panel-head">
            <h2 className="dash-clean-panel-title">Knowledge bases</h2>
            <a href="/members" className="dash-clean-inline-link">
              Team roles
            </a>
          </div>

          {loading ? (
            <div className="fut-alert-info">Loading workspace list...</div>
          ) : kbs.length === 0 ? (
            <div className="fut-alert-info">No knowledge base found yet.</div>
          ) : (
            <ul className="dash-clean-kb-list">
              {kbs.slice(0, 6).map((kb) => (
                <li key={kb.id} className="dash-clean-kb-row">
                  <div>
                    <p className="dash-clean-kb-name">{kb.name}</p>
                    <small>KB #{kb.id}</small>
                  </div>
                  <span className="dash-clean-role-chip">{kb.role || "viewer"}</span>
                </li>
              ))}
            </ul>
          )}
        </article>
      </section>
    </div>
  );
}
