"use client";
import React, { useState, useRef, useEffect, useCallback } from "react";
import type { ChatMessage, AgentConfig } from "@/lib/types";
import { Send, Bot, User, Wrench, CheckCircle, XCircle, MessageCircleQuestion, Loader2, Copy, ChevronDown, ChevronUp, Mic, MicOff, Search, Edit2, Trash2, History, Square, Folder } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "@/hooks/useApi";
import { DiffViewer } from "@/components/DiffViewer";

interface Props {
  messages: ChatMessage[];
  agents: AgentConfig[];
  onSendMessage: (text: string, attachments?: any[]) => void;
  onDeleteMessage?: (id: string) => void;
  onRollbackMessage?: (id: string) => void;
  teamId: string | null;
  onToggleExplorer?: () => void;
}

const AVATAR_COLORS = ["#3b82f6","#8b5cf6","#00d992","#f97316","#ef4444","#eab308"];
function avatarColor(name: string) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = name.charCodeAt(i) + ((h << 5) - h);
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length];
}
function fmtTime(ts?: string | number) {
  if (!ts) return "";
  return new Date(typeof ts === "number" ? ts : ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}


function ApprovalCard({ msg }: { msg: ChatMessage }) {
  const [status, setStatus] = useState<"pending"|"approved"|"denied">("pending");
  const [loading, setLoading] = useState(false);
  const decide = async (approved: boolean) => {
    if (!msg.tx_id || status !== "pending") return;
    setLoading(true);
    try { await api.approveToolExecution(msg.tx_id, approved); setStatus(approved ? "approved" : "denied"); }
    catch (e) { console.error(e); }
    finally { setLoading(false); }
  };
  const borderColor = status === "pending" ? "var(--color-warning)" : status === "approved" ? "var(--color-primary)" : "var(--color-danger)";
  return (
    <div style={{ border: `1px solid ${borderColor}`, borderRadius: "var(--radius-md)", padding: "var(--sp-lg)", background: "var(--color-canvas-raised)", display: "flex", flexDirection: "column", gap: "var(--sp-md)", maxWidth: 460 }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
        <span style={{ fontSize: 16 }}>🛑</span>
        <span className="body-sm-strong">Approval Required</span>
        {status !== "pending" && <span className={`pill ${status === "approved" ? "pill-live" : "pill-error"}`}>{status.toUpperCase()}</span>}
      </div>
      <div className="body-sm">
        <span className="text-mute">Agent </span><strong>{msg.sender_name}</strong>
        <span className="text-mute"> wants to run </span>
        <span className="code-inline">{msg.tool_name}</span>
      </div>
      {msg.arguments && Object.keys(msg.arguments).length > 0 && (
        <pre style={{ fontSize: 11, background: "var(--color-canvas)", borderRadius: "var(--radius-xs)", padding: "var(--sp-sm) var(--sp-md)", overflowX: "auto", maxHeight: 120, border: "1px solid var(--color-hairline)", margin: 0 }}>
          {JSON.stringify(msg.arguments, null, 2)}
        </pre>
      )}
      {status === "pending" && (
        <div style={{ display: "flex", gap: "var(--sp-md)" }}>
          <button className="btn btn-primary btn-sm" style={{ flex: 1 }} disabled={loading} onClick={() => decide(true)}>
            {loading ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle size={12} />} Approve
          </button>
          <button className="btn btn-danger btn-sm" style={{ flex: 1 }} disabled={loading} onClick={() => decide(false)}>
            <XCircle size={12} /> Deny
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
    <div style={{ border: "1px solid var(--color-info)", borderRadius: "var(--radius-md)", padding: "var(--sp-lg)", background: "var(--color-canvas-raised)", display: "flex", flexDirection: "column", gap: "var(--sp-md)", maxWidth: 460 }}>
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
  const preview = obs.length > 120 ? obs.slice(0, 120) + "…" : obs;
  return (
    <div style={{ paddingLeft: 36, display: "flex", flexDirection: "column", gap: 2 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--color-mute)", fontSize: 12 }}>
        <Wrench size={11} style={{ color: isEnd ? "var(--color-primary)" : "var(--color-warning)" }} />
        <span className="code-inline" style={{ padding: "0 4px", fontSize: 11 }}>{msg.tool_name}</span>
        <span>{isEnd ? "done" : "running…"}</span>
        {isEnd && obs && (
          <button onClick={() => setOpen(o => !o)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--color-mute)", display: "flex", padding: 0 }}>
            {open ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          </button>
        )}
      </div>
      {isEnd && obs && open && (
        <pre style={{ fontSize: 11, background: "var(--color-canvas-soft)", border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-xs)", padding: "var(--sp-sm) var(--sp-md)", overflow: "auto", maxHeight: 200, color: "var(--color-body)", marginLeft: 17 }}>
          {obs}
        </pre>
      )}
    </div>
  );
}

function ThoughtsPanel({ reasoning, isStreaming }: { reasoning?: string; isStreaming?: boolean }) {
  const [open, setOpen] = useState(false);
  if (!reasoning) return null;
  return (
    <div style={{ marginTop: "var(--sp-sm)", borderTop: "1px dashed var(--color-hairline)", paddingTop: "var(--sp-sm)" }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: "flex", alignItems: "center", gap: "var(--sp-xs)",
          background: "none", border: "none", cursor: "pointer",
          color: "var(--color-mute)", fontSize: 12, padding: 0
        }}
      >
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        <span style={{ fontSize: 11, letterSpacing: "0.3px", fontWeight: 600 }}>🧠 Thoughts</span>
        {isStreaming && <Loader2 size={10} className="animate-spin" style={{ marginLeft: 4, color: "var(--color-warning)" }} />}
      </button>
      {open && (
        <div style={{
          marginTop: "var(--sp-sm)", background: "var(--color-canvas)",
          border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-sm)",
          padding: "var(--sp-md)", fontSize: 12, color: "var(--color-body)",
          maxHeight: 400, overflowY: "auto", lineHeight: 1.6,
        }}>
          <div className="markdown-body" style={{ fontSize: 12 }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
              code: ({node, className, children, ...props}) => {
                const isBlock = /language-(\w+)/.exec(className || '');
                return isBlock ? (
                  <pre className="code-block" style={{ fontSize: 11, marginTop: 6, marginBottom: 6 }}>
                    <code className={className} {...props}>{children}</code>
                  </pre>
                ) : <code className="code-inline" style={{ fontSize: 11 }} {...props}>{children}</code>;
              }
            }}>
              {reasoning}
            </ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ChatInterface({ messages, agents, onSendMessage, onDeleteMessage, onRollbackMessage, teamId, onToggleExplorer }: Props) {
  const [inputText, setInputText] = useState("");
  const [recording, setRecording]   = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [searchQuery, setSearchQuery]   = useState("");
  const [searchMode, setSearchMode]     = useState(false);
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const mediaRef  = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  // Editing state
  const [editingMsgId, setEditingMsgId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  // Attachments state
  const [attachments, setAttachments] = useState<any[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Mention state
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionQuery, setMentionQuery] = useState("");
  const [mentionIndex, setMentionIndex] = useState(0);

  const filteredAgents = agents.filter(a => a.name.toLowerCase().includes(mentionQuery.toLowerCase()));

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  const handleSend = useCallback(() => {
    if (!inputText.trim() && attachments.length === 0) return;
    onSendMessage(inputText.trim(), attachments);
    setInputText("");
    setAttachments([]);
    setMentionOpen(false);
  }, [inputText, attachments, onSendMessage]);

  const insertMention = (agentName: string) => {
    const textBefore = inputText.slice(0, inputRef.current?.selectionStart || inputText.length);
    const atIndex = textBefore.lastIndexOf("@");
    if (atIndex !== -1) {
      const newText = inputText.slice(0, atIndex) + "@" + agentName + " " + inputText.slice(textBefore.length);
      setInputText(newText);
      setMentionOpen(false);
      setTimeout(() => inputRef.current?.focus(), 10);
    }
  };

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (mentionOpen) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setMentionIndex(i => (i + 1) % filteredAgents.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setMentionIndex(i => (i - 1 + filteredAgents.length) % filteredAgents.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        if (filteredAgents.length > 0) insertMention(filteredAgents[mentionIndex].name);
        return;
      }
      if (e.key === "Escape") {
        setMentionOpen(false);
        return;
      }
    }

    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }, [handleSend, mentionOpen, filteredAgents, mentionIndex]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setInputText(val);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";

    const sel = e.target.selectionStart;
    const textBefore = val.slice(0, sel);
    const atMatch = textBefore.match(/@(\w*)$/);
    if (atMatch) {
      setMentionOpen(true);
      setMentionQuery(atMatch[1]);
      setMentionIndex(0);
    } else {
      setMentionOpen(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files?.length) return;
    setUploading(true);
    const file = e.target.files[0];
    try {
      const res = await api.uploadFile(file);
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
    catch (e) { console.error(e); }
  };

  const doRollback = async (msgId: string) => {
    if (!confirm("Are you sure? This will delete this message, all following messages, and revert any files the agents modified during those messages.")) return;
    if (onRollbackMessage) onRollbackMessage(msgId);
    try { await api.rollbackFromMessage(msgId); }
    catch (e) { console.error(e); }
  };

  const toggleRecord = async () => {
    if (recording) {
      mediaRef.current?.stop();
      setRecording(false);
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mr = new MediaRecorder(stream);
        chunksRef.current = [];
        mr.ondataavailable = e => chunksRef.current.push(e.data);
        mr.onstop = async () => {
          stream.getTracks().forEach(t => t.stop());
          if (!teamId) return;
          setTranscribing(true);
          try {
            const blob = new Blob(chunksRef.current, { type: "audio/webm" });
            const res = await api.transcribeAudio(teamId, blob);
            if (res.text) setInputText(t => t + res.text);
          } catch { /* ignore */ }
          finally { setTranscribing(false); }
        };
        mr.start();
        mediaRef.current = mr;
        setRecording(true);
      } catch { /* microphone denied */ }
    }
  };

  const handleSearch = useCallback(async () => {
    if (!teamId || !searchQuery.trim()) return;
    try {
      const r = await api.searchMessages(teamId, searchQuery);
      setSearchResults(r);
    } catch { /* ignore */ }
  }, [teamId, searchQuery]);

  const displayMessages = searchMode ? searchResults.map((m: any) => ({ ...m, id: m.id, type: "message", timestamp: m.created_at })) : messages;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <header className="section-header" style={{ padding: "var(--sp-md) var(--sp-2xl)", background: "var(--color-canvas)" }}>
        <div>
          <h2 className="display-sm">Team Chat</h2>
          <p className="caption">Collaborate with your AI agents · <kbd style={{ fontSize: 10, padding: "1px 4px", borderRadius: 3, border: "1px solid var(--color-hairline)", background: "var(--color-canvas-soft)" }}>Shift+Enter</kbd> for newline</p>
        </div>
        <div style={{ display: "flex", gap: "var(--sp-sm)" }}>
          {onToggleExplorer && (
            <button className="btn btn-icon btn-outline btn-sm" onClick={onToggleExplorer} title="Toggle File Explorer">
              <Folder size={14} />
            </button>
          )}
          <button className={`btn btn-icon btn-outline btn-sm ${searchMode ? "card-active" : ""}`}
            onClick={() => setSearchMode(s => !s)} title="Search messages">
            <Search size={14} />
          </button>
        </div>
      </header>

      {/* Search bar */}
      {searchMode && (
        <div style={{ padding: "var(--sp-sm) var(--sp-2xl)", borderBottom: "1px solid var(--color-hairline)", display: "flex", gap: "var(--sp-sm)" }}>
          <input className="input" style={{ flex: 1, minHeight: 32 }} placeholder="Search messages..."
            value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") handleSearch(); }} autoFocus />
          <button className="btn btn-primary btn-sm" onClick={handleSearch}><Search size={13} /> Search</button>
          <button className="btn btn-ghost btn-sm" onClick={() => { setSearchMode(false); setSearchResults([]); setSearchQuery(""); }}>Clear</button>
        </div>
      )}

      {/* Messages */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "var(--sp-2xl)", display: "flex", flexDirection: "column", gap: "var(--sp-lg)" }}>
        {displayMessages.map(msg => {
          const isHuman    = msg.sender_id === "human";
          const isTool     = msg.type === "tool_start" || msg.type === "tool_end";
          const isApproval = msg.type === "approval_request";
          const isQuestion = msg.type === "agent_question";
          const isFileChange = msg.type === "file_change";
          const isSystem   = msg.sender_id === "system";
          const isStreaming = msg.type === "streaming";

          if (isTool)     return <ToolRow key={msg.id} msg={msg} />;
          if (isSystem)   return <div key={msg.id} style={{ textAlign: "center" }}><span className="eyebrow">{msg.text}</span></div>;
          if (isFileChange) return (
            <div key={msg.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start" }}>
              <div style={{ width: 30, height: 30, borderRadius: "50%", background: avatarColor(msg.sender_name || "agent"), display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><Bot size={14} color="#fff" /></div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: 4 }}>
                  <span className="body-sm-strong">{msg.sender_name || "agent"}</span>
                  <span className="caption">modified file: {msg.path} ({msg.action})</span>
                  {msg.timestamp && <span className="caption" style={{ marginLeft: "auto" }}>{fmtTime(msg.timestamp)}</span>}
                </div>
                <DiffViewer diff={msg.diff || ""} path={msg.path} maxLinesVisible={20} />
              </div>
            </div>
          );
          if (isApproval) return (
            <div key={msg.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start" }}>
              <div style={{ width: 30, height: 30, borderRadius: "50%", background: avatarColor(msg.sender_name || ""), display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><Bot size={14} color="#fff" /></div>
              <div><div className="body-sm-strong" style={{ marginBottom: 4 }}>{msg.sender_name}</div><ApprovalCard msg={msg} /></div>
            </div>
          );
          if (isQuestion)  return (
            <div key={msg.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start" }}>
              <div style={{ width: 30, height: 30, borderRadius: "50%", background: avatarColor(msg.sender_name || ""), display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><Bot size={14} color="#fff" /></div>
              <div><div className="body-sm-strong" style={{ marginBottom: 4 }}>{msg.sender_name}</div><AskUserCard msg={msg} /></div>
            </div>
          );

          const ac = isHuman ? "var(--color-canvas-raised)" : avatarColor(msg.sender_name || "agent");
          const isThinking = msg.type === "thinking";

          return (
            <div key={msg.id} className="animate-fade-in group" style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start", flexDirection: isHuman ? "row-reverse" : "row", position: "relative" }}>
              
              <div style={{ width: 30, height: 30, borderRadius: "50%", flexShrink: 0, background: ac, border: isHuman ? "1px solid var(--color-hairline)" : "none", display: "flex", alignItems: "center", justifyContent: "center" }}>
                {isHuman ? <User size={14} color="var(--color-mute)" /> : <Bot size={14} color="#fff" />}
              </div>
              <div style={{ maxWidth: "78%" }}>
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
                  <div style={{ background: "var(--color-canvas)", border: "1px solid var(--color-primary)", padding: "var(--sp-sm)", borderRadius: "var(--radius-md)", display: "flex", flexDirection: "column", gap: "var(--sp-sm)", width: "100%", minWidth: 400 }}>
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
                    background: isHuman ? "var(--color-primary-glow-sm)" : "var(--color-canvas-soft)",
                    border: isHuman ? "1px solid rgba(0,217,146,0.2)" : "1px solid var(--color-hairline)",
                    borderRadius: "var(--radius-md)",
                    borderTopRightRadius: isHuman ? 2 : undefined,
                    borderTopLeftRadius: !isHuman ? 2 : undefined,
                    color: isHuman ? "var(--color-primary)" : "var(--color-ink)",
                    position: "relative", fontSize: 14,
                  }}>
                    {isThinking ? (
                      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", color: "var(--color-mute)" }}>
                        <Loader2 size={14} className="animate-spin" />
                        <span className="body-sm">Thinking...</span>
                      </div>
                    ) : isHuman ? (
                      <div style={{ whiteSpace: "pre-wrap" }}>
                        {msg.text}
                        {msg.attachments && msg.attachments.length > 0 && (
                          <div style={{ display: "flex", gap: "var(--sp-sm)", marginTop: "var(--sp-sm)", flexWrap: "wrap" }}>
                            {msg.attachments.map((att: any, i: number) => (
                              att.type?.startsWith("image/") ? (
                                <img key={i} src={att.url} alt="attachment" style={{ maxWidth: 200, maxHeight: 200, borderRadius: "var(--radius-sm)", border: "1px solid rgba(0,217,146,0.2)" }} />
                              ) : (
                                <a key={i} href={att.url} target="_blank" rel="noreferrer" style={{ padding: "4px 8px", background: "rgba(0,217,146,0.1)", borderRadius: "var(--radius-sm)", fontSize: 12, color: "var(--color-primary)", textDecoration: "none" }}>📎 {att.name}</a>
                              )
                            ))}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="markdown-body">
                        <ReactMarkdown 
                          remarkPlugins={[remarkGfm]}
                          components={{
                            table: ({node, ...props}) => <div style={{overflowX: 'auto', margin: 'var(--sp-md) 0'}}><table style={{borderCollapse: 'collapse', width: '100%'}} {...props} /></div>,
                            th: ({node, ...props}) => <th style={{border: '1px solid var(--color-hairline)', padding: 'var(--sp-sm)', background: 'var(--color-canvas-raised)'}} {...props} />,
                            td: ({node, ...props}) => <td style={{border: '1px solid var(--color-hairline)', padding: 'var(--sp-sm)'}} {...props} />,
                            code: ({node, className, children, ...props}) => {
                              const match = /language-(\w+)/.exec(className || '')
                              const inline = !match;
                              return inline ? (
                                <code className="code-inline" {...props}>{children}</code>
                              ) : (
                                <pre className="code-block" style={{ marginTop: 8, marginBottom: 8 }}>
                                  <code className={className} {...props}>{children}</code>
                                </pre>
                              )
                            }
                          }}
                        >
                          {msg.text || ""}
                        </ReactMarkdown>
                      </div>
                    )}
                    {isStreaming && (
                      <span style={{ display: "inline-block", width: 2, height: 14, background: "var(--color-primary)", borderRadius: 1, marginLeft: 2, verticalAlign: "text-bottom", animation: "blink 1s step-end infinite" }} />
                    )}
                    {/* Stop Generating button — visible while streaming or thinking */}
                    {(isStreaming || isThinking) && !isHuman && (
                      <div style={{ marginTop: "var(--sp-sm)", display: "flex", justifyContent: "flex-end" }}>
                        <button
                          onClick={() => api.stopAgent(msg.sender_id)}
                          style={{
                            display: "inline-flex", alignItems: "center", gap: 6,
                            padding: "4px 10px", fontSize: 12, cursor: "pointer",
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
                      <ThoughtsPanel reasoning={msg.reasoning} isStreaming={isStreaming} />
                    )}
                  </div>
                )}
              </div>

              {/* Action Menu Hover */}
              {!isThinking && !isStreaming && !isSystem && !isApproval && !isQuestion && editingMsgId !== msg.id && (
                <div className="msg-actions" style={{ 
                  display: "flex", gap: 4, position: "absolute", top: -10, 
                  [isHuman ? "left" : "right"]: 0, 
                  background: "var(--color-canvas)", border: "1px solid var(--color-hairline)", 
                  padding: "2px 4px", borderRadius: "var(--radius-md)",
                  opacity: 0, transition: "opacity 0.1s"
                }}>
                  <button className="btn btn-icon btn-ghost btn-sm" title="Edit text only" onClick={() => { setEditingMsgId(msg.id); setEditText(msg.text || ""); }}>
                    <Edit2 size={12} />
                  </button>
                  <button className="btn btn-icon btn-ghost btn-sm" title="Delete this message only" onClick={() => doDelete(msg.id)}>
                    <Trash2 size={12} />
                  </button>
                  <button className="btn btn-icon btn-ghost btn-sm" style={{ color: "var(--color-warning)" }} title="Rollback context and file changes to this point" onClick={() => doRollback(msg.id)}>
                    <History size={12} />
                  </button>
                </div>
              )}
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

      {/* Attachments preview */}
      {attachments.length > 0 && (
        <div style={{ display: "flex", gap: "var(--sp-sm)", padding: "var(--sp-sm) var(--sp-2xl)", background: "var(--color-canvas)" }}>
          {attachments.map((att, i) => (
            <div key={i} style={{ position: "relative", width: 48, height: 48, borderRadius: "var(--radius-sm)", border: "1px solid var(--color-hairline)", overflow: "hidden", background: "var(--color-canvas-soft)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              {att.type?.startsWith("image/") ? (
                <img src={att.url} alt="attachment" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              ) : (
                <div style={{ fontSize: 10, color: "var(--color-mute)" }}>File</div>
              )}
              <button 
                onClick={() => setAttachments(prev => prev.filter((_, idx) => idx !== i))}
                style={{ position: "absolute", top: 2, right: 2, background: "rgba(0,0,0,0.5)", color: "white", border: "none", borderRadius: "50%", padding: 2, cursor: "pointer", display: "flex" }}
              >
                <XCircle size={10} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Input */}
      <div style={{ padding: "var(--sp-md) var(--sp-2xl)", borderTop: "1px solid var(--color-hairline)", background: "var(--color-canvas)" }}>
        <div style={{ display: "flex", gap: "var(--sp-sm)", alignItems: "flex-end", position: "relative" }}>
          
          <input type="file" ref={fileInputRef} style={{ display: "none" }} onChange={handleFileUpload} />
          <button className="btn btn-sm btn-icon btn-ghost" title="Attach file" onClick={() => fileInputRef.current?.click()} disabled={uploading} style={{ flexShrink: 0, padding: "8px 12px" }}>
            {uploading ? <Loader2 size={16} className="animate-spin" /> : <Folder size={16} />}
          </button>
          
          {/* Mention Dropdown */}
          {mentionOpen && filteredAgents.length > 0 && (
            <div style={{
              position: "absolute", bottom: "100%", left: 0, marginBottom: "var(--sp-sm)",
              background: "var(--color-canvas)", border: "1px solid var(--color-hairline)",
              borderRadius: "var(--radius-md)", boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
              maxHeight: 200, overflowY: "auto", minWidth: 200, zIndex: 10
            }}>
              {filteredAgents.map((agent, i) => (
                <div key={agent.id} 
                  style={{
                    padding: "var(--sp-sm) var(--sp-md)", cursor: "pointer",
                    background: i === mentionIndex ? "var(--color-canvas-raised)" : "transparent",
                    display: "flex", alignItems: "center", gap: "var(--sp-sm)"
                  }}
                  onMouseEnter={() => setMentionIndex(i)}
                  onClick={() => insertMention(agent.name)}
                >
                  <div style={{ width: 16, height: 16, borderRadius: "50%", background: avatarColor(agent.name) }} />
                  <span className="body-sm-strong">{agent.name}</span>
                  <span className="caption" style={{ marginLeft: "auto" }}>{agent.role}</span>
                </div>
              ))}
            </div>
          )}

          <textarea 
            ref={inputRef}
            className="input" style={{ flex: 1, resize: "none", minHeight: 40, maxHeight: 160, lineHeight: 1.5, padding: "9px var(--sp-md)" }}
            placeholder="Instruct your agents... (Enter to send, Shift+Enter for newline)"
            value={inputText} rows={1}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
          />
          <button className={`btn btn-sm ${recording ? "btn-danger" : "btn-outline"}`}
            onClick={toggleRecord} style={{ height: 40 }} title={recording ? "Stop recording" : "Voice input"}>
            {transcribing ? <Loader2 size={14} className="animate-spin" /> : recording ? <MicOff size={14} /> : <Mic size={14} />}
          </button>
          <button className="btn btn-primary btn-sm" onClick={handleSend} disabled={!inputText.trim()} style={{ height: 40 }}>
            <Send size={14} /> Send
          </button>
        </div>
      </div>

      <style>{`@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}`}</style>
    </div>
  );
}
