"use client";
import React, { useState, useRef, useEffect, useCallback } from "react";
import type { ChatMessage, AgentConfig } from "@/lib/types";
import { Send, Bot, User, Wrench, CheckCircle, XCircle, MessageCircleQuestion, Loader2 } from "lucide-react";
import { api } from "@/hooks/useApi";

interface Props {
  messages: ChatMessage[];
  agents: AgentConfig[];
  onSendMessage: (text: string) => void;
}

const AVATAR_COLORS = [
  "var(--accent-blue)", "var(--accent-purple)", "var(--accent-green)",
  "var(--accent-orange)", "var(--accent-red)", "var(--accent-yellow)"
];

function getAvatarColor(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function formatTimestamp(ts?: string | number): string {
  if (!ts) return "";
  const d = new Date(typeof ts === "number" ? ts : ts);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// ─── Inline Approval Card ───────────────────────────────────────────────────
function ApprovalCard({ msg }: { msg: ChatMessage }) {
  const [status, setStatus] = useState<"pending" | "approved" | "denied">("pending");
  const [loading, setLoading] = useState(false);

  const decide = async (approved: boolean) => {
    if (!msg.tx_id || status !== "pending") return;
    setLoading(true);
    try {
      await api.approveToolExecution(msg.tx_id, approved);
      setStatus(approved ? "approved" : "denied");
    } catch (e) {
      console.error("Approval failed:", e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      border: `1px solid ${status === "pending" ? "var(--color-warning)" : status === "approved" ? "var(--color-primary)" : "var(--color-danger)"}`,
      borderRadius: "var(--radius-md)",
      padding: "var(--sp-lg)",
      background: "var(--color-canvas-soft)",
      display: "flex",
      flexDirection: "column",
      gap: "var(--sp-md)",
      maxWidth: 480,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
        <span style={{ fontSize: 18 }}>🛑</span>
        <span className="body-sm-strong">Approval Required</span>
        {status !== "pending" && (
          <span className={`pill ${status === "approved" ? "pill-live" : "pill-idle"}`}>
            {status.toUpperCase()}
          </span>
        )}
      </div>
      <div>
        <span className="caption" style={{ color: "var(--color-mute)" }}>Agent </span>
        <span className="body-sm-strong">{msg.sender_name}</span>
        <span className="caption" style={{ color: "var(--color-mute)" }}> wants to run </span>
        <span className="code-inline">{msg.tool_name}</span>
      </div>
      {msg.arguments && Object.keys(msg.arguments).length > 0 && (
        <pre style={{
          fontSize: 11, background: "var(--color-canvas)", borderRadius: "var(--radius-xs)",
          padding: "var(--sp-sm) var(--sp-md)", overflowX: "auto", maxHeight: 120,
          border: "1px solid var(--color-hairline)", color: "var(--color-ink)", margin: 0,
        }}>
          {JSON.stringify(msg.arguments, null, 2)}
        </pre>
      )}
      {status === "pending" && (
        <div style={{ display: "flex", gap: "var(--sp-md)" }}>
          <button
            className="btn btn-primary"
            style={{ flex: 1, gap: "var(--sp-sm)", display: "flex", alignItems: "center", justifyContent: "center" }}
            disabled={loading}
            onClick={() => decide(true)}
          >
            {loading ? <Loader2 size={14} className="spin" /> : <CheckCircle size={14} />} Approve
          </button>
          <button
            className="btn btn-outline"
            style={{ flex: 1, gap: "var(--sp-sm)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-danger)", borderColor: "var(--color-danger)" }}
            disabled={loading}
            onClick={() => decide(false)}
          >
            <XCircle size={14} /> Deny
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Inline Ask-User Card ────────────────────────────────────────────────────
function AskUserCard({ msg }: { msg: ChatMessage }) {
  const [answer, setAnswer] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!msg.question_id || !answer.trim() || submitted) return;
    setLoading(true);
    try {
      await api.answerAgentQuestion(msg.question_id, answer.trim());
      setSubmitted(true);
    } catch (e) {
      console.error("Answer submission failed:", e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      border: "1px solid var(--accent-blue)",
      borderRadius: "var(--radius-md)",
      padding: "var(--sp-lg)",
      background: "var(--color-canvas-soft)",
      display: "flex",
      flexDirection: "column",
      gap: "var(--sp-md)",
      maxWidth: 480,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
        <MessageCircleQuestion size={16} color="var(--accent-blue)" />
        <span className="body-sm-strong">{msg.sender_name} asks:</span>
      </div>
      <p className="body-sm" style={{ margin: 0 }}>{msg.question || msg.text}</p>
      {submitted ? (
        <span className="pill pill-live" style={{ alignSelf: "flex-start" }}>Answered ✓</span>
      ) : (
        <div style={{ display: "flex", gap: "var(--sp-sm)" }}>
          <input
            className="input"
            style={{ flex: 1 }}
            placeholder="Type your answer..."
            value={answer}
            onChange={e => setAnswer(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) submit(); }}
            autoFocus
          />
          <button className="btn btn-primary" onClick={submit} disabled={loading || !answer.trim()}>
            {loading ? <Loader2 size={14} className="spin" /> : <Send size={14} />}
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Main ChatInterface ───────────────────────────────────────────────────────
export default function ChatInterface({ messages, agents, onSendMessage }: Props) {
  const [inputText, setInputText] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = useCallback(() => {
    if (!inputText.trim()) return;
    onSendMessage(inputText.trim());
    setInputText("");
  }, [inputText, onSendMessage]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
    // Shift+Enter inserts a newline — textarea handles this natively, no action needed
  }, [handleSend]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <header style={{ padding: "var(--sp-lg) var(--sp-2xl)", borderBottom: "1px solid var(--color-hairline)", background: "var(--color-canvas)" }}>
        <h2 className="display-md">Team Chat</h2>
        <p className="caption">Collaborate with your AI agents · <kbd style={{ fontSize: 11, padding: "1px 4px", borderRadius: 3, border: "1px solid var(--color-hairline)", background: "var(--color-canvas-soft)" }}>Shift+Enter</kbd> for newline</p>
      </header>

      {/* Messages Area */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "var(--sp-2xl)", display: "flex", flexDirection: "column", gap: "var(--sp-xl)" }}>
        {messages.map((msg) => {
          const isHuman = msg.sender_id === "human";
          const isSystem = msg.sender_id === "system";
          const isTool = msg.type === "tool_start" || msg.type === "tool_end";
          const isApproval = msg.type === "approval_request";
          const isQuestion = msg.type === "agent_question";
          const isStreaming = msg.type === "streaming";

          // ── Tool events (compact inline row) ──
          if (isTool) {
            return (
              <div key={msg.id} style={{ paddingLeft: 40, color: "var(--color-mute)", fontSize: 13, display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                <Wrench size={12} />
                <span className="code-inline" style={{ padding: "0 4px" }}>{msg.tool_name}</span>
                <span>{(msg.text || "").length > 100 ? (msg.text || "").substring(0, 100) + "..." : (msg.text || "")}</span>
              </div>
            );
          }

          // ── System events ──
          if (isSystem) {
            return (
              <div key={msg.id} style={{ textAlign: "center", color: "var(--color-mute)" }}>
                <span className="eyebrow">{msg.text}</span>
              </div>
            );
          }

          // ── Approval cards ──
          if (isApproval) {
            return (
              <div key={msg.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start" }}>
                <div style={{ width: 32, height: 32, borderRadius: "50%", flexShrink: 0, background: getAvatarColor(msg.sender_name || ""), display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <Bot size={16} />
                </div>
                <div style={{ maxWidth: "75%" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: 4 }}>
                    <span className="body-sm-strong">{msg.sender_name}</span>
                    {msg.timestamp && <span className="caption" style={{ color: "var(--color-mute)" }}>{formatTimestamp(msg.timestamp)}</span>}
                  </div>
                  <ApprovalCard msg={msg} />
                </div>
              </div>
            );
          }

          // ── Agent question cards ──
          if (isQuestion) {
            return (
              <div key={msg.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start" }}>
                <div style={{ width: 32, height: 32, borderRadius: "50%", flexShrink: 0, background: getAvatarColor(msg.sender_name || ""), display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <Bot size={16} />
                </div>
                <div style={{ maxWidth: "75%" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: 4 }}>
                    <span className="body-sm-strong">{msg.sender_name}</span>
                    {msg.timestamp && <span className="caption" style={{ color: "var(--color-mute)" }}>{formatTimestamp(msg.timestamp)}</span>}
                  </div>
                  <AskUserCard msg={msg} />
                </div>
              </div>
            );
          }

          const avatarColor = isHuman ? "var(--color-canvas-soft)" : getAvatarColor(msg.sender_name || "");

          return (
            <div key={msg.id} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start", flexDirection: isHuman ? "row-reverse" : "row" }}>
              {/* Avatar */}
              <div style={{
                width: 32, height: 32, borderRadius: "50%", flexShrink: 0,
                background: avatarColor,
                border: isHuman ? "1px solid var(--color-hairline)" : "none",
                display: "flex", alignItems: "center", justifyContent: "center",
                color: isHuman ? "var(--color-ink)" : "#000"
              }}>
                {isHuman ? <User size={16} /> : <Bot size={16} />}
              </div>

              {/* Message Bubble */}
              <div style={{ maxWidth: "75%" }}>
                {!isHuman && (
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: 4 }}>
                    <span className="body-sm-strong">{msg.sender_name}</span>
                    <span className="caption">{msg.role}</span>
                    {msg.timestamp && <span className="caption" style={{ color: "var(--color-mute)", marginLeft: "auto" }}>{formatTimestamp(msg.timestamp)}</span>}
                  </div>
                )}
                {isHuman && msg.timestamp && (
                  <div style={{ textAlign: "right", marginBottom: 4 }}>
                    <span className="caption" style={{ color: "var(--color-mute)" }}>{formatTimestamp(msg.timestamp)}</span>
                  </div>
                )}

                <div style={{
                  padding: "var(--sp-md) var(--sp-lg)",
                  background: isHuman ? "var(--color-primary-glow-sm)" : isStreaming ? "var(--color-canvas-soft)" : "var(--color-canvas-soft)",
                  border: isHuman ? "1px solid var(--color-primary-soft)" : "1px solid var(--color-hairline)",
                  borderRadius: "var(--radius-md)",
                  borderTopRightRadius: isHuman ? 2 : undefined,
                  borderTopLeftRadius: !isHuman ? 2 : undefined,
                  color: isHuman ? "var(--color-primary)" : "var(--color-ink)",
                  whiteSpace: "pre-wrap",
                  lineHeight: 1.6,
                  position: "relative",
                }}>
                  {msg.text}
                  {isStreaming && (
                    <span style={{
                      display: "inline-block", width: 8, height: 14,
                      background: "var(--color-primary)", borderRadius: 2,
                      marginLeft: 2, verticalAlign: "text-bottom",
                      animation: "blink 1s step-end infinite",
                    }} />
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {messages.length === 0 && (
          <div style={{ textAlign: "center", color: "var(--color-mute)", marginTop: "100px" }}>
            <Bot size={48} style={{ margin: "0 auto var(--sp-md)", opacity: 0.5 }} />
            <p>No messages yet. Say hello to your team!</p>
          </div>
        )}
      </div>

      {/* Input Area */}
      <div style={{ padding: "var(--sp-lg) var(--sp-2xl)", borderTop: "1px solid var(--color-hairline)", background: "var(--color-canvas)" }}>
        <div style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-end" }}>
          <textarea
            className="input"
            style={{ flex: 1, resize: "none", minHeight: 44, maxHeight: 160, lineHeight: 1.5, padding: "10px var(--sp-lg)" }}
            placeholder="Instruct your agents... (Enter to send, Shift+Enter for newline)"
            value={inputText}
            rows={1}
            onChange={(e) => {
              setInputText(e.target.value);
              // Auto-grow
              e.target.style.height = "auto";
              e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
            }}
            onKeyDown={handleKeyDown}
          />
          <button className="btn btn-primary" onClick={handleSend} style={{ alignSelf: "flex-end", height: 44 }}>
            <Send size={16} /> Send
          </button>
        </div>
        <div className="caption" style={{ marginTop: "var(--sp-sm)", textAlign: "center" }}>
          Agents process messages autonomously. Give clear instructions.
        </div>
      </div>

      <style>{`
        @keyframes blink { 0%, 100% { opacity: 1 } 50% { opacity: 0 } }
        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }
      `}</style>
    </div>
  );
}
