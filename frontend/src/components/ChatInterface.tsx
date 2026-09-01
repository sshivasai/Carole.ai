"use client";
import React, { useState, useRef, useEffect, useCallback, useMemo } from "react";
import type { ChatMessage, AgentConfig, CompactionEvent } from "@/lib/types";
import { 
  Send, Bot, User, Wrench, CheckCircle, XCircle, MessageCircleQuestion, 
  Loader2, ChevronDown, ChevronUp, ChevronRight, Search, Edit2, Trash2, 
  History, Square, Folder, Info, CheckSquare, Users, Lightbulb, FileCode, 
  Terminal, Copy, Check, ThumbsUp, ThumbsDown, Cpu, Scale, Sparkles, 
  FileText, Globe, GitBranch, CheckCircle2, AlertTriangle, ShieldCheck, ArrowDown
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

interface Props {
  messages: ChatMessage[];
  agents: AgentConfig[];
  onSendMessage: (text: string, attachments?: any[]) => void;
  onDeleteMessage?: (id: string) => void;
  onRollbackMessage?: (id: string) => void;
  onClearChat?: () => void;
  teamId: string | null;
  projectId?: string | null;
  onToggleExplorer?: () => void;
  onOpenFile?: (path: string) => void;
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

function ApprovalCard({ msg }: { msg: ChatMessage }) {
  const [loading, setLoading] = useState(false);
  const txId = msg.pending_approval?.tx_id || msg.tx_id;

  const decide = async (approved: boolean) => {
    if (!txId) return;
    setLoading(true);
    try {
      await api.approveToolExecution(txId, approved);
    } catch (e) {
      console.error("Failed to submit approval decision:", e);
    } finally {
      setLoading(false);
    }
  };

  return <AgentPermissionCard msg={msg} onDecide={decide} loading={loading} />;
}

function AskUserCard({ msg }: { msg: ChatMessage }) {
  const [answer, setAnswer] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

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

  const options = parsedOptions;

  const submit = async (text: string) => {
    if (!msg.question_id || !text.trim() || submitted) return;
    setLoading(true);
    try { await api.answerAgentQuestion(msg.question_id, text.trim()); setSubmitted(true); setAnswer(text.trim()); }
    catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  return (
    <div style={{ border: "1px solid var(--color-info)", borderRadius: "var(--radius-md)", padding: "var(--sp-lg)", background: "var(--bg-glass-card)", backdropFilter: "var(--blur-md)", WebkitBackdropFilter: "var(--blur-md)", boxShadow: "var(--shadow-clay)", display: "flex", flexDirection: "column", gap: "var(--sp-md)", maxWidth: 460 }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
        <MessageCircleQuestion size={15} color="var(--color-info)" />
        <span className="body-sm-strong">{msg.sender_name} asks:</span>
      </div>
      <p className="body-sm" style={{ margin: 0 }}>{parsedQuestion}</p>
      {submitted ? (
        <span className="pill pill-live" style={{ alignSelf: "flex-start" }}>Answered: {answer} ✓</span>
      ) : (
        <>
          {/* Multiple-choice option buttons */}
          {options.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {options.map((opt, i) => (
                <button
                  key={i}
                  onClick={() => submit(opt)}
                  disabled={loading}
                  style={{
                    textAlign: "left", background: "var(--color-canvas-soft, #111827)",
                    border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-sm)",
                    padding: "8px 12px", fontSize: 13, color: "var(--color-ink)",
                    cursor: "pointer", transition: "all 0.15s",
                    display: "flex", alignItems: "center", gap: 8,
                  }}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLElement).style.background = "var(--color-info)";
                    (e.currentTarget as HTMLElement).style.color = "#fff";
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLElement).style.background = "var(--color-canvas-soft, #111827)";
                    (e.currentTarget as HTMLElement).style.color = "var(--color-ink)";
                  }}
                >
                  <span style={{ fontSize: 10, color: "var(--color-mute)", width: 18, flexShrink: 0, fontWeight: 700 }}>
                    {String.fromCharCode(65 + i)}.
                  </span>
                  {opt}
                </button>
              ))}
            </div>
          )}
          {/* Free-form input */}
          <div style={{ display: "flex", gap: "var(--sp-sm)" }}>
            <input className="input" style={{ flex: 1, minHeight: 36 }}
              placeholder={options.length > 0 ? "Or type a custom answer…" : "Your answer…"}
              value={answer} onChange={e => setAnswer(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) submit(answer); }} autoFocus />
            <button className="btn btn-primary btn-sm" onClick={() => submit(answer)} disabled={loading || !answer.trim()}>
              {loading ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
            </button>
          </div>
        </>
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

function parseReasoningIntoSections(raw: string): Array<{
  type: "thought" | "tool";
  text?: string;
  toolName?: string;
  argsJson?: string;
  argsObj?: any;
  result?: string;
  isError?: boolean;
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
    return [{ type: "thought", text: raw.trim() }];
  }

  if (matches[0].index > 0) {
    const pre = raw.slice(0, matches[0].index).trim();
    if (pre) {
      sections.push({ type: "thought", text: pre });
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

    sections.push({
      type: "tool",
      toolName: current.toolName,
      argsJson: argsRaw,
      argsObj,
      result,
      isError,
    });

    if (afterResultText) {
      sections.push({ type: "thought", text: afterResultText });
    }
  }

  return sections;
}

function extractFileChanges(reasoning: string, msg: ChatMessage): ChangedFileItem[] {
  const map = new Map<string, ChangedFileItem>();

  if (msg.path) {
    const lines = (msg.arguments?.content || msg.text || "").split("\n");
    map.set(msg.path, {
      path: msg.path,
      diff: msg.diff,
      content: msg.arguments?.content || msg.text,
      action: msg.action || "modified",
      additions: msg.diff ? msg.diff.split("\n").filter(l => l.startsWith("+") && !l.startsWith("+++")).length : (lines.length || 1),
      deletions: msg.diff ? msg.diff.split("\n").filter(l => l.startsWith("-") && !l.startsWith("---")).length : 0
    });
  }

  if (reasoning) {
    const sections = parseReasoningIntoSections(reasoning);
    for (const sec of sections) {
      if (sec.type === "tool" && sec.toolName && ["write_file", "edit_file", "create_file"].includes(sec.toolName.toLowerCase())) {
        const args = sec.argsObj || {};
        const p = args.relative_path || args.path || args.TargetFile;
        if (p) {
          const content = args.content || args.CodeContent || "";
          const diff = args.diff;
          const diffLines = diff ? diff.split("\n") : (content ? content.split("\n") : []);
          const adds = diff ? diffLines.filter((l: string) => l.startsWith("+") && !l.startsWith("+++")).length : (diffLines.length || 1);
          const dels = diff ? diffLines.filter((l: string) => l.startsWith("-") && !l.startsWith("---")).length : 0;

          map.set(p, {
            path: p,
            diff,
            content,
            action: sec.toolName.toLowerCase().includes("write") ? "created" : "modified",
            additions: adds,
            deletions: dels
          });
        }
      }
    }
  }

  return Array.from(map.values());
}

function TraceToolCard({ 
  toolName, 
  argsObj, 
  argsRaw, 
  result, 
  isError, 
  defaultOpen = false,
  agentName,
  timestamp
}: { 
  toolName: string; 
  argsObj?: any; 
  argsRaw?: string; 
  result?: string; 
  isError?: boolean; 
  defaultOpen?: boolean;
  agentName?: string;
  timestamp?: string | number;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [copied, setCopied] = useState<"args" | "result" | null>(null);

  const toolMeta = getToolMeta(toolName);
  const ToolIcon = toolMeta.icon;
  const summary = getToolSummaryText(toolName, argsObj || argsRaw);

  const handleCopy = (type: "args" | "result", text: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopied(type);
    setTimeout(() => setCopied(null), 1500);
  };

  const statusColor = isError ? "var(--color-danger, #ef4444)" : result ? "var(--color-success, #10b981)" : "var(--color-warning, #f59e0b)";
  const statusBg = isError ? "rgba(239, 68, 68, 0.12)" : result ? "rgba(16, 185, 129, 0.12)" : "rgba(245, 158, 11, 0.12)";

  return (
    <div 
      style={{
        margin: "4px 0",
        borderRadius: "var(--radius-md, 8px)",
        border: "1px solid rgba(255, 255, 255, 0.08)",
        background: "rgba(15, 15, 22, 0.65)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        overflow: "hidden",
        boxShadow: "0 2px 8px rgba(0, 0, 0, 0.2)",
        transition: "border-color 0.2s, box-shadow 0.2s"
      }}
    >
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "7px 12px",
          cursor: "pointer",
          background: open ? "rgba(255, 255, 255, 0.03)" : "transparent",
          borderBottom: open ? "1px solid rgba(255, 255, 255, 0.06)" : "none",
          userSelect: "none",
          gap: 8
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0, flex: 1 }}>
          <div style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 22,
            height: 22,
            borderRadius: 6,
            background: "rgba(167, 139, 250, 0.15)",
            color: "var(--color-primary-soft, #a78bfa)",
            flexShrink: 0
          }}>
            <ToolIcon size={12} />
          </div>

          <span style={{
            fontFamily: "var(--font-mono, monospace)",
            fontSize: 11.5,
            fontWeight: 600,
            color: "var(--text-primary, #f1f5f9)",
            letterSpacing: "-0.2px"
          }}>
            {toolName}
          </span>

          {summary && (
            <span 
              title={summary}
              style={{
                fontFamily: "var(--font-mono, monospace)",
                fontSize: 10.5,
                color: "var(--text-muted, #94a3b8)",
                background: "rgba(255, 255, 255, 0.05)",
                padding: "1px 7px",
                borderRadius: 4,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                maxWidth: 260,
                border: "1px solid rgba(255, 255, 255, 0.06)"
              }}
            >
              {summary}
            </span>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {result !== undefined && result !== "" && (
            <span style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              fontSize: 10,
              fontWeight: 500,
              padding: "2px 7px",
              borderRadius: 10,
              background: statusBg,
              color: statusColor,
              border: `1px solid ${statusColor}33`
            }}>
              {isError ? <AlertTriangle size={10} /> : <Check size={10} />}
              {isError ? "Error" : "Done"}
            </span>
          )}

          {agentName && (
            <span style={{ fontSize: 10, color: "var(--color-mute)", opacity: 0.8 }}>
              {agentName}
            </span>
          )}

          <div style={{ color: "var(--color-mute)", display: "flex", alignItems: "center" }}>
            {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </div>
        </div>
      </div>

      {open && (
        <div style={{ padding: "10px 12px", display: "flex", flexDirection: "column", gap: 10, fontSize: 11 }}>
          {(argsRaw || argsObj) && (
            <div>
              <div style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 4,
                fontSize: 9.5,
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.6px",
                color: "var(--color-mute, #64748b)"
              }}>
                <span>Parameters</span>
                <button
                  onClick={(e) => handleCopy("args", argsRaw || JSON.stringify(argsObj, null, 2), e)}
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: copied === "args" ? "var(--color-success, #4ade80)" : "var(--color-mute)",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 3,
                    fontSize: 10,
                    padding: "1px 4px",
                    borderRadius: 3
                  }}
                  title="Copy parameters"
                >
                  {copied === "args" ? <Check size={10} /> : <Copy size={10} />}
                  {copied === "args" ? "Copied" : "Copy"}
                </button>
              </div>
              <pre style={{
                margin: 0,
                padding: "8px 10px",
                background: "#0c0c12",
                border: "1px solid rgba(255, 255, 255, 0.07)",
                borderRadius: 6,
                fontSize: 11,
                lineHeight: 1.45,
                fontFamily: "var(--font-mono, monospace)",
                color: "#e2e8f0",
                overflowX: "auto",
                maxHeight: 140
              }}>
                {argsRaw || JSON.stringify(argsObj, null, 2)}
              </pre>
            </div>
          )}

          {result && (
            <div>
              <div style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 4,
                fontSize: 9.5,
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.6px",
                color: isError ? "var(--color-danger, #f87171)" : "var(--color-mute, #64748b)"
              }}>
                <span>{isError ? "Error Output" : "Observation Output"}</span>
                <button
                  onClick={(e) => handleCopy("result", result, e)}
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: copied === "result" ? "var(--color-success, #4ade80)" : "var(--color-mute)",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 3,
                    fontSize: 10,
                    padding: "1px 4px",
                    borderRadius: 3
                  }}
                  title="Copy output"
                >
                  {copied === "result" ? <Check size={10} /> : <Copy size={10} />}
                  {copied === "result" ? "Copied" : "Copy"}
                </button>
              </div>
              <pre style={{
                margin: 0,
                padding: "8px 10px",
                background: isError ? "rgba(239, 68, 68, 0.05)" : "#0c0c12",
                border: isError ? "1px solid rgba(239, 68, 68, 0.2)" : "1px solid rgba(255, 255, 255, 0.07)",
                borderRadius: 6,
                fontSize: 11,
                lineHeight: 1.45,
                fontFamily: "var(--font-mono, monospace)",
                color: isError ? "#fca5a5" : "#cbd5e1",
                overflowX: "auto",
                maxHeight: 200,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word"
              }}>
                {result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ThoughtsPanel({ reasoning, isStreaming, components }: { reasoning?: string; isStreaming?: boolean; components?: any }) {
  const [elapsedSecs, setElapsedSecs] = useState(0);

  const sections = useMemo(() => parseReasoningIntoSections(reasoning || ""), [reasoning]);

  useEffect(() => {
    if (isStreaming) {
      const interval = setInterval(() => setElapsedSecs(s => s + 1), 1000);
      return () => clearInterval(interval);
    } else {
      setElapsedSecs(0);
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
    text: sec.text
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
  projectId,
  onToggleExplorer,
  onOpenFile,
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
  const [showTeamAgents, setShowTeamAgents] = useState(false);
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

  // Auto-grow textarea height up to 4 inches (384px)
  useEffect(() => {
    const textarea = inputRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(Math.max(textarea.scrollHeight, 40), 384)}px`;
    }
  }, [inputText]);

  // Wave 4.1 — Load older messages
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [hasOlderMessages, setHasOlderMessages] = useState(true);
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);
  const [feedbackState, setFeedbackState] = useState<Record<string, "up" | "down">>({});

  const childMessagesByParent = useMemo(() => {
    const groups: Record<string, ChatMessage[]> = {};
    for (const msg of messages) {
      const parentAttachment = msg.attachments?.find((a: any) => a.type === "parent_message");
      if (parentAttachment?.id) {
        const pid = parentAttachment.id;
        if (!groups[pid]) groups[pid] = [];
        groups[pid].push(msg);
      }
    }
    return groups;
  }, [messages]);

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

  // Editing state
  const [editingMsgId, setEditingMsgId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

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

  useEffect(() => {
    // If there is an active pending approval request or question, prioritize scrolling to bottom immediately
    const hasPendingApproval = messages.some(
      m => Boolean(m.pending_approval?.status === "pending" || m.type === "approval_request" || m.type === "ask_user")
    );
    if (hasPendingApproval) {
      scrollToBottom(true);
      return;
    }
    // Only auto-scroll to bottom if the user is not reading scrolled-up history
    if (!isUserScrolledUpRef.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, scrollToBottom]);

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
    { command: "/compact", description: "Manually compact the conversation history" },
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

  const handleSend = useCallback(() => {
    if (!inputText.trim() && attachments.length === 0) return;

    // ── /compact slash command ──
    // Intercept before sending to backend. Triggers manual compaction via API.
    if (inputText.trim() === "/compact") {
      setInputText("");
      setAttachments([]);
      if (onCompact) {
        onCompact().catch(() => {/* error handled in parent */});
      }
      return;
    }

    // Extract @file:path references and pass them as structured file_ref
    // attachments so the backend injects their contents into agent context
    // (sandboxed to the agent's project). The visible @file:path text is kept
    // so humans and other agents can see what was referenced.
    const fileRefRegex = /@file:(\S+)/g;
    const seen = new Set<string>();
    const fileRefs: any[] = [];
    let m: RegExpExecArray | null;
    while ((m = fileRefRegex.exec(inputText)) !== null) {
      const p = m[1].replace(/[),.;]+$/, ""); // strip trailing punctuation
      if (!seen.has(p)) { seen.add(p); fileRefs.push({ type: "file_ref", path: p }); }
    }
    onSendMessage(inputText.trim(), [...attachments, ...fileRefs]);
    setInputText("");
    setAttachments([]);
    setMentionOpen(false);
  }, [inputText, attachments, onSendMessage, onCompact]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
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

  const saveEdit = async (msgId: string) => {
    if (!editText.trim()) return;
    try { await api.editMessage(msgId, editText); }
    catch (e) { console.error(e); }
    finally { setEditingMsgId(null); }
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
    <div style={{ flex: 1, minHeight: 0, height: "100%", width: "100%", position: "relative" }}>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* Header */}
        <header className="section-header" style={{ flexShrink: 0, padding: "var(--sp-md) var(--sp-2xl)", background: "var(--bg-surface)", borderBottom: "1px solid var(--border-glass)" }}>
          <div style={{ maxWidth: "1080px", width: "100%", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "var(--sp-md)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-lg)" }}>
              <div>
                <h2 className="display-sm" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  Team Chat
                  {agents.length > 0 && (
                    <span className="pill pill-live" style={{ fontSize: 9, padding: "1px 6px" }}>
                      <span className="live-dot" /> LIVE
                    </span>
                  )}
                </h2>
                <p className="caption">Collaborate with your <del style={{ opacity: 0.6 }}>AI agents</del> <span style={{ color: "var(--color-primary)", fontWeight: 500 }}>AI teammates</span> · <kbd style={{ fontSize: 9, padding: "1px 4px", borderRadius: 3, border: "1px solid var(--color-hairline)", background: "var(--color-canvas-soft)" }}>Shift+Enter</kbd> for newline</p>
              </div>
              
              <div style={{ position: "relative" }}>
                <div 
                  onClick={() => setShowTeamAgents(!showTeamAgents)}
                  className="live-team-presence"
                  style={{ cursor: "pointer" }}
                  title="View active team agents and subagents"
                >
                  <div style={{ display: "flex", marginRight: "4px" }}>
                    {agents.slice(0, 3).map((agent, i) => (
                      <div key={agent.id} style={{ marginLeft: i > 0 ? "-8px" : 0, borderRadius: "50%", border: "2px solid var(--bg-surface)", zIndex: 3 - i }}>
                        <AgentHoverCard agent={agent} onMention={handleDirectMention}>
                          <AgentAvatar name={agent.name} id={agent.id} role={agent.role} size={22} hideBadge />
                        </AgentHoverCard>
                      </div>
                    ))}
                    {agents.length > 3 && (
                      <div style={{ marginLeft: "-8px", borderRadius: "50%", border: "2px solid var(--bg-surface)", width: 22, height: 22, background: "var(--color-canvas-raised)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 9, fontWeight: 700, color: "var(--color-primary-soft)", zIndex: 0 }}>
                        +{agents.length - 3}
                      </div>
                    )}
                  </div>
                  <span style={{ fontSize: 11, fontWeight: 600, color: "var(--color-ink)" }}>
                    {agents.length} Agent{agents.length !== 1 ? "s" : ""}
                  </span>
                  <ChevronDown size={12} color="var(--color-mute)" style={{ transform: showTeamAgents ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />
                </div>

                {showTeamAgents && (
                  <div style={{ position: "absolute", top: "100%", left: 0, marginTop: "8px", width: "280px", background: "var(--bg-glass-card)", backdropFilter: "var(--blur-lg)", WebkitBackdropFilter: "var(--blur-lg)", border: "1px solid var(--border-glass)", borderRadius: "var(--radius-md)", boxShadow: "0 12px 36px rgba(0,0,0,0.5)", zIndex: 100, overflow: "hidden" }}>
                    <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-glass)", background: "rgba(255,255,255,0.02)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <span style={{ fontSize: "11px", fontWeight: 700, letterSpacing: "0.5px", color: "var(--color-mute)", textTransform: "uppercase" }}>TEAM PRESENCE</span>
                      <span className="caption" style={{ fontSize: 10, color: "var(--color-primary)" }}>{agents.length} available</span>
                    </div>
                    <div style={{ maxHeight: "300px", overflowY: "auto", padding: "6px" }}>
                      {agents.map(a => {
                        const isSub = a.name.startsWith("Sub-") || a.name.startsWith("Subagent-");
                        return (
                          <AgentHoverCard key={a.id} agent={a} onMention={handleDirectMention}>
                            <div style={{ display: "flex", alignItems: "center", gap: "10px", padding: "7px 10px", borderRadius: "var(--radius-sm)", transition: "background var(--t-fast)", width: "100%", cursor: "pointer" }} className="hover:bg-[var(--color-canvas-raised)]">
                              <AgentAvatar name={a.name} id={a.id} role={a.role} size={28} hideBadge />
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontWeight: 600, fontSize: "12px", color: "var(--color-ink)", display: "flex", alignItems: "center", gap: 5 }}>
                                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</span>
                                  {isSub && <span className="subagent-chip" style={{ fontSize: 8, padding: "1px 4px" }}>SUB</span>}
                                </div>
                                <div className="caption" style={{ fontSize: "10px", color: "var(--color-mute)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                  {a.role || a.model || "Active Agent"}
                                </div>
                              </div>
                            </div>
                          </AgentHoverCard>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
            <div style={{ display: "flex", gap: "var(--sp-sm)", alignItems: "center" }}>
              {/* Context Window & Token Usage Meter */}
              <ContextUsageGauge
                projectId={projectId || undefined}
                teamId={teamId || undefined}
                activeModel={contextUsage?.model || agents[0]?.model || "claude-3-7-sonnet"}
                estimatedTokens={contextUsage?.estimated_tokens}
                contextWindow={contextUsage?.context_window}
                usagePercent={contextUsage?.usage_percent}
                lastTokenEvent={lastTokenEvent}
                messages={messages}
                agents={agents}
              />

              {onToggleExplorer && (
                <button className="btn btn-icon btn-outline btn-sm" onClick={onToggleExplorer} title="Toggle File Explorer">
                  <Folder size={14} />
                </button>
              )}
              <button className={`btn btn-icon btn-outline btn-sm ${searchMode ? "card-active" : ""}`}
                onClick={() => setSearchMode(s => !s)} title="Search messages">
                <Search size={14} />
              </button>
              <button className="btn btn-icon btn-outline btn-sm"
                onClick={() => setClearChatOpen(true)} title="Clear all chat messages"
                style={{ color: "var(--color-danger)" }}>
                <Trash2 size={14} />
              </button>
              <McpStatusIndicator />
            </div>
          </div>
        </header>

        {/* Search bar */}
        {searchMode && (
          <div style={{ flexShrink: 0, padding: "var(--sp-sm) var(--sp-2xl)", borderBottom: "1px solid var(--border-glass)", background: "var(--bg-glass-panel)" }}>
            <div style={{ maxWidth: "1080px", width: "100%", margin: "0 auto", display: "flex", gap: "var(--sp-sm)" }}>
              <input className="input" style={{ flex: 1, minHeight: 32 }} placeholder="Search messages..."
                value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") handleSearch(); }} autoFocus />
              <button className="btn btn-primary btn-sm" onClick={handleSearch}><Search size={13} /> Search</button>
              <button className="btn btn-ghost btn-sm" onClick={() => { setSearchMode(false); setSearchResults([]); setSearchQuery(""); }}>Clear</button>
            </div>
          </div>
        )}

        {/* Messages */}
        <div ref={scrollRef} onScroll={handleScroll} style={{ flex: 1, overflowY: "auto", minHeight: 0, padding: "var(--sp-xl) var(--sp-2xl)" }}>
          <div style={{ maxWidth: "1080px", width: "100%", margin: "0 auto", display: "flex", flexDirection: "column", gap: "var(--sp-lg)", minHeight: "100%" }}>
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
              // Hide child subagent/teammate messages from top-level chat flow
              const isChild = msg.attachments?.some((a: any) => a.type === "parent_message");
              if (isChild && !searchMode) {
                return null;
              }

              const isHuman = msg.sender_id === "human";
              const isTool = msg.type === "tool_start" || msg.type === "tool_end";
              const isApproval = msg.type === "approval_request";
              const isQuestion = msg.type === "agent_question";
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
                    <div key={msg.id} style={{ marginLeft: 8, marginBottom: 4, maxWidth: "85%" }}>
                      {sections.map((sec, idx) => (
                        sec.type === "tool" ? (
                          <TraceToolCard
                            key={idx}
                            toolName={sec.toolName!}
                            argsObj={sec.argsObj}
                            argsRaw={sec.argsJson}
                            result={sec.result}
                            isError={sec.isError}
                            agentName={msg.sender_name}
                            timestamp={msg.timestamp}
                            defaultOpen={false}
                          />
                        ) : null
                      ))}
                    </div>
                  );
                }

                const isExpanded = expandedTraces.has(msg.id);
                const toolNameMatch = (msg.text || "").match(/🛠️\s*\*\*([^\*]+)\*\*/);
                const toolName = toolNameMatch ? toolNameMatch[1] : "Tool Action";
                const toolMeta = getToolMeta(toolName);
                const ToolIcon = toolMeta.icon;

                return (
                  <div key={msg.id} style={{ display: "flex", gap: "var(--sp-sm)", alignItems: "flex-start", marginLeft: 8, marginBottom: 2 }}>
                    <AgentAvatar name={msg.sender_name || "agent"} id={msg.sender_id} role={msg.role} size={22} isStreaming={isStreaming} />
                    <div style={{ flex: 1, minWidth: 0 }}>
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
                  <div key={msg.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start", position: "relative", marginLeft: 8 }}>
                    <div style={{ position: "absolute", top: 15, bottom: -15, left: 14, width: 2, background: "var(--border-glass)", zIndex: 0 }} />
                    <div style={{ width: 30, height: 30, borderRadius: "50%", background: "var(--bg-glass-panel)", border: `1px solid ${color}`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, zIndex: 1, position: "relative" }}>
                      {icon}
                    </div>
                    <div style={{ flex: 1, minWidth: 0, paddingTop: 4 }}>
                      <span className="caption" style={{ color: "var(--color-mute)" }}>{cleanText}</span>
                      {msg.timestamp && <span className="caption" style={{ marginLeft: "var(--sp-sm)", opacity: 0.5 }}>{fmtTime(msg.timestamp)}</span>}
                    </div>
                  </div>
                );
              }
              if (isFileChange && msg.path) {
                const isHandledByAssistant = displayMessages.some(m =>
                  m.id !== msg.id &&
                  m.sender_id !== "human" &&
                  m.sender_id !== "system" &&
                  (m.reasoning?.includes(msg.path!) || m.path === msg.path)
                );
                if (isHandledByAssistant) return null;

                return (
                  <div key={msg.id} style={{ margin: "4px 0" }}>
                    <FileChangeCard
                      senderName={msg.sender_name}
                      path={msg.path}
                      diff={msg.diff}
                      content={msg.arguments?.content || msg.text}
                      action={msg.action || "modified"}
                      timestamp={msg.timestamp}
                      onOpenFile={onOpenFile}
                    />
                  </div>
                );
              }
              if (isApproval) return (
                <div key={msg.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start" }}>
                  <AgentAvatar name={msg.sender_name || "Agent"} id={msg.sender_id} role={msg.role} size={30} />
                  <div><div className="body-sm-strong" style={{ marginBottom: 4 }}>{msg.sender_name}</div><ApprovalCard msg={msg} /></div>
                </div>
              );
              if (isQuestion) return (
                <div key={msg.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start" }}>
                  <AgentAvatar name={msg.sender_name || "Agent"} id={msg.sender_id} role={msg.role} size={30} />
                  <div><div className="body-sm-strong" style={{ marginBottom: 4 }}>{msg.sender_name}</div><AskUserCard msg={msg} /></div>
                </div>
              );
              
              if (msg.type === "llm_error" && msg.llm_error) {
                const err = msg.llm_error;
                return (
                  <div key={msg.id} className="animate-fade-in" style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start", width: "100%" }}>
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
                  <div key={msg.id} className="animate-fade-in" style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start", width: "100%" }}>
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
                  <div key={msg.id} className="animate-fade-in" style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start", width: "100%" }}>
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

              const finalReasoning = rawReasoning ? (rawReasoning + "\n\n" + embeddedReasoning).trim() : embeddedReasoning.trim();
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
                <div key={msg.id} className="animate-fade-in group" style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start", flexDirection: isHuman ? "row-reverse" : "row", width: "100%" }}>

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
                  })() : (
                    <AgentAvatar
                      name={msg.sender_name || (user?.first_name ? `${user.first_name} ${user.last_name || ""}`.trim() : user?.email) || "Admin"}
                      id={msg.sender_id || user?.id}
                      role="human"
                      size={32}
                    />
                  )}
                  <div style={{ maxWidth: isHuman ? "78%" : "88%", minWidth: 0, position: "relative" }}>
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

                    {/* Edit Mode vs Normal Mode */}
                    {editingMsgId === msg.id ? (
                      <div style={{ background: "var(--bg-glass-card)", backdropFilter: "var(--blur-md)", WebkitBackdropFilter: "var(--blur-md)", border: "1px solid var(--color-primary)", padding: "var(--sp-sm)", borderRadius: "var(--radius-md)", boxShadow: "var(--shadow-clay)", display: "flex", flexDirection: "column", gap: "var(--sp-sm)", width: "100%", minWidth: 320 }}>
                        <textarea
                          className="input"
                          style={{ minHeight: 80, resize: "vertical" }}
                          value={editText}
                          onChange={e => setEditText(e.target.value)}
                          autoFocus
                        />
                        <div style={{ display: "flex", gap: "var(--sp-sm)", justifyContent: "flex-end" }}>
                          <button className="btn btn-ghost btn-sm" onClick={() => setEditingMsgId(null)}>Cancel</button>
                          <button className="btn btn-primary btn-sm" onClick={() => saveEdit(msg.id)}>Save</button>
                        </div>
                      </div>
                    ) : (
                      <div style={{
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
                            <span className="body-sm" style={{ opacity: 0.8 }}>Thinking & analyzing...</span>
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
                          <div className="markdown-body">
                            <ReactMarkdown
                              skipHtml={true}
                              remarkPlugins={[remarkGfm]}
                              components={markdownComponents}
                            >
                              {markdownText}
                            </ReactMarkdown>
                          </div>
                        )}
                        {isStreaming && <TypingIndicator />}
                        {/* Stop Generating button — visible while streaming or thinking */}
                        {(isStreaming || isThinking) && !isHuman && (
                          <div style={{ marginTop: "var(--sp-sm)", display: "flex", justifyContent: "flex-end" }}>
                            <button
                              onClick={() => api.stopAgent(msg.sender_id)}
                              style={{
                                display: "inline-flex", alignItems: "center", gap: 6,
                                padding: "4px 10px", fontSize: 11, cursor: "pointer",
                                background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.4)",
                                borderRadius: "var(--radius-sm)", color: "var(--color-danger)",
                                transition: "background 0.15s",
                              }}
                              onMouseOver={e => (e.currentTarget.style.background = "rgba(239,68,68,0.2)")}
                              onMouseOut={e => (e.currentTarget.style.background = "rgba(239,68,68,0.1)")}
                            >
                              <Square size={11} fill="currentColor" />
                              Stop generating
                            </button>
                          </div>
                        )}
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
                              />
                            </div>
                          );
                        })()}

                        {/* Thoughts Panel — renders reasoning trace + tool calls */}
                        {!isHuman && !isThinking && (
                          <ThoughtsPanel reasoning={finalReasoning} isStreaming={isStreaming} components={markdownComponents} />
                        )}

                        {/* Subagent Activities / Worker reports enqueued for this message */}
                        {!isHuman && !isThinking && childMessagesByParent[msg.id]?.length > 0 && (
                          <div style={{ marginTop: "12px", display: "flex", flexDirection: "column", gap: "10px", borderTop: "1px solid var(--border-glass)", paddingTop: "12px", width: "100%" }}>
                            {childMessagesByParent[msg.id].map(child => {
                              const isChildTaskNotification = Boolean(child.text?.includes("<task-notification>"));
                              const isChildIntermediate = child.is_intermediate === true || child.type === "tool_trace";
                              
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
                              
                              if (isChildIntermediate) {
                                const sections = parseReasoningIntoSections(child.text || "");
                                const hasTools = sections.some(s => s.type === "tool");
                                if (hasTools || sections.some(s => s.type === "thought")) {
                                  return (
                                    <div key={child.id} style={{ maxWidth: "100%", display: "flex", flexDirection: "column", gap: 4 }}>
                                      {sections.map((sec, idx) => (
                                        sec.type === "tool" ? (
                                          <TraceToolCard
                                            key={idx}
                                            toolName={sec.toolName!}
                                            argsObj={sec.argsObj}
                                            argsRaw={sec.argsJson}
                                            result={sec.result}
                                            isError={sec.isError}
                                            agentName={child.sender_name}
                                            timestamp={child.timestamp}
                                            defaultOpen={false}
                                          />
                                        ) : (
                                          <div key={idx} style={{ 
                                            display: "flex", 
                                            alignItems: "center", 
                                            gap: "8px", 
                                            padding: "6px 12px", 
                                            color: "var(--text-secondary)", 
                                            fontSize: "12px",
                                            fontStyle: "italic",
                                            opacity: 0.85
                                          }}>
                                            <Sparkles size={12} style={{ color: "var(--color-primary)", flexShrink: 0 }} />
                                            <span>{sec.text}</span>
                                          </div>
                                        )
                                      ))}
                                    </div>
                                  );
                                }
                                return null;
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
                    )}

                    {/* Action Menu Hover — anchored right on top of this message bubble */}
                    {!isThinking && !isStreaming && !isSystem && !isApproval && !isQuestion && editingMsgId !== msg.id && (
                      <div className="msg-actions" style={{
                        display: "flex", gap: 4, position: "absolute", top: -12,
                        [isHuman ? "left" : "right"]: 0,
                        background: "var(--bg-glass-panel)", backdropFilter: "var(--blur-md)", WebkitBackdropFilter: "var(--blur-md)",
                        border: "1px solid var(--border-glass)", boxShadow: "var(--shadow-clay-sm)",
                        padding: "2px 4px", borderRadius: "var(--radius-md)",
                        opacity: 0, transition: "opacity 0.15s ease", zIndex: 10,
                      }}>
                        <button className="btn btn-icon btn-ghost btn-sm" title="Copy message text"
                          onClick={() => handleCopyMessage(msg.text || "", msg.id)}
                          style={{ color: copiedMsgId === msg.id ? "var(--color-success, #4ade80)" : undefined }}>
                          {copiedMsgId === msg.id ? <Check size={12} /> : <Copy size={12} />}
                        </button>
                        {!isHuman && (
                          <>
                            <button className="btn btn-icon btn-ghost btn-sm" title="Helpful"
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
                        <button className="btn btn-icon btn-ghost btn-sm" title="Edit text only" onClick={() => { setEditingMsgId(msg.id); setEditText(msg.text || ""); }}>
                          <Edit2 size={12} />
                        </button>
                        <button className="btn btn-icon btn-ghost btn-sm" title="Delete this message only" onClick={() => doDelete(msg.id)}>
                          <Trash2 size={12} />
                        </button>
                        <button className="btn btn-icon btn-ghost btn-sm" style={{ color: "var(--color-warning)" }} title="Rollback context and file changes to this point" onClick={() => requestRollback(msg.id)}>
                          <History size={12} />
                        </button>
                      </div>
                    )}
                  </div>

                </div>
              );
            })}

            {messages.length === 0 && !searchMode && (
              <div className="empty-state" style={{ marginTop: 60 }}>
                <Bot size={40} className="empty-state-icon" />
                <h3>No messages yet</h3>
                <p>Send a message to start collaborating with your AI agent team</p>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-sm)", justifyContent: "center", marginTop: "var(--sp-md)" }}>
                  {["Summarize our latest tasks", "What tools do you have?", "Research competitor pricing"].map(s => (
                    <button key={s} className="btn btn-outline btn-sm" onClick={() => onSendMessage(s)}>{s}</button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Attachments preview */}
        {attachments.length > 0 && (
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
        )}

        {/* Input */}
        <div style={{ flexShrink: 0, padding: "var(--sp-md) var(--sp-2xl)", borderTop: "1px solid var(--border-subtle)", background: "var(--bg-app)", zIndex: 10, position: "relative" }}>
          {isUserScrolledUp && (
            <button
              onClick={() => scrollToBottom(true)}
              className="btn btn-sm"
              style={{
                position: "absolute",
                top: -38,
                left: "50%",
                transform: "translateX(-50%)",
                background: "rgba(18, 18, 36, 0.95)",
                border: "1px solid rgba(168, 85, 247, 0.4)",
                backdropFilter: "blur(12px)",
                borderRadius: 20,
                boxShadow: "0 8px 24px rgba(0,0,0,0.6)",
                padding: "3px 14px",
                fontSize: 11,
                fontWeight: 600,
                color: "#c084fc",
                zIndex: 30,
                display: "flex",
                alignItems: "center",
                gap: 6,
                cursor: "pointer",
                animation: "fadeIn 0.15s ease-out",
              }}
            >
              <ArrowDown size={12} /> Jump to latest
            </button>
          )}
          <div style={{ maxWidth: "1080px", width: "100%", margin: "0 auto" }}>
            <div style={{ display: "flex", gap: "var(--sp-sm)", alignItems: "flex-end", position: "relative" }}>

              <input
                type="file"
                ref={fileInputRef}
                style={{ display: "none" }}
                onChange={handleFileUpload}
                accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.json,.md,.py,.ts,.tsx,.js,.jsx"
              />
              <button className="btn btn-sm btn-icon btn-ghost" title="Attach file" onClick={() => fileInputRef.current?.click()} disabled={uploading} style={{ flexShrink: 0, padding: "8px 12px" }}>
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
                className="input" style={{ flex: 1, resize: "none", minHeight: 40, maxHeight: 384, lineHeight: 1.5, padding: "9px var(--sp-md)", overflowY: "auto" }}
                placeholder="Message your team... (@ to mention an agent or a file · Enter to send, Shift+Enter for newline)"
                value={inputText} rows={1}
                onChange={handleChange}
                onKeyDown={handleKeyDown}
              />
              <button className="btn btn-primary btn-sm" onClick={handleSend} disabled={!inputText.trim() && attachments.length === 0} style={{ height: 40 }}>
                <Send size={14} /> Send
              </button>
            </div>
          </div>
        </div>

      <style>{`@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}`}</style>

      <Modal open={rollbackOpen} onClose={() => setRollbackOpen(false)} title="Confirm Rollback">
        <p className="body-sm">
          Are you sure? This will delete this message, all following messages, and revert any files the agents modified during those messages.
        </p>
        <div style={{ display: "flex", gap: "var(--sp-sm)", justifyContent: "flex-end", marginTop: "var(--sp-xl)" }}>
          <button className="btn btn-ghost" onClick={() => setRollbackOpen(false)}>Cancel</button>
          <button className="btn btn-danger" onClick={doRollbackConfirm}>Rollback</button>
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
      </div>
    </div>
  );
}
