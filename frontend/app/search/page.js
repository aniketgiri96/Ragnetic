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
    <div className="space-y-8">
      <section className="space-y-3">
        <p className="fut-kicker">Semantic + Sparse Retrieval</p>
        <h1 className="fut-title text-4xl sm:text-5xl flex items-end gap-3">
          <span className="fut-script text-6xl sm:text-7xl text-slate-900">Search</span>
          <span className="fut-title-gradient">Retrieval Probe</span>
        </h1>
        <p className="max-w-3xl text-slate-600">
          Query your indexed documents with hybrid retrieval and inspect ranking signals for each result.
        </p>
      </section>

      <div className="fut-panel max-w-5xl">
        <form onSubmit={handleSearch} className="space-y-4 p-4 sm:p-5">
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
          <button type="submit" disabled={loading} className={btnPrimary}>
            {loading ? "Searching…" : "Search"}
          </button>
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

      {results.length > 0 ? (
        <ul className="fut-panel max-w-5xl space-y-0">
          {results.map((r, i) => (
            <li
              key={i}
              className={`fut-card ${i === results.length - 1 ? "border-b-0" : ""}`}
            >
              <p className="text-slate-900">{r.snippet}</p>
              {r.score != null && (
                <p className="mt-2 text-sm text-slate-600">
                  Score: {r.score.toFixed(3)}
                  {r.dense_score != null && ` · dense ${Number(r.dense_score).toFixed(3)}`}
                  {r.sparse_score != null && ` · sparse ${Number(r.sparse_score).toFixed(3)}`}
                </p>
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
