const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const features = [
  {
    title: "Upload",
    description: "Add documents to a knowledge base",
    href: "/upload",
  },
  {
    title: "Search",
    description: "Semantic search over your docs",
    href: "/search",
  },
  {
    title: "Chat",
    description: "Ask questions with source attribution",
    href: "/chat",
  },
  {
    title: "Members",
    description: "Share knowledge bases with editors and viewers",
    href: "/members",
  },
  {
    title: "API docs",
    description: "REST API reference",
    href: `${API_URL}/docs`,
    external: true,
  },
];

export default function Home() {
  return (
    <div className="space-y-14">
      <section className="space-y-5 fut-fade-up">
        <p className="fut-kicker">
          Private AI Infrastructure
        </p>
        <h1 className="fut-title text-5xl sm:text-6xl flex flex-wrap items-end gap-3">
          <span className="fut-script text-7xl sm:text-8xl text-slate-900">Ragnetic</span>
          <span className="fut-title-gradient">Command Layer</span>
        </h1>
        <p className="max-w-2xl text-lg text-slate-700">
          Open-source RAG platform for teams that want futuristic UX with strict control over data, models, and retrieval behavior.
        </p>
        <p className="max-w-xl text-sm text-slate-600">
          Deploy in minutes. Keep proprietary knowledge private. Share searchable and chat-ready KBs across your organization.
        </p>
      </section>

      <section className="fut-panel max-w-5xl">
        <h2 className="sr-only">Get started</h2>
        <ul className="space-y-0">
          {features.map((item, idx) => (
            <li key={item.href} className="fut-fade-up" style={{ animationDelay: `${idx * 60}ms` }}>
              <a
                href={item.href}
                target={item.external ? "_blank" : undefined}
                rel={item.external ? "noopener noreferrer" : undefined}
                className={`fut-card block focus:outline-none focus:ring-2 focus:ring-cyan-400/70 ${idx === features.length - 1 ? "border-b-0" : ""}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.24em] text-cyan-700/80">Module {String(idx + 1).padStart(2, "0")}</p>
                    <span className="mt-1 block text-xl font-semibold text-slate-900">{item.title}</span>
                  </div>
                  <span className="text-cyan-700/80 text-sm uppercase tracking-[0.22em]">Open</span>
                </div>
                <p className="mt-2 text-sm text-slate-600">{item.description}</p>
              </a>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
