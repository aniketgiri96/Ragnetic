"use client";

import { useState, useEffect } from "react";
import { deleteDocument, documentStatus, listDocuments, listKb, renameDocument, retryDocumentIngestion, uploadFile } from "../../lib/api.js";

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
  const [documents, setDocuments] = useState([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [docActionId, setDocActionId] = useState(null);
  const [menuDocId, setMenuDocId] = useState(null);
  const [menuDirection, setMenuDirection] = useState("down");

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

  async function refreshDocuments(targetKbId = kbId) {
    if (!targetKbId) return;
    const numericKbId = parseInt(targetKbId, 10);
    if (Number.isNaN(numericKbId)) return;
    setLoadingDocs(true);
    try {
      const rows = await listDocuments(numericKbId);
      setDocuments(Array.isArray(rows) ? rows : []);
    } catch (err) {
      if (err?.status === 401) setStatus("Please log in to manage documents.");
      else setStatus(err?.message || "Failed to load documents.");
    } finally {
      setLoadingDocs(false);
    }
  }

  useEffect(() => {
    if (!kbId) return;
    setMenuDocId(null);
    refreshDocuments(kbId);
  }, [kbId]);

  useEffect(() => {
    if (!menuDocId) return undefined;
    const handlePointerDown = (event) => {
      if (!(event.target instanceof Element)) return;
      if (event.target.closest(`[data-doc-menu="${menuDocId}"]`)) return;
      setMenuDocId(null);
    };
    const handleKeyDown = (event) => {
      if (event.key === "Escape") setMenuDocId(null);
    };
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuDocId]);

  useEffect(() => {
    if (!docId || !polling) return;
    const t = setInterval(() => {
      documentStatus(docId)
        .then((d) => {
          setStatus(`Document status: ${d.status}`);
          if (d.status === "indexed" || d.status === "failed") {
            setPolling(false);
            refreshDocuments();
          }
        })
        .catch(() => setPolling(false));
    }, 2000);
    return () => clearInterval(t);
  }, [docId, polling, kbId]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) return;
    setStatus("Uploading...");
    try {
      const res = await uploadFile(
        file,
        kbId ? parseInt(kbId, 10) : undefined,
      );
      if (res.deduplicated) {
        setStatus(`Already uploaded (deduplicated). Document ID: ${res.document_id}`);
        setPolling(false);
      } else if (res.replace_required) {
        setStatus("Filename already exists in this knowledge base. Rename or delete the existing document first.");
        setPolling(false);
      } else {
        setStatus(`Queued. Document ID: ${res.document_id}`);
        setDocId(res.document_id);
        setPolling(true);
      }
      refreshDocuments();
    } catch (err) {
      if (err?.status === 401)
        setStatus("Please log in to upload.");
      else
        setStatus(`Error: ${err?.message || "Upload failed"}`);
    }
  };

  const handleRename = async (doc) => {
    setMenuDocId(null);
    const nextName = window.prompt("Rename document", doc.filename || "");
    if (nextName == null) return;
    const normalized = nextName.trim();
    if (!normalized) {
      setStatus("Filename cannot be empty.");
      return;
    }
    if (normalized === (doc.filename || "").trim()) {
      setStatus("Filename unchanged. No re-indexing queued.");
      return;
    }
    setDocActionId(doc.document_id);
    try {
      const out = await renameDocument(doc.document_id, normalized);
      setStatus(out?.message || "Rename queued.");
      setDocId(doc.document_id);
      setPolling(true);
      await refreshDocuments();
    } catch (err) {
      setStatus(`Error: ${err?.message || "Rename failed"}`);
    } finally {
      setDocActionId(null);
    }
  };

  const handleDelete = async (doc) => {
    setMenuDocId(null);
    const ok = window.confirm(`Delete "${doc.filename}"? This removes indexed chunks and file storage.`);
    if (!ok) return;
    setDocActionId(doc.document_id);
    try {
      const out = await deleteDocument(doc.document_id);
      setStatus(out?.message || "Document deleted.");
      if (docId === doc.document_id) {
        setDocId(null);
        setPolling(false);
      }
      await refreshDocuments();
    } catch (err) {
      setStatus(`Error: ${err?.message || "Delete failed"}`);
    } finally {
      setDocActionId(null);
    }
  };

  const handleRetry = async (doc) => {
    setMenuDocId(null);
    setDocActionId(doc.document_id);
    try {
      const out = await retryDocumentIngestion(doc.document_id);
      setStatus(out?.message || "Retry queued.");
      setDocId(doc.document_id);
      setPolling(true);
      await refreshDocuments();
    } catch (err) {
      setStatus(`Error: ${err?.message || "Retry failed"}`);
    } finally {
      setDocActionId(null);
    }
  };

  const isAuthError = status.startsWith("Please log in");

  const formatUploadedAt = (value) => {
    if (!value) return "-";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "-";
    return d.toLocaleString([], {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

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
          <p className="fut-alert-info">Filename must be unique per knowledge base (case-insensitive).</p>
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

      <div className="ui-card">
        <div className="upload-docs-head">
          <h2 className="ui-card-title">Uploaded documents</h2>
          <button
            type="button"
            className="fut-btn-ghost"
            onClick={() => refreshDocuments()}
            disabled={loadingDocs || !kbId}
          >
            {loadingDocs ? "Refreshing..." : "Refresh"}
          </button>
        </div>
        {!kbId ? (
          <div className="fut-alert-info">Select a knowledge base to see documents.</div>
        ) : loadingDocs ? (
          <div className="fut-alert-info">Loading documents...</div>
        ) : documents.length === 0 ? (
          <div className="fut-alert-info">No uploaded documents yet.</div>
        ) : (
          <div className="upload-docs-table-wrap">
            <table className="upload-docs-table">
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Status</th>
                  <th>Uploaded</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => {
                  const busy = docActionId === doc.document_id;
                  return (
                    <tr key={doc.document_id}>
                      <td className="upload-docs-col-filename">{doc.filename}</td>
                      <td className="upload-docs-col-status">
                        {doc.status}
                        {doc.error_message ? ` (${doc.error_message})` : ""}
                      </td>
                      <td className="upload-docs-col-created">{formatUploadedAt(doc.created_at)}</td>
                      <td className="upload-docs-actions">
                        <div className="upload-docs-menu-wrap" data-doc-menu={doc.document_id}>
                          <button
                            type="button"
                            className="upload-docs-menu-btn"
                            aria-haspopup="menu"
                            aria-expanded={menuDocId === doc.document_id}
                            onClick={(event) => {
                              if (menuDocId === doc.document_id) {
                                setMenuDocId(null);
                                return;
                              }
                              const rect = event.currentTarget?.getBoundingClientRect?.();
                              if (rect) {
                                const estimatedMenuHeight = doc.status === "failed" ? 156 : 112;
                                const spaceAbove = rect.top;
                                const spaceBelow = window.innerHeight - rect.bottom;
                                setMenuDirection(
                                  spaceBelow < estimatedMenuHeight && spaceAbove > spaceBelow ? "up" : "down",
                                );
                              } else {
                                setMenuDirection("down");
                              }
                              setMenuDocId(doc.document_id);
                            }}
                            disabled={busy}
                            title="Document actions"
                          >
                            <span className="sr-only">Open document actions</span>
                            <span className="upload-docs-menu-icon" aria-hidden="true">
                              <span />
                              <span />
                              <span />
                            </span>
                          </button>
                          {menuDocId === doc.document_id && (
                            <div
                              className={`upload-docs-menu ${menuDirection === "up" ? "is-up" : "is-down"}`}
                              role="menu"
                              aria-label="Document actions"
                            >
                              <button
                                type="button"
                                className="upload-docs-menu-item is-danger"
                                onClick={() => handleDelete(doc)}
                                disabled={busy}
                                role="menuitem"
                              >
                                Delete
                              </button>
                              <button
                                type="button"
                                className="upload-docs-menu-item"
                                onClick={() => handleRename(doc)}
                                disabled={busy}
                                role="menuitem"
                              >
                                Rename
                              </button>
                              {doc.status === "failed" && (
                                <button
                                  type="button"
                                  className="upload-docs-menu-item"
                                  onClick={() => handleRetry(doc)}
                                  disabled={busy}
                                  role="menuitem"
                                >
                                  Retry ingestion
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
