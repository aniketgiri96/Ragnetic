export default function Home() {
  return (
    <div className="space-y-8">
      <section className="space-y-5 fut-fade-up">
        <p className="fut-kicker">Private AI Infrastructure</p>
        <h1 className="fut-title text-5xl sm:text-6xl flex flex-wrap items-end gap-3">
          <span className="fut-script text-7xl sm:text-8xl text-slate-900">Ragnetic</span>
          <span className="fut-title-gradient">Command Layer</span>
        </h1>
        <p className="max-w-2xl text-lg text-slate-700">
          Open-source RAG platform with strict control over data, models, and retrieval behavior.
        </p>
      </section>

      <section className="fut-panel max-w-2xl fut-fade-up">
        <div className="p-4 sm:p-5 space-y-3">
          <p className="text-slate-700">Login to continue to your dashboard.</p>
          <a href="/login" className="fut-btn inline-flex">
            Login
          </a>
        </div>
      </section>
    </div>
  );
}
