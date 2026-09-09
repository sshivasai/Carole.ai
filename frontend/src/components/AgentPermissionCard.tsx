"use client";

import React, { useState, useEffect, useMemo } from "react";
import { 
  FileCode, Terminal, Globe, ShieldAlert, Check, X, 
  Loader2, Eye, EyeOff, FileText, Bot, Scale, AlertOctagon,
  Copy, MessageSquareQuote, ChevronDown, ChevronUp, CornerDownLeft
} from "lucide-react";
import type { ChatMessage } from "@/lib/types";
import { DiffViewer } from "./DiffViewer";

interface AgentPermissionCardProps {
  msg: ChatMessage;
  onDecide: (approved: boolean, feedback?: string) => Promise<void>;
  loading?: boolean;
}

export default function AgentPermissionCard({ msg, onDecide, loading = false }: AgentPermissionCardProps) {
  const [showDiff, setShowDiff] = useState(false);
  const [copied, setCopied] = useState(false);
  const [feedbackText, setFeedbackText] = useState("");
  const [showFeedbackInput, setShowFeedbackInput] = useState(false);

  const toolName = msg.pending_approval?.tool_name || msg.tool_name || "";
  const args = msg.pending_approval?.arguments || msg.arguments || {};
  const reason = (msg.pending_approval as any)?.reason || msg.reason || "";
  const agentName = msg.sender_name || "Agent";

  // Derive target summary string
  const targetSummary = useMemo(() => {
    if (["write_file", "edit_file", "read_file", "append_file", "delete_file"].includes(toolName)) {
      const p = args.relative_path || args.path || args.TargetFile || args.file_path || "file";
      const content = args.content || args.CodeContent || "";
      const lineCount = content ? content.split('\n').length : 0;
      return lineCount > 1 ? `${p} (${lineCount} lines)` : p;
    }
    if (["execute_command", "run_command", "bash", "shell"].includes(toolName)) {
      return args.command || args.cmd || args.CommandLine || JSON.stringify(args);
    }
    if (["web_search", "web_fetch", "browser_navigate"].includes(toolName)) {
      return args.query || args.url || JSON.stringify(args);
    }
    return typeof args === "object" ? JSON.stringify(args, null, 2) : String(args);
  }, [toolName, args]);

  // Derive Risk Tier (0, 1, 2, 3)
  const riskTier = useMemo(() => {
    const rawTier = (msg.pending_approval as any)?.risk_tier ?? (msg as any).risk_tier;
    if (typeof rawTier === "number") return rawTier;

    const lowerTarget = targetSummary.toLowerCase();
    const isCriticalFile = [".env", "id_rsa", ".pem", ".ssh", "credentials", "secret", "token"].some(k => lowerTarget.includes(k));
    const isDestructiveCmd = ["rm -rf", "rmdir /s", "drop database", "drop table", "truncate", "format ", "taskkill /f /pid 1", "chmod 777"].some(k => lowerTarget.includes(k));

    if (isCriticalFile || isDestructiveCmd) return 3;
    if (["execute_command", "run_command", "bash", "delete_file"].includes(toolName)) return 2;
    if (["write_file", "edit_file", "append_file", "git_push"].includes(toolName)) return 1;
    return 0;
  }, [toolName, targetSummary, msg]);

  // Derive Human-readable intent title
  const getActionTitle = () => {
    switch (toolName) {
      case "read_file":
        return `${agentName} wants to inspect a file`;
      case "write_file":
      case "edit_file":
      case "append_file":
        return `${agentName} wants to modify workspace code`;
      case "delete_file":
        return `${agentName} requests file deletion`;
      case "execute_command":
      case "run_command":
      case "bash":
        return `${agentName} requests terminal command execution`;
      case "web_search":
      case "web_fetch":
      case "browser_navigate":
        return `${agentName} requests external web access`;
      case "hire_subagent":
      case "spawn_agent":
        return `${agentName} wants to spawn a specialist subagent`;
      default:
        return `${agentName} requests permission for ${toolName || "action"}`;
    }
  };

  const getToolIcon = () => {
    switch (toolName) {
      case "write_file":
      case "edit_file":
      case "read_file":
      case "append_file":
      case "delete_file":
        return <FileCode size={15} color="#38bdf8" />;
      case "execute_command":
      case "run_command":
      case "bash":
        return <Terminal size={15} color="#34d399" />;
      case "web_search":
      case "web_fetch":
      case "browser_navigate":
        return <Globe size={15} color="#f59e0b" />;
      case "hire_subagent":
      case "spawn_agent":
        return <Bot size={15} color="#a78bfa" />;
      default:
        return <ShieldAlert size={15} color="#fbbf24" />;
    }
  };

  const targetContent = args.content || args.CodeContent || "";
  const hasDiffContent = Boolean(targetContent || args.diff || args.Instruction || args.ReplacementContent);
  const diffString = args.diff || (targetContent ? targetContent.split('\n').map((l: string) => `+ ${l}`).join('\n') : "");

  const [localDecision, setLocalDecision] = useState<"approved" | "denied" | "expired" | null>(null);
  const [localFeedback, setLocalFeedback] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [timeLeft, setTimeLeft] = useState<number | null>(null);

  const approvalId = msg.pending_approval?.tx_id || msg.tx_id || msg.id;

  useEffect(() => {
    setLocalDecision(null);
    setLocalFeedback("");
    setErrorMessage(null);
  }, [approvalId]);

  const rawStatus = msg.pending_approval?.status || msg.status || (msg.type?.includes("approved") ? "approved" : msg.type?.includes("denied") ? "denied" : "pending");
  const status = localDecision || (rawStatus === "approved" ? "approved" : rawStatus === "denied" ? "denied" : "pending");

  // Only run countdown if explicit expires_at is provided by server
  const expiresAt = (msg.pending_approval as any)?.expires_at || (msg as any)?.expires_at;

  useEffect(() => {
    if (status !== "pending" || !expiresAt) {
      setTimeLeft(null);
      return;
    }
    
    const expiryTime = typeof expiresAt === "number" ? expiresAt : new Date(expiresAt).getTime();
    if (isNaN(expiryTime)) {
      setTimeLeft(null);
      return;
    }
    
    const updateTime = () => {
      const remaining = Math.max(0, Math.floor((expiryTime - Date.now()) / 1000));
      setTimeLeft(remaining);
      if (remaining === 0) {
        setLocalDecision("expired");
      }
    };
    
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, [expiresAt, status]);

  const handleDecide = async (approved: boolean) => {
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      await onDecide(approved, feedbackText.trim() || undefined);
      setLocalDecision(approved ? "approved" : "denied");
      setLocalFeedback(feedbackText.trim());
    } catch (e: any) {
      if (e?.status === 404 || e?.message?.includes("not found") || e?.message?.includes("expired")) {
        setLocalDecision("expired");
      } else {
        setErrorMessage(e?.message || "Failed to submit decision. Please check connection and try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const copyPayload = () => {
    navigator.clipboard.writeText(targetSummary);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      style={{
        margin: "12px 0",
        borderRadius: "14px",
        background: "linear-gradient(145deg, rgba(20, 20, 38, 0.88), rgba(12, 12, 24, 0.94))",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        border: riskTier === 3 
          ? "1px solid rgba(239, 68, 68, 0.35)" 
          : riskTier === 2 
          ? "1px solid rgba(245, 158, 11, 0.3)" 
          : "1px solid rgba(99, 102, 241, 0.25)",
        boxShadow: riskTier === 3
          ? "0 12px 32px rgba(0, 0, 0, 0.5), 0 0 24px rgba(239, 68, 68, 0.12)"
          : "0 12px 32px rgba(0, 0, 0, 0.45), 0 0 20px rgba(99, 102, 241, 0.08)",
        overflow: "hidden",
        maxWidth: "600px",
        width: "100%",
        fontFamily: "var(--font-sans, system-ui, -apple-system, sans-serif)",
        color: "#f1f5f9",
        transition: "all 0.25s cubic-bezier(0.16, 1, 0.3, 1)"
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 16px",
          borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
          background: "rgba(255, 255, 255, 0.02)"
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: 28,
              height: 28,
              borderRadius: "8px",
              background: "rgba(255, 255, 255, 0.06)",
              border: "1px solid rgba(255, 255, 255, 0.08)"
            }}
          >
            {getToolIcon()}
          </div>
          <span style={{ fontSize: "13px", fontWeight: 700, letterSpacing: "-0.2px", color: "var(--color-ink, #ffffff)" }}>
            {getActionTitle()}
          </span>
        </div>

        {/* Risk Tier Badge */}
        <div>
          {riskTier === 3 && (
            <span className="antigravity-badge-tier3">
              <AlertOctagon size={11} /> Tier 3 • Critical
            </span>
          )}
          {riskTier === 2 && (
            <span className="antigravity-badge-tier2">
              <ShieldAlert size={11} /> Tier 2 • Sensitive
            </span>
          )}
          {riskTier === 1 && (
            <span className="antigravity-badge-tier1">
              <Scale size={11} /> Tier 1 • Audited
            </span>
          )}
          {riskTier === 0 && (
            <span className="antigravity-badge-tier0">
              <Check size={11} /> Tier 0 • Safe
            </span>
          )}
        </div>
      </div>

      {/* Main Body */}
      <div style={{ padding: "14px 16px" }}>
        {/* Monospace Target Preview */}
        <div
          style={{
            background: "rgba(10, 10, 20, 0.75)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "10px",
            padding: "10px 14px",
            fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
            fontSize: "12px",
            color: "#e2e8f0",
            wordBreak: "break-all",
            lineHeight: 1.5,
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: "10px"
          }}
        >
          <span style={{ flex: 1 }}>{targetSummary}</span>
          <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
            <button
              onClick={copyPayload}
              title="Copy arguments"
              style={{
                background: "transparent",
                border: "none",
                color: copied ? "#34d399" : "var(--color-mute, #94a3b8)",
                cursor: "pointer",
                padding: "2px 4px",
                display: "inline-flex",
                alignItems: "center"
              }}
            >
              {copied ? <Check size={13} /> : <Copy size={13} />}
            </button>
            {hasDiffContent && (
              <button
                onClick={() => setShowDiff(s => !s)}
                className="antigravity-pill-btn"
                style={{ height: "24px", padding: "2px 8px" }}
              >
                {showDiff ? <EyeOff size={11} /> : <Eye size={11} />}
                <span>{showDiff ? "Hide Diff" : "View Diff"}</span>
              </button>
            )}
          </div>
        </div>

        {/* View Proposed Diff Container */}
        {showDiff && hasDiffContent && (
          <div style={{ marginTop: "10px", maxHeight: "240px", overflowY: "auto", borderRadius: "8px", border: "1px solid rgba(255, 255, 255, 0.08)" }}>
            <DiffViewer diff={diffString} path={args.relative_path || args.path} maxLinesVisible={30} />
          </div>
        )}

        {/* Judge AI Security Rationale */}
        {reason && (
          <div
            style={{
              marginTop: "12px",
              padding: "8px 12px",
              background: "rgba(99, 102, 241, 0.07)",
              border: "1px solid rgba(99, 102, 241, 0.2)",
              borderRadius: "8px",
              fontSize: "12px",
              color: "#cbd5e1",
              display: "flex",
              alignItems: "flex-start",
              gap: "8px"
            }}
          >
            <ShieldAlert size={14} color="#a5b4fc" style={{ marginTop: "2px", flexShrink: 0 }} />
            <div style={{ flex: 1, lineHeight: 1.45 }}>
              <strong style={{ color: "#e0e7ff" }}>Judge LLM Assessment:</strong> {reason}
            </div>
          </div>
        )}

        {/* Status Pending: Countdown & Action Controls */}
        {status === "pending" ? (
          timeLeft !== null && timeLeft <= 0 ? (
            <div style={{ marginTop: "14px", display: "flex", alignItems: "center", gap: "8px", padding: "10px 14px", background: "rgba(255, 255, 255, 0.03)", borderRadius: "8px", border: "1px solid rgba(255, 255, 255, 0.08)", fontSize: "12px", color: "#94a3b8" }}>
              <Scale size={14} color="#a78bfa" />
              <span>Approval window elapsed • Action settled by Autonomous Judge AI</span>
            </div>
          ) : (
            <div style={{ marginTop: "14px" }}>
              {/* Timer Bar (rendered only if server provided explicit expires_at) */}
              {timeLeft !== null && (
                <>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px", fontSize: "11px", color: "var(--color-mute, #94a3b8)" }}>
                    <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                      <Loader2 size={12} className="animate-spin" style={{ color: "var(--color-primary-soft, #6366f1)" }} />
                      <span>Awaiting human decision</span>
                    </span>
                    <span style={{ fontWeight: 600, fontFamily: "var(--font-mono, monospace)" }}>{timeLeft}s remaining</span>
                  </div>
                  
                  <div style={{ height: "3px", background: "rgba(255,255,255,0.06)", borderRadius: "2px", marginBottom: "14px", overflow: "hidden" }}>
                    <div style={{ height: "100%", background: riskTier === 3 ? "#f87171" : "#6366f1", width: `${(timeLeft / 60) * 100}%`, transition: "width 1s linear" }} />
                  </div>
                </>
              )}

              {/* Feedback toggle & input */}
              <div style={{ marginBottom: "12px" }}>
                <button
                  onClick={() => setShowFeedbackInput(f => !f)}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--color-mute, #94a3b8)",
                    fontSize: "11px",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "4px",
                    cursor: "pointer",
                    padding: 0,
                    marginBottom: showFeedbackInput ? "6px" : 0
                  }}
                >
                  <MessageSquareQuote size={12} />
                  <span>{showFeedbackInput ? "Hide instructions for agent" : "+ Add instructions or feedback..."}</span>
                </button>

                {showFeedbackInput && (
                  <input
                    className="input input-sm"
                    style={{
                      width: "100%",
                      fontSize: "12px",
                      background: "rgba(10, 10, 20, 0.75)",
                      borderColor: "rgba(255, 255, 255, 0.12)",
                      borderRadius: "6px"
                    }}
                    placeholder="Provide guidance if declining or approving with changes..."
                    value={feedbackText}
                    onChange={e => setFeedbackText(e.target.value)}
                  />
                )}
              </div>

              {/* Inline Error Message on Failure */}
              {errorMessage && (
                <div
                  style={{
                    padding: "8px 12px",
                    borderRadius: "6px",
                    background: "rgba(239, 68, 68, 0.12)",
                    border: "1px solid rgba(239, 68, 68, 0.3)",
                    color: "#fca5a5",
                    fontSize: "12px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "8px"
                  }}
                >
                  <span>{errorMessage}</span>
                  <button
                    onClick={() => setErrorMessage(null)}
                    style={{ background: "none", border: "none", color: "#fca5a5", cursor: "pointer", fontSize: "11px", fontWeight: 600 }}
                  >
                    Dismiss
                  </button>
                </div>
              )}

              {/* Action Buttons */}
              <div style={{ display: "flex", gap: "10px" }}>
                <button
                  onClick={() => handleDecide(true)}
                  disabled={loading || isSubmitting}
                  style={{
                    flex: 1.2,
                    height: "38px",
                    borderRadius: "8px",
                    background: "linear-gradient(135deg, #10b981, #059669)",
                    border: "none",
                    color: "#ffffff",
                    fontSize: "12.5px",
                    fontWeight: 600,
                    cursor: (loading || isSubmitting) ? "not-allowed" : "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "6px",
                    boxShadow: "0 4px 14px rgba(16, 185, 129, 0.35)",
                    transition: "all 0.15s ease",
                    opacity: (loading || isSubmitting) ? 0.7 : 1
                  }}
                  title="Approve action"
                >
                  {(loading || isSubmitting) ? <Loader2 size={13} className="animate-spin" /> : <Check size={14} />}
                  <span>Approve once</span>
                </button>

                <button
                  onClick={() => handleDecide(false)}
                  disabled={loading || isSubmitting}
                  style={{
                    flex: 1,
                    height: "38px",
                    borderRadius: "8px",
                    background: "rgba(248, 113, 113, 0.08)",
                    border: "1px solid rgba(248, 113, 113, 0.25)",
                    color: "#fca5a5",
                    fontSize: "12.5px",
                    fontWeight: 600,
                    cursor: (loading || isSubmitting) ? "not-allowed" : "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "6px",
                    transition: "all 0.15s ease",
                    opacity: (loading || isSubmitting) ? 0.7 : 1
                  }}
                  className="hover:bg-[rgba(248,113,113,0.18)]"
                >
                  <X size={14} />
                  <span>Deny</span>
                </button>
              </div>
            </div>
          )
        ) : (
          /* Resolved State */
          <div
            style={{
              marginTop: "12px",
              padding: "10px 14px",
              borderRadius: "8px",
              background: status === "approved" 
                ? "rgba(52, 211, 153, 0.08)" 
                : status === "expired" 
                ? "rgba(148, 163, 184, 0.08)" 
                : "rgba(248, 113, 113, 0.08)",
              border: status === "approved" 
                ? "1px solid rgba(52, 211, 153, 0.25)" 
                : status === "expired"
                ? "1px solid rgba(148, 163, 184, 0.25)"
                : "1px solid rgba(248, 113, 113, 0.25)",
              display: "flex",
              flexDirection: "column",
              gap: "4px"
            }}
          >
            <div style={{ 
              display: "flex", 
              alignItems: "center", 
              gap: "8px", 
              fontSize: "12px", 
              fontWeight: 600, 
              color: status === "approved" ? "#34d399" : status === "expired" ? "var(--color-mute, #94a3b8)" : "#f87171" 
            }}>
              {status === "approved" ? <Check size={14} /> : status === "expired" ? <AlertOctagon size={14} /> : <X size={14} />}
              <span>
                {status === "approved" 
                  ? "Action Approved" 
                  : status === "expired" 
                  ? "Approval Request Expired or No Longer Valid" 
                  : "Action Declined"}
              </span>
            </div>
            {localFeedback && (
              <div style={{ fontSize: "11px", color: "var(--color-mute, #94a3b8)", marginTop: "2px" }}>
                Guidance: &quot;{localFeedback}&quot;
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
