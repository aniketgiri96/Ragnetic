"use client";

import { useEffect, useMemo, useState } from "react";
import { createOnboardingSampleKb, getOnboardingStatus, listKb } from "../../lib/api.js";

function toPercent(value) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}

export default function OnboardingPage() {
  const [status, setStatus] = useState(null);
  const [kbs, setKbs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creatingSample, setCreatingSample] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [statusData, kbData] = await Promise.all([getOnboardingStatus(), listKb()]);
      setStatus(statusData || null);
      setKbs(Array.isArray(kbData) ? kbData : []);
    } catch (err) {
      if (err?.status === 401) setError("Please log in to use onboarding.");
      else setError(err?.message || "Failed to load onboarding status.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const progress = useMemo(() => toPercent(status?.progress_percent), [status]);
  const primaryKb = useMemo(() => {
    if (!status?.primary_kb_id) return null;
    return kbs.find((kb) => kb.id === status.primary_kb_id) || null;
  }, [kbs, status?.primary_kb_id]);

  const handleCreateSample = async () => {
    setCreatingSample(true);
    setError("");
    setMessage("");
    try {
      const res = await createOnboardingSampleKb();
      setMessage(`Sample KB queued: ${res?.kb_name || "KnowAI Starter KB"}.`);
      await load();
    } catch (err) {
      setError(err?.message || "Failed to create sample KB.");
    } finally {
      setCreatingSample(false);
    }
  };

  return (
    <div className="space-y-6">
      <section className="page-head">
        <p className="page-kicker">First-time setup</p>
        <h1 className="page-title">Onboarding Wizard</h1>
        <p className="page-subtitle">Track progress from empty workspace to first grounded answer.</p>
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
      {message && <div className="fut-alert-success">{message}</div>}

      <section className="ui-card space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Progress</h2>
            <p className="text-xs text-slate-500">
              {loading
                ? "Loading setup status..."
                : `${status?.completed_steps || 0}/${status?.total_steps || 0} steps completed`}
            </p>
          </div>
          <div className="text-xs font-semibold text-slate-700">{loading ? "--" : `${progress}%`}</div>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
          <div
            className="h-full rounded-full bg-slate-900 transition-all"
            style={{ width: `${loading ? 0 : progress}%` }}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="fut-btn" onClick={handleCreateSample} disabled={creatingSample}>
            {creatingSample ? "Creating..." : "Create sample KB"}
          </button>
          <button type="button" className="fut-btn-ghost" onClick={load} disabled={loading}>
            Refresh status
          </button>
        </div>
        <p className="text-xs text-slate-500">
          Primary KB: {primaryKb ? `${primaryKb.name} (#${primaryKb.id})` : "Not created yet"}
        </p>
      </section>

      <section className="ui-card">
        <h2 className="text-sm font-semibold text-slate-900">Setup steps</h2>
        {loading ? (
          <p className="mt-3 text-sm text-slate-500">Loading steps...</p>
        ) : (
          <ol className="mt-3 space-y-3">
            {(status?.steps || []).map((step, idx) => (
              <li key={step.id || idx} className="rounded-xl border border-slate-200 bg-slate-50/70 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">
                      {idx + 1}. {step.label}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">{step.detail}</p>
                  </div>
                  <span
                    className={`rounded-full px-2 py-1 text-[11px] font-semibold ${
                      step.completed ? "bg-emerald-100 text-emerald-800" : "bg-slate-200 text-slate-700"
                    }`}
                  >
                    {step.completed ? "Done" : "Pending"}
                  </span>
                </div>
                {!step.completed && step.action_path && (
                  <div className="mt-3">
                    <a href={step.action_path} className="fut-btn-ghost inline-flex">
                      Open {step.action_path.replace("/", "") || "dashboard"}
                    </a>
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
