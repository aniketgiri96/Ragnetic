export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <p className="fut-kicker">Control Center</p>
        <h1 className="fut-title text-4xl sm:text-5xl flex items-end gap-3">
          <span className="fut-script text-6xl sm:text-7xl text-slate-900">Dashboard</span>
          <span className="fut-title-gradient">Workspace Overview</span>
        </h1>
        <p className="max-w-3xl text-slate-600">
          Your core tools are now organized in the sidebar for a cleaner flow.
        </p>
      </section>

      <section className="fut-panel max-w-4xl">
        <div className="p-4 sm:p-5 space-y-3">
          <p className="text-slate-700">
            Use the sidebar to open Upload, Search, Chat, Members, or API Docs.
          </p>
          <p className="text-sm text-slate-600">
            Start with Upload to index documents, then use Search or Chat to query your knowledge base.
          </p>
        </div>
      </section>
    </div>
  );
}
