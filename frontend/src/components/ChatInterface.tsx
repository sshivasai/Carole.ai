"use client";
import React, { useState, useRef, useEffect, useCallback, useMemo } from "react";
import type { ChatMessage, AgentConfig, CompactionEvent } from "@/lib/types";
import {
  Send, Bot, User, Wrench, CheckCircle, XCircle, MessageCircleQuestion,
  Loader2, ChevronDown, ChevronUp, ChevronRight, Search, Trash2,
  RotateCcw, Square, Folder, Info, CheckSquare, Users, Lightbulb, FileCode,
  Terminal, Copy, Check, ThumbsUp, ThumbsDown, Cpu, Scale, Sparkles, MoreHorizontal,
  FileText, Globe, GitBranch, CheckCircle2, AlertTriangle, ShieldCheck, ArrowDown, ShieldAlert
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import Modal from "./Modal";
import AgentAvatar from "./AgentAvatar";
import AgentHoverCard from "./AgentHoverCard";
import AppSpinner from "./AppSpinner";
import { DiffViewer } from "./DiffViewer";
import { McpStatusIndicator } from "./McpStatusIndicator";
import FileChangeCard, { ChangedFileItem } from "./FileChangeCard";
import AgentPermissionCard from "./AgentPermissionCard";
import AgentActivityStream, { ActivityStep } from "./AgentActivityStream";
import ContextUsageGauge from "./ContextUsageGauge";
import InChatPlanCard from "./InChatPlanCard";
import AskUserQuestionCard from "./AskUserQuestionCard";
import BackgroundWork from "@/features/chat/BackgroundWork";
import { useBackgroundWork } from "@/features/chat/useBackgroundWork";
import "./chat-workspace.css";

interface Props {
  messages: ChatMessage[];
  agents: AgentConfig[];
  onSendMessage: (text: string, attachments?: any[]) => { success: boolean; error?: string } | void | Promise<{ success: boolean; error?: string } | void>;
  onDeleteMessage?: (id: string) => void;
  onRollbackMessage?: (id: string) => void;
  onClearChat?: () => void;
  teamId: string | null;
  teamName?: string;
  projectId?: string | null;
  onToggleExplorer?: () => void;
  onOpenFile?: (path: string) => void;
  onOpenDiffFile?: (path: string, originalContent: string) => void;
  lastTokenEvent?: any;
  contextUsage?: any;
  pendingChatInputAppend?: string | null;
  onAppendConsumed?: () => void;
  /** List of compaction checkpoints to render as dividers in the timeline. */
  compactionEvents?: CompactionEvent[];
  /** Called when the user types /compact — triggers manual compaction via API. */
  onCompact?: () => Promise<void>;
}

const AVATAR_COLORS = ["#3b82f6", "#8b5cf6", "#00d992", "#f97316", "#ef4444", "#eab308"];
function avatarColor(name: string) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = name.charCodeAt(i) + ((h << 5) - h);
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length];
}
function fmtTime(ts?: string | number) {
  if (!ts) return "";
  return new Date(typeof ts === "number" ? ts : ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function BackgroundWorkMark({ size = 15 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="3.1" fill="currentColor" />
      <circle cx="5.5" cy="8" r="2.05" fill="currentColor" opacity=".72" />
      <circle cx="17.8" cy="6.2" r="2.05" fill="currentColor" opacity=".72" />
      <circle cx="18.2" cy="17.5" r="2.05" fill="currentColor" opacity=".72" />
      <path d="M7.3 9.2 9.5 10.5M15.3 7.7l-1.6 2.2m2.8 5.8-2.1-1.6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity=".72" />
    </svg>
  );
}

export function getToolMeta(toolName: string) {
  if (!toolName) return { label: "Tool", icon: Wrench, className: "tool-pill" };
  const lower = toolName.toLowerCase();
  if (lower.startsWith("mcp_")) {
    return { label: "MCP", icon: Wrench, className: "tool-pill-mcp" };
  }
  if (["write_file", "edit_file", "read_file", "append_file", "delete_file", "list_directory", "copy_file", "move_file"].some(t => lower.includes(t))) {
    return { label: "File", icon: FileText, className: "tool-pill-file" };
  }
  if (["execute_command", "bash", "shell", "terminal"].some(t => lower.includes(t))) {
    return { label: "Shell", icon: Terminal, className: "tool-pill-bash" };
  }
  if (["hire_subagent", "spawn_agent"].some(t => lower.includes(t))) {
    return { label: "Subagent", icon: Cpu, className: "tool-pill-subagent" };
  }
  if (lower.startsWith("browser_")) {
    return { label: "Browser", icon: Globe, className: "tool-pill-browser" };
  }
  if (lower.startsWith("git_")) {
    return { label: "Git", icon: GitBranch, className: "tool-pill-git" };
  }
  if (["write_scratchpad", "read_scratchpad", "update_memory", "search_learnings"].some(t => lower.includes(t))) {
    return { label: "Memory", icon: Lightbulb, className: "tool-pill-memory" };
  }
  return { label: "Action", icon: Wrench, className: "tool-pill" };
}

function TaskNotificationCard({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);

  const taskIdMatch = text.match(/<task_id>(.*?)<\/task_id>/);
  const agentMatch = text.match(/<agent>(.*?)<\/agent>/);
  const statusMatch = text.match(/<status>(.*?)<\/status>/);
  const resultMatch = text.match(/<result>([\s\S]*?)<\/result>/);

  const taskId = taskIdMatch ? taskIdMatch[1].trim() : "";
  const agentName = agentMatch ? agentMatch[1].trim() : "";
  const status = statusMatch ? statusMatch[1].trim() : "completed";
  const result = resultMatch ? resultMatch[1].trim() : text;

  const isSuccess = status.toLowerCase() === "completed" || status.toLowerCase() === "success";

  const truncateLength = 200;
  const isTruncated = result.length > truncateLength;
  const displayResult = expanded || !isTruncated ? result : result.slice(0, truncateLength) + "...";

  return (
    <div className="task-notif-card" style={{ maxWidth: 640 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 13 }}>{isSuccess ? "✅" : "⚠️"}</span>
          <span className="body-sm-strong" style={{ color: isSuccess ? "#34d399" : "#f87171" }}>
            {agentName.startsWith("Sub-") ? "Subagent" : "Teammate"} Task {isSuccess ? "Completed" : "Report"}
          </span>
          {agentName && (
            <span className="subagent-chip" style={{ fontSize: 10 }}>
              {agentName.startsWith("Sub-") ? "🤖" : "👤"} {agentName}
            </span>
          )}
        </div>
        {taskId && <span className="caption" style={{ fontFamily: "monospace", fontSize: 10, opacity: 0.7 }}>ID: {taskId.slice(0, 8)}</span>}
      </div>
      <div className="markdown-body" style={{ fontSize: 12, lineHeight: 1.5, color: "var(--color-ink)" }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayResult}</ReactMarkdown>
      </div>
      {isTruncated && (
        <div style={{ marginTop: 8, display: "flex", justifyContent: "flex-end" }}>
          <button
            onClick={() => setExpanded(!expanded)}
            className="btn-ghost"
            style={{ fontSize: 11, padding: "2px 8px", minHeight: 24 }}
          >
            {expanded ? "Show Less" : "Expand Report"}
          </button>
        </div>
      )}
    </div>
  );
}

function ApprovalCard({ msg, onFeedback }: { msg: ChatMessage; onFeedback?: (text: string) => void }) {
  const [loading, setLoading] = useState(false);
  const txId = msg.pending_approval?.tx_id || msg.tx_id;

  const decide = async (approved: boolean, feedback?: string) => {
    if (!txId) return;
    setLoading(true);
    try {
      const result = await api.approveToolExecution(txId, approved, feedback);
      const actual = String(result?.action || "").toLowerCase();
      if (actual && actual !== (approved ? "approved" : "denied")) throw new Error("This request was already " + actual + ". Its latest status will appear when the conversation updates.");
      if (feedback && onFeedback) {
        onFeedback(`[Guidance on ${msg.pending_approval?.tool_name || msg.tool_name || "action"}]: ${feedback}`);
      }
    } catch (e: any) {
      console.error("Failed to submit approval decision:", e);
      throw e;
    } finally {
      setLoading(false);
    }
  };

  return <AgentPermissionCard msg={msg} onDecide={decide} loading={loading} />;
}

function AskUserCard({ msg, onAnswerSubmit }: { msg: ChatMessage; onAnswerSubmit?: (text: string) => void }) {
  // Parse questions list if provided
  const questionsList = useMemo(() => {
    if (msg.questions && Array.isArray(msg.questions) && msg.questions.length > 0) {
      return msg.questions;
    }
    const trimmed = (msg.question || msg.text || "").trim();
    if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
      try {
        const parsed = JSON.parse(trimmed);
        if (Array.isArray(parsed) && parsed.length > 0 && parsed[0].question) {
          return parsed;
        }
      } catch { }
    }
    return undefined;
  }, [msg.questions, msg.question, msg.text]);

  // Parse question and options from raw message fields
  const { parsedQuestion, parsedOptions } = useMemo(() => {
    let questionText = msg.question || msg.text || "";
    let optionsList: string[] = (msg as any).options || [];

    const trimmed = questionText.trim();
    if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
      try {
        let parsed: any = null;
        try {
          parsed = JSON.parse(trimmed);
        } catch {
          const jsonified = trimmed
            .replace(/([{,]\s*)([a-zA-Z0-9_]+)\s*:/g, '$1"$2":')
            .replace(/'/g, '"');
          parsed = JSON.parse(jsonified);
        }
        if (parsed) {
          if (parsed.question) questionText = parsed.question;
          else if (parsed.value) questionText = parsed.value;
          if (parsed.options && Array.isArray(parsed.options)) {
            optionsList = parsed.options.map(String);
          }
        }
      } catch (e) {
        console.warn("Failed to parse stringified question object:", e);
      }
    }

    if (questionText.startsWith("❓")) {
      const match = questionText.match(/❓\s*[^\n]+asks:\s*([\s\S]+)/i);
      if (match && match[1]) questionText = match[1].trim();
    }

    return { parsedQuestion: questionText, parsedOptions: optionsList };
  }, [msg.question, msg.text, (msg as any).options]);

  const handleAnswer = async (qId: string, answerText: string) => {
    try {
      await api.answerAgentQuestion(qId, answerText);
      (msg as any).is_answered = true;
      (msg as any).answer = answerText;
      if (onAnswerSubmit) onAnswerSubmit(`Answer to ${msg.sender_name}: ${answerText}`);
    } catch (e) {
      console.error("Failed to submit question answer:", e);
      throw e;
    }
  };

  return (
    <AskUserQuestionCard
      questionId={msg.question_id || msg.id}
      agentName={msg.sender_name || "Agent"}
      question={parsedQuestion}
      options={parsedOptions}
      questions={questionsList}
      answered={Boolean((msg as any).is_answered)}
      chosenAnswer={(msg as any).answer}
      onAnswer={handleAnswer}
      onSkip={async (qId) => {
        try {
          await api.answerAgentQuestion(qId, "Skipped by user");
          (msg as any).is_answered = true;
          (msg as any).answer = "Skipped by user";
        } catch (e) {
          console.error("Failed to skip question:", e);
          throw e;
        }
      }}
    />
  );
}

function BrowserInterventionCard({ msg }: { msg: ChatMessage }) {
  const [solutionText, setSolutionText] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [resolvedStatus, setResolvedStatus] = useState("");

  const reason = (msg as any).reason || msg.text || "CAPTCHA or security challenge detected in the browser.";
  const captchaImage = (msg as any).captcha_image;

  const handleResolve = async (answerText: string) => {
    if (!msg.question_id || submitted) return;
    setLoading(true);
    try {
      await api.resolveBrowserHIL(msg.question_id, answerText);
      setSubmitted(true);
      setResolvedStatus(answerText);
    } catch (e) {
      console.error("Failed to resolve browser intervention:", e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      border: "1px solid var(--color-warning, #f59e0b)",
      borderRadius: "var(--radius-md)",
      padding: "var(--sp-lg)",
      background: "rgba(245, 158, 11, 0.05)",
      backdropFilter: "var(--blur-md)",
      WebkitBackdropFilter: "var(--blur-md)",
      boxShadow: "var(--shadow-clay)",
      display: "flex",
      flexDirection: "column",
      gap: "var(--sp-md)",
      maxWidth: 500,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
        <ShieldAlert size={16} color="var(--color-warning, #f59e0b)" />
        <span className="body-sm-strong" style={{ color: "var(--color-warning, #f59e0b)" }}>
          Browser Takeover Required
        </span>
        <span className="badge badge-warning" style={{ fontSize: 9, marginLeft: "auto" }}>HIL Takeover</span>
      </div>

      <div style={{ fontSize: 13, color: "var(--color-ink)", lineHeight: 1.5 }}>
        <strong>{msg.sender_name}</strong> encountered a roadblock:
        <p style={{ margin: "4px 0 0 0", color: "var(--color-mute)" }}>{reason}</p>
      </div>

      {captchaImage && (
        <div style={{ border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-sm)", overflow: "hidden", background: "#000", textAlign: "center" }}>
          <img
            src={captchaImage.startsWith("data:") ? captchaImage : `data:image/jpeg;base64,${captchaImage}`}
            alt="CAPTCHA Challenge"
            style={{ maxWidth: "100%", maxHeight: 200, objectFit: "contain" }}
          />
        </div>
      )}

      {submitted ? (
        <span className="pill pill-live" style={{ alignSelf: "flex-start", background: "rgba(34, 197, 94, 0.15)", color: "#4ade80" }}>
          Takeover resolved: {resolvedStatus} ✓
        </span>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-sm)" }}>
          {/* Solution 1: Direct text input for CAPTCHA / OTP code */}
          <div style={{ display: "flex", gap: "var(--sp-sm)" }}>
            <input
              className="input input-sm"
              style={{ flex: 1 }}
              placeholder="Enter CAPTCHA text or 2FA code..."
              value={solutionText}
              onChange={e => setSolutionText(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") handleResolve(solutionText); }}
              autoFocus
            />
            <button
              className="btn btn-primary btn-sm"
              onClick={() => handleResolve(solutionText)}
              disabled={loading || !solutionText.trim()}
            >
              {loading ? <Loader2 size={12} className="animate-spin" /> : "Submit"}
            </button>
          </div>

          {/* Quick Action Button for on-screen manual completion */}
          <div style={{ display: "flex", gap: "var(--sp-sm)", flexWrap: "wrap" }}>
            <button
              className="btn btn-outline btn-sm"
              style={{ flex: 1, borderColor: "var(--color-warning, #f59e0b)", color: "var(--color-warning, #f59e0b)" }}
              onClick={() => handleResolve("Solved on screen by user")}
              disabled={loading}
            >
              <CheckCircle2 size={12} /> I&apos;ve Solved It On Screen
            </button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => handleResolve("Cancelled by user")}
              disabled={loading}
            >
              Skip / Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ToolRow({ msg }: { msg: ChatMessage }) {
  const [open, setOpen] = useState(false);
  const isEnd = msg.type === "tool_end";
  const obs = msg.text || "";
  const toolMeta = getToolMeta(msg.tool_name || "");
  const ToolIcon = toolMeta.icon;

  return (
    <div style={{ paddingLeft: 36, display: "flex", flexDirection: "column", gap: 2, margin: "2px 0" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--color-mute)", fontSize: 11 }}>
        <span className={toolMeta.className} style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
          <ToolIcon size={10} /> {toolMeta.label}
        </span>
        <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11, color: "var(--color-ink)", fontWeight: 500 }}>
          {msg.tool_name}
        </span>
        <span style={{ fontSize: 10, color: isEnd ? "var(--color-success)" : "var(--color-warning)", display: "flex", alignItems: "center", gap: 3 }}>
          {isEnd ? <Check size={10} /> : <AppSpinner size={10} />}
          {isEnd ? "completed" : "running…"}
        </span>
        {isEnd && obs && (
          <button onClick={() => setOpen(o => !o)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--color-mute)", display: "flex", padding: 0 }}>
            {open ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          </button>
        )}
      </div>
      {isEnd && obs && open && (
        <pre style={{ fontSize: 10, background: "var(--color-canvas-soft)", border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-xs)", padding: "var(--sp-sm) var(--sp-md)", overflow: "auto", maxHeight: 200, color: "var(--color-body)", marginLeft: 17 }}>
          {obs}
        </pre>
      )}
    </div>
  );
}

function TypingIndicator() {
  return (
    <span className="typing-indicator" title="Agent is working...">
      <span className="typing-dot" style={{ animationDelay: "0ms" }} />
      <span className="typing-dot" style={{ animationDelay: "200ms" }} />
      <span className="typing-dot" style={{ animationDelay: "400ms" }} />
    </span>
  );
}

function getToolSummaryText(toolName: string, args: any): string {
  if (!args) return "";
  if (typeof args === "string") {
    try {
      args = JSON.parse(args);
    } catch {
      return args.slice(0, 60);
    }
  }
  if (typeof args !== "object") return String(args);

  const lower = toolName.toLowerCase();
  if (lower.includes("search")) {
    return args.query ? `"${args.query}"` : "";
  }
  if (lower.includes("navigate") || lower.includes("open") || lower.includes("url")) {
    return args.url || args.link || "";
  }
  if (lower.includes("file") || lower.includes("read") || lower.includes("write") || lower.includes("edit") || lower.includes("append")) {
    return args.path || args.relative_path || args.file_path || args.TargetFile || "";
  }
  if (lower.includes("command") || lower.includes("bash") || lower.includes("terminal") || lower.includes("shell") || lower.includes("exec")) {
    return args.command || args.cmd || args.CommandLine || "";
  }
  if (lower.includes("agent") || lower.includes("spawn") || lower.includes("subagent")) {
    return args.name || args.role || args.task || "";
  }
  if (args.query) return `"${args.query}"`;
  if (args.path) return String(args.path);
  if (args.command) return String(args.command);

  const entries = Object.entries(args);
  if (entries.length > 0) {
    const [k, v] = entries[0];
    const valStr = typeof v === "object" ? JSON.stringify(v) : String(v);
    return `${k}: ${valStr.length > 35 ? valStr.slice(0, 35) + "…" : valStr}`;
  }
  return "";
}

const VALID_TOOL_NAMES = new Set([
  "write_file", "read_file", "edit_file", "list_dir", "view_file_outline",
  "execute_command", "git_status", "git_diff", "git_commit", "git_log",
  "web_search", "web_fetch", "browser_navigate", "browser_click",
  "write_scratchpad", "read_scratchpad", "hire_subagent", "spawn_agent",
  "inspect_code_definition", "find_references", "fetch_web_page", "get_tools"
]);

function splitThoughtsAndObservations(rawText: string): Array<{ type: "thought"; text: string }> {
  if (!rawText || !rawText.trim()) return [];
  const obsRegex = /(?:\[OBSERVATION\][\s\S]*?\[\/OBSERVATION\]|💭\s*\*\*(?:Observation|System Note):\*\*[\s\S]*?(?=\n\n💭|\n\n🛠️|$))/g;
  const parts: Array<{ type: "thought"; text: string }> = [];
  let lastIdx = 0;
  let m: RegExpExecArray | null;
  while ((m = obsRegex.exec(rawText)) !== null) {
    if (m.index > lastIdx) {
      const leading = rawText.slice(lastIdx, m.index).trim();
      if (leading) parts.push({ type: "thought", text: leading });
    }
    const obsText = m[0].trim();
    if (obsText) parts.push({ type: "thought", text: obsText });
    lastIdx = m.index + m[0].length;
  }
  if (lastIdx < rawText.length) {
    const trailing = rawText.slice(lastIdx).trim();
    if (trailing) parts.push({ type: "thought", text: trailing });
  }
  return parts.length > 0 ? parts : [{ type: "thought", text: rawText.trim() }];
}

function parseReasoningIntoSections(raw: string): Array<{
  type: "thought" | "tool";
  text?: string;
  toolName?: string;
  argsJson?: string;
  argsObj?: any;
  result?: string;
  isError?: boolean;
  pid?: number | null;
}> {
  if (!raw || !raw.trim()) return [];

  const sections: Array<{
    type: "thought" | "tool";
    text?: string;
    toolName?: string;
    argsJson?: string;
    argsObj?: any;
    result?: string;
    isError?: boolean;
    pid?: number | null;
  }> = [];

  // Match only genuine tool headers formatted by backend: 🛠️ **tool_name**
  const toolSplitRegex = /(?:^|\n)🛠️\s*(?:\*\*)?([a-zA-Z0-9_]+)(?:\*\*)?/g;
  const matches: { index: number; toolName: string; headerLength: number }[] = [];
  let m: RegExpExecArray | null;

  while ((m = toolSplitRegex.exec(raw)) !== null) {
    const tName = m[1].toLowerCase();
    // Only accept genuine tool names or snake_case identifiers with underscore
    if (VALID_TOOL_NAMES.has(tName) || (tName.includes("_") && !["def", "class", "function", "return"].includes(tName))) {
      matches.push({ index: m.index, toolName: m[1], headerLength: m[0].length });
    }
  }

  if (matches.length === 0) {
    return splitThoughtsAndObservations(raw);
  }

  if (matches[0].index > 0) {
    const pre = raw.slice(0, matches[0].index).trim();
    if (pre) {
      sections.push(...splitThoughtsAndObservations(pre));
    }
  }

  for (let i = 0; i < matches.length; i++) {
    const current = matches[i];
    const nextIndex = i + 1 < matches.length ? matches[i + 1].index : raw.length;
    const chunk = raw.slice(current.index + current.headerLength, nextIndex).trim();

    // Extract args from ```json ... ``` or ``` ... ```
    const argsMatch = chunk.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
    const argsRaw = argsMatch ? argsMatch[1].trim() : "";
    let argsObj = null;
    if (argsRaw) {
      try { argsObj = JSON.parse(argsRaw); } catch { /* ignore */ }
    }

    // Extract result from 📄 Result:
    let result = "";
    let afterResultText = "";
    const resultHeaderMatch = chunk.match(/📄\s*(?:\*\*)?Result:(?:\*\*)?/);
    if (resultHeaderMatch && resultHeaderMatch.index !== undefined) {
      const restAfterResult = chunk.slice(resultHeaderMatch.index + resultHeaderMatch[0].length);
      const codeResultMatch = restAfterResult.match(/```(?:[a-zA-Z0-9_\-]*)?\s*([\s\S]*?)\s*```/);
      if (codeResultMatch) {
        result = codeResultMatch[1].trim();
        afterResultText = restAfterResult.slice(codeResultMatch.index! + codeResultMatch[0].length).trim();
      } else {
        result = restAfterResult.trim();
      }
    }

    const isError = /error|failed|exception|not implemented/i.test(result);

    let pid: number | null = null;
    const pidMatch = result.match(/launched in background with PID (\d+)/i);
    if (pidMatch) {
      pid = parseInt(pidMatch[1], 10);
    }

    sections.push({
      type: "tool",
      toolName: current.toolName,
      argsJson: argsRaw,
      argsObj,
      result,
      isError,
      pid
    });

    if (afterResultText) {
      sections.push(...splitThoughtsAndObservations(afterResultText));
    }
  }

  return sections;
}

function extractFileChanges(_reasoning: string, msg: ChatMessage): ChangedFileItem[] {
  // Proposed tool arguments are not evidence that a file was changed.
  if (!msg.path || (!msg.diff && msg.type !== "file_change")) return [];
  return [{ path: msg.path, diff: msg.diff, content: msg.arguments?.content, action: msg.action || "modified" }];
}

function TraceToolCard({ toolName, argsObj, argsRaw, result, isError, pid }: {
  toolName: string; argsObj?: any; argsRaw?: string; result?: string; isError?: boolean;
  pid?: number | null; defaultOpen?: boolean; agentName?: string; timestamp?: string | number;
}) {
  return <AgentActivityStream steps={[{ type: "tool", toolName, argsObj, argsJson: argsRaw, result, isError, pid }]} />;
}

function StopAgentButton({ agentId }: { agentId: string }) {
  const [status, setStatus] = useState<"idle" | "sending" | "requested">("idle");
  const [error, setError] = useState("");
  const lock = useRef(false);
  return <div className="cw-stop-control">
    <button className="cw-text-button" disabled={status !== "idle"} onClick={async () => {
      if (lock.current) return;
      lock.current = true; setStatus("sending"); setError("");
      try { await api.stopAgent(agentId); setStatus("requested"); }
      catch (e) { setStatus("idle"); setError(e instanceof Error ? e.message : "Could not stop this agent."); }
      finally { lock.current = false; }
    }}>{status === "sending" ? <Loader2 size={13} className="cw-spin" /> : <Square size={13} />}{status === "idle" ? "Stop agent" : status === "sending" ? "Requesting stop…" : "Stop requested"}</button>
    {error && <p role="alert" className="cw-inline-error">{error}</p>}
  </div>;
}

function ThoughtsPanel({ reasoning, isStreaming, components }: { reasoning?: string; isStreaming?: boolean; components?: any }) {
  const [elapsedSecs, setElapsedSecs] = useState(0);

  const sections = useMemo(() => parseReasoningIntoSections(reasoning || ""), [reasoning]);

  useEffect(() => {
    if (isStreaming) {
      const start = Date.now();
      const interval = setInterval(() => {
        setElapsedSecs(Math.max(1, Math.floor((Date.now() - start) / 1000)));
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [isStreaming]);

  if (!reasoning || !reasoning.trim()) return null;

  const activitySteps: ActivityStep[] = sections.map((sec, idx) => ({
    id: `step-${idx}`,
    type: sec.type,
    toolName: sec.toolName,
    argsJson: sec.argsJson,
    argsObj: sec.argsObj,
    result: sec.result,
    isError: sec.isError,
    text: sec.text,
    pid: sec.pid
  }));

  return (
    <div style={{ marginTop: "6px" }}>
      <AgentActivityStream
        steps={activitySteps}
        isStreaming={isStreaming}
        elapsedSecs={elapsedSecs}
      />
    </div>
  );
}

// ── Compaction Divider ───────────────────────────────────────────────────────
// Rendered in the message list timeline at every compaction checkpoint.
// Shows how many messages were compressed and the trigger type (auto/manual/emergency).
function CompactionDivider({ event }: { event: CompactionEvent }) {
  const [expanded, setExpanded] = React.useState(false);

  const labelMap: Record<string, string> = {
    auto: "Auto-Compacted",
    manual: "Manually Compacted",
    emergency: "Emergency Compacted",
  };
  const colorMap: Record<string, string> = {
    auto: "var(--color-primary)",
    manual: "#00d992",
    emergency: "#f97316",
  };
  const label = labelMap[event.triggered_by] ?? "Compacted";
  const color = colorMap[event.triggered_by] ?? "var(--color-primary)";
  const ts = event.created_at ? new Date(event.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, margin: "8px 0" }}>
      {/* Divider line with badge */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ flex: 1, height: 1, background: `linear-gradient(to right, transparent, ${color}40, transparent)` }} />
        <button
          onClick={() => setExpanded(e => !e)}
          title={expanded ? "Hide summary" : "Show compaction summary"}
          style={{
            display: "flex", alignItems: "center", gap: 6,
            padding: "3px 12px",
            borderRadius: 20,
            border: `1px solid ${color}55`,
            background: `${color}12`,
            color,
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: "0.03em",
            cursor: "pointer",
            whiteSpace: "nowrap",
            transition: "background 0.15s",
          }}
        >
          <Sparkles size={11} />
          {label}
          {event.message_count_before != null && (
            <span style={{ opacity: 0.7, fontWeight: 400 }}>· {event.message_count_before} msgs</span>
          )}
          {ts && <span style={{ opacity: 0.5, fontWeight: 400 }}>· {ts}</span>}
          {event.summary_preview && (
            expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />
          )}
        </button>
        <div style={{ flex: 1, height: 1, background: `linear-gradient(to left, transparent, ${color}40, transparent)` }} />
      </div>

      {/* Collapsible summary preview */}
      {expanded && event.summary_preview && (
        <div style={{
          margin: "2px 12px",
          padding: "10px 14px",
          borderRadius: 8,
          border: `1px solid ${color}30`,
          background: `${color}08`,
          fontSize: 12,
          color: "var(--color-mute)",
          lineHeight: 1.6,
          whiteSpace: "pre-wrap",
          maxHeight: 220,
          overflowY: "auto",
        }}>
          <span style={{ display: "block", fontWeight: 600, color, marginBottom: 4, fontSize: 11 }}>
            Compaction Summary
          </span>
          {event.summary_preview}
        </div>
      )}
    </div>
  );
}

export default function ChatInterface({
  messages,
  agents,
  onSendMessage,
  onDeleteMessage,
  onRollbackMessage,
  onClearChat,
  teamId,
  teamName,
  projectId,
  onToggleExplorer,
  onOpenFile,
  onOpenDiffFile,
  lastTokenEvent,
  contextUsage,
  pendingChatInputAppend,
  onAppendConsumed,
  compactionEvents = [],
  onCompact,
}: Props) {
  const { user } = useAuth();
  const [inputText, setInputText] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState(false);
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [showBackground, setShowBackground] = useState(false);
  const backgroundWork = useBackgroundWork(teamId);
  const runningJobs = backgroundWork.error ? [] : backgroundWork.jobs.filter(job => job.status === "running");
  const [sendError, setSendError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const sendLock = useRef(false);
  const activeTeamRef = useRef(teamId);
  activeTeamRef.current = teamId;
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (pendingChatInputAppend) {
      setInputText(prev => {
        const textToAppend = pendingChatInputAppend;
        const separator = prev.endsWith("\n") || prev === "" ? "" : "\n";
        return prev + separator + textToAppend;
      });
      setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.focus();
        }
      }, 50);
      onAppendConsumed?.();
    }
  }, [pendingChatInputAppend, onAppendConsumed]);

  // Grow only as needed, preserving room for the conversation.
  useEffect(() => {
    const textarea = inputRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(Math.max(textarea.scrollHeight, 40), 160)}px`;
    }
  }, [inputText]);

  // Wave 4.1 — Load older messages
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [hasOlderMessages, setHasOlderMessages] = useState(true);
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);
  const [feedbackState, setFeedbackState] = useState<Record<string, "up" | "down">>({});

  const { childMessagesByParent, orphanIntermediateIds } = useMemo(() => {
    const groups: Record<string, ChatMessage[]> = {};
    const orphanIds = new Set<string>();

    // 1. Explicit parent_message attachments
    for (const msg of messages) {
      const parentAttachment = msg.attachments?.find((a: any) => a.type === "parent_message");
      if (parentAttachment?.id) {
        const pid = parentAttachment.id;
        if (!groups[pid]) groups[pid] = [];
        groups[pid].push(msg);
      }
    }

    // 2. Link orphan intermediate messages (is_intermediate / tool_trace / agent_question) without explicit parentAttachment
    // to the assistant message in the same conversation turn
    let pendingIntermediates: ChatMessage[] = [];
    for (let i = 0; i < messages.length; i++) {
      const msg = messages[i];
      const isExplicitChild = msg.attachments?.some((a: any) => a.type === "parent_message");
      const isTurnActivity = msg.is_intermediate === true ||
        msg.type === "tool_trace" ||
        msg.type === "agent_question" ||
        msg.type === "ask_user" ||
        msg.type === "approval_request" ||
        msg.type === "browser_intervention" ||
        (msg.sender_id === "system" && (msg.text?.startsWith("Approval Event:") || msg.text?.includes("ACTION")));

      const isAssistantFinal = !isTurnActivity &&
        msg.sender_id !== "human" &&
        msg.sender_id !== "system" &&
        msg.sender_id !== user?.id &&
        msg.role !== "user" &&
        msg.type !== "file_change" &&
        msg.type !== "llm_error";

      if (isTurnActivity && !isExplicitChild) {
        pendingIntermediates.push(msg);
      } else if (isAssistantFinal) {
        // Assistant message in this turn
        if (pendingIntermediates.length > 0) {
          if (!groups[msg.id]) groups[msg.id] = [];
          for (const orphan of pendingIntermediates) {
            groups[msg.id].push(orphan);
            orphanIds.add(orphan.id);
          }
          pendingIntermediates = [];
        }
      } else if (msg.sender_id === "human" || msg.role === "user" || msg.sender_id === user?.id) {
        pendingIntermediates = [];
      }
    }

    return { childMessagesByParent: groups, orphanIntermediateIds: orphanIds };
  }, [messages, user?.id]);

  const markdownComponents = useMemo(() => ({
    a: ({ href, children, ...props }: any) => {
      // Intercept @file:path chips and relative file links to open the file in the
      // explorer instead of navigating away.
      if (href && onOpenFile) {
        if (href.startsWith("file:")) {
          const path = href.slice("file:".length);
          return (
            <a
              {...props}
              href="#"
              onClick={(e) => { e.preventDefault(); onOpenFile(path); }}
              style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "1px 7px", margin: "0 2px", background: "var(--color-primary-glow-sm)", border: "1px solid var(--color-primary-soft)", borderRadius: 4, color: "var(--color-primary)", textDecoration: "none", fontFamily: "var(--font-mono)", fontSize: "0.9em", cursor: "pointer" }}
              title={`Open ${path}`}
            >
              {children}
            </a>
          );
        }

        // Intercept relative links (no scheme) as file paths
        if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(href) && !href.startsWith("#")) {
          return (
            <a
              {...props}
              href="#"
              onClick={(e) => { e.preventDefault(); onOpenFile(href); }}
              title={`Open ${href}`}
            >
              {children}
            </a>
          );
        }
      }
      return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>;
    },
    table: ({ ...props }: any) => <div style={{ overflowX: 'auto', margin: 'var(--sp-md) 0' }}><table style={{ borderCollapse: 'collapse', width: '100%' }} {...props} /></div>,
    th: ({ ...props }: any) => <th style={{ border: '1px solid var(--color-hairline)', padding: 'var(--sp-sm)', background: 'var(--color-canvas-raised)' }} {...props} />,
    td: ({ ...props }: any) => <td style={{ border: '1px solid var(--color-hairline)', padding: 'var(--sp-sm)' }} {...props} />,
    code: ({ className, children, ...props }: any) => {
      const match = /language-(\w+)/.exec(className || '')
      const inline = !match;
      return inline ? (
        <code className="code-inline" {...props}>{children}</code>
      ) : (
        <pre className="code-block" style={{ marginTop: 8, marginBottom: 8 }}>
          <code className={className} {...props}>{children}</code>
        </pre>
      )
    },
    del: ({ children, ...props }: any) => searchMode && searchQuery.trim() ? <mark style={{ backgroundColor: "var(--color-primary-glow)", color: "var(--color-primary)", borderRadius: 2, padding: "0 2px" }} {...props}>{children}</mark> : <del {...props}>{children}</del>
  }), [onOpenFile, searchMode, searchQuery]);


  // Attachments state
  const [attachments, setAttachments] = useState<any[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Mention state — @ triggers a combined picker of agents + project files.
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionQuery, setMentionQuery] = useState("");
  const [mentionIndex, setMentionIndex] = useState(0);

  // File tree for @file mentions (cached per project).
  const [fileTree, setFileTree] = useState<string[]>([]);
  const [fileTreeLoadedFor, setFileTreeLoadedFor] = useState<string | null>(null);

  // Intermediate trace expansion state
  const [expandedTraces, setExpandedTraces] = useState<Set<string>>(new Set());

  // Smart manual scroll tracking (allows free scrolling during streaming)
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);
  const isUserScrolledUpRef = useRef(false);

  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    // If distance from bottom is greater than 100px, user has scrolled up
    const isUp = scrollHeight - (scrollTop + clientHeight) > 100;
    isUserScrolledUpRef.current = isUp;
    setIsUserScrolledUp(isUp);
  }, []);

  const scrollToBottom = useCallback((smooth = true) => {
    isUserScrolledUpRef.current = false;
    setIsUserScrolledUp(false);
    if (scrollRef.current) {
      if (smooth) {
        scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
      } else {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    }
  }, []);

  const pendingActions = useMemo(() => {
    return messages.filter(m => {
      const isPendingApproval = Boolean(
        (m.pending_approval && m.pending_approval.status !== "approved" && m.pending_approval.status !== "denied" && m.pending_approval.status !== "expired" && m.pending_approval.status !== "cancelled" && m.pending_approval.status !== "superseded") ||
        (m.type === "approval_request" && m.status !== "approved" && m.status !== "denied" && m.status !== "expired" && m.status !== "cancelled" && m.status !== "superseded")
      );
      const isPendingQuestion = Boolean((m.type === "ask_user" || m.type === "agent_question") && !(m as any).is_answered);
      return isPendingApproval || isPendingQuestion;
    });
  }, [messages]);

  useEffect(() => {
    // Only auto-scroll to bottom if the user is not reading scrolled-up history
    if (!isUserScrolledUpRef.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Reset scroll on room/project change
  useEffect(() => {
    scrollToBottom(false);
  }, [teamId, projectId, scrollToBottom]);

  const handleDirectMention = useCallback((name: string) => {
    setInputText(prev => {
      const mention = `@${name} `;
      if (prev.includes(mention)) return prev;
      return prev ? `${prev} ${mention}` : mention;
    });
    if (inputRef.current) {
      inputRef.current.focus();
    }
  }, []);

  const getAgentInfo = useCallback((id?: string, name?: string, role?: string): AgentConfig => {
    const found = agents.find(a => (id && a.id === id) || (name && a.name.toLowerCase() === name.toLowerCase()));
    if (found) return found;
    return {
      id: id || "",
      name: name || "Agent",
      role: role || "Active Agent",
      model: "openrouter/free",
    };
  }, [agents]);

  // Lazy-load the project file tree once (and when the project changes).
  const ensureFileTree = useCallback(async () => {
    if (!projectId) return;
    if (fileTreeLoadedFor === projectId) return;
    try {
      const res = await api.listFileTree(projectId, teamId ?? undefined);
      setFileTree(res.files || []);
    } catch (e) {
      console.warn("Failed to load file tree for mentions", e);
      setFileTree([]);
    } finally {
      setFileTreeLoadedFor(projectId);
    }
  }, [projectId, teamId, fileTreeLoadedFor]);

  // Build the combined, query-filtered mention list. Agents first, then files
  // (files capped to keep the dropdown snappy). Each item knows how to insert
  // itself.
  type MentionItem =
    | { kind: "agent"; name: string; role?: string; id: string }
    | { kind: "file"; path: string };

  const mentionItems: MentionItem[] = useMemo(() => {
    const q = mentionQuery.toLowerCase();
    const agentItems: MentionItem[] = agents
      .filter(a => a.name.toLowerCase().includes(q))
      .map(a => ({ kind: "agent" as const, name: a.name, role: a.role, id: a.id }));
    const fileItems: MentionItem[] = fileTree
      .filter(p => {
        if (!q) return true;
        const base = p.split("/").pop()!.toLowerCase();
        return base.includes(q) || p.toLowerCase().includes(q);
      })
      // Prefer basename matches, then alphabetical.
      .sort((a, b) => {
        const ba = a.split("/").pop()!, bb = b.split("/").pop()!;
        const ma = ba.toLowerCase().includes(q) ? 0 : 1;
        const mb = bb.toLowerCase().includes(q) ? 0 : 1;
        if (ma !== mb) return ma - mb;
        return a.localeCompare(b);
      })
      .slice(0, 12)
      .map(p => ({ kind: "file" as const, path: p }));
    return [...agentItems, ...fileItems];
  }, [agents, fileTree, mentionQuery]);

  const insertMention = (item: MentionItem) => {
    const sel = inputRef.current?.selectionStart ?? inputText.length;
    const textBefore = inputText.slice(0, sel);
    const atIndex = textBefore.lastIndexOf("@");
    if (atIndex === -1) { setMentionOpen(false); return; }
    const token = item.kind === "agent" ? `@${item.name} ` : `@file:${item.path} `;
    const newText = inputText.slice(0, atIndex) + token + inputText.slice(sel);
    setInputText(newText);
    setMentionOpen(false);
    setTimeout(() => {
      inputRef.current?.focus();
      const pos = atIndex + token.length;
      inputRef.current?.setSelectionRange(pos, pos);
    }, 10);
  };

  // ── Slash Commands ──
  interface SlashCommandItem {
    command: string;
    description: string;
  }
  const AVAILABLE_COMMANDS: SlashCommandItem[] = useMemo(() => [
    { command: "/goal", description: "Autonomous long-running execution mode — runs until objective is fully achieved" },
    { command: "/plan", description: "Planning Mode — forces agent to generate an implementation plan before executing" },
    { command: "/learn", description: "Persistent Memory — commits rules, user corrections, or preferences to long-term memory" },
    { command: "/schedule", description: "Scheduled Task — schedule a recurring cron prompt or timer for the agent" },
    { command: "/compact", description: "Context Compaction — compress older conversation turns into summaries" },
  ], []);

  const [commandOpen, setCommandOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");
  const [commandIndex, setCommandIndex] = useState(0);

  const commandItems = useMemo(() => {
    const q = commandQuery.toLowerCase();
    const staticCommands = AVAILABLE_COMMANDS.filter(c =>
      c.command.toLowerCase().includes(q) ||
      c.command.toLowerCase().replace("/", "").includes(q)
    );

    // Dynamic private mentions: /@agentName
    const privateMentionCommands: SlashCommandItem[] = agents
      .filter(a => {
        // If they typed something like "@" or "@co", match agents
        const mentionMatch = q.startsWith("@") ? q.slice(1) : q;
        return a.name.toLowerCase().includes(mentionMatch);
      })
      .map(a => ({
        command: `/@${a.name}`,
        description: `Send a private message to ${a.name}`
      }));

    return [...staticCommands, ...privateMentionCommands];
  }, [commandQuery, AVAILABLE_COMMANDS, agents]);

  const insertCommand = (item: SlashCommandItem) => {
    const sel = inputRef.current?.selectionStart ?? inputText.length;
    const textBefore = inputText.slice(0, sel);
    const slashIndex = textBefore.lastIndexOf("/");
    if (slashIndex === -1) { setCommandOpen(false); return; }

    // Ensure the slash was at the start of line or input
    const isStartOfLine = slashIndex === 0 || textBefore[slashIndex - 1] === "\n";
    if (!isStartOfLine) { setCommandOpen(false); return; }

    const newText = inputText.slice(0, slashIndex) + item.command + " " + inputText.slice(sel);
    setInputText(newText);
    setCommandOpen(false);
    setTimeout(() => {
      inputRef.current?.focus();
      const pos = slashIndex + item.command.length + 1;
      inputRef.current?.setSelectionRange(pos, pos);
    }, 10);
  };

  const handleSend = useCallback(async () => {
    if (!teamId || sendLock.current || isSending || uploading || (!inputText.trim() && attachments.length === 0)) return;

    let textToSend = inputText.trim();

    // ── /compact slash command ──
    // Intercept before sending to backend. Triggers manual compaction via API.
    if (textToSend === "/compact") {
      if (!onCompact) { setSendError("Compaction is unavailable for this conversation."); return; }
      sendLock.current = true; setIsSending(true);
      try {
        await onCompact();
        if (activeTeamRef.current === teamId) setInputText(current => current === inputText ? "" : current);
      } catch (e) { setSendError(e instanceof Error ? e.message : "Could not compact the conversation."); }
      finally { sendLock.current = false; setIsSending(false); }
      return;
    }

    // ── Slash Command Directive Augmentations ──
    if (textToSend.startsWith("/goal ")) {
      const rest = textToSend.slice(6).trim();
      textToSend = `[AUTONOMOUS GOAL MODE: Execute relentlessly until this high-level objective is fully achieved. Delegate subtasks, perform thorough verifications, and continue autonomously until complete.]\n\n${rest}`;
    } else if (textToSend.startsWith("/plan ")) {
      const rest = textToSend.slice(6).trim();
      textToSend = `[PLANNING MODE: Formulate a detailed step-by-step implementation plan before making any code modifications. Specify tasks, dependencies, risks, and verification steps.]\n\n${rest}`;
    } else if (textToSend.startsWith("/learn ")) {
      const rest = textToSend.slice(7).trim();
      textToSend = `[PERSISTENT LEARNING: Commit the following rule, preference, or architectural constraint to your long-term memory so all agents follow it in future tasks.]\n\n${rest}`;
    } else if (textToSend.startsWith("/schedule ")) {
      const rest = textToSend.slice(10).trim();
      textToSend = `[SCHEDULED TASK: Set up or register a recurring schedule/cron for the following task.]\n\n${rest}`;
    }

    // Extract @file:path references and pass them as structured file_ref
    // attachments so the backend injects their contents into agent context
    const fileRefRegex = /@file:(\S+)/g;
    const seen = new Set<string>();
    const fileRefs: any[] = [];
    let m: RegExpExecArray | null;
    while ((m = fileRefRegex.exec(inputText)) !== null) {
      const p = m[1].replace(/[),.;]+$/, ""); // strip trailing punctuation
      if (!seen.has(p)) { seen.add(p); fileRefs.push({ type: "file_ref", path: p }); }
    }

    sendLock.current = true;
    setIsSending(true);
    setSendError(null);
    try {
      const res = await onSendMessage(textToSend, [...attachments, ...fileRefs]);
      if (activeTeamRef.current !== teamId) return;
      if (res && typeof res === "object" && "success" in res && !res.success) {
        setSendError(res.error || "Message delivery failed. Connection offline.");
        return; // PRESERVE draft text and attachments!
      }
      setInputText(current => current === inputText ? "" : current);
      setAttachments(current => current.filter(item => !attachments.includes(item)));
      setMentionOpen(false);
      setSendError(null);
    } catch (err: any) {
      setSendError(err?.message || "Failed to dispatch message.");
    } finally {
      sendLock.current = false;
      setIsSending(false);
    }
  }, [inputText, attachments, onSendMessage, onCompact, teamId, isSending, uploading]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
    if (mentionOpen && mentionItems.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setMentionIndex(i => (i + 1) % mentionItems.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setMentionIndex(i => (i - 1 + mentionItems.length) % mentionItems.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        insertMention(mentionItems[mentionIndex]);
        return;
      }
      if (e.key === "Escape") {
        setMentionOpen(false);
        return;
      }
    }

    if (commandOpen && commandItems.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setCommandIndex(i => (i + 1) % commandItems.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setCommandIndex(i => (i - 1 + commandItems.length) % commandItems.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        insertCommand(commandItems[commandIndex]);
        return;
      }
      if (e.key === "Escape") {
        setCommandOpen(false);
        return;
      }
    }

    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }, [handleSend, mentionOpen, mentionItems, mentionIndex, commandOpen, commandItems, commandIndex]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setInputText(val);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";

    const sel = e.target.selectionStart;
    const textBefore = val.slice(0, sel);

    // Mention Check
    const atMatch = textBefore.match(/@([^\s]*)$/);
    if (atMatch) {
      setMentionOpen(true);
      setMentionQuery(atMatch[1]);
      setMentionIndex(0);
      void ensureFileTree();
    } else {
      setMentionOpen(false);
    }

    // Command Check
    const slashMatch = textBefore.match(/(^|\n)\/([^\s]*)$/);
    if (slashMatch) {
      setCommandOpen(true);
      setCommandQuery(slashMatch[2]);
      setCommandIndex(0);
    } else {
      setCommandOpen(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files?.length) return;
    setUploading(true);
    const file = e.target.files[0];
    try {
      const res = await api.uploadFile(teamId, file);
      setAttachments(prev => [...prev, res]);
    } catch (err) {
      console.error(err);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };


  const doDelete = async (msgId: string) => {
    if (onDeleteMessage) {
      onDeleteMessage(msgId);
    } else {
      try {
        await api.deleteMessage(msgId);
      } catch (e: any) {
        // 404 is expected for ephemeral WS-only messages (typing, tool_start, streaming)
        // that were never persisted to the DB. Swallow silently.
        if (e?.status !== 404) console.error("deleteMessage failed:", e);
      }
    }
  };

  const [rollbackOpen, setRollbackOpen] = useState(false);
  const [rollbackMsgId, setRollbackMsgId] = useState<string | null>(null);

  const requestRollback = (msgId: string) => {
    setRollbackMsgId(msgId);
    setRollbackOpen(true);
  };

  const doRollbackConfirm = async () => {
    if (!rollbackMsgId) return;
    const msgId = rollbackMsgId;
    setRollbackOpen(false);
    setRollbackMsgId(null);
    if (onRollbackMessage) {
      onRollbackMessage(msgId);
    } else {
      try {
        await api.rollbackFromMessage(msgId);
      } catch (e: any) {
        if (e?.status !== 404) console.error("rollbackFromMessage failed:", e);
      }
    }
  };

  const [clearChatOpen, setClearChatOpen] = useState(false);

  const doClearChatConfirm = async () => {
    if (!teamId) return;
    setClearChatOpen(false);
    if (onClearChat) onClearChat();
    try {
      await api.clearTeamChat(teamId);
    } catch (e: any) {
      console.error("clearTeamChat failed:", e);
    }
  };


  const handleSearch = useCallback(async () => {
    if (!teamId || !searchQuery.trim()) return;
    try {
      const r = await api.searchMessages(teamId, searchQuery);
      setSearchResults(r);
    } catch { /* ignore */ }
  }, [teamId, searchQuery]);

  const handleCopyMessage = (text: string, msgId: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedMsgId(msgId);
      setTimeout(() => setCopiedMsgId(null), 1800);
    });
  };

  const loadOlderMessages = useCallback(async () => {
    if (!teamId || !messages.length || loadingOlder) return;
    const oldest = messages[0];
    setLoadingOlder(true);
    try {
      const older = await (api as any).listMessages(teamId, { limit: 30, before: oldest.id });
      if (!older || older.length === 0) { setHasOlderMessages(false); return; }
      // Parent component owns messages state; we emit them via onSendMessage analogue
      // For now just set a no-more flag if less than limit returned
      if (older.length < 30) setHasOlderMessages(false);
    } catch (e) { console.warn("loadOlderMessages:", e); }
    finally { setLoadingOlder(false); }
  }, [teamId, messages, loadingOlder]);

  const displayMessages = searchMode ? searchResults.map((m: any) => ({ ...m, id: m.id, type: "message", timestamp: m.created_at })) : messages;

  // Build merged timeline: messages + compaction dividers interleaved by timestamp.
  // Each item is either { kind: "message", msg } or { kind: "compaction", event }.
  // Compaction dividers are only shown outside search mode.
  type MergedItem =
    | { kind: "message"; msg: ChatMessage }
    | { kind: "compaction"; event: CompactionEvent };

  const mergedItems = useMemo((): MergedItem[] => {
    if (searchMode || compactionEvents.length === 0) {
      return displayMessages.map(msg => ({ kind: "message" as const, msg }));
    }
    // Sort compaction events by created_at ascending
    const sortedEvents = [...compactionEvents].sort((a, b) => {
      const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
      const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
      return ta - tb;
    });
    const result: MergedItem[] = [];
    let evtIdx = 0;
    for (const msg of displayMessages) {
      const msgTs = msg.timestamp ? (typeof msg.timestamp === "number" ? msg.timestamp : new Date(msg.timestamp as string).getTime()) : 0;
      // Insert any compaction events that happened before this message
      while (evtIdx < sortedEvents.length) {
        const evtTs = sortedEvents[evtIdx].created_at ? new Date(sortedEvents[evtIdx].created_at!).getTime() : 0;
        if (evtTs <= msgTs) {
          result.push({ kind: "compaction", event: sortedEvents[evtIdx] });
          evtIdx++;
        } else {
          break;
        }
      }
      result.push({ kind: "message", msg });
    }
    // Append any remaining compaction events after all messages
    while (evtIdx < sortedEvents.length) {
      result.push({ kind: "compaction", event: sortedEvents[evtIdx] });
      evtIdx++;
    }
    return result;
  }, [displayMessages, compactionEvents, searchMode]);


  return (
    <div className="cw-workspace" style={{ flex: 1, minHeight: 0, height: "100%", width: "100%", position: "relative" }}>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div className="cw-team-reveal" tabIndex={0} aria-label="Show team controls">
        <header className="cw-header" style={{ position: "relative", zIndex: 40 }}>
          <div className="cw-header-left">
            <div className="cw-title">
              <h2>{teamName || "Team chat"}</h2>
              <p>{teamId ? agents.length + " teammates ready" : "Choose a team to begin"}</p>
            </div>
            <div className="cw-team-presence" aria-label="Team members">
              <div className="cw-team-stack">
                {agents.slice(0, 6).map((agent, index) => (
                  <AgentHoverCard key={agent.id} agent={agent} onMention={handleDirectMention} side="bottom">
                    <button className="cw-team-avatar" style={{ zIndex: 8 - index }} onClick={() => handleDirectMention(agent.name)} aria-label={"View " + agent.name + " or mention in chat"}>
                      <AgentAvatar name={agent.name} id={agent.id} role={agent.role} size={30} hideBadge />
                    </button>
                  </AgentHoverCard>
                ))}
              </div>
              {agents.length > 6 && <span className="cw-team-more">+{agents.length - 6}</span>}
            </div>
          </div>
          <div className="cw-header-actions">
            <ContextUsageGauge projectId={projectId || undefined} teamId={teamId || undefined} estimatedTokens={contextUsage?.estimated_tokens} contextWindow={contextUsage?.context_window} usagePercent={contextUsage?.usage_percent} lastTokenEvent={lastTokenEvent} messages={messages} agents={agents} />
            <button className={`cw-background-button ${showBackground ? "cw-background-button-active" : ""}`} aria-expanded={showBackground} onClick={() => setShowBackground(v => !v)} title="View background work">
              <BackgroundWorkMark />
              <span>Work</span>
              {runningJobs.length > 0 && <b>{runningJobs.length}</b>}
            </button>
            <details className="cw-menu"><summary className="cw-icon-button" aria-label="Conversation options"><MoreHorizontal size={18} /></summary><div className="cw-menu-content">
              <button className="cw-text-button" onClick={() => setSearchMode(v => !v)}><Search size={14} />Search conversation</button>
              {onToggleExplorer && <button className="cw-text-button" onClick={onToggleExplorer}><Folder size={14} />Open files and changes</button>}
              <button className="cw-text-button cw-danger" onClick={() => setClearChatOpen(true)}><Trash2 size={14} />Clear conversation</button>
              <McpStatusIndicator />
            </div></details>
          </div>
        </header>
        </div>
        {showBackground && <BackgroundWork work={backgroundWork} onClose={() => setShowBackground(false)} />}

        {/* Search bar */}
        {
          searchMode && (
            <div style={{ flexShrink: 0, padding: "var(--sp-sm) var(--sp-2xl)", borderBottom: "1px solid var(--border-glass)", background: "var(--bg-glass-panel)" }}>
              <div style={{ maxWidth: "1080px", width: "100%", margin: "0 auto", display: "flex", gap: "var(--sp-sm)" }}>
                <input className="input" style={{ flex: 1, minHeight: 32 }} placeholder="Search messages..."
                  value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") handleSearch(); }} autoFocus />
                <button className="btn btn-primary btn-sm" onClick={handleSearch}><Search size={13} /> Search</button>
                <button className="btn btn-ghost btn-sm" onClick={() => { setSearchMode(false); setSearchResults([]); setSearchQuery(""); }}>Clear</button>
              </div>
            </div>
          )
        }

        {/* Messages */}
        <div className="cw-scroll" ref={scrollRef} onScroll={handleScroll} style={{ flex: 1, overflowY: "auto", minHeight: 0, padding: "var(--sp-xl) var(--sp-2xl)", position: "relative", zIndex: 1 }}>
          <div className="cw-timeline" style={{ maxWidth: "min(1360px, 94%)", width: "100%", margin: "0 auto", display: "flex", flexDirection: "column", gap: "var(--sp-lg)", minHeight: "100%" }}>
            {/* Load older button */}
            {!searchMode && hasOlderMessages && messages.length >= 50 && (
              <div style={{ display: "flex", justifyContent: "center", paddingBottom: 8 }}>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={loadOlderMessages}
                  disabled={loadingOlder}
                  style={{ fontSize: 12, color: "var(--color-mute)", border: "1px solid var(--color-hairline)", borderRadius: 20, padding: "3px 16px" }}
                >
                  {loadingOlder ? "Loading…" : "↑ Load older messages"}
                </button>
              </div>
            )}
            {mergedItems.map((item) => {
              // ── Compaction divider ──
              if (item.kind === "compaction") {
                return <CompactionDivider key={`cp-${item.event.id}`} event={item.event} />;
              }

              const msg = item.msg;
              // Hide child subagent/teammate messages and linked intermediate messages from top-level chat flow
              const isChild = msg.attachments?.some((a: any) => a.type === "parent_message") || orphanIntermediateIds.has(msg.id);
              if (isChild && !searchMode) {
                return null;
              }

              const isHuman = msg.sender_id === "human" || msg.sender_id === user?.id || msg.role === "user";
              const isTool = msg.type === "tool_start" || msg.type === "tool_end";
              const isApproval = msg.type === "approval_request";
              const isQuestion = msg.type === "agent_question" || msg.type === "ask_user";
              const isIntervention = msg.type === "browser_intervention";
              const isFileChange = msg.type === "file_change";
              const isSystem = msg.sender_id === "system";
              const isStreaming = msg.type === "streaming";
              const isIntermediate = msg.is_intermediate === true || msg.type === "tool_trace";

              if (isTool) return <ToolRow key={msg.id} msg={msg} />;

              // Compact collapsible row for intermediate tool-trace records
              if (isIntermediate) {
                const sections = parseReasoningIntoSections(msg.text || "");
                const hasTools = sections.some(s => s.type === "tool");

                if (hasTools) {
                  return (
                    <div data-chat-message={msg.id} key={msg.id} style={{ marginLeft: 8, marginBottom: 4, maxWidth: "85%", display: "flex", alignItems: "center", gap: 6 }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        {sections.map((sec, idx) => (
                          sec.type === "tool" ? (
                            <TraceToolCard
                              key={idx}
                              toolName={sec.toolName!}
                              argsObj={sec.argsObj}
                              argsRaw={sec.argsJson}
                              result={sec.result}
                              isError={sec.isError}
                              pid={sec.pid}
                              agentName={msg.sender_name}
                              timestamp={msg.timestamp}
                              defaultOpen={false}
                            />
                          ) : null
                        ))}
                      </div>
                      <button
                        className="btn btn-icon btn-ghost btn-sm"
                        title="Delete activity"
                        onClick={() => doDelete(msg.id)}
                        style={{ opacity: 0.35, padding: 3 }}
                        onMouseEnter={e => (e.currentTarget.style.opacity = "1")}
                        onMouseLeave={e => (e.currentTarget.style.opacity = "0.35")}
                      >
                        <Trash2 size={11} />
                      </button>
                    </div>
                  );
                }

                const isExpanded = expandedTraces.has(msg.id);
                const toolNameMatch = (msg.text || "").match(/🛠️\s*\*\*([^\*]+)\*\*/);
                const toolName = toolNameMatch ? toolNameMatch[1] : "Tool Action";
                const toolMeta = getToolMeta(toolName);
                const ToolIcon = toolMeta.icon;

                const traceAgentInfo = getAgentInfo(msg.sender_id, msg.sender_name, msg.role);
                const traceRole = traceAgentInfo?.role && traceAgentInfo.role !== "Active Agent" ? traceAgentInfo.role : (msg.role !== "assistant" ? msg.role : undefined);

                return (
                  <div data-chat-message={msg.id} key={msg.id} style={{ display: "flex", gap: "var(--sp-sm)", alignItems: "flex-start", marginLeft: 8, marginBottom: 2 }}>
                    <AgentAvatar name={msg.sender_name || "agent"} id={traceAgentInfo?.id || msg.sender_id} role={traceRole} size={22} isStreaming={isStreaming} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                        <button
                          onClick={() => setExpandedTraces(prev => {
                            const s = new Set(prev);
                            isExpanded ? s.delete(msg.id) : s.add(msg.id);
                            return s;
                          })}
                          style={{
                            background: "var(--bg-glass-card)", border: "1px solid var(--border-glass)",
                            borderRadius: "var(--radius-sm)", cursor: "pointer", padding: "4px 8px",
                            display: "inline-flex", alignItems: "center", gap: 6, color: "var(--color-body)",
                            transition: "all var(--t-fast)"
                          }}
                        >
                          {isExpanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                          <span className={toolMeta.className} style={{ fontSize: 9, padding: "1px 5px" }}>
                            <ToolIcon size={9} /> {toolMeta.label}
                          </span>
                          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11, color: "var(--color-ink)", fontWeight: 500 }}>
                            {toolName}
                          </span>
                          <span className="caption" style={{ fontSize: 10, color: "var(--color-mute)" }}>
                            ({msg.sender_name})
                          </span>
                          {msg.timestamp && <span className="caption" style={{ marginLeft: 4, opacity: 0.5 }}>{fmtTime(msg.timestamp)}</span>}
                        </button>
                        <button
                          className="btn btn-icon btn-ghost btn-sm"
                          title="Delete activity"
                          onClick={() => doDelete(msg.id)}
                          style={{ opacity: 0.35, padding: 3 }}
                          onMouseEnter={e => (e.currentTarget.style.opacity = "1")}
                          onMouseLeave={e => (e.currentTarget.style.opacity = "0.35")}
                        >
                          <Trash2 size={11} />
                        </button>
                      </div>
                      {isExpanded && (
                        <div className="markdown-body" style={{ fontSize: 11, marginTop: 4, padding: "var(--sp-sm) var(--sp-md)", background: "var(--color-canvas-raised)", borderRadius: "var(--radius-sm)", border: "1px solid var(--color-hairline)", overflow: "auto", maxHeight: 300 }}>
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text || ""}</ReactMarkdown>
                        </div>
                      )}
                    </div>
                  </div>
                );
              }

              if (isSystem) {
                let icon = <Info size={14} color="var(--color-primary)" />;
                let color = "var(--color-primary)";
                const text = msg.text || "";
                let cleanText = text;
                if (text.startsWith("[TASK_")) {
                  icon = <CheckSquare size={14} color="var(--color-success)" />;
                  color = "var(--color-success)";
                  cleanText = text.replace(/\[TASK_[^\]]+\]\s*/, "");
                } else if (text.startsWith("[AGENT_")) {
                  icon = <Users size={14} color="var(--color-warning)" />;
                  color = "var(--color-warning)";
                  cleanText = text.replace(/\[AGENT_[^\]]+\]\s*/, "");
                } else if (text.startsWith("[MCP_") || text.startsWith("[TOOL_")) {
                  icon = <Wrench size={14} color="var(--color-brand)" />;
                  color = "var(--color-brand)";
                  cleanText = text.replace(/\[(MCP|TOOL)_[^\]]+\]\s*/, "");
                } else if (text.startsWith("[LEARNING_")) {
                  icon = <Lightbulb size={14} color="#FBBF24" />;
                  color = "#FBBF24";
                  cleanText = text.replace(/\[LEARNING_[^\]]+\]\s*/, "");
                }

                cleanText = cleanText.replace(/ by (?:Human|Admin)(?=\s|$)/g, " by admin").replace(/\(Admin\)/gi, "(admin)");

                return (
                  <div data-chat-message={msg.id} key={msg.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start", position: "relative", marginLeft: 8 }}>
                    <div style={{ position: "absolute", top: 15, bottom: -15, left: 14, width: 2, background: "var(--border-glass)", zIndex: 0 }} />
                    <div style={{ width: 30, height: 30, borderRadius: "50%", background: "var(--bg-glass-panel)", border: `1px solid ${color}`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, zIndex: 1, position: "relative" }}>
                      {icon}
                    </div>
                    <div style={{ flex: 1, minWidth: 0, paddingTop: 4, display: "flex", alignItems: "center", gap: 6 }}>
                      <span className="caption" style={{ color: "var(--color-mute)" }}>{cleanText}</span>
                      {msg.timestamp && <span className="caption" style={{ marginLeft: "var(--sp-sm)", opacity: 0.5 }}>{fmtTime(msg.timestamp)}</span>}
                      <button
                        className="btn btn-icon btn-ghost btn-sm"
                        title="Delete system notification"
                        onClick={() => doDelete(msg.id)}
                        style={{ opacity: 0.3, transition: "opacity 0.15s", padding: 2, marginLeft: "auto" }}
                        onMouseEnter={e => (e.currentTarget.style.opacity = "1")}
                        onMouseLeave={e => (e.currentTarget.style.opacity = "0.3")}
                      >
                        <Trash2 size={11} />
                      </button>
                    </div>
                  </div>
                );
              }
              if (isFileChange && msg.path) {
                return (
                  <div data-chat-message={msg.id} key={msg.id} style={{ margin: "4px 0" }}>
                    <FileChangeCard
                      senderName={msg.sender_name}
                      path={msg.path}
                      diff={msg.diff}
                      content={msg.arguments?.content}
                      action={msg.action || "modified"}
                      timestamp={msg.timestamp}
                      onOpenFile={onOpenFile}
                      onOpenDiffFile={onOpenDiffFile ? (p: string) => onOpenDiffFile(p, msg.diff || "") : undefined}
                    />
                  </div>
                );
              }
              if (isApproval) {
                const agentInfo = getAgentInfo(msg.sender_id, msg.sender_name, msg.role);
                const displayRole = agentInfo?.role && agentInfo.role !== "Active Agent" ? agentInfo.role : (msg.role !== "assistant" ? msg.role : undefined);
                return (
                  <div data-chat-message={msg.id} key={msg.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start" }}>
                    <AgentHoverCard agent={agentInfo} name={msg.sender_name} id={msg.sender_id} role={displayRole} onMention={handleDirectMention}>
                      <AgentAvatar name={msg.sender_name || "Agent"} id={agentInfo?.id || msg.sender_id} role={displayRole} size={32} />
                    </AgentHoverCard>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: 4 }}>
                        <span className="body-sm-strong">{msg.sender_name}</span>
                        {displayRole && <span className="caption">{displayRole}</span>}
                        {msg.timestamp && <span className="caption" style={{ marginLeft: "auto" }}>{fmtTime(msg.timestamp)}</span>}
                      </div>
                      <ApprovalCard msg={msg} />
                    </div>
                  </div>
                );
              }
              if (isQuestion) {
                const agentInfo = getAgentInfo(msg.sender_id, msg.sender_name, msg.role);
                const displayRole = agentInfo?.role && agentInfo.role !== "Active Agent" ? agentInfo.role : (msg.role !== "assistant" ? msg.role : undefined);
                return (
                  <div data-chat-message={msg.id} key={msg.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start" }}>
                    <AgentHoverCard agent={agentInfo} name={msg.sender_name} id={msg.sender_id} role={displayRole} onMention={handleDirectMention}>
                      <AgentAvatar name={msg.sender_name || "Agent"} id={agentInfo?.id || msg.sender_id} role={displayRole} size={32} />
                    </AgentHoverCard>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: 4 }}>
                        <span className="body-sm-strong">{msg.sender_name}</span>
                        {displayRole && <span className="caption">{displayRole}</span>}
                        {msg.timestamp && <span className="caption" style={{ marginLeft: "auto" }}>{fmtTime(msg.timestamp)}</span>}
                      </div>
                      <AskUserCard msg={msg} />
                    </div>
                  </div>
                );
              }
              if (isIntervention) {
                const agentInfo = getAgentInfo(msg.sender_id, msg.sender_name, msg.role);
                const displayRole = agentInfo?.role && agentInfo.role !== "Active Agent" ? agentInfo.role : (msg.role !== "assistant" ? msg.role : undefined);
                return (
                  <div data-chat-message={msg.id} key={msg.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start" }}>
                    <AgentHoverCard agent={agentInfo} name={msg.sender_name} id={msg.sender_id} role={displayRole} onMention={handleDirectMention}>
                      <AgentAvatar name={msg.sender_name || "Agent"} id={agentInfo?.id || msg.sender_id} role={displayRole} size={32} />
                    </AgentHoverCard>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: 4 }}>
                        <span className="body-sm-strong">{msg.sender_name}</span>
                        {displayRole && <span className="caption">{displayRole}</span>}
                        {msg.timestamp && <span className="caption" style={{ marginLeft: "auto" }}>{fmtTime(msg.timestamp)}</span>}
                      </div>
                      <BrowserInterventionCard msg={msg} />
                    </div>
                  </div>
                );
              }

              if (msg.type === "llm_error" && msg.llm_error) {
                const err = msg.llm_error;
                return (
                  <div data-chat-message={msg.id} key={msg.id} className="animate-fade-in" style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start", width: "100%" }}>
                    <div style={{
                      width: 32, height: 32, borderRadius: "50%",
                      background: "rgba(239, 68, 68, 0.15)", // red-500 with opacity
                      display: "flex", alignItems: "center", justifyContent: "center",
                      color: "#ef4444", flexShrink: 0
                    }}>
                      <AlertTriangle size={16} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: 3 }}>
                        <span className="body-sm-strong" style={{ color: "#ef4444" }}>LLM Provider Error</span>
                        <span className="subagent-chip" style={{ fontSize: 9, padding: "1px 5px", background: "rgba(239, 68, 68, 0.15)", color: "#fca5a5" }}>{err.provider.toUpperCase()}</span>
                        {msg.timestamp && <span className="caption" style={{ marginLeft: "auto" }}>{fmtTime(msg.timestamp)}</span>}
                      </div>
                      <div style={{
                        background: "rgba(255, 255, 255, 0.03)",
                        border: "1px solid rgba(239, 68, 68, 0.3)",
                        padding: "12px 16px",
                        borderRadius: "8px",
                        color: "#e2e8f0"
                      }}>
                        <div style={{ fontWeight: 600, fontSize: "13px", marginBottom: "8px" }}>
                          {err.message}
                        </div>
                        <div style={{ fontSize: "12px", color: "var(--color-mute)", marginBottom: "12px" }}>
                          Model: <span style={{ fontFamily: "monospace", color: "#fca5a5" }}>{err.model}</span>
                        </div>
                        <div style={{
                          background: "rgba(0,0,0,0.2)",
                          padding: "8px 12px",
                          borderRadius: "4px",
                          borderLeft: "2px solid #ef4444",
                          fontSize: "12px",
                          display: "flex",
                          alignItems: "center",
                          gap: "8px"
                        }}>
                          <Info size={14} color="#ef4444" />
                          <span><strong>Action Required:</strong> {err.action_hint}</span>
                        </div>
                        {err.env_key_name && (
                          <div style={{ marginTop: "12px" }}>
                            <button className="btn btn-primary btn-sm" onClick={() => window.open('/settings', '_blank')}>
                              Configure API Keys in Settings
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              }

              // Check if message is a subagent task notification report
              const isTaskNotification = Boolean(msg.text?.includes("<task-notification>"));
              if (isTaskNotification) {
                return (
                  <div data-chat-message={msg.id} key={msg.id} className="animate-fade-in" style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start", width: "100%" }}>
                    <AgentAvatar name={msg.sender_name || "Subagent"} id={msg.sender_id} role={msg.role || "subagent"} size={32} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: 3 }}>
                        <span className="body-sm-strong">{msg.sender_name}</span>
                        <span className="subagent-chip" style={{ fontSize: 9, padding: "1px 5px" }}>WORKER REPORT</span>
                        {msg.timestamp && <span className="caption" style={{ marginLeft: "auto" }}>{fmtTime(msg.timestamp)}</span>}
                      </div>
                      <TaskNotificationCard text={msg.text || ""} />
                    </div>
                  </div>
                );
              }

              // Check if message is a system task update/assign
              const isTaskSys = msg.text?.startsWith("[TASK_ASSIGN]") || msg.text?.startsWith("[TASK_UPDATE]");
              if (isTaskSys && msg.sender_id === "system") {
                let cleanSysText = msg.text || "";
                // Strip out the prompt instructions intended for the LLM
                cleanSysText = cleanSysText.replace(/IMPORTANT: DO NOT use create_task[\s\S]*?(?=when finished\.|update_task|to start it).*?(?:when finished\.|to continue work\.)?/gi, "").trim();
                // Optionally remove the prefix
                cleanSysText = cleanSysText.replace(/\[TASK_ASSIGN\]|\[TASK_UPDATE\]/g, "").trim();

                return (
                  <div data-chat-message={msg.id} key={msg.id} className="animate-fade-in" style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start", width: "100%" }}>
                    <div style={{
                      width: 32, height: 32, borderRadius: "50%",
                      background: "rgba(167, 139, 250, 0.15)",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      color: "#a78bfa", flexShrink: 0
                    }}>
                      <CheckSquare size={16} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: 3 }}>
                        <span className="body-sm-strong">System</span>
                        <span className="subagent-chip" style={{ fontSize: 9, padding: "1px 5px", background: "rgba(167, 139, 250, 0.15)", color: "#c4b5fd" }}>KANBAN</span>
                        {msg.timestamp && <span className="caption" style={{ marginLeft: "auto" }}>{fmtTime(msg.timestamp)}</span>}
                      </div>
                      <div style={{
                        background: "rgba(255, 255, 255, 0.03)",
                        border: "1px solid rgba(255, 255, 255, 0.08)",
                        padding: "10px 14px",
                        borderRadius: "8px",
                        fontSize: "13px",
                        color: "#e2e8f0"
                      }}>
                        {cleanSysText}
                      </div>
                    </div>
                  </div>
                );
              }

              const isThinking = msg.type === "thinking";

              let cleanText = msg.text || "";
              let embeddedReasoning = "";

              const thinkRegex = /<think>([\s\S]*?)<\/think>/g;
              let match;
              while ((match = thinkRegex.exec(cleanText)) !== null) {
                embeddedReasoning += match[1].trim() + "\n\n";
              }
              cleanText = cleanText.replace(thinkRegex, "");

              const toolRegex = /<tool_call>([\s\S]*?)<\/tool_call>/g;
              while ((match = toolRegex.exec(cleanText)) !== null) {
                embeddedReasoning += "```json\n" + match[1].trim() + "\n```\n\n";
              }
              cleanText = cleanText.replace(toolRegex, "");

              const actionRegex = /\[ACTION\]([\s\S]*?)\[\/ACTION\]/g;
              while ((match = actionRegex.exec(cleanText)) !== null) {
                embeddedReasoning += "```json\n" + match[1].trim() + "\n```\n\n";
              }
              cleanText = cleanText.replace(actionRegex, "");

              // Strip out <function_calls> wrapper tags if the LLM output them
              cleanText = cleanText.replace(/<function_calls>/g, "").replace(/<\/function_calls>/g, "");
              cleanText = cleanText.trim();

              let rawReasoning = msg.reasoning || "";
              rawReasoning = rawReasoning.replace(/\[ACTION\][\s\S]*?\[\/ACTION\]/g, "");
              rawReasoning = rawReasoning.replace(/<tool_call>([\s\S]*?)<\/tool_call>/g, "\n```json\n$1\n```\n");
              rawReasoning = rawReasoning.replace(/<function_calls>|<\/function_calls>/g, "");
              rawReasoning = rawReasoning.trim();

              const linkedChildIntermediates = childMessagesByParent[msg.id] || [];
              let combinedChildReasoning = "";
              for (const child of linkedChildIntermediates) {
                if ((child.is_intermediate || child.type === "tool_trace") && child.text) {
                  const t = child.text.trim();
                  if (t && !rawReasoning.includes(t)) {
                    if (t.startsWith("[OBSERVATION]")) {
                      combinedChildReasoning += `\n\n💭 **Observation:**\n${t}\n\n`;
                    } else {
                      combinedChildReasoning += `\n\n${t}\n\n`;
                    }
                  }
                }
              }

              const allReasoning = (rawReasoning + (combinedChildReasoning ? "\n\n" + combinedChildReasoning : "") + "\n\n" + embeddedReasoning).trim();
              const finalReasoning = allReasoning;
              let markdownText = cleanText;

              if (onOpenFile) {
                markdownText = markdownText.replace(
                  /(^|[^`])@file:(\S+)/g,
                  (_m: string, pre: string, p: string) => {
                    const path = p.replace(/[),.;]+$/, "");
                    const base = path.split("/").pop() || path;
                    return `${pre}[\`📄 ${base}\`](file:${path})`;
                  }
                );

                const parts = markdownText.split(/(```[\s\S]*?```|`[^`]*`|\[.*?\]\(.*?\))/g);
                const fileRegex = /(^|\s|'|"|\()([a-zA-Z0-9_./-]+\.(?:md|ts|tsx|js|jsx|py|html|css|json|txt|yml|yaml|sh|bash|ini|env))(?=$|\s|'|"|\)|,|\.|\!|\?)/gi;

                markdownText = parts.map((part: string, i: number) => {
                  if (i % 2 === 0) {
                    return part.replace(fileRegex, '$1[$2](file:$2)');
                  }
                  return part;
                }).join('');
              }
              if (searchMode && searchQuery.trim()) {
                const safeQuery = searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                const regex = new RegExp(`(${safeQuery})`, 'gi');
                const parts = markdownText.split(/(```[\s\S]*?```|`[^`]*`|\[.*?\]\(.*?\))/g);
                markdownText = parts.map((part: string, i: number) => (i % 2 === 0 ? part.replace(regex, '~~$1~~') : part)).join('');
              }

              return (
                <div data-chat-message={msg.id} key={msg.id} className={"cw-message group " + (isHuman ? "cw-message-human" : "cw-message-assistant")} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start", flexDirection: isHuman ? "row-reverse" : "row", width: "100%" }}>

                  {!isHuman ? (() => {
                    const agentInfo = getAgentInfo(msg.sender_id, msg.sender_name, msg.role);
                    const displayRole = agentInfo?.role && agentInfo.role !== "Active Agent" ? agentInfo.role : (msg.role !== "assistant" ? msg.role : undefined);
                    return (
                      <AgentHoverCard
                        agent={agentInfo}
                        name={msg.sender_name}
                        id={msg.sender_id}
                        role={displayRole}
                        isStreaming={isStreaming}
                        isThinking={isThinking}
                        onMention={handleDirectMention}
                      >
                        <AgentAvatar
                          name={msg.sender_name || "Agent"}
                          id={msg.sender_id}
                          role={displayRole}
                          size={32}
                          isStreaming={isStreaming}
                          isThinking={isThinking}
                        />
                      </AgentHoverCard>
                    );
                  })() : (() => {
                    const humanDisplayName = (user?.first_name ? `${user.first_name} ${user.last_name || ""}`.trim() : user?.email) || (msg.sender_name && msg.sender_name !== "human" ? msg.sender_name : "You");
                    return (
                      <AgentAvatar
                        name={humanDisplayName}
                        id={msg.sender_id || user?.id}
                        role="human"
                        size={32}
                      />
                    );
                  })()}
                  <div className="cw-message-body" style={{ maxWidth: isHuman ? "78%" : "88%", minWidth: 0, position: "relative" }}>
                    {!isHuman && (() => {
                      const agentInfo = getAgentInfo(msg.sender_id, msg.sender_name, msg.role);
                      const displayRole = agentInfo?.role && agentInfo.role !== "Active Agent" ? agentInfo.role : (msg.role !== "assistant" ? msg.role : undefined);
                      return (
                        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: 3 }}>
                          <AgentHoverCard
                            agent={agentInfo}
                            name={msg.sender_name}
                            id={msg.sender_id}
                            role={displayRole}
                            onMention={handleDirectMention}
                          >
                            <span className="body-sm-strong" style={{ cursor: "pointer" }}>{msg.sender_name}</span>
                          </AgentHoverCard>
                          {displayRole && <span className="caption">{displayRole}</span>}
                          {msg.timestamp && <span className="caption" style={{ marginLeft: "auto" }}>{fmtTime(msg.timestamp)}</span>}
                        </div>
                      );
                    })()}
                    {isHuman && msg.timestamp && <div style={{ textAlign: "right", marginBottom: 3 }}><span className="caption">{fmtTime(msg.timestamp)}</span></div>}

                    <div className="cw-message-content" style={{
                      padding: "var(--sp-md) var(--sp-lg)", lineHeight: 1.6,
                      background: isHuman ? "var(--bg-surface-raised)" : "var(--bg-surface)",
                      border: isHuman ? "1px solid var(--border-subtle)" : "1px solid var(--border-subtle)",
                      borderRadius: isHuman ? "var(--radius-md) 2px var(--radius-md) var(--radius-md)" : "2px var(--radius-md) var(--radius-md) var(--radius-md)",
                      color: "var(--text-primary)",
                      position: "relative", fontSize: "var(--text-sm)",
                    }}>
                      {isThinking ? (
                        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", color: "var(--color-mute)" }}>
                          <TypingIndicator />
                          <span className="body-sm" style={{ opacity: 0.8 }}>Thinking…</span>
                        </div>
                      ) : isHuman ? (
                        <div style={{ whiteSpace: "pre-wrap" }}>
                          {cleanText}
                          {msg.attachments && msg.attachments.length > 0 && (
                            <div style={{ display: "flex", gap: "var(--sp-sm)", marginTop: "var(--sp-sm)", flexWrap: "wrap" }}>
                              {msg.attachments.map((att: any, i: number) => (
                                att.type?.startsWith("image/") ? (
                                  <img key={i} src={att.url} alt="attachment" style={{ maxWidth: 200, maxHeight: 200, borderRadius: "var(--radius-sm)", border: "1px solid rgba(167, 139, 250, 0.2)" }} />
                                ) : (
                                  <a key={i} href={att.url} target="_blank" rel="noreferrer" style={{ padding: "4px 8px", background: "rgba(167, 139, 250, 0.1)", borderRadius: "var(--radius-sm)", fontSize: 11, color: "var(--color-primary)", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4 }}>
                                    📎 {att.name}
                                  </a>
                                )
                              ))}
                            </div>
                          )}
                        </div>
                      ) : (
                        <>
                          {(!isHuman && (cleanText.includes("# Implementation Plan") || cleanText.includes("[ARTIFACT: implementation_plan]") || cleanText.includes("## User Review Required"))) && (
                            <div style={{ marginBottom: "12px" }}>
                              <InChatPlanCard
                                planContent={cleanText}
                                onProceed={() => onSendMessage("Proceed with the approved plan")}
                              />
                            </div>
                          )}
                          {/* Linked interactive questions asked during this turn */}
                          {!isHuman && !isThinking && (childMessagesByParent[msg.id] || [])
                            .filter(c => c.type === "agent_question" || c.type === "ask_user")
                            .map(qChild => (
                              <div key={qChild.id} style={{ marginBottom: "12px" }}>
                                <AskUserCard msg={qChild} />
                              </div>
                            ))
                          }
                          {/* Linked interactive approvals requested during this turn */}
                          {!isHuman && !isThinking && (childMessagesByParent[msg.id] || [])
                            .filter(c => c.type === "approval_request")
                            .map(appChild => (
                              <div key={appChild.id} style={{ marginBottom: "12px" }}>
                                <ApprovalCard msg={appChild} />
                              </div>
                            ))
                          }
                          <div className="markdown-body">
                            <ReactMarkdown
                              skipHtml={true}
                              remarkPlugins={[remarkGfm]}
                              components={markdownComponents}
                            >
                              {markdownText}
                            </ReactMarkdown>
                          </div>
                        </>
                      )}
                      {isStreaming && <TypingIndicator />}
                      {(isStreaming || isThinking) && !isHuman && <StopAgentButton agentId={msg.sender_id} />}
                      {/* File Changes Card — associated directly with this assistant message! */}
                      {!isHuman && !isThinking && (() => {
                        const fileChanges = extractFileChanges(finalReasoning, msg);
                        if (fileChanges.length === 0) return null;
                        return (
                          <div style={{ marginTop: "var(--sp-sm, 8px)" }}>
                            <FileChangeCard
                              files={fileChanges}
                              senderName={msg.sender_name}
                              timestamp={msg.timestamp}
                              onOpenFile={onOpenFile}
                              onOpenDiffFile={onOpenDiffFile ? (p: string) => onOpenDiffFile(p, msg.diff || "") : undefined}
                            />
                          </div>
                        );
                      })()}

                      {/* Thoughts Panel — renders reasoning trace + tool calls */}
                      {!isHuman && !isThinking && (
                        <ThoughtsPanel reasoning={finalReasoning} isStreaming={isStreaming} components={markdownComponents} />
                      )}

                      {/* Subagent Activities / Worker reports enqueued for this message */}
                      {!isHuman && !isThinking && (childMessagesByParent[msg.id] || []).some(c => !c.is_intermediate && c.type !== "tool_trace" && c.type !== "agent_question" && c.type !== "ask_user" && c.type !== "approval_request" && c.type !== "browser_intervention") && (
                        <div style={{ marginTop: "12px", display: "flex", flexDirection: "column", gap: "10px", borderTop: "1px solid var(--border-glass)", paddingTop: "12px", width: "100%" }}>
                          {(childMessagesByParent[msg.id] || [])
                            .filter(c => !c.is_intermediate && c.type !== "tool_trace" && c.type !== "agent_question" && c.type !== "ask_user" && c.type !== "approval_request" && c.type !== "browser_intervention")
                            .map(child => {
                              const isChildTaskNotification = Boolean(child.text?.includes("<task-notification>"));

                              if (isChildTaskNotification) {
                                const childReasoning = child.reasoning || "";
                                return (
                                  <div key={child.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start", width: "100%" }}>
                                    <AgentAvatar name={child.sender_name || "Agent"} id={child.sender_id} role={child.role || "subagent"} size={26} />
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: 3 }}>
                                        <span className="body-sm-strong" style={{ fontSize: 12 }}>{child.sender_name}</span>
                                        <span className="subagent-chip" style={{ fontSize: 8, padding: "1px 4px" }}>WORKER REPORT</span>
                                        {child.timestamp && <span className="caption" style={{ marginLeft: "auto" }}>{fmtTime(child.timestamp)}</span>}
                                      </div>
                                      <TaskNotificationCard text={child.text || ""} />
                                      {childReasoning && (
                                        <div style={{ marginTop: "8px", borderTop: "1px solid var(--border-glass)", paddingTop: "8px" }}>
                                          <ThoughtsPanel reasoning={childReasoning} isStreaming={false} components={markdownComponents} />
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                );
                              }

                              // Fallback for standard child text messages (e.g. permanent teammate outputs)
                              return (
                                <div key={child.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start", width: "100%" }}>
                                  <AgentAvatar name={child.sender_name || "Agent"} id={child.sender_id} role={child.role} size={26} />
                                  <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: 3 }}>
                                      <span className="body-sm-strong" style={{ fontSize: 12 }}>{child.sender_name}</span>
                                      {child.role && <span className="caption" style={{ fontSize: 10 }}>{child.role}</span>}
                                      {child.timestamp && <span className="caption" style={{ marginLeft: "auto" }}>{fmtTime(child.timestamp)}</span>}
                                    </div>
                                    <div style={{
                                      padding: "8px 12px",
                                      background: "var(--bg-glass-card)",
                                      border: "1px solid var(--border-subtle)",
                                      borderRadius: "0 8px 8px 8px",
                                      fontSize: "12px",
                                    }} className="markdown-body">
                                      <ReactMarkdown skipHtml={true} remarkPlugins={[remarkGfm]} components={markdownComponents}>
                                        {child.text || ""}
                                      </ReactMarkdown>
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                        </div>
                      )}
                      {msg.pending_approval && msg.pending_approval.status !== "approved" && (
                        <div style={{ marginTop: "var(--sp-md)" }}>
                          <ApprovalCard msg={{ ...msg, ...msg.pending_approval, type: "approval_request" } as ChatMessage} />
                        </div>
                      )}
                    </div>

                    {/* Action Menu Hover — anchored on left side above this message */}
                    {!isThinking && !isStreaming && !isSystem && !isApproval && !isQuestion && (
                      <div className="msg-actions" style={{
                        display: "flex", gap: 3, position: "absolute",
                        top: -24,
                        ...(isHuman ? { right: 0, left: "auto" } : { left: 0, right: "auto" }),
                        background: "rgba(18, 18, 30, 0.94)",
                        backdropFilter: "blur(14px)",
                        WebkitBackdropFilter: "blur(14px)",
                        border: "1px solid rgba(255, 255, 255, 0.14)",
                        boxShadow: "0 6px 20px rgba(0, 0, 0, 0.5)",
                        padding: "2px 5px",
                        borderRadius: "8px",
                        opacity: 0,
                        transition: "opacity 0.15s ease, transform 0.15s ease",
                        zIndex: 25,
                      }}>
                        <button className="btn btn-icon btn-ghost btn-sm" title="Copy message text"
                          onClick={() => handleCopyMessage(msg.text || "", msg.id)}
                          style={{ color: copiedMsgId === msg.id ? "var(--color-success, #4ade80)" : undefined }}>
                          {copiedMsgId === msg.id ? <Check size={12} /> : <Copy size={12} />}
                        </button>
                        {!isHuman && (
                          <>
                            <button className="btn btn-icon btn-ghost btn-sm" title="Helpful response"
                              onClick={() => setFeedbackState(prev => ({ ...prev, [msg.id]: prev[msg.id] === "up" ? undefined : "up" } as any))}
                              style={{ color: feedbackState[msg.id] === "up" ? "var(--color-success, #4ade80)" : undefined }}>
                              <ThumbsUp size={12} fill={feedbackState[msg.id] === "up" ? "currentColor" : "none"} />
                            </button>
                            <button className="btn btn-icon btn-ghost btn-sm" title="Not helpful"
                              onClick={() => setFeedbackState(prev => ({ ...prev, [msg.id]: prev[msg.id] === "down" ? undefined : "down" } as any))}
                              style={{ color: feedbackState[msg.id] === "down" ? "var(--color-danger, #ef4444)" : undefined }}>
                              <ThumbsDown size={12} fill={feedbackState[msg.id] === "down" ? "currentColor" : "none"} />
                            </button>
                          </>
                        )}
                        <button className="btn btn-icon btn-ghost btn-sm" title="Delete this message only" onClick={() => doDelete(msg.id)}>
                          <Trash2 size={12} />
                        </button>
                        <button
                          className="btn btn-icon btn-ghost btn-sm"
                          style={{ color: "var(--color-warning, #f59e0b)" }}
                          title="Rollback to this checkpoint (undo messages, file changes, tasks & memories)"
                          onClick={() => requestRollback(msg.id)}
                        >
                          <RotateCcw size={12} />
                        </button>
                      </div>
                    )}
                  </div>

                </div>
              );
            })}

            {messages.length === 0 && !searchMode && (
              <div className="cw-welcome">
                <div className="cw-welcome-mark"><MessageCircleQuestion size={22} /><span>Your team, on the same page.</span></div>
                <h3>What shall we work on?</h3>
                <p>Bring an idea, a tricky bug, or a fresh perspective. We’ll work through it together.</p>
                <div className="cw-starters">
                  {[{ icon: FileCode, title: "Understand this codebase", prompt: "Explore this codebase and explain its structure and the most important flows." }, { icon: Lightbulb, title: "Think through a change", prompt: "/plan Help me think through a change. Start by asking what I want to improve." }, { icon: Search, title: "Find what needs attention", prompt: "Review this project for bugs and explain the most important findings before making changes." }].map(item => <button key={item.title} onClick={() => { setInputText(item.prompt); inputRef.current?.focus(); }}><item.icon size={18} /><span>{item.title}</span><ChevronRight size={16} /></button>)}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Attachments preview */}
        {
          attachments.length > 0 && (
            <div style={{ flexShrink: 0, padding: "var(--sp-sm) var(--sp-2xl)", background: "var(--bg-glass-panel)", backdropFilter: "var(--blur-md)", WebkitBackdropFilter: "var(--blur-md)" }}>
              <div style={{ maxWidth: "1080px", width: "100%", margin: "0 auto", display: "flex", flexWrap: "wrap", gap: "var(--sp-sm)" }}>
                {attachments.map((att, i) => {
                  const isImage = att.type?.startsWith("image/");
                  const ext = (att.name || "").split(".").pop()?.toLowerCase() ?? "";
                  const typeLabel: Record<string, string> = {
                    pdf: "PDF", doc: "DOC", docx: "DOCX", xls: "XLS", xlsx: "XLSX",
                    ppt: "PPT", pptx: "PPTX", txt: "TXT", csv: "CSV",
                    json: "JSON", md: "MD", py: "PY", ts: "TS", tsx: "TSX", js: "JS",
                  };
                  const label = typeLabel[ext] ?? ext.toUpperCase() ?? "FILE";
                  return (
                    <div key={i} style={{
                      position: "relative",
                      borderRadius: "var(--radius-sm)",
                      border: "1px solid var(--color-hairline)",
                      overflow: "hidden",
                      background: "var(--color-canvas-soft)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      ...(isImage ? { width: 56, height: 56 } : { height: 44, maxWidth: 180, padding: "0 10px", gap: 6 })
                    }}>
                      {isImage ? (
                        <img src={att.url} alt={att.name ?? "attachment"} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                      ) : (
                        <>
                          <span style={{
                            fontSize: 9, fontWeight: 700, letterSpacing: 0.5,
                            background: "var(--color-primary-glow)", color: "var(--color-primary)",
                            borderRadius: 3, padding: "2px 5px", flexShrink: 0
                          }}>{label}</span>
                          <span style={{
                            fontSize: 11, color: "var(--color-mute)",
                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                            maxWidth: 110
                          }} title={att.name}>{att.name}</span>
                        </>
                      )}
                      <button
                        onClick={() => setAttachments(prev => prev.filter((_, idx) => idx !== i))}
                        style={{
                          position: "absolute", top: 2, right: 2,
                          background: "rgba(0,0,0,0.55)", color: "white",
                          border: "none", borderRadius: "50%", padding: 2,
                          cursor: "pointer", display: "flex", lineHeight: 1
                        }}
                      >
                        <XCircle size={10} />
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )
        }

        {/* Composer and persistent attention controls */}
        <div className="cw-composer-region" style={{ flexShrink: 0, zIndex: 10, position: "relative" }}>
          {(pendingActions.length > 0 || isUserScrolledUp || runningJobs.length > 0) && <div className="cw-attention">
            {pendingActions.length > 0 && <button onClick={() => {
              const target = pendingActions[0];
              const element = [...(scrollRef.current?.querySelectorAll<HTMLElement>("[data-chat-message]") || [])].find(node => node.dataset.chatMessage === target.id);
              if (element) element.scrollIntoView({ behavior: "smooth", block: "center" }); else scrollToBottom(true);
            }}><MessageCircleQuestion size={14} />{pendingActions.length} {pendingActions.length === 1 ? "request needs" : "requests need"} you</button>}
            {runningJobs.length > 0 && <button onClick={() => setShowBackground(true)}><Loader2 size={13} className="cw-spin" />{runningJobs.length} running</button>}
            {isUserScrolledUp && <button onClick={() => scrollToBottom(true)}><ArrowDown size={13} />Latest</button>}
          </div>}
          <div className="cw-composer">
            {/* Inline Send Error Banner */}
            {sendError && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "6px 12px",
                  background: "rgba(239, 68, 68, 0.14)",
                  border: "1px solid rgba(239, 68, 68, 0.3)",
                  borderRadius: "6px",
                  marginBottom: "8px",
                  fontSize: "12px",
                  color: "#fca5a5",
                }}
              >
                <span role="alert">{sendError}</span>
                <div style={{ display: "flex", gap: "8px" }}>
                  <button
                    onClick={handleSend}
                    disabled={isSending}
                    style={{ background: "none", border: "none", color: "#f87171", cursor: "pointer", fontWeight: 600, fontSize: "11px" }}
                  >
                    Retry Send
                  </button>
                  <button
                    onClick={() => setSendError(null)}
                    style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: "11px" }}
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            )}

            <div className="cw-composer-entry" style={{ display: "flex", gap: "var(--sp-sm)", alignItems: "flex-end", position: "relative" }}>
              <input
                type="file"
                ref={fileInputRef}
                style={{ display: "none" }}
                onChange={handleFileUpload}
                accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.json,.md,.py,.ts,.tsx,.js,.jsx"
              />
              <button
                className="btn btn-sm btn-icon btn-ghost"
                title="Attach file"
                aria-label="Attach file"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                style={{ flexShrink: 0, padding: "8px 10px", borderRadius: "8px" }}
              >
                {uploading ? <Loader2 size={16} className="animate-spin" /> : <Folder size={16} />}
              </button>

              {/* Command Dropdown */}
              {commandOpen && commandItems.length > 0 && (
                <div style={{
                  position: "absolute", bottom: "100%", left: 0, marginBottom: "var(--sp-sm)",
                  background: "var(--bg-glass-card)", backdropFilter: "var(--blur-lg)", WebkitBackdropFilter: "var(--blur-lg)", border: "1px solid var(--border-glass)",
                  borderRadius: "var(--radius-md)", boxShadow: "0 8px 32px rgba(0,0,0,0.6)",
                  maxHeight: 240, overflowY: "auto", minWidth: 300, maxWidth: 450, zIndex: 10
                }}>
                  {commandItems.map((item, i) => {
                    const isActive = i === commandIndex;
                    return (
                      <div
                        key={item.command}
                        className="mention-item"
                        style={{
                          padding: "var(--sp-sm) var(--sp-md)",
                          display: "flex", flexDirection: "column", gap: 2, cursor: "pointer",
                          background: isActive ? "var(--bg-hover)" : "transparent",
                          borderBottom: "1px solid var(--border-glass)",
                        }}
                        onMouseEnter={() => setCommandIndex(i)}
                        onClick={(e) => { e.preventDefault(); insertCommand(item); }}
                      >
                        <span className="body-md" style={{ fontWeight: 600, color: "var(--color-primary)" }}>{item.command}</span>
                        <span className="caption" style={{ color: "var(--color-mute)" }}>{item.description}</span>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Mention Dropdown — agents + project files */}
              {mentionOpen && mentionItems.length > 0 && (
                <div style={{
                  position: "absolute", bottom: "100%", left: 0, marginBottom: "var(--sp-sm)",
                  background: "var(--bg-glass-card)", backdropFilter: "var(--blur-lg)", WebkitBackdropFilter: "var(--blur-lg)", border: "1px solid var(--border-glass)",
                  borderRadius: "var(--radius-md)", boxShadow: "0 8px 32px rgba(0,0,0,0.6)",
                  maxHeight: 240, overflowY: "auto", minWidth: 240, maxWidth: 360, zIndex: 10
                }}>
                  {mentionItems.map((item, i) => {
                    const isActive = i === mentionIndex;
                    if (item.kind === "agent") {
                      return (
                        <div key={"a:" + item.id}
                          style={{
                            padding: "var(--sp-sm) var(--sp-md)", cursor: "pointer",
                            background: isActive ? "var(--color-canvas-raised)" : "transparent",
                            display: "flex", alignItems: "center", gap: "var(--sp-sm)"
                          }}
                          onMouseEnter={() => setMentionIndex(i)}
                          onClick={() => insertMention(item)}
                        >
                          <AgentAvatar name={item.name} id={item.id} role={item.role} size={18} />
                          <span className="body-sm-strong">{item.name}</span>
                          <span className="caption" style={{ marginLeft: "auto" }}>{item.role}</span>
                        </div>
                      );
                    }
                    const base = item.path.split("/").pop();
                    const dir = item.path.includes("/") ? item.path.slice(0, item.path.lastIndexOf("/")) : "";
                    return (
                      <div key={"f:" + item.path}
                        style={{
                          padding: "var(--sp-sm) var(--sp-md)", cursor: "pointer",
                          background: isActive ? "var(--color-canvas-raised)" : "transparent",
                          display: "flex", alignItems: "center", gap: "var(--sp-sm)"
                        }}
                        onMouseEnter={() => setMentionIndex(i)}
                        onClick={() => insertMention(item)}
                      >
                        <FileCode size={15} color="var(--color-brand)" style={{ flexShrink: 0 }} />
                        <div style={{ display: "flex", flexDirection: "column", minWidth: 0, flex: 1 }}>
                          <span className="body-sm" style={{ fontWeight: 500 }}>{base}</span>
                          {dir && <span className="caption" style={{ fontSize: 9, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{dir}</span>}
                        </div>
                        <span className="caption" style={{ marginLeft: "auto", fontSize: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>file</span>
                      </div>
                    );
                  })}
                </div>
              )}

              <textarea
                ref={inputRef}
                className="input"
                style={{
                  flex: 1,
                  resize: "none",
                  minHeight: 40,
                  maxHeight: 160,
                  lineHeight: 1.5,
                  padding: "9px var(--sp-md)",
                  overflowY: "auto",
                  background: "transparent",
                  border: "none",
                  boxShadow: "none"
                }}
                aria-label="Message your team"
                placeholder="Ask a question, describe a task, or share an idea…"
                disabled={!teamId}
                value={inputText}
                rows={1}
                onChange={handleChange}
                onKeyDown={handleKeyDown}
              />
              <button
                className="btn btn-primary btn-sm"
                onClick={handleSend}
                disabled={!teamId || (!inputText.trim() && attachments.length === 0) || isSending || uploading}
                style={{
                  height: 38,
                  padding: "0 16px",
                  borderRadius: "10px",
                  background: "linear-gradient(135deg, #4f46e5, #6366f1)",
                  boxShadow: "0 4px 14px rgba(79, 70, 229, 0.4)",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  opacity: isSending ? 0.7 : 1,
                  cursor: isSending ? "not-allowed" : "pointer"
                }}
              >
                {isSending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                <span>{isSending ? "Sending..." : "Send"}</span>
              </button>
            </div>
          </div>
          <div className="cw-composer-hint"><span>@ mention · / commands</span><span><kbd>Enter</kbd> send <span aria-hidden="true"> · </span><kbd>Shift Enter</kbd> new line</span></div>
        </div>

        <style>{`@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}`}</style>

        <Modal open={rollbackOpen} onClose={() => setRollbackOpen(false)} title="Confirm Checkpoint Rollback">
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-sm)" }}>
            <p className="body-sm" style={{ color: "var(--text-primary)" }}>
              Are you sure you want to rollback to this checkpoint?
            </p>
            <div style={{
              padding: "var(--sp-sm) var(--sp-md)",
              background: "var(--bg-surface-raised)",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border-subtle)",
              fontSize: "var(--text-xs)",
              color: "var(--text-secondary)",
              display: "flex",
              flexDirection: "column",
              gap: 4
            }}>
              <div>• <b>Messages</b>: Permanently deletes all subsequent conversation turns.</div>
              <div>• <b>Files</b>: Reverts modified files and unlinks newly created files.</div>
              <div>• <b>Tasks</b>: Deletes newly created tasks and plan files from that turn.</div>
              <div>• <b>Memory</b>: Purges learnings and vector memories generated during those turns.</div>
            </div>
          </div>
          <div style={{ display: "flex", gap: "var(--sp-sm)", justifyContent: "flex-end", marginTop: "var(--sp-lg)" }}>
            <button className="btn btn-ghost" onClick={() => setRollbackOpen(false)}>Cancel</button>
            <button className="btn btn-danger" onClick={doRollbackConfirm} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <RotateCcw size={13} /> Revert Changes & Rollback
            </button>
          </div>
        </Modal>

        <Modal open={clearChatOpen} onClose={() => setClearChatOpen(false)} title="Confirm Clear Chat">
          <p className="body-sm">
            Are you sure? This will permanently delete <b>all</b> messages in this chat. This action cannot be undone.
          </p>
          <div style={{ display: "flex", gap: "var(--sp-sm)", justifyContent: "flex-end", marginTop: "var(--sp-xl)" }}>
            <button className="btn btn-ghost" onClick={() => setClearChatOpen(false)}>Cancel</button>
            <button className="btn btn-danger" onClick={doClearChatConfirm}>Clear Chat</button>
          </div>
        </Modal>
      </div >
    </div >
  );
}
