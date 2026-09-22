"use client";

import React, { useState, useEffect, useRef, useId } from "react";
import { X, Eye, EyeOff, Loader2 } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import CaroleLogo from "./CaroleLogo";
import styles from "./AuthModal.module.css";

interface AuthModalProps {
  isOpen: boolean;
  initialMode?: "login" | "signup";
  onClose: () => void;
  onSuccess?: () => void;
}

export default function AuthModal(props: AuthModalProps) {
  return props.isOpen ? <AuthModalContent key={props.initialMode || "login"} {...props} /> : null;
}

function AuthModalContent({
  isOpen,
  initialMode = "login",
  onClose,
  onSuccess,
}: AuthModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; }, [onClose]);
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirst] = useState("");
  const [lastName, setLast] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isOpen) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialogRef.current?.querySelector<HTMLInputElement>('input[type="email"]')?.focus();
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); closeRef.current(); }
      if (e.key !== "Tab") return;
      const controls = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), a[href], [tabindex="0"]') || []);
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    if (!email || !password) {
      setError("Email and password are required.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await signup(
          email,
          password,
          firstName.trim() || undefined,
          lastName.trim() || undefined
        );
      }
      onSuccess?.();
    } catch (err: unknown) {
      const failure = err as { body?: unknown; message?: string };
      const body = failure?.body || failure?.message || "An error occurred.";
      let detail: unknown = body;
      try { detail = typeof body === "string" ? JSON.parse(body)?.detail || body : body; } catch {}
      setError(typeof detail === "string" ? detail : "Unable to sign in. Check your details and try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className={styles.modalBackdrop}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <div ref={dialogRef} className={styles.modalContent}>
        {/* Close Button */}
        <button
          onClick={onClose}
          className={styles.closeBtn}
          title="Close modal"
          aria-label="Close"
        >
          <X size={17} />
        </button>

        {/* Modal Header */}
        <div className={styles.modalHeader}>
          <div className={styles.logoWrap}>
            <CaroleLogo variant="mark" size={32} />
          </div>
          <h2 id={titleId} className={styles.modalTitle}>
            {mode === "login" ? "Sign in to Carole.ai" : "Create your account"}
          </h2>
          <p className={styles.modalSubtitle}>
            {mode === "login"
              ? "Access your autonomous multi-agent workspaces and flightdeck."
              : "Start orchestrating autonomous engineering teams locally."}
          </p>
        </div>

        {/* Tab Toggle: Sign In / Create Account */}
        <div className={styles.tabToggle}>
          <button
            type="button"
            className={`${styles.tabBtn} ${
              mode === "login" ? styles.tabBtnActive : ""
            }`}
            onClick={() => {
              setMode("login");
              setError("");
            }}
          >
            Sign In
          </button>
          <button
            type="button"
            className={`${styles.tabBtn} ${
              mode === "signup" ? styles.tabBtnActive : ""
            }`}
            onClick={() => {
              setMode("signup");
              setError("");
            }}
          >
            Create Account
          </button>
        </div>

        {/* Auth Form */}
        <form onSubmit={handleSubmit} className={styles.authForm}>
          {mode === "signup" && (
            <div className={styles.nameRow}>
              <div className={styles.formField}>
                <label htmlFor={`${titleId}-first`} className={styles.formLabel}>First Name</label>
                <input id={`${titleId}-first`} autoComplete="given-name"
                  className={styles.formInput}
                  placeholder="Ada"
                  value={firstName}
                  onChange={(e) => setFirst(e.target.value)}
                  disabled={loading}
                />
              </div>
              <div className={styles.formField}>
                <label htmlFor={`${titleId}-last`} className={styles.formLabel}>Last Name</label>
                <input id={`${titleId}-last`} autoComplete="family-name"
                  className={styles.formInput}
                  placeholder="Lovelace"
                  value={lastName}
                  onChange={(e) => setLast(e.target.value)}
                  disabled={loading}
                />
              </div>
            </div>
          )}

          <div className={styles.formField}>
            <label htmlFor={`${titleId}-email`} className={styles.formLabel}>Email Address</label>
            <input id={`${titleId}-email`} autoComplete="email"
              className={styles.formInput}
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={loading}
            />
          </div>

          <div className={styles.formField}>
            <label htmlFor={`${titleId}-password`} className={styles.formLabel}>Password</label>
            <div className={styles.inputWrap}>
              <input id={`${titleId}-password`} autoComplete={mode === "signup" ? "new-password" : "current-password"}
                className={styles.formInput}
                type={showPw ? "text" : "password"}
                placeholder={
                  mode === "signup" ? "min 8 characters" : "your password"
                }
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={loading}
                style={{ paddingRight: 40 }}
              />
              <button
                type="button"
                onClick={() => setShowPw((s) => !s)}
                className={styles.eyeBtn}
                title={showPw ? "Hide password" : "Show password"}
                aria-label={showPw ? "Hide password" : "Show password"}
                aria-pressed={showPw}
              >
                {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {error && <div role="alert" className={styles.errorBanner}>{error}</div>}

          <button
            className={styles.submitBtn}
            type="submit"
            disabled={loading}
          >
            {loading ? (
              <Loader2 size={15} className="animate-spin" />
            ) : null}
            <span>{mode === "login" ? "Sign in to Console" : "Create Account"}</span>
          </button>
        </form>

        <p className={styles.footerNote}>
          {mode === "login"
            ? "New to Carole.ai? "
            : "Already have an account? "}
          <button
            type="button"
            className={styles.switchLink}
            onClick={() => {
              setMode(mode === "login" ? "signup" : "login");
              setError("");
            }}
          >
            {mode === "login" ? "Create an account" : "Sign in"}
          </button>
        </p>
      </div>
    </div>
  );
}
