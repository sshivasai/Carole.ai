"use client";
import React, { useEffect, useRef, useState } from "react";
import { agentContext, type ContextSnapshot, type TokenUsageEvent } from "@/features/chat/contextUsage";
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
  contextByAgent?: Record<string, ContextSnapshot>;
  usageByAgent?: Record<string, TokenUsageEvent>;
}

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
  messages,
  agents = [],
  lastTokenEvent,
  contextByAgent = {},
  usageByAgent = {},
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

  const snapshot = current ? contextByAgent[current.id] : undefined;
  const usage = current ? usageByAgent[current.id] : undefined;
  const measured = agentContext(snapshot, usage);
  const tokens = measured.tokens ?? 0;
  const limit = measured.limit ?? 0;
  const percent = measured.percent ?? 0;
  const color = tone(percent);

  return (
    <div className="cw-context" ref={root}>
      <button
        className="cw-context-trigger"
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        title={`${current?.name || "Agent"}: ${measured.percent === undefined ? "No request measurement yet" : `${percent.toFixed(0)}% context (${measured.source})`}`}
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
          <strong>{measured.percent === undefined ? "—" : `${percent.toFixed(0)}%`}</strong>
          <small>context</small>
        </span>
        <ChevronDown size={13} />
      </button>

      {open && (
        <div className="cw-context-popover">
          <div className="cw-context-summary">
            <span>{current?.name || "Agent"} context</span>
            <strong style={{ color }}>{measured.percent === undefined ? "Not measured" : `${compact(tokens)} / ${compact(limit)}`}</strong>
          </div>
          <div className="cw-context-track">
            <i style={{ width: percent + "%", background: color }} />
          </div>
          <p>
            {measured.percent === undefined
              ? "No request measurement yet. Each agent has its own context window."
              : percent >= 85
              ? "Near the context limit. Compact soon to keep the conversation reliable."
              : percent >= 65
              ? "Context is filling up. Longer work may benefit from compaction."
              : "Plenty of working context remains."}
          </p>
          {snapshot && <p>Input {measured.source}. Capacity: {snapshot.capacity_source || "estimated"}. Output reserve: {compact(snapshot.output_reserve || 0)}.</p>}
          {snapshot?.components && <details><summary>Request breakdown</summary>
            {Object.entries(snapshot.components).map(([name, count]) => <div key={name}>{name}: {compact(count)}</div>)}
          </details>}
          {usage && <p>Latest model call: {compact(usage.prompt_tokens || 0)} input + {compact(usage.completion_tokens || 0)} output ({usage.usage_source || "estimated"}). Cache read: {usage.cache_read_tokens == null ? "unavailable" : compact(usage.cache_read_tokens)}; reasoning: {usage.reasoning_tokens == null ? "unavailable" : compact(usage.reasoning_tokens)}.</p>}

          {agents.length > 0 && (
            <div className="cw-context-team">
              {agents.map(agent => {
                const data = agentContext(contextByAgent[agent.id], usageByAgent[agent.id]);
                const agentLimit = data.limit || 0;
                const agentPct = data.percent || 0;
                const agentColor = tone(agentPct);
                return (
                  <AgentContextAnalysisCard
                    key={agent.id}
                    agent={{...agent, model: usageByAgent[agent.id]?.resolved_model || contextByAgent[agent.id]?.model || agent.model}}
                    totalTokens={data.tokens || 0}
                    contextWindow={agentLimit}
                    inputSource={data.source}
                    messages={messages}
                    lastTokenEvent={usageByAgent[agent.id]}
                  >
                    <button onClick={() => setCycle(agents.findIndex(item => item.id === agent.id))}>
                      <AgentAvatar name={agent.name} id={agent.id} role={agent.role} size={25} hideBadge />
                      <span>
                        <strong>{agent.name}</strong>
                        <small>{agentLimit ? `${compact(agentLimit)} window` : "Not measured"}</small>
                      </span>
                      <em style={{ color: agentColor }}>{data.percent === undefined ? "—" : `${agentPct.toFixed(0)}%`}</em>
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
