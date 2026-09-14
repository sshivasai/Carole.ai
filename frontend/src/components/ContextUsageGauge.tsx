"use client";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, RefreshCw } from "lucide-react";
import AgentAvatar from "./AgentAvatar";
import AgentContextAnalysisCard from "./AgentContextAnalysisCard";
import type { AgentConfig } from "@/lib/types";
import { api } from "@/hooks/useApi";
import "./chat-workspace.css";

interface Props {
  projectId?: string;
  teamId?: string;
  activeModel?: string;
  estimatedTokens?: number;
  contextWindow?: number;
  usagePercent?: number;
  messages?: any[];
  agents?: AgentConfig[];
  lastTokenEvent?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number; agent_name?: string } | null;
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

export default function ContextUsageGauge({
  projectId,
  estimatedTokens,
  contextWindow,
  usagePercent,
  messages,
  agents = [],
  lastTokenEvent,
}: Props) {
  const [open, setOpen] = useState(false);
  const [cycle, setCycle] = useState(0);
  const [cost, setCost] = useState<{ total_tokens?: number; total_spend_usd?: number } | null>(null);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!projectId) return;
    api.getCostStats(projectId).then(setCost).catch(() => {});
  }, [projectId, lastTokenEvent]);

  useEffect(() => {
    if (agents.length < 2 || open) return;
    const timer = setInterval(() => setCycle(v => (v + 1) % agents.length), 5200);
    return () => clearInterval(timer);
  }, [agents.length, open]);

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  const current = agents[cycle % Math.max(1, agents.length)];

  // Accurately compute active conversation context tokens
  const tokens = useMemo(() => {
    // If the conversation has no messages, active context is empty
    if (!messages || messages.length === 0) {
      return 0;
    }
    // If agent is actively running or provided an estimated context usage
    if (estimatedTokens !== undefined && estimatedTokens > 0) {
      return estimatedTokens;
    }
    // If the last token event had prompt tokens for this conversation turn
    if (lastTokenEvent?.prompt_tokens && lastTokenEvent.prompt_tokens > 0) {
      return lastTokenEvent.prompt_tokens;
    }
    // Fallback: estimate from message text & reasoning
    const chars = messages.reduce((sum, item) => sum + (item.text?.length || 0) + (item.reasoning?.length || 0), 0);
    const msgTokens = Math.round(chars / 4);
    return msgTokens > 0 ? msgTokens + 2200 : 0;
  }, [messages, estimatedTokens, lastTokenEvent]);

  const limit = contextWindow || contextLimit(current?.model) || 128_000;
  const percent = tokens === 0
    ? 0
    : Math.min(100, usagePercent ?? (limit > 0 ? Math.round((tokens / limit) * 1000) / 10 : 0));
  const color = tone(percent);

  return (
    <div className="cw-context" ref={root}>
      <button
        className="cw-context-trigger"
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        title={`Team context: ${percent.toFixed(0)}% used (${compact(Math.round(tokens))} / ${compact(limit)})`}
      >
        <span className="cw-context-orbit" style={{ "--meter": color, "--fill": percent + "%" } as React.CSSProperties}>
          <span className="cw-context-avatar" key={current?.id || "team"}>
            {current ? (
              <AgentAvatar name={current.name} id={current.id} role={current.role} size={27} hideBadge />
            ) : (
              <span className="cw-context-core" />
            )}
          </span>
        </span>
        <span className="cw-context-copy">
          <strong>{percent.toFixed(0)}%</strong>
          <small>context</small>
        </span>
        <ChevronDown size={13} />
      </button>

      {open && (
        <div className="cw-context-popover">
          <div className="cw-context-summary">
            <span>Team context</span>
            <strong style={{ color }}>{compact(Math.round(tokens))} / {compact(limit)}</strong>
          </div>
          <div className="cw-context-track">
            <i style={{ width: percent + "%", background: color }} />
          </div>
          <p>
            {tokens === 0
              ? "Context is clear. Ready for your next message."
              : percent >= 85
              ? "Near the context limit. Compact soon to keep the conversation reliable."
              : percent >= 65
              ? "Context is filling up. Longer work may benefit from compaction."
              : "Plenty of working context remains."}
          </p>

          {agents.length > 0 && (
            <div className="cw-context-team">
              {agents.map(agent => {
                const agentLimit = contextLimit(agent.model);
                const agentPct = tokens === 0 ? 0 : Math.min(100, Math.round((tokens / agentLimit) * 100));
                const agentColor = tone(agentPct);
                return (
                  <AgentContextAnalysisCard
                    key={agent.id}
                    agent={agent}
                    totalTokens={tokens}
                    messages={messages}
                    lastTokenEvent={lastTokenEvent}
                  >
                    <button onClick={() => setCycle(agents.findIndex(item => item.id === agent.id))}>
                      <AgentAvatar name={agent.name} id={agent.id} role={agent.role} size={25} hideBadge />
                      <span>
                        <strong>{agent.name}</strong>
                        <small>{compact(agentLimit)} window</small>
                      </span>
                      <em style={{ color: agentColor }}>{agentPct.toFixed(0)}%</em>
                    </button>
                  </AgentContextAnalysisCard>
                );
              })}
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--cw-line)", fontSize: 11, color: "var(--cw-muted)" }}>
            {cost?.total_tokens ? (
              <span>Project lifetime: <strong style={{ color: "var(--cw-text)" }}>{compact(cost.total_tokens)} tokens</strong></span>
            ) : (
              <span />
            )}
            <button className="cw-text-button" style={{ padding: "3px 7px" }} onClick={() => projectId && api.getCostStats(projectId).then(setCost).catch(() => {})}>
              <RefreshCw size={11} />Refresh
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
