"use client";

import React, { useState, useEffect } from "react";
import { 
  FileCode, Terminal, Globe, ShieldAlert, Check, X, 
  Loader2, Eye, EyeOff, FileText, Bot, Scale 
} from "lucide-react";
import type { ChatMessage } from "@/lib/types";
import { DiffViewer } from "./DiffViewer";

interface AgentPermissionCardProps {
  msg: ChatMessage;
  onDecide: (approved: boolean) => Promise<void>;
  loading?: boolean;
}

export default function AgentPermissionCard({ msg, onDecide, loading = false }: AgentPermissionCardProps) {
  const [showDiff, setShowDiff] = useState(false);
  const toolName = msg.pending_approval?.tool_name || msg.tool_name || "";
  const args = msg.pending_approval?.arguments || msg.arguments || {};
  
  // status resolved below with localDecision
  const agentName = msg.sender_name || "Agent";

  // Derive human-readable permission intent title (e.g. "Nova wants to edit this file")
  const getActionTitle = () => {
    switch (toolName) {
      case "read_file":
        return `${agentName} wants to read this file`;
      case "write_file":
      case "edit_file":
        return `${agentName} wants to edit this file`;
      case "execute_command":
      case "run_command":
      case "bash":
        return `${agentName} wants to run a shell command`;
      case "web_search":
      case "web_fetch":
      case "browser_navigate":
        return `${agentName} wants to access the web`;
      case "hire_subagent":
      case "spawn_agent":
        return `${agentName} wants to spawn a worker subagent`;
      default:
        return `${agentName} wants to run ${toolName || "action"}`;
    }
  };

  // Derive target summary (e.g. "backend/core/agent/react_agent.py (up to 2000 lines)")
  const getTargetSummary = () => {
    if (toolName === "write_file" || toolName === "edit_file" || toolName === "read_file") {
      const p = args.relative_path || args.path || args.TargetFile || "target file";
      const lineCount = (args.content || args.CodeContent || "").split('\n').length;
      return lineCount > 1 ? `${p} (${lineCount} lines)` : p;
    }
    if (toolName === "execute_command" || toolName === "run_command" || toolName === "bash") {
      return args.command || args.cmd || args.CommandLine || JSON.stringify(args);
    }
    if (toolName === "web_search" || toolName === "web_fetch" || toolName === "browser_navigate") {
      return args.query || args.url || JSON.stringify(args);
    }
    return JSON.stringify(args, null, 2);
  };

  const getToolIcon = () => {
    switch (toolName) {
      case "write_file":
      case "edit_file":
      case "read_file":
        return <FileCode size={16} color="#38bdf8" />;
      case "execute_command":
      case "run_command":
      case "bash":
        return <Terminal size={16} color="#34d399" />;
      case "web_search":
      case "web_fetch":
      case "browser_navigate":
        return <Globe size={16} color="#f59e0b" />;
      case "hire_subagent":
      case "spawn_agent":
        return <Bot size={16} color="#a78bfa" />;
      default:
        return <ShieldAlert size={16} color="#fbbf24" />;
    }
  };

  const targetContent = args.content || args.CodeContent || "";
  const hasDiffContent = Boolean(targetContent || args.diff || args.Instruction);
    const diffString = args.diff || (targetContent ? targetContent.split('\n').map((l: string) => `+ ${l}`).join('\n') : "");

  const [localDecision, setLocalDecision] = useState<"approved" | "denied" | null>(null);
  const [timeLeft, setTimeLeft] = useState<number>(60);

  const approvalId = msg.pending_approval?.tx_id || msg.tx_id || msg.id;

  useEffect(() => {
    setLocalDecision(null);
  }, [approvalId]);

  const rawStatus = msg.pending_approval?.status || msg.status || (msg.type?.includes("approved") ? "approved" : msg.type?.includes("denied") ? "denied" : "pending");
  const status = localDecision || (rawStatus === "approved" ? "approved" : rawStatus === "denied" ? "denied" : "pending");

  useEffect(() => {
    if (status !== "pending") return;
    
    let startTime = Date.now();
    if (msg.timestamp) {
      const ts = typeof msg.timestamp === "number" ? msg.timestamp : new Date(msg.timestamp).getTime();
      if (!isNaN(ts)) startTime = ts;
    }
    
    const updateTime = () => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      const remaining = Math.max(0, 60 - elapsed);
      setTimeLeft(remaining);
    };
    
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, [msg.timestamp, status]);

  const handleDecide = async (approved: boolean) => {
    setLocalDecision(approved ? "approved" : "denied");
    try {
      await onDecide(approved);
    } catch (e: any) {
      // If already resolved or 404, keep decision as approved/denied
      if (e?.message?.includes("already resolved") || e?.message?.includes("not found") || e?.status === 404) {
        setLocalDecision(approved ? "approved" : "denied");
      } else {
        setLocalDecision(null);
      }
    }
  };

  return (
    <div
      style={{
        margin: "10px 0",
        borderRadius: "12px",
        background: "#141419",
        border: "1px solid rgba(255, 255, 255, 0.1)",
        overflow: "hidden",
        boxShadow: "0 8px 24px rgba(0, 0, 0, 0.4)",
        maxWidth: "540px",
        width: "100%",
        fontFamily: "var(--font-sans, system-ui, -apple-system, sans-serif)",
        color: "#f1f5f9"
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
          padding: "12px 16px",
          borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
          background: "rgba(255, 255, 255, 0.02)"
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 28,
            height: 28,
            borderRadius: "6px",
            background: "rgba(255, 255, 255, 0.05)"
          }}
        >
          {getToolIcon()}
        </div>
        <span style={{ fontSize: "13.5px", fontWeight: 700, letterSpacing: "-0.2px" }}>
          {getActionTitle()}
        </span>
      </div>

      {/* Target Preview Box */}
      <div style={{ padding: "14px 16px" }}>
        <div
          style={{
            background: "#1e1e24",
            border: "1px solid #2e2e38",
            borderRadius: "8px",
            padding: "10px 14px",
            fontFamily: "var(--font-mono, monospace)",
            fontSize: "12px",
            color: "#e2e8f0",
            wordBreak: "break-all",
            lineHeight: 1.5,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "8px"
          }}
        >
          <span>{getTargetSummary()}</span>
          {hasDiffContent && (
            <button
              onClick={() => setShowDiff(s => !s)}
              className="btn btn-sm"
              style={{
                background: showDiff ? "rgba(167, 139, 250, 0.2)" : "rgba(255, 255, 255, 0.08)",
                border: "1px solid rgba(255, 255, 255, 0.12)",
                color: showDiff ? "#c4b5fd" : "#cbd5e1",
                fontSize: "10.5px",
                padding: "2px 8px",
                height: "24px",
                borderRadius: "5px",
                display: "inline-flex",
                alignItems: "center",
                gap: "4px",
                flexShrink: 0
              }}
            >
              {showDiff ? <EyeOff size={11} /> : <Eye size={11} />}
              {showDiff ? "Hide Changes" : "View Changes"}
            </button>
          )}
        </div>

        {/* View Proposed Diff Container */}
        {showDiff && hasDiffContent && (
          <div style={{ marginTop: "10px", maxHeight: "240px", overflowY: "auto", borderRadius: "6px" }}>
            <DiffViewer diff={diffString} path={args.relative_path || args.path} maxLinesVisible={30} />
          </div>
        )}

        {/* Decision Buttons (Bright Blue Approve vs Dark Slate Deny) */}
        {status === "pending" ? (
          timeLeft <= 0 ? (
            <div style={{ marginTop: "12px", display: "flex", alignItems: "center", gap: "8px", padding: "8px 12px", background: "rgba(255, 255, 255, 0.03)", borderRadius: "8px", border: "1px solid rgba(255, 255, 255, 0.08)", fontSize: "12px", color: "#94a3b8" }}>
              <Scale size={14} color="#a78bfa" />
              <span>Approval window elapsed • Action evaluated by Judge AI / settled</span>
            </div>
          ) : (
          <div style={{ marginTop: "14px" }}>
            <div style={{
              display: "flex", 
              justifyContent: "space-between", 
              alignItems: "flex-start",
              marginBottom: "10px",
              fontSize: "11.5px",
              color: "#94a3b8",
              gap: "12px"
            }}>
              <span style={{ display: "flex", alignItems: "flex-start", gap: "6px", whiteSpace: "pre-line", lineHeight: 1.4, flex: 1 }}>
                <Loader2 size={12} className="animate-spin" style={{ marginTop: "2px", flexShrink: 0 }} />
                <span>{msg.pending_approval?.text || msg.text || "Judge AI evaluating..."}</span>
              </span>
              <span style={{ flexShrink: 0, fontWeight: 600 }}>{timeLeft}s</span>
            </div>
            
            <div style={{ height: "3px", background: "rgba(255,255,255,0.06)", borderRadius: "2px", marginBottom: "12px", overflow: "hidden" }}>
              <div style={{ height: "100%", background: "#a78bfa", width: `${(timeLeft / 60) * 100}%`, transition: "width 1s linear" }} />
            </div>

            <div style={{ display: "flex", gap: "10px" }}>
              <button
                onClick={() => handleDecide(true)}
                disabled={loading}
                style={{
                  flex: 1,
                  height: "36px",
                  borderRadius: "8px",
                  background: "#0078d4",
                  border: "none",
                  color: "#ffffff",
                  fontSize: "12.5px",
                  fontWeight: 600,
                  cursor: loading ? "not-allowed" : "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "6px",
                  boxShadow: "0 2px 8px rgba(0, 120, 212, 0.35)",
                  transition: "background 0.15s, transform 0.1s"
                }}
                className="hover:bg-[#106ebe] active:scale-[0.99]"
              >
                {loading ? <Loader2 size={13} className="animate-spin" /> : <Check size={14} />}
                Approve
              </button>
              <button
                onClick={() => handleDecide(false)}
                disabled={loading}
                style={{
                  flex: 1,
                  height: "36px",
                  borderRadius: "8px",
                  background: "#27272a",
                  border: "1px solid #3f3f46",
                  color: "#e4e4e7",
                  fontSize: "12.5px",
                  fontWeight: 600,
                  cursor: loading ? "not-allowed" : "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "6px",
                  transition: "background 0.15s"
                }}
                className="hover:bg-[#3f3f46] hover:text-white"
              >
                <X size={14} />
                Deny
              </button>
            </div>
          </div>
          )
        ) : (
          <div style={{ marginTop: "10px", display: "flex", alignItems: "center", gap: "6px", fontSize: "11.5px", color: status === "approved" ? "#34d399" : "#f87171" }}>
            {status === "approved" ? <Check size={13} /> : <X size={13} />}
            <span style={{ fontWeight: 600 }}>{status === "approved" ? "Request Approved" : "Request Denied"}</span>
          </div>
        )}
      </div>
    </div>
  );
}

