const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const featureCards = [
  {
    title: "Self-hosted by default",
    description: "Run the full stack on your own infrastructure and keep internal knowledge private.",
  },
  {
    title: "Hybrid retrieval",
    description: "Combine semantic and sparse retrieval to improve relevance on real internal documents.",
  },
  {
    title: "Grounded chat",
    description: "Generate answers with citations from your indexed content instead of generic model output.",
  },
  {
    title: "Team permissions",
    description: "Manage owner, editor, and viewer roles for each knowledge base in one place.",
  },
];

const workflowSteps = [
  {
    title: "Ingest",
    text: "Upload documents and process them into retrieval-ready chunks.",
  },
  {
    title: "Validate",
    text: "Use search to verify relevance and tune the retrieval quality.",
  },
  {
    title: "Assist",
    text: "Run chat on top of your knowledge base with source grounding.",
  },
];

const statItems = [
  { value: "Private", label: "data stays in your stack" },
  { value: "Fast", label: "indexed retrieval workflow" },
  { value: "Team", label: "role-based access control" },
];

export default function Home() {
  return (
    <div className="landing-shell">
      <section className="landing-hero">
        <div className="landing-hero-grid">
          <div>
            <p className="landing-kicker">Private AI Knowledge Platform</p>
            <h1 className="landing-title">A clean workspace for team knowledge ingestion, retrieval, and chat.</h1>
            <p className="landing-subtitle">
              Ragnetic helps teams build internal AI assistants with controlled data access, search-first validation, and grounded responses.
            </p>
            <div className="landing-cta-row">
              <a href="/login" className="fut-btn">
                Open Dashboard
              </a>
              <a href={`${API_URL}/docs`} target="_blank" rel="noopener noreferrer" className="fut-btn-ghost">
                API Docs
              </a>
            </div>
          </div>
          <div className="landing-highlight">
            <h2>Built for operational clarity</h2>
            <ul>
              <li>Upload and index documents by knowledge base.</li>
              <li>Inspect search relevance before production rollout.</li>
              <li>Enable grounded chat with clear source snippets.</li>
              <li>Control user roles with owner/editor/viewer permissions.</li>
            </ul>
          </div>
        </div>
        <ul className="landing-stat-grid" aria-label="Platform highlights">
          {statItems.map((item) => (
            <li key={item.label} className="landing-stat-card">
              <span className="landing-stat-value">{item.value}</span>
              <span className="landing-stat-label">{item.label}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="landing-section">
        <h2 className="landing-section-title">Key capabilities</h2>
        <div className="landing-grid">
          {featureCards.map((item) => (
            <article key={item.title} className="landing-card">
              <h3>{item.title}</h3>
              <p>{item.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <h2 className="landing-section-title">Typical workflow</h2>
        <div className="landing-step-grid">
          {workflowSteps.map((step, idx) => (
            <article key={step.title} className="landing-step-card">
              <span className="landing-step-index">{idx + 1}</span>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-final">
        <h2>Start with your first knowledge base</h2>
        <p>Login, upload files, validate search quality, and launch grounded chat for your team.</p>
        <a href="/login" className="fut-btn">
          Login
        </a>
      </section>
    </div>
  );
}
