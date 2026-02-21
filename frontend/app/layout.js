import "./globals.css";

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Just+Another+Hand&family=Space+Grotesk:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen flex flex-col overflow-x-hidden">
        <div className="fut-bg-orb fut-bg-orb-a" />
        <div className="fut-bg-orb fut-bg-orb-b" />
        <header className="sticky top-0 z-50 bg-white/42 backdrop-blur-2xl">
          <nav className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 border-b border-slate-300/45 px-4 py-3 sm:px-6" aria-label="Main navigation">
            <a
              href="/"
              className="fut-brand"
            >
              <span className="h-2 w-2 rounded-full bg-cyan-500 shadow-[0_0_10px_rgba(14,165,233,0.55)]" />
              <span className="fut-script text-4xl leading-none text-slate-900">Ragnetic</span>
            </a>
            <div className="fut-nav-strip">
              <a
                href="/"
                className="fut-nav-link"
              >
                Home
              </a>
              <a
                href="/upload"
                className="fut-nav-link"
              >
                Upload
              </a>
              <a
                href="/search"
                className="fut-nav-link"
              >
                Search
              </a>
              <a
                href="/chat"
                className="fut-nav-link"
              >
                Chat
              </a>
              <a
                href="/members"
                className="fut-nav-link"
              >
                Members
              </a>
              <a
                href="/login"
                className="fut-nav-link fut-nav-link-active"
              >
                Login
              </a>
            </div>
          </nav>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-11 sm:px-6">
          {children}
        </main>
      </body>
    </html>
  );
}
