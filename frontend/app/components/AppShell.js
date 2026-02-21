"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "ragnetic_token";

const DASHBOARD_ROUTES = new Set(["/dashboard", "/upload", "/search", "/chat", "/members"]);

const SIDEBAR_SECTIONS = [
  {
    title: "Core",
    links: [
      { href: "/dashboard", label: "Overview" },
      { href: "/upload", label: "Upload" },
      { href: "/search", label: "Search" },
      { href: "/chat", label: "Chat" },
    ],
  },
  {
    title: "Team",
    links: [{ href: "/members", label: "Members" }],
  },
  {
    title: "Resources",
    links: [{ href: `${API_URL}/docs`, label: "API Docs", external: true }],
  },
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
    if (!hasToken && DASHBOARD_ROUTES.has(pathname)) {
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

  const brandHref = isAuthenticated ? "/dashboard" : "/";
  const isLanding = pathname === "/";
  const mainClass = showDashboardShell
    ? "mx-auto w-full max-w-[1240px] flex-1 px-4 py-5 sm:px-6"
    : isLanding
      ? "mx-auto w-full max-w-[1240px] flex-1 px-4 pb-12 pt-8 sm:px-6"
      : "mx-auto w-full max-w-[760px] flex-1 px-4 py-10 sm:px-6";
  const isDashboardHome = pathname === "/dashboard";

  return (
    <>
      <header className="dash-topbar">
        <nav className="dash-topbar-nav" aria-label="Main navigation">
          <a href={brandHref} className="dash-brand">
            <span className="dash-brand-logo">R</span>
            <span className="dash-brand-stack">
              <span className="dash-brand-text">Ragnetic</span>
              <span className="dash-brand-subtext">Knowledge workspace</span>
            </span>
          </a>
          <div className="dash-topbar-actions">
            {!isAuthenticated ? (
              <a href="/login" className="dash-topbar-primary">
                Login
              </a>
            ) : (
              <>
                <a href="/dashboard" className={`dash-topbar-link ${isDashboardHome ? "is-active" : ""}`}>
                  Dashboard
                </a>
                <button type="button" onClick={handleLogout} className="dash-topbar-ghost">
                  Logout
                </button>
              </>
            )}
          </div>
        </nav>
      </header>

      <main className={mainClass}>
        {shouldHideProtectedContent ? (
          <div className="fut-alert-info">Checking your session...</div>
        ) : showDashboardShell ? (
          <div className="dash-layout">
            <aside className="dash-sidebar" aria-label="Dashboard navigation">
              <div className="dash-workspace-card">
                <p className="dash-workspace-kicker">Workspace</p>
                <h2 className="dash-workspace-title">Knowledge Ops</h2>
                <p className="dash-workspace-copy">Clean flow for ingestion, retrieval, chat, and access control.</p>
              </div>
              {SIDEBAR_SECTIONS.map((section) => (
                <div key={section.title} className="dash-sidebar-section">
                  <p className="dash-sidebar-heading">{section.title}</p>
                  <nav className="dash-sidebar-nav">
                    {section.links.map((item) => {
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
                </div>
              ))}
            </aside>
            <section className="dash-main">
              <div className="dash-main-canvas">{children}</div>
            </section>
          </div>
        ) : (
          children
        )}
      </main>
    </>
  );
}
