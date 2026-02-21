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
        setDone("Logged in.");
        setTimeout(() => router.push("/upload"), 500);
      }
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="space-y-8 max-w-2xl mx-auto">
      <section className="space-y-3">
        <p className="fut-kicker">Identity Verification</p>
        <h1 className="fut-title text-4xl sm:text-5xl flex items-end gap-3">
          <span className="fut-script text-6xl sm:text-7xl text-slate-900">
            {isRegister ? "Register" : "Login"}
          </span>
          <span className="fut-title-gradient">Access Node</span>
        </h1>
        <p className="text-slate-600">
          Authenticate locally against your self-hosted Ragnetic backend.
        </p>
      </section>

      <div className="fut-panel">
        <form onSubmit={handleSubmit} className="space-y-4 p-4 sm:p-5">
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
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className={inputClass}
              autoComplete={isRegister ? "new-password" : "current-password"}
            />
          </div>
          <button type="submit" className={btnPrimary}>
            {isRegister ? "Register" : "Login"}
          </button>
        </form>

        <div className="mt-4 border-t border-slate-300/45 pt-4 px-4 sm:px-5">
          <button
            type="button"
            onClick={() => {
              setIsRegister(!isRegister);
              setError("");
              setDone("");
            }}
            className={`${btnSecondary} w-full sm:w-auto`}
          >
            {isRegister ? "Already have an account? Log in" : "Need an account? Register"}
          </button>
        </div>
      </div>

      {error && (
        <div className="fut-alert-error">
          {error}
        </div>
      )}
      {done && (
        <div className="fut-alert-success">
          {done}
        </div>
      )}
    </div>
  );
}
