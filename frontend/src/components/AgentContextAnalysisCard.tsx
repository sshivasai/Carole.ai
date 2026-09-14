"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import type { AgentConfig } from "@/lib/types";
import AgentAvatar from "./AgentAvatar";
import { Activity, Cpu, Sparkles, Database, CheckCircle2, AlertTriangle, ArrowUpRight, Zap } from "lucide-react";
import { getAvatarTheme } from "./PrettyAvatar";

interface AgentContextAnalysisCardProps {
  agent: AgentConfig;
  totalTokens: number;
  messages?: any[];
  lastTokenEvent?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number; agent_name?: string } | null;
  children: React.ReactNode;
}

const contextLimit = (model = "") => {
  const value = model.toLowerCase();
  if (value.includes("gemini")) return 1_000_000;
  if (value.includes("claude")) return 200_000;
  if (value.includes("32k") || value.includes("mistral")) return 32_768;
  if (value.includes("16k") || value.includes("gpt-3.5")) return 16_384;
  return 128_000;
};

const tone = (percent: number) => {
  if (percent >= 85) return "#ef6464";
  if (percent >= 65) return "#e5a84b";
  return "#57c59a";
};

const compact = (value: number) => {
  if (!value || isNaN(value) || value <= 0) return "0";
  if (value >= 1_000_000) return (value / 1_000_000).toFixed(1) + "M";
  if (value >= 1000) return (value / 1000).toFixed(value >= 10000 ? 0 : 1) + "k";
  return String(Math.round(value));
};

export default function AgentContextAnalysisCard({
  agent,
  totalTokens,
  messages = [],
  lastTokenEvent,
  children,
}: AgentContextAnalysisCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const [mounted, setMounted] = useState(false);

  const triggerRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const openTimer = useRef<NodeJS.Timeout | null>(null);
  const closeTimer = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    setMounted(true);
    return () => {
      if (openTimer.current) clearTimeout(openTimer.current);
      if (closeTimer.current) clearTimeout(closeTimer.current);
    };
  }, []);

  const agentLimit = contextLimit(agent.model);
  const agentPct = totalTokens === 0 ? 0 : Math.min(100, Math.round((totalTokens / agentLimit) * 1000) / 10);
  const remainingTokens = Math.max(0, agentLimit - totalTokens);
  const meterColor = tone(agentPct);
  const avatarTheme = getAvatarTheme(agent.name, agent.role, agent.id);

  // Compute this agent's message & token statistics
  const agentMsgs = messages.filter(
    (m: any) =>
      m.sender_id === agent.id ||
      m.sender_name?.toLowerCase() === agent.name.toLowerCase()
  );
  const messageCount = agentMsgs.length;
  const toolCallCount = agentMsgs.reduce((acc: number, m: any) => {
    if (m.type === "tool_start" || m.type === "tool_end" || m.tool_name) return acc + 1;
    const toolMatches = (m.reasoning || "").match(/<tool_call>|\[ACTION\]|🛠️/g);
    return acc + (toolMatches ? toolMatches.length : 0);
  }, 0);

  const generatedChars = agentMsgs.reduce((acc: number, m: any) => {
    return acc + (m.text?.length || 0) + (m.reasoning?.length || 0);
  }, 0);
  const generatedTokens = Math.round(generatedChars / 4);

  const isLastAgent =
    lastTokenEvent?.agent_name?.toLowerCase() === agent.name.toLowerCase();

  const calculatePosition = useCallback(() => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const cardWidth = 330;
    const cardHeight = 350;
    const padding = 12;

    // Prefer popping out to the left of the context popover
    let left = rect.left - cardWidth - 14;
    if (left < padding) {
      // If not enough room on left, place under or right
      left = Math.max(padding, rect.right - cardWidth);
    }

    let top = rect.top - 16;
    if (top + cardHeight > window.innerHeight - padding) {
      top = Math.max(padding, window.innerHeight - cardHeight - padding);
    }
    if (top < padding) top = padding;

    setCoords({ top, left });
  }, []);

  const handleMouseEnter = () => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
    openTimer.current = setTimeout(() => {
      calculatePosition();
      setIsOpen(true);
    }, 150);
  };

  const handleMouseLeave = () => {
    if (openTimer.current) {
      clearTimeout(openTimer.current);
      openTimer.current = null;
    }
    closeTimer.current = setTimeout(() => {
      setIsOpen(false);
    }, 200);
  };

  const statusLabel =
    agentPct >= 85 ? "Critical" : agentPct >= 65 ? "Elevated" : "Optimal";
  const StatusIcon =
    agentPct >= 85 ? AlertTriangle : agentPct >= 65 ? Activity : CheckCircle2;

  return (
    <>
      <div
        ref={triggerRef}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        style={{ display: "block", width: "100%" }}
      >
        {children}
      </div>

      {mounted && isOpen && createPortal(
        <div
          ref={cardRef}
          onMouseEnter={() => {
            if (closeTimer.current) clearTimeout(closeTimer.current);
          }}
          onMouseLeave={handleMouseLeave}
          style={{
            position: "fixed",
            top: coords.top,
            left: coords.left,
            width: "330px",
            zIndex: 999999,
            background: "rgba(15, 17, 26, 0.96)",
            backdropFilter: "blur(24px)",
            WebkitBackdropFilter: "blur(24px)",
            border: `1px solid ${avatarTheme.bgGrad[0]}44`,
            borderRadius: "16px",
            boxShadow: `0 24px 50px -10px rgba(0, 0, 0, 0.8), 0 0 28px -4px ${avatarTheme.bgGrad[0]}25`,
            overflow: "hidden",
            color: "#f1f5f9",
            animation: "agentCardFadeIn 0.16s cubic-bezier(0.16, 1, 0.3, 1) forwards",
            pointerEvents: "auto",
            fontFamily: "var(--font-sans, system-ui, sans-serif)",
          }}
        >
          {/* Header Banner */}
          <div
            style={{
              padding: "14px 16px 12px",
              background: `linear-gradient(135deg, ${avatarTheme.bgGrad[0]}18 0%, rgba(15, 17, 26, 0.4) 100%)`,
              borderBottom: "1px solid rgba(255, 255, 255, 0.07)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 10,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <AgentAvatar name={agent.name} id={agent.id} role={agent.role} size={34} hideBadge />
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontWeight: 600, fontSize: 13, color: "#fff" }}>{agent.name}</span>
                  <span
                    style={{
                      fontSize: 10,
                      padding: "1px 6px",
                      borderRadius: 999,
                      background: `${avatarTheme.bgGrad[0]}25`,
                      color: avatarTheme.bgGrad[0],
                      border: `1px solid ${avatarTheme.bgGrad[0]}40`,
                      fontWeight: 500,
                    }}
                  >
                    {agent.role || "Teammate"}
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "rgba(255, 255, 255, 0.5)", marginTop: 2, display: "flex", alignItems: "center", gap: 4 }}>
                  <Cpu size={11} />
                  <span>{agent.model || "default"}</span>
                </div>
              </div>
            </div>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 4,
                fontSize: 10,
                fontWeight: 600,
                padding: "3px 7px",
                borderRadius: 6,
                background: `${meterColor}18`,
                color: meterColor,
                border: `1px solid ${meterColor}33`,
              }}
            >
              <StatusIcon size={11} />
              <span>{statusLabel}</span>
            </div>
          </div>

          {/* Context Window Section */}
          <div style={{ padding: "14px 16px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
              <span style={{ fontSize: 11, fontWeight: 500, color: "rgba(255, 255, 255, 0.6)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                Context Window
              </span>
              <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
                <strong style={{ fontSize: 14, color: meterColor, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                  {compact(Math.round(totalTokens))}
                </strong>
                <span style={{ fontSize: 11, color: "rgba(255, 255, 255, 0.4)" }}>
                  / {compact(agentLimit)} ({agentPct.toFixed(1)}%)
                </span>
              </div>
            </div>

            {/* Context Progress Track */}
            <div
              style={{
                height: 6,
                width: "100%",
                background: "rgba(255, 255, 255, 0.08)",
                borderRadius: 999,
                overflow: "hidden",
                marginBottom: 10,
                position: "relative",
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${Math.max(agentPct, 2)}%`,
                  background: meterColor,
                  borderRadius: 999,
                  transition: "width 0.3s ease",
                  boxShadow: `0 0 10px ${meterColor}66`,
                }}
              />
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "rgba(255, 255, 255, 0.5)", marginBottom: 14 }}>
              <span>Headroom left:</span>
              <strong style={{ color: "#e2e8f0", fontWeight: 600 }}>{compact(remainingTokens)} tokens free</strong>
            </div>

            {/* Token & Turn Metrics Grid */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 8,
                marginBottom: 12,
              }}
            >
              <div
                style={{
                  background: "rgba(255, 255, 255, 0.03)",
                  border: "1px solid rgba(255, 255, 255, 0.06)",
                  borderRadius: 10,
                  padding: "8px 10px",
                }}
              >
                <div style={{ fontSize: 10, color: "rgba(255, 255, 255, 0.4)", marginBottom: 3, display: "flex", alignItems: "center", gap: 4 }}>
                  <Database size={10} /> Active Prompt
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#f8fafc" }}>
                  {compact(Math.round(totalTokens))} <span style={{ fontSize: 10, fontWeight: 400, color: "rgba(255, 255, 255, 0.4)" }}>tokens</span>
                </div>
              </div>

              <div
                style={{
                  background: "rgba(255, 255, 255, 0.03)",
                  border: "1px solid rgba(255, 255, 255, 0.06)",
                  borderRadius: 10,
                  padding: "8px 10px",
                }}
              >
                <div style={{ fontSize: 10, color: "rgba(255, 255, 255, 0.4)", marginBottom: 3, display: "flex", alignItems: "center", gap: 4 }}>
                  <ArrowUpRight size={10} /> Output Created
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#f8fafc" }}>
                  {compact(generatedTokens)} <span style={{ fontSize: 10, fontWeight: 400, color: "rgba(255, 255, 255, 0.4)" }}>est. tokens</span>
                </div>
              </div>

              <div
                style={{
                  background: "rgba(255, 255, 255, 0.03)",
                  border: "1px solid rgba(255, 255, 255, 0.06)",
                  borderRadius: 10,
                  padding: "8px 10px",
                }}
              >
                <div style={{ fontSize: 10, color: "rgba(255, 255, 255, 0.4)", marginBottom: 3 }}>
                  Messages
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#f8fafc" }}>
                  {messageCount} <span style={{ fontSize: 10, fontWeight: 400, color: "rgba(255, 255, 255, 0.4)" }}>turns</span>
                </div>
              </div>

              <div
                style={{
                  background: "rgba(255, 255, 255, 0.03)",
                  border: "1px solid rgba(255, 255, 255, 0.06)",
                  borderRadius: 10,
                  padding: "8px 10px",
                }}
              >
                <div style={{ fontSize: 10, color: "rgba(255, 255, 255, 0.4)", marginBottom: 3, display: "flex", alignItems: "center", gap: 4 }}>
                  <Zap size={10} /> Tool Actions
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#f8fafc" }}>
                  {toolCallCount} <span style={{ fontSize: 10, fontWeight: 400, color: "rgba(255, 255, 255, 0.4)" }}>calls</span>
                </div>
              </div>
            </div>

            {/* Last Execution Telemetry (if this agent participated in the latest event) */}
            {isLastAgent && lastTokenEvent?.prompt_tokens && (
              <div
                style={{
                  background: `${avatarTheme.bgGrad[0]}10`,
                  border: `1px solid ${avatarTheme.bgGrad[0]}25`,
                  borderRadius: 10,
                  padding: "7px 10px",
                  fontSize: 11,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  color: "#cbd5e1",
                  marginBottom: 10,
                }}
              >
                <span>Latest Turn:</span>
                <span style={{ fontVariantNumeric: "tabular-nums" }}>
                  <strong style={{ color: "#fff" }}>{lastTokenEvent.prompt_tokens}</strong> prompt +{" "}
                  <strong style={{ color: "#fff" }}>{lastTokenEvent.completion_tokens || 0}</strong> completion
                </span>
              </div>
            )}

            {/* Analysis Note */}
            <div
              style={{
                fontSize: 11,
                lineHeight: 1.5,
                color: "rgba(255, 255, 255, 0.55)",
                background: "rgba(0, 0, 0, 0.2)",
                padding: "8px 10px",
                borderRadius: 8,
                border: "1px solid rgba(255, 255, 255, 0.04)",
              }}
            >
              {agentPct >= 85
                ? "⚠️ Working memory is nearly exhausted. Compaction is urgently recommended to prevent token cutoff."
                : agentPct >= 65
                ? "⚡ Context is elevated. Monitor response accuracy or run compaction for extended tasks."
                : "✨ Context is running optimally with generous working headroom."}
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
