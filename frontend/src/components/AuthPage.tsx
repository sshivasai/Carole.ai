"use client";
import React, { useState } from "react";
import { Eye, EyeOff, Loader2, Zap } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import CaroleLogo from "./CaroleLogo";

interface AuthPageProps {
  onBackToLanding?: () => void;
}

export default function AuthPage({ onBackToLanding }: AuthPageProps) {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirst]   = useState("");
  const [lastName, setLast]     = useState("");
  const [showPw, setShowPw]     = useState(false);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) { setError("Email and password are required."); return; }
    setLoading(true);
    setError("");
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await signup(email, password, firstName || undefined, lastName || undefined);
      }
    } catch (err: any) {
      const body = err.body || err.message || "An error occurred.";
      try { setError(JSON.parse(body)?.detail || body); } catch { setError(body); }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "var(--color-canvas)", padding: "var(--sp-lg)", position: "relative", overflow: "hidden",
    }}>
      {/* Background glow */}
      <div style={{ position: "absolute", top: "20%", left: "50%", transform: "translateX(-50%)",
        width: 400, height: 400, borderRadius: "50%", background: "var(--color-primary-glow)",
        filter: "blur(80px)", opacity: 0.4, pointerEvents: "none" }} />

      {onBackToLanding && (
        <button
          onClick={onBackToLanding}
          style={{
            position: "absolute", top: 20, left: 24, background: "none", border: "none",
            color: "var(--color-mute)", cursor: "pointer", fontSize: 13, fontWeight: 500,
            display: "flex", alignItems: "center", gap: 6, zIndex: 10,
          }}
        >
          ← Back to Overview
        </button>
      )}

      <div style={{ width: "100%", maxWidth: 420, position: "relative", zIndex: 1 }}>
        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: "var(--sp-3xl)", cursor: onBackToLanding ? "pointer" : "default" }} onClick={onBackToLanding}>
          <CaroleLogo variant="full" size={220} />
        </div>

        {/* Tab toggle */}
        <div style={{ display: "flex", background: "var(--color-canvas-soft)", borderRadius: "var(--radius-md)", padding: 3, marginBottom: "var(--sp-2xl)", border: "1px solid var(--color-hairline)" }}>
          {(["login", "signup"] as const).map(m => (
            <button
              key={m}
              onClick={() => { setMode(m); setError(""); }}
              style={{
                flex: 1, padding: "var(--sp-sm)", fontSize: 13, fontWeight: 600,
                border: "none", borderRadius: "var(--radius-sm)", cursor: "pointer",
                transition: "all var(--t-fast)",
                background: mode === m ? "var(--color-primary)" : "transparent",
                color: mode === m ? "var(--color-on-primary)" : "var(--color-mute)",
              }}
            >
              {m === "login" ? "Sign In" : "Create Account"}
            </button>
          ))}
        </div>

        {/* Form card */}
        <div className="card" style={{ padding: "var(--sp-3xl)" }}>
          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: "var(--sp-lg)" }}>
            {mode === "signup" && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--sp-md)" }}>
                <div className="form-group">
                  <label className="form-label">First Name</label>
                  <input className="input" placeholder="Ada" value={firstName} onChange={e => setFirst(e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Last Name</label>
                  <input className="input" placeholder="Lovelace" value={lastName} onChange={e => setLast(e.target.value)} />
                </div>
              </div>
            )}

            <div className="form-group">
              <label className="form-label">Email</label>
              <input className="input" type="email" placeholder="you@example.com"
                value={email} onChange={e => setEmail(e.target.value)} autoFocus />
            </div>

            <div className="form-group">
              <label className="form-label">Password</label>
              <div style={{ position: "relative" }}>
                <input className="input" type={showPw ? "text" : "password"}
                  placeholder={mode === "signup" ? "min 8 characters" : "your password"}
                  value={password} onChange={e => setPassword(e.target.value)}
                  style={{ paddingRight: 44 }} />
                <button type="button" onClick={() => setShowPw(s => !s)}
                  style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)",
                    background: "none", border: "none", cursor: "pointer", color: "var(--color-mute)", display: "flex" }}>
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {error && (
              <div style={{ padding: "var(--sp-sm) var(--sp-md)", background: "var(--color-danger-glow)",
                border: "1px solid rgba(248,113,113,0.3)", borderRadius: "var(--radius-sm)",
                fontSize: 13, color: "var(--color-danger)" }}>
                {error}
              </div>
            )}

            <button className="btn btn-primary btn-lg" type="submit" disabled={loading}
              style={{ width: "100%", justifyContent: "center", marginTop: "var(--sp-sm)" }}>
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
              {mode === "login" ? "Sign In" : "Create Account"}
            </button>
          </form>
        </div>

        <p className="caption" style={{ textAlign: "center", marginTop: "var(--sp-xl)" }}>
          {mode === "login" ? "New to Carole.ai? " : "Already have an account? "}
          <button onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(""); }}
            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--color-primary)", fontSize: 11, fontWeight: 600 }}>
            {mode === "login" ? "Create account" : "Sign in"}
          </button>
        </p>
      </div>
    </div>
  );
}
