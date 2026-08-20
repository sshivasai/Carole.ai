"use client";
import React, { useState, useRef, useEffect, useCallback, useMemo } from "react";
import type { ChatMessage, AgentConfig } from "@/lib/types";
import { 
  Send, Bot, User, Wrench, CheckCircle, XCircle, MessageCircleQuestion, 
  Loader2, ChevronDown, ChevronUp, ChevronRight, Search, Edit2, Trash2, 
  History, Square, Folder, Info, CheckSquare, Users, Lightbulb, FileCode, 
  Terminal, Copy, Check, ThumbsUp, ThumbsDown, Cpu, Scale, Sparkles, 
  FileText, Globe, GitBranch, CheckCircle2, AlertTriangle, ShieldCheck
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "@/hooks/useApi";
import Modal from "./Modal";
import AgentAvatar from "./AgentAvatar";
import AppSpinner from "./AppSpinner";
import { DiffViewer } from "./DiffViewer";
import { McpStatusIndicator } from "./McpStatusIndicator";

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
  const taskIdMatch = text.match(/<task_id>(.*?)<\/task_id>/);
  const agentMatch = text.match(/<agent>(.*?)<\/agent>/);
  const statusMatch = text.match(/<status>(.*?)<\/status>/);
  const resultMatch = text.match(/<result>([\s\S]*?)<\/result>/);

  const taskId = taskIdMatch ? taskIdMatch[1].trim() : "";
  const agentName = agentMatch ? agentMatch[1].trim() : "";
  const status = statusMatch ? statusMatch[1].trim() : "completed";
  const result = resultMatch ? resultMatch[1].trim() : text;

  const isSuccess = status.toLowerCase() === "completed" || status.toLowerCase() === "success";

  return (
    <div className="task-notif-card" style={{ maxWidth: 640 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 13 }}>{isSuccess ? "✅" : "⚠️"}</span>
          <span className="body-sm-strong" style={{ color: isSuccess ? "#34d399" : "#f87171" }}>
            Subagent Task {isSuccess ? "Completed" : "Report"}
          </span>
          {agentName && <span className="subagent-chip" style={{ fontSize: 10 }}>🤖 {agentName}</span>}
        </div>
        {taskId && <span className="caption" style={{ fontFamily: "monospace", fontSize: 10, opacity: 0.7 }}>ID: {taskId.slice(0, 8)}</span>}
      </div>
      <div className="markdown-body" style={{ fontSize: 12, lineHeight: 1.5, color: "var(--color-ink)" }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{result}</ReactMarkdown>
      </div>
    </div>
  );
}

function ApprovalCard({ msg }: { msg: ChatMessage }) {
  const backendStatus = (msg as any).status;
  const [localStatus, setLocalStatus] = useState<"pending" | "approved" | "denied">("pending");
  const status = backendStatus && backendStatus !== "pending" ? backendStatus : localStatus;

  const [loading, setLoading] = useState(false);
  const decide = async (approved: boolean) => {
    if (!msg.tx_id || status !== "pending") return;
    setLoading(true);
    setLocalStatus(approved ? "approved" : "denied");
    try {
      await api.approveToolExecution(msg.tx_id, approved);
    } catch (e: any) {
      const errText = e?.message || e?.body || String(e);
      if (e?.status === 404 || errText.includes("already resolved") || errText.includes("not found")) {
        console.log(`[ApprovalCard] Transaction ${msg.tx_id} already resolved on server.`);
      } else {
        console.error("Failed to approve tool execution:", e);
        setLocalStatus("pending");
      }
    } finally {
      setLoading(false);
    }
  };

  const isJudgeEvaluating = msg.text?.includes("Judge AI is evaluating") || msg.text?.includes("Judge");
  const toolMeta = getToolMeta(msg.tool_name || "");
  const ToolIcon = toolMeta.icon;

  const borderColor = status === "pending" ? (isJudgeEvaluating ? "var(--color-primary)" : "var(--color-warning)") : status === "approved" ? "var(--color-success)" : "var(--color-danger)";

  return (
    <div className="judge-card-evaluating" style={{ border: `1px solid ${borderColor}`, display: "flex", flexDirection: "column", gap: "var(--sp-md)", maxWidth: 500 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
          {isJudgeEvaluating ? <Scale size={16} color="var(--color-primary)" className="animate-pulse" /> : <AlertTriangle size={16} color="var(--color-warning)" />}
          <span className="body-sm-strong">{isJudgeEvaluating ? "Judge AI Security Gate" : "Approval Required"}</span>
        </div>
        {status !== "pending" ? (
          <span className={`pill ${status === "approved" ? "pill-live" : "pill-error"}`}>{status.toUpperCase()}</span>
        ) : (
          <span className="pill" style={{ background: "rgba(167, 139, 250, 0.15)", color: "var(--color-primary-soft)", border: "1px solid rgba(167, 139, 250, 0.3)" }}>
            PENDING DECISION
          </span>
        )}
      </div>

      <div className="body-sm" style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <span className="text-mute">Agent</span>
        <strong style={{ color: "var(--color-ink)" }}>{msg.sender_name}</strong>
        <span className="text-mute">requests execution:</span>
        <span className={toolMeta.className} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <ToolIcon size={11} /> {msg.tool_name}
        </span>
      </div>

      {msg.text && (
        <div className="body-sm" style={{ whiteSpace: "pre-wrap", background: "var(--color-canvas)", padding: "var(--sp-sm) var(--sp-md)", borderRadius: "var(--radius-sm)", borderLeft: "2px solid var(--color-primary)", color: "var(--color-body)", fontSize: 11 }}>
          {msg.text}
        </div>
      )}

      {msg.arguments && Object.keys(msg.arguments).length > 0 && (
        <div style={{ background: "var(--color-canvas)", borderRadius: "var(--radius-xs)", padding: "var(--sp-sm) var(--sp-md)", border: "1px solid var(--color-hairline)" }}>
          <div className="caption" style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4, color: "var(--color-mute)" }}>Arguments:</div>
          <pre style={{ fontSize: 10, overflowX: "auto", maxHeight: 140, margin: 0, color: "var(--color-ink)", fontFamily: "var(--font-mono, monospace)" }}>
            {JSON.stringify(msg.arguments, null, 2)}
          </pre>
        </div>
      )}

      {status === "pending" && (
        <div style={{ display: "flex", gap: "var(--sp-md)", marginTop: 2 }}>
          <button className="btn btn-primary btn-sm" style={{ flex: 1 }} disabled={loading} onClick={() => decide(true)}>
            {loading ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle size={12} />} Approve Override
          </button>
          <button className="btn btn-danger btn-sm" style={{ flex: 1 }} disabled={loading} onClick={() => decide(false)}>
            <XCircle size={12} /> Deny Execution
          </button>
        </div>
      )}
    </div>
  );
}

function AskUserCard({ msg }: { msg: ChatMessage }) {
  const [answer, setAnswer] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const submit = async () => {
    if (!msg.question_id || !answer.trim() || submitted) return;
    setLoading(true);
    try { await api.answerAgentQuestion(msg.question_id, answer.trim()); setSubmitted(true); }
    catch (e) { console.error(e); }
    finally { setLoading(false); }
  };
  return (
    <div style={{ border: "1px solid var(--color-info)", borderRadius: "var(--radius-md)", padding: "var(--sp-lg)", background: "var(--bg-glass-card)", backdropFilter: "var(--blur-md)", WebkitBackdropFilter: "var(--blur-md)", boxShadow: "var(--shadow-clay)", display: "flex", flexDirection: "column", gap: "var(--sp-md)", maxWidth: 460 }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
        <MessageCircleQuestion size={15} color="var(--color-info)" />
        <span className="body-sm-strong">{msg.sender_name} asks:</span>
      </div>
      <p className="body-sm" style={{ margin: 0 }}>{msg.question || msg.text}</p>
      {submitted ? (
        <span className="pill pill-live" style={{ alignSelf: "flex-start" }}>Answered ✓</span>
      ) : (
        <div style={{ display: "flex", gap: "var(--sp-sm)" }}>
          <input className="input" style={{ flex: 1, minHeight: 36 }} placeholder="Your answer..."
            value={answer} onChange={e => setAnswer(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) submit(); }} autoFocus />
          <button className="btn btn-primary btn-sm" onClick={submit} disabled={loading || !answer.trim()}>
            {loading ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
          </button>
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

function ThoughtsPanel({ reasoning, isStreaming, components }: { reasoning?: string; isStreaming?: boolean; components?: any }) {
  const [open, setOpen] = useState<boolean>(Boolean(isStreaming));
  const scrollRef = useRef<HTMLDivElement>(null);
  const [elapsedSecs, setElapsedSecs] = useState(0);

  useEffect(() => {
    if (isStreaming) {
      setOpen(true);
      const interval = setInterval(() => setElapsedSecs(s => s + 1), 1000);
      return () => clearInterval(interval);
    } else {
      setElapsedSecs(0);
    }
  }, [isStreaming]);

  useEffect(() => {
    if (open && isStreaming && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [reasoning, open, isStreaming]);

  if (!reasoning) return null;
  return (
    <div style={{ marginTop: "var(--sp-sm)", borderTop: "1px dashed var(--color-hairline)", paddingTop: "var(--sp-sm)" }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: "flex", alignItems: "center", gap: "var(--sp-xs)",
          background: "none", border: "none", cursor: "pointer",
          color: "var(--color-mute)", fontSize: 11, padding: 0
        }}
      >
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        <span style={{ fontSize: 10, letterSpacing: "0.3px", fontWeight: 600, color: "var(--color-primary-soft)" }}>
          🧠 Reasoning Trace & Tool Activity
        </span>
        {isStreaming && (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, marginLeft: 6, color: "var(--color-primary)", fontSize: 10 }}>
            <AppSpinner size={12} />
            <span style={{ fontSize: 9, opacity: 0.9, fontWeight: 500 }}>Executing ({elapsedSecs}s)...</span>
          </span>
        )}
      </button>
      {open && (
        <div
          ref={scrollRef}
          className="thoughts-scrollbar markdown-body"
          style={{
            marginTop: "var(--sp-sm)", background: "var(--bg-glass-panel)", backdropFilter: "var(--blur-md)", WebkitBackdropFilter: "var(--blur-md)",
            border: "1px solid var(--border-glass)", borderRadius: "var(--radius-sm)",
            padding: "var(--sp-md)", fontSize: 11, color: "var(--color-body)",
            lineHeight: 1.6, maxHeight: 320, overflowY: "auto"
          }}
        >
          <ReactMarkdown skipHtml={true} remarkPlugins={[remarkGfm]} components={components}>
            {reasoning}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );
}

export default function ChatInterface({ messages, agents, onSendMessage, onDeleteMessage, onRollbackMessage, onClearChat, teamId, projectId, onToggleExplorer, onOpenFile }: Props) {
  const [inputText, setInputText] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState(false);
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [showTeamAgents, setShowTeamAgents] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Wave 4.1 — Load older messages
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [hasOlderMessages, setHasOlderMessages] = useState(true);
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);
  const [feedbackState, setFeedbackState] = useState<Record<string, "up" | "down">>({});

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

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

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

  const handleSend = useCallback(() => {
    if (!inputText.trim() && attachments.length === 0) return;
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
  }, [inputText, attachments, onSendMessage]);

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

    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }, [handleSend, mentionOpen, mentionItems, mentionIndex]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setInputText(val);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";

    const sel = e.target.selectionStart;
    const textBefore = val.slice(0, sel);
    const atMatch = textBefore.match(/@([^\s]*)$/);
    if (atMatch) {
      setMentionOpen(true);
      setMentionQuery(atMatch[1]);
      setMentionIndex(0);
      void ensureFileTree();
    } else {
      setMentionOpen(false);
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
    if (onDeleteMessage) onDeleteMessage(msgId);
    try { await api.deleteMessage(msgId); }
    catch (e: any) {
      // 404 is expected for ephemeral WS-only messages (typing, tool_start, streaming)
      // that were never persisted to the DB. Swallow silently.
      if (e?.status !== 404) console.error("deleteMessage failed:", e);
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
    setRollbackOpen(false);
    if (onRollbackMessage) onRollbackMessage(rollbackMsgId);
    try { await api.rollbackFromMessage(rollbackMsgId); }
    catch (e: any) {
      if (e?.status !== 404) console.error("rollbackFromMessage failed:", e);
    }
    finally { setRollbackMsgId(null); }
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
                  <span className="pill pill-live" style={{ fontSize: 9, padding: "1px 6px" }}>
                    <span className="live-dot" /> LIVE
                  </span>
                </h2>
                <p className="caption">Collaborate with your AI agents · <kbd style={{ fontSize: 9, padding: "1px 4px", borderRadius: 3, border: "1px solid var(--color-hairline)", background: "var(--color-canvas-soft)" }}>Shift+Enter</kbd> for newline</p>
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
                        <AgentAvatar name={agent.name} avatarSeed={agent.id} size={22} />
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
                          <div key={a.id} style={{ display: "flex", alignItems: "center", gap: "10px", padding: "7px 10px", borderRadius: "var(--radius-sm)", transition: "background var(--t-fast)" }} className="hover:bg-[var(--color-canvas-raised)]">
                            <AgentAvatar name={a.name} avatarSeed={a.id} size={28} />
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
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
            <div style={{ display: "flex", gap: "var(--sp-sm)", alignItems: "center" }}>
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
        <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", minHeight: 0, padding: "var(--sp-xl) var(--sp-2xl)" }}>
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
            {displayMessages.map(msg => {
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
                const isExpanded = expandedTraces.has(msg.id);
                // Extract tool name if formatted like 🛠️ **tool_name**
                const toolNameMatch = (msg.text || "").match(/🛠️\s*\*\*([^\*]+)\*\*/);
                const toolName = toolNameMatch ? toolNameMatch[1] : "Tool Action";
                const toolMeta = getToolMeta(toolName);
                const ToolIcon = toolMeta.icon;

                return (
                  <div key={msg.id} style={{ display: "flex", gap: "var(--sp-sm)", alignItems: "flex-start", marginLeft: 8, marginBottom: 2 }}>
                    <AgentAvatar name={msg.sender_name || "agent"} id={msg.sender_id} size={22} isStreaming={isStreaming} />
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
              if (isFileChange) return (
                <div
                  key={msg.id}
                  onClick={() => msg.path && onOpenFile?.(msg.path)}
                  style={{
                    display: "flex", gap: "var(--sp-md)", alignItems: "center", background: "var(--bg-glass-panel)",
                    padding: "10px 14px", borderRadius: 8, margin: "8px 0",
                    cursor: msg.path && onOpenFile ? "pointer" : "default",
                    border: "1px solid var(--color-hairline)",
                    transition: "background 0.15s, border-color 0.15s",
                  }}
                  className="hover:bg-[var(--color-surface)]"
                  title={msg.path && onOpenFile ? `Open ${msg.path} in editor` : undefined}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "10px", flex: 1, minWidth: 0 }}>
                    <div style={{ background: "var(--color-surface)", padding: 6, borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <FileCode size={16} color="var(--color-brand)" />
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                      <span className="body-sm" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        <strong style={{ color: "var(--color-body)" }}>{msg.sender_name || "Agent"}</strong> modified <strong style={{ color: "var(--color-body)" }}>{msg.path?.split('/').pop() || msg.path}</strong>
                      </span>
                      <span className="caption" style={{ color: "var(--color-mute)" }}>{msg.path && onOpenFile ? "Click to open in editor" : "View details in the Activity Log tab"}</span>
                    </div>
                  </div>
                  {msg.timestamp && <span className="caption" style={{ opacity: 0.5 }}>{fmtTime(msg.timestamp)}</span>}
                </div>
              );
              if (isApproval) return (
                <div key={msg.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start" }}>
                  <AgentAvatar name={msg.sender_name || "Agent"} id={msg.sender_id} size={30} />
                  <div><div className="body-sm-strong" style={{ marginBottom: 4 }}>{msg.sender_name}</div><ApprovalCard msg={msg} /></div>
                </div>
              );
              if (isQuestion) return (
                <div key={msg.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start" }}>
                  <AgentAvatar name={msg.sender_name || "Agent"} id={msg.sender_id} size={30} />
                  <div><div className="body-sm-strong" style={{ marginBottom: 4 }}>{msg.sender_name}</div><AskUserCard msg={msg} /></div>
                </div>
              );

              // Check if message is a subagent task notification report
              const isTaskNotification = Boolean(msg.text?.includes("<task-notification>"));
              if (isTaskNotification) {
                return (
                  <div key={msg.id} className="animate-fade-in" style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start", width: "100%" }}>
                    <AgentAvatar name={msg.sender_name || "Subagent"} id={msg.sender_id} size={32} />
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

                  <AgentAvatar
                    name={msg.sender_name || (isHuman ? "admin" : "Agent")}
                    id={msg.sender_id}
                    role={msg.role}
                    size={32}
                    isStreaming={isStreaming}
                    isThinking={isThinking}
                  />
                  <div style={{ maxWidth: isHuman ? "78%" : "88%", minWidth: 0, position: "relative" }}>
                    {!isHuman && (
                      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: 3 }}>
                        <span className="body-sm-strong">{msg.sender_name}</span>
                        {msg.role && <span className="caption">{msg.role}</span>}
                        {msg.timestamp && <span className="caption" style={{ marginLeft: "auto" }}>{fmtTime(msg.timestamp)}</span>}
                      </div>
                    )}
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
                        {/* Thoughts Panel — renders reasoning trace + tool calls */}
                        {!isHuman && !isThinking && (
                          <ThoughtsPanel reasoning={finalReasoning} isStreaming={isStreaming} components={markdownComponents} />
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
        <div style={{ flexShrink: 0, padding: "var(--sp-md) var(--sp-2xl)", borderTop: "1px solid var(--border-subtle)", background: "var(--bg-app)", zIndex: 10 }}>
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
                className="input" style={{ flex: 1, resize: "none", minHeight: 40, maxHeight: 160, lineHeight: 1.5, padding: "9px var(--sp-md)" }}
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
