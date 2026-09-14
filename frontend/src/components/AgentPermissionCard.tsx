"use client";
import React, { useEffect, useRef, useState } from "react";
import { ShieldCheck, Check, X, Loader2, Clock, ChevronDown } from "lucide-react";
import type { ChatMessage } from "@/lib/types";
import { DiffViewer } from "./DiffViewer";
import "./chat-workspace.css";

export default function AgentPermissionCard({ msg, onDecide, loading = false }: {
  msg: ChatMessage; onDecide: (approved: boolean, feedback?: string) => Promise<void>; loading?: boolean;
}) {
  const request = msg.pending_approval;
  const id = request?.tx_id || msg.tx_id || msg.id;
  const tool = request?.tool_name || msg.tool_name || "action";
  const args = request?.arguments || msg.arguments || {};
  const [decision, setDecision] = useState<{ id: string; status: string } | null>(null);
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState<number | null>(null);
  const lock = useRef(false);
  const currentId = useRef(id);
  currentId.current = id;
  const rawExpiry = (request as { expires_at?: string | number } | undefined)?.expires_at || (msg as ChatMessage & { expires_at?: string | number }).expires_at;
  const expiry = typeof rawExpiry === "number" ? (rawExpiry < 1e12 ? rawExpiry * 1000 : rawExpiry) : rawExpiry ? Date.parse(rawExpiry) : NaN;
  const serverStatus = request?.status || msg.status || "pending";
  const terminal = ["approved", "denied", "expired", "cancelled", "superseded"];
  const status = terminal.includes(serverStatus) ? serverStatus : decision?.id === id ? decision.status : Number.isFinite(expiry) && now !== null && now >= expiry ? "expired" : "pending";
  useEffect(() => { setFeedback(""); setError(""); }, [id]);
  useEffect(() => {
    if (!Number.isFinite(expiry) || status !== "pending") return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [expiry, status]);
  const decide = async (approved: boolean) => {
    if (lock.current || loading || status !== "pending") return;
    lock.current = true; setBusy(true); setError("");
    try {
      await onDecide(approved, feedback.trim() || undefined);
      if (currentId.current === id) setDecision({ id, status: approved ? "approved" : "denied" });
    } catch (e) {
      if (currentId.current === id) setError(e instanceof Error ? e.message : "Decision was not sent. Please try again.");
    } finally { lock.current = false; setBusy(false); }
  };
  const target = args.command || args.cmd || args.CommandLine || args.relative_path || args.path || args.file_path || args.url || args.query;
  const reason = (request as { reason?: string } | undefined)?.reason || msg.reason || request?.text || msg.text;
  const content = args.content || args.CodeContent || args.ReplacementContent;
  if (status !== "pending") return <section className="cw-request" aria-label="Approval outcome"><div className="cw-receipt">{status === "approved" ? <Check size={16} /> : status === "expired" ? <Clock size={16} /> : <X size={16} />}<strong>{status.charAt(0).toUpperCase() + status.slice(1)}</strong><span>{tool.replace(/_/g, " ")}</span><small>{msg.sender_name || "Agent"}</small></div>{error && <p className="cw-inline-error" role="alert">{error}</p>}</section>;
  return <section className="cw-request" aria-label="Approval request">
    <div className="cw-request-heading"><ShieldCheck size={20} /><div><h3>Permission to {tool.replace(/_/g, " ")}</h3><p>{msg.sender_name || "Your agent"} is waiting for your decision.</p></div>{Number.isFinite(expiry) && now !== null && <span className="cw-muted">{Math.max(0, Math.ceil((expiry - now) / 1000))}s left</span>}</div>
    <div className="cw-request-content">
      {reason && <p>{reason}</p>}
      {target && <pre>{String(target)}</pre>}
      <details><summary className="cw-text-button"><ChevronDown size={13} />Inspect request</summary>
        {typeof args.diff === "string" && args.diff ? <DiffViewer diff={args.diff} path={args.path || args.relative_path} /> : content ? <><p className="cw-muted">Proposed content · a before/after diff is not available</p><pre>{String(content)}</pre></> : null}
        <span className="cw-detail-label">Exact arguments</span><pre>{JSON.stringify(args, null, 2)}</pre>
      </details>
      <label className="cw-detail-label" htmlFor={"feedback-" + id}>Guidance (optional)</label>
      <textarea id={"feedback-" + id} value={feedback} onChange={e => setFeedback(e.target.value)} placeholder="Add context or explain a different approach…" rows={2} disabled={busy || loading} />
      {error && <p className="cw-inline-error" role="alert">{error}</p>}
      <div className="cw-request-actions"><button className="cw-button" disabled={busy || loading} onClick={() => void decide(false)}><X size={14} />Deny</button><button className="cw-button cw-primary" disabled={busy || loading} onClick={() => void decide(true)}>{busy || loading ? <Loader2 size={14} className="cw-spin" /> : <Check size={14} />}{busy || loading ? "Sending decision…" : "Approve once"}</button></div>
    </div>
  </section>;
}
