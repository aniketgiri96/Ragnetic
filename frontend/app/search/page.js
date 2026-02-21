"use client";

import { useState, useEffect } from "react";
import { listKb, search } from "../../lib/api.js";

const inputClass =
  "fut-input";
const labelClass = "fut-label";
const btnPrimary = "fut-btn";

export default function SearchPage() {
  const [kbs, setKbs] = useState([]);
  const [kbId, setKbId] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    listKb()
      .then((data) => {
        setKbs(data);
        if (data.length && !kbId) setKbId(String(data[0].id));
      })
      .catch((err) => {
        if (err?.status === 401) setError("Please log in to access search.");
        else setError("Failed to load knowledge bases.");
      });
  }, []);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError("");
    try {
      const data = await search(query, kbId ? parseInt(kbId, 10) : undefined);
      setResults(Array.isArray(data) ? data : []);
    } catch (err) {
      if (err?.status === 401) setError("Please log in to search.");
      else setError(err?.message || "Search failed");
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <section className="page-head">
        <p className="page-kicker">Retrieval</p>
        <h1 className="page-title">Search indexed content</h1>
        <p className="page-subtitle">Run semantic + sparse retrieval and inspect score signals.</p>
      </section>

      <div className="ui-card">
        <form onSubmit={handleSearch} className="space-y-4">
          <div className="ui-grid-two">
            <div>
              <label htmlFor="search-kb" className={labelClass}>
                Knowledge base
              </label>
              <select
                id="search-kb"
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
              <label htmlFor="search-query" className={labelClass}>
                Query
              </label>
              <input
                id="search-query"
                type="text"
                placeholder="Search your documents..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className={inputClass}
              />
            </div>
          </div>
          <button type="submit" disabled={loading} className={btnPrimary}>
            {loading ? "Searching..." : "Search"}
          </button>
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

      {results.length > 0 ? (
        <ul className="ui-result-list">
          {results.map((r, i) => (
            <li
              key={i}
              className={`ui-result-item ${i === results.length - 1 ? "is-last" : ""}`}
            >
              <p className="text-slate-900">{r.snippet}</p>
              {r.score != null && (
                <div className="ui-score-row">
                  <span className="ui-score-chip">score {r.score.toFixed(3)}</span>
                  {r.dense_score != null && <span className="ui-score-chip">dense {Number(r.dense_score).toFixed(3)}</span>}
                  {r.sparse_score != null && <span className="ui-score-chip">sparse {Number(r.sparse_score).toFixed(3)}</span>}
                </div>
              )}
            </li>
          ))}
        </ul>
      ) : (
        query.trim() && !loading && !error && (
          <div className="fut-alert-info">
            No matches found for this query.
          </div>
        )
      )}
    </div>
  );
}
