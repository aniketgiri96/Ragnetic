export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <section className="page-head">
        <p className="page-kicker">Workspace overview</p>
        <h1 className="page-title">Knowledge Operations Dashboard</h1>
        <p className="page-subtitle">Use the sidebar modules to ingest files, run retrieval, and manage access.</p>
      </section>

      <section className="ui-stat-grid">
        <article className="ui-stat-card">
          <p className="ui-stat-label">Primary flow</p>
          <p className="ui-stat-value">Upload - Search - Chat</p>
        </article>
        <article className="ui-stat-card">
          <p className="ui-stat-label">Access model</p>
          <p className="ui-stat-value">Owner / Editor / Viewer</p>
        </article>
        <article className="ui-stat-card">
          <p className="ui-stat-label">Runtime</p>
          <p className="ui-stat-value">Self-hosted backend + API</p>
        </article>
      </section>

      <section className="ui-grid-two">
        <article className="ui-card">
          <h2 className="ui-card-title">Quick actions</h2>
          <div className="ui-action-row">
            <a href="/upload" className="fut-btn">
              Upload files
            </a>
            <a href="/search" className="fut-btn-ghost">
              Run search
            </a>
            <a href="/chat" className="fut-btn-ghost">
              Open chat
            </a>
            <a href="/members" className="fut-btn-ghost">
              Manage members
            </a>
          </div>
        </article>

        <article className="ui-card">
          <h2 className="ui-card-title">Recommended sequence</h2>
          <ol className="ui-list">
            <li>Select a knowledge base and upload your source documents.</li>
            <li>Validate retrieval quality with search and score inspection.</li>
            <li>Use chat with grounded sources for team Q&A workflows.</li>
            <li>Assign member roles to control access by responsibility.</li>
          </ol>
        </article>
      </section>
    </div>
  );
}
