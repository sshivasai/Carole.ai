"use client";
import React, { useState, useRef, useEffect } from "react";
import type { ChatMessage, AgentConfig } from "@/lib/types";
import { Send, Bot, User, Wrench } from "lucide-react";

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

export default function ChatInterface({ messages, agents, onSendMessage }: Props) {
  const [inputText, setInputText] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = () => {
    if (!inputText.trim()) return;
    onSendMessage(inputText.trim());
    setInputText("");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <header style={{ padding: "var(--sp-lg) var(--sp-2xl)", borderBottom: "1px solid var(--color-hairline)", background: "var(--color-canvas)" }}>
        <h2 className="display-md">Team Chat</h2>
        <p className="caption">Collaborate with your AI agents</p>
      </header>

      {/* Messages Area */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "var(--sp-2xl)", display: "flex", flexDirection: "column", gap: "var(--sp-xl)" }}>
        {messages.map((msg, idx) => {
          const isHuman = msg.sender_id === "human";
          const isSystem = msg.sender_id === "system";
          const isTool = msg.type === "tool_start" || msg.type === "tool_end";
          
          if (isTool) {
            return (
              <div key={idx} style={{ paddingLeft: "40px", color: "var(--color-mute)", fontSize: "13px", display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                <Wrench size={12} />
                <span className="code-inline" style={{ padding: "0 4px" }}>{msg.tool_name}</span>
                <span>{msg.text.length > 100 ? msg.text.substring(0, 100) + "..." : msg.text}</span>
              </div>
            );
          }

          if (isSystem) {
            return (
              <div key={idx} style={{ textAlign: "center", color: "var(--color-mute)" }}>
                <span className="eyebrow">{msg.text}</span>
              </div>
            );
          }

          const avatarColor = isHuman ? "var(--color-canvas-soft)" : getAvatarColor(msg.sender_name || "");

          return (
            <div key={idx} style={{ display: "flex", gap: "var(--sp-md)", alignItems: "flex-start", flexDirection: isHuman ? "row-reverse" : "row" }}>
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
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: "4px" }}>
                    <span className="body-sm-strong">{msg.sender_name}</span>
                    <span className="caption">{msg.role}</span>
                  </div>
                )}
                
                <div style={{
                  padding: "var(--sp-md) var(--sp-lg)",
                  background: isHuman ? "var(--color-primary-glow-sm)" : "var(--color-canvas-soft)",
                  border: isHuman ? "1px solid var(--color-primary-soft)" : "1px solid var(--color-hairline)",
                  borderRadius: "var(--radius-md)",
                  borderTopRightRadius: isHuman ? 2 : undefined,
                  borderTopLeftRadius: !isHuman ? 2 : undefined,
                  color: isHuman ? "var(--color-primary)" : "var(--color-ink)",
                  whiteSpace: "pre-wrap",
                  lineHeight: 1.6
                }}>
                  {msg.text}
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
        <div style={{ display: "flex", gap: "var(--sp-md)" }}>
          <input
            className="input"
            style={{ flex: 1 }}
            placeholder="Instruct your agents..."
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleSend(); }}
          />
          <button className="btn btn-primary" onClick={handleSend}>
            <Send size={16} /> Send
          </button>
        </div>
        <div className="caption" style={{ marginTop: "var(--sp-sm)", textAlign: "center" }}>
          Agents process messages autonomously. Give clear instructions.
        </div>
      </div>
    </div>
  );
}
