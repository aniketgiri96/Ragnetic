"use client";

import { useState, useEffect } from "react";
import { listKb, uploadFile, documentStatus } from "../../lib/api.js";

const inputClass =
  "fut-input";
const labelClass = "fut-label";
const btnPrimary = "fut-btn";

export default function UploadPage() {
  const [kbs, setKbs] = useState([]);
  const [kbId, setKbId] = useState("");
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("");
  const [docId, setDocId] = useState(null);
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    listKb()
      .then((data) => {
        setKbs(data);
        if (data.length && !kbId) setKbId(String(data[0].id));
      })
      .catch((err) => {
        if (err?.status === 401) setStatus("Please log in to access knowledge bases.");
        else setStatus("Failed to load knowledge bases.");
      });
  }, []);

  useEffect(() => {
    if (!docId || !polling) return;
    const t = setInterval(() => {
      documentStatus(docId)
        .then((d) => {
          setStatus(`Document status: ${d.status}`);
          if (d.status === "indexed" || d.status === "failed") {
            setPolling(false);
          }
        })
        .catch(() => setPolling(false));
    }, 2000);
    return () => clearInterval(t);
  }, [docId, polling]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) return;
    setStatus("Uploading...");
    try {
      const res = await uploadFile(file, kbId ? parseInt(kbId, 10) : undefined);
      if (res.deduplicated) {
        setStatus(`Already indexed/queued (deduplicated). Document ID: ${res.document_id}`);
      } else {
        setStatus(`Queued. Document ID: ${res.document_id}`);
      }
      setDocId(res.document_id);
      if (res.document_id) setPolling(true);
    } catch (err) {
      if (err?.status === 401)
        setStatus("Please log in to upload.");
      else
        setStatus(`Error: ${err?.message || "Upload failed"}`);
    }
  };

  const isAuthError = status.startsWith("Please log in");

  return (
    <div className="space-y-6">
      <section className="page-head">
        <p className="page-kicker">Ingestion</p>
        <h1 className="page-title">Upload documents</h1>
        <p className="page-subtitle">Attach files, queue indexing, and track document status.</p>
      </section>

      <div className="ui-card">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="ui-grid-two">
            <div>
              <label htmlFor="upload-kb" className={labelClass}>
                Knowledge base
              </label>
              <select
                id="upload-kb"
                value={kbId}
                onChange={(e) => setKbId(e.target.value)}
                className={inputClass}
              >
                {kbs.map((kb) => (
                  <option key={kb.id} value={kb.id}>
                    {kb.name}{kb.role ? ` (${kb.role})` : ""}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="upload-file" className={labelClass}>
                File
              </label>
              <input
                id="upload-file"
                type="file"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="ui-file-input"
              />
            </div>
          </div>
          <button type="submit" disabled={!file} className={btnPrimary}>
            Upload
          </button>
        </form>
      </div>

      {status && (
        <div
          className={`${
            isAuthError
              ? "fut-alert-warn"
              : status.startsWith("Error") || status.startsWith("Failed")
                ? "fut-alert-error"
                : "fut-alert-info"
          }`}
        >
          {status}
          {isAuthError && (
            <>
              {" "}
              <a href="/login" className="font-medium underline text-slate-900">
                Log in
              </a>
            </>
          )}
        </div>
      )}
    </div>
  );
}
