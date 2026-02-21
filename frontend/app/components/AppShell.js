"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "ragnetic_token";

const DASHBOARD_ROUTES = new Set(["/dashboard", "/upload", "/search", "/chat", "/members"]);

const SIDEBAR_LINKS = [
  { href: "/dashboard", label: "Overview" },
  { href: "/upload", label: "Upload" },
  { href: "/search", label: "Search" },
  { href: "/chat", label: "Chat" },
  { href: "/members", label: "Members" },
  { href: `${API_URL}/docs`, label: "API Docs", external: true },
];

function readToken() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_KEY) || "";
}

export default function AppShell({ children }) {
  const router = useRouter();
  const pathname = usePathname() || "/";
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setIsAuthenticated(Boolean(readToken()));
    setMounted(true);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const syncAuth = () => setIsAuthenticated(Boolean(readToken()));
    window.addEventListener("storage", syncAuth);
    window.addEventListener("ragnetic-auth-changed", syncAuth);
    return () => {
      window.removeEventListener("storage", syncAuth);
      window.removeEventListener("ragnetic-auth-changed", syncAuth);
    };
  }, []);

  useEffect(() => {
    if (!mounted) return;
    const hasToken = Boolean(readToken());
    if (hasToken !== isAuthenticated) {
      setIsAuthenticated(hasToken);
      return;
    }
    if (!hasToken && (DASHBOARD_ROUTES.has(pathname) || pathname === "/")) {
      router.replace("/login");
      return;
    }
    if (hasToken && (pathname === "/" || pathname === "/login")) {
      router.replace("/dashboard");
    }
  }, [isAuthenticated, mounted, pathname, router]);

  const showDashboardShell = useMemo(
    () => mounted && isAuthenticated && DASHBOARD_ROUTES.has(pathname),
    [isAuthenticated, mounted, pathname],
  );
  const shouldHideProtectedContent = DASHBOARD_ROUTES.has(pathname) && (!mounted || !isAuthenticated);

  const handleLogout = () => {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(TOKEN_KEY);
      window.dispatchEvent(new Event("ragnetic-auth-changed"));
    }
    setIsAuthenticated(false);
    router.push("/login");
  };

  const brandHref = isAuthenticated ? "/dashboard" : "/login";

  return (
    <>
      <header className="sticky top-0 z-50 bg-white/42 backdrop-blur-2xl">
        <nav
          className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 border-b border-slate-300/45 px-4 py-3 sm:px-6"
          aria-label="Main navigation"
        >
          <a href={brandHref} className="fut-brand">
            <span className="h-2 w-2 rounded-full bg-cyan-500 shadow-[0_0_10px_rgba(14,165,233,0.55)]" />
            <span className="fut-script text-4xl leading-none text-slate-900">Ragnetic</span>
          </a>
          <div className="fut-nav-strip">
            {!isAuthenticated ? (
              <a
                href="/login"
                className={`fut-nav-link ${pathname === "/login" ? "fut-nav-link-active" : ""}`}
              >
                Login
              </a>
            ) : (
              <>
                <a
                  href="/dashboard"
                  className={`fut-nav-link ${pathname === "/dashboard" ? "fut-nav-link-active" : ""}`}
                >
                  Dashboard
                </a>
                <button type="button" onClick={handleLogout} className="fut-nav-link fut-nav-button">
                  Logout
                </button>
              </>
            )}
          </div>
        </nav>
      </header>

      <main className={showDashboardShell ? "mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6" : "mx-auto w-full max-w-4xl flex-1 px-4 py-11 sm:px-6"}>
        {shouldHideProtectedContent ? (
          <div className="fut-alert-info">Checking your session...</div>
        ) : showDashboardShell ? (
          <div className="dash-layout">
            <aside className="dash-sidebar" aria-label="Dashboard navigation">
              <p className="dash-sidebar-kicker">Workspace</p>
              <h2 className="dash-sidebar-title">Dashboard</h2>
              <nav className="dash-sidebar-nav">
                {SIDEBAR_LINKS.map((item) => {
                  const isActive = !item.external && pathname === item.href;
                  return (
                    <a
                      key={item.href}
                      href={item.href}
                      target={item.external ? "_blank" : undefined}
                      rel={item.external ? "noopener noreferrer" : undefined}
                      className={`dash-sidebar-link ${isActive ? "dash-sidebar-link-active" : ""}`}
                    >
                      {item.label}
                    </a>
                  );
                })}
              </nav>
            </aside>
            <section className="dash-main">{children}</section>
          </div>
        ) : (
          children
        )}
      </main>
    </>
  );
}
