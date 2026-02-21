"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const inputClass = "fut-input";
const labelClass = "fut-label";
const btnPrimary = "fut-btn";
const btnSecondary = "fut-btn-ghost";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setDone("");
    const url = isRegister ? `${API}/auth/register` : `${API}/auth/login`;
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.detail || res.statusText);
        return;
      }
      if (isRegister) {
        setDone("Registered. You can log in now.");
      } else {
        localStorage.setItem("ragnetic_token", data.access_token);
        window.dispatchEvent(new Event("ragnetic-auth-changed"));
        setDone("Logged in. Redirecting to dashboard...");
        setTimeout(() => router.push("/dashboard"), 350);
      }
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="space-y-6">
      <section className="page-head">
        <p className="page-kicker">Authentication</p>
        <h1 className="page-title">{isRegister ? "Create account" : "Login to dashboard"}</h1>
        <p className="page-subtitle">Authenticate against your self-hosted Ragnetic backend.</p>
      </section>

      <div className="ui-card">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="ui-grid-two">
            <div>
              <label htmlFor="login-email" className={labelClass}>
                Email
              </label>
              <input
                id="login-email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className={inputClass}
                autoComplete="email"
              />
            </div>
            <div>
              <label htmlFor="login-password" className={labelClass}>
                Password
              </label>
              <input
                id="login-password"
                type="password"
                placeholder="********"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className={inputClass}
                autoComplete={isRegister ? "new-password" : "current-password"}
              />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button type="submit" className={btnPrimary}>
              {isRegister ? "Register" : "Login"}
            </button>
            <button
              type="button"
              onClick={() => {
                setIsRegister(!isRegister);
                setError("");
                setDone("");
              }}
              className={btnSecondary}
            >
              {isRegister ? "Switch to login" : "Create account instead"}
            </button>
          </div>
        </form>
      </div>

      {error && <div className="fut-alert-error">{error}</div>}
      {done && <div className="fut-alert-success">{done}</div>}
    </div>
  );
}
