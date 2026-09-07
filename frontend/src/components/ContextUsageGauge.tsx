"use client";
/**
 * ContextUsageGauge.tsx
 *
 * Real-time Context Window & Token Economy visualizer for Carole.ai multi-agent teams.
 * Features:
 *  - Animated pulse & shimmer gauge effects with smooth 60fps transitions
 *  - Multi-agent / multi-model team context inspection & dynamic limits
 *  - Team bottleneck detection (identifies teammates with smaller context windows)
 *  - Live token consumption meter & context window percentage
 *  - Breakdown of Prompt vs Completion tokens and estimated spend
 *  - Micro-compaction, AST snipping & Prompt caching health monitors
 */
import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  Activity, Zap, Shield, Sparkles, RefreshCw, AlertTriangle, X, Bot, ArrowUpRight, CheckCircle2, TrendingDown, Layers
} from "lucide-react";
import AgentAvatar from "./AgentAvatar";
import { api } from "@/hooks/useApi";
import type { AgentConfig } from "@/lib/types";

interface Props {
  projectId?: string;
  teamId?: string;
  activeModel?: string;
  estimatedTokens?: number;
  contextWindow?: number;
  usagePercent?: number;
  messages?: any[];
  agents?: AgentConfig[];
  lastTokenEvent?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    estimated_cost_usd?: string;
    model?: string;
    agent_name?: string;
  } | null;
}

export default function ContextUsageGauge({
  projectId,
  teamId,
  activeModel = "claude-3-7-sonnet",
  estimatedTokens,
  contextWindow,
  usagePercent,
  messages,
  agents = [],
  lastTokenEvent,
}: Props) {
  const [open, setOpen] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [cycleIndex, setCycleIndex] = useState(0);
  const [isHovered, setIsHovered] = useState(false);
  const [costStats, setCostStats] = useState<{
    total_spend_usd: number;
    budget_limit_usd: number | null;
    total_prompt_tokens: number;
    total_completion_tokens: number;
    total_tokens: number;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  const fetchStats = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const res = await api.getCostStats(projectId);
      setCostStats(res);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  // Refresh stats when a live token event arrives over WebSocket
  useEffect(() => {
    if (lastTokenEvent && projectId) {
      fetchStats();
    }
  }, [lastTokenEvent, projectId, fetchStats]);

  // Rotate active displayed agent every 5 seconds
  useEffect(() => {
    if (!agents || agents.length <= 1 || isHovered || open) return;
    const timer = setInterval(() => {
      setCycleIndex(prev => (prev + 1) % agents.length);
    }, 5000);
    return () => clearInterval(timer);
  }, [agents, isHovered, open]);

  // Close popover on outside click
  useEffect(() => {
    const handleDocClick = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) {
      document.addEventListener("mousedown", handleDocClick);
    }
    return () => document.removeEventListener("mousedown", handleDocClick);
  }, [open]);

  // Model-aware context window lookup helper (aligned with backend multi_model_router)
  const getContextWindow = useCallback((modelStr: string): number => {
    const m = (modelStr || "").toLowerCase();
    if (m.includes("gemini")) return 1000000;
    if (m.includes("claude") || m.includes("anthropic")) return 200000;
    if (
      m.includes("gpt-4") ||
      m.includes("o1") ||
      m.includes("o3") ||
      m.includes("o4") ||
      m.includes("llama-3") ||
      m.includes("deepseek") ||
      m.includes("qwen") ||
      m.includes("mistral-large") ||
      m.includes("free") ||
      m.includes("auto") ||
      m.includes("128k")
    ) {
      return 128000;
    }
    if (m.includes("32k") || m.includes("mistral")) return 32768;
    if (m.includes("gpt-3.5") || m.includes("phi") || m.includes("16k")) return 16384;
    if (m.includes("8k")) return 8192;
    if (m.includes("4k")) return 4096;
    return 128000;
  }, []);

  // Determine current active agent & model
  const selectedAgent = useMemo(() => {
    if (selectedAgentId) {
      return agents.find(a => a.id === selectedAgentId) || null;
    }
    return agents[0] || null;
  }, [selectedAgentId, agents]);

  const currentModel = selectedAgent?.model || activeModel;

  const windowLimit = useMemo(() => {
    if (selectedAgent) {
      const agentLimit = getContextWindow(selectedAgent.model);
      if (contextWindow && contextWindow > 0 && (!selectedAgentId || selectedAgent.model === activeModel)) {
        return contextWindow;
      }
      return agentLimit;
    }
    return contextWindow && contextWindow > 0 ? contextWindow : getContextWindow(currentModel);
  }, [selectedAgent, selectedAgentId, contextWindow, activeModel, currentModel, getContextWindow]);

  // Compute active context load (tokens currently loaded in prompt/memory)
  const currentTokens = useMemo(() => {
    if (estimatedTokens !== undefined && estimatedTokens > 0) return estimatedTokens;
    if (lastTokenEvent?.prompt_tokens) return lastTokenEvent.prompt_tokens;
    // Estimate from currently loaded messages if available
    if (messages && messages.length > 0) {
      const chars = messages.reduce((acc, m) => {
        let c = (m.text || "").length;
        if (m.reasoning) c += m.reasoning.length;
        return acc + c;
      }, 0);
      const msgTokens = Math.round(chars / 4);
      return msgTokens > 0 ? msgTokens + 2200 : 0; // +2200 base tokens for system instructions, agent persona & tool registry
    }
    return 0;
  }, [estimatedTokens, lastTokenEvent, messages]);

  const pct = usagePercent !== undefined && usagePercent > 0 && (!selectedAgentId || selectedAgent?.model === activeModel)
    ? usagePercent
    : windowLimit > 0
    ? Math.min(100, Math.round((currentTokens / windowLimit) * 1000) / 10)
    : 0;

  // Gauge color based on usage %
  const getGaugeColor = (val: number) => {
    if (val >= 80) return "#ef4444"; // Red
    if (val >= 50) return "#f59e0b"; // Amber
    return "#10b981"; // Emerald
  };

  const gaugeColor = getGaugeColor(pct);

  // Find team context window range and bottleneck
  const teamWindows = useMemo(() => {
    if (!agents.length) return [];
    return agents.map(a => ({
      agent: a,
      limit: getContextWindow(a.model),
      cleanModel: a.model.split("/").pop() || a.model,
    })).sort((a, b) => a.limit - b.limit);
  }, [agents, getContextWindow]);

  const maxTeamLimit = teamWindows.length > 0 ? teamWindows[teamWindows.length - 1].limit : 0;
  const bottleneck = teamWindows.length > 1 && teamWindows[0].limit < maxTeamLimit && teamWindows[0].limit < 100000
    ? teamWindows[0]
    : null;

  // Rotating Agent calculations for top-bar pill
  const activeCycleAgent = useMemo(() => {
    if (!agents || agents.length === 0) return null;
    return agents[cycleIndex % agents.length];
  }, [agents, cycleIndex]);

  const pillAgent = open ? selectedAgent : activeCycleAgent || selectedAgent;
  const pillLimit = pillAgent ? getContextWindow(pillAgent.model) : windowLimit;
  const pillPct = pillLimit > 0 ? Math.min(100, Math.round((currentTokens / pillLimit) * 1000) / 10) : 0;
  const pillColor = getGaugeColor(pillPct);
  const pillFormattedTokens = currentTokens > 0
    ? `${currentTokens >= 1000 ? (currentTokens / 1000).toFixed(1) + "k" : currentTokens} tokens`
    : "Context Meter";

  return (
    <div style={{ position: "relative", display: "inline-block" }} ref={popoverRef}>
      <style>{`
        @keyframes meterPulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.7; transform: scale(1.18); }
        }
        @keyframes liquidShimmer {
          0% { background-position: -250% 0; }
          100% { background-position: 250% 0; }
        }
        @keyframes popoverEnter {
          0% { opacity: 0; transform: translateY(-8px) scale(0.96); }
          100% { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes avatarSpinIn {
          0% {
            opacity: 0;
            transform: translateY(8px) scale(0.5) rotate(-25deg);
            filter: blur(2px);
          }
          60% {
            transform: translateY(-2px) scale(1.15) rotate(4deg);
            filter: blur(0px);
          }
          100% {
            opacity: 1;
            transform: translateY(0) scale(1) rotate(0deg);
          }
        }
        @keyframes tickerSlideUp {
          0% {
            opacity: 0;
            transform: translateY(12px);
            filter: blur(3px);
          }
          60% {
            opacity: 1;
            transform: translateY(-1.5px);
            filter: blur(0px);
          }
          100% {
            opacity: 1;
            transform: translateY(0);
          }
        }
        @keyframes percentPulse {
          0% {
            opacity: 0;
            transform: translateY(8px) scale(0.75);
          }
          60% {
            transform: translateY(-1px) scale(1.18);
            filter: drop-shadow(0 0 6px ${pillColor});
          }
          100% {
            opacity: 1;
            transform: translateY(0) scale(1);
            filter: drop-shadow(0 0 0px transparent);
          }
        }
        @keyframes timerCountdown {
          0% { width: 0%; opacity: 0.9; }
          85% { width: 100%; opacity: 0.9; }
          100% { width: 100%; opacity: 0; }
        }
        @keyframes pillBorderFlash {
          0% {
            border-color: ${pillColor}cc;
            box-shadow: 0 0 16px ${pillColor}55, var(--shadow-clay-sm, 0 2px 6px rgba(0,0,0,0.15));
          }
          100% {
            border-color: var(--border-glass, rgba(255,255,255,0.08));
            box-shadow: var(--shadow-clay-sm, 0 2px 6px rgba(0,0,0,0.15));
          }
        }
        .context-pill-trigger:hover {
          border-color: var(--color-primary, #6366f1) !important;
          background: rgba(99, 102, 241, 0.12) !important;
          transform: translateY(-1px);
        }
        .shimmer-progress {
          background: linear-gradient(90deg, ${pillColor} 0%, #a78bfa 50%, ${pillColor} 100%);
          background-size: 200% 100%;
          animation: liquidShimmer 2.4s infinite linear;
        }
        .pill-avatar-spring {
          animation: avatarSpinIn 0.45s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        .pill-ticker-text {
          animation: tickerSlideUp 0.42s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .pill-pct-pulse {
          animation: percentPulse 0.45s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
      `}</style>

      {/* Trigger pill */}
      <button
        key={`pill-btn-${open ? "open" : cycleIndex}`}
        onClick={() => setOpen(p => !p)}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className="context-pill-trigger"
        style={{
          position: "relative",
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "4px 11px 4px 7px",
          borderRadius: "var(--radius-pill, 999px)",
          border: `1px solid ${open ? "var(--color-primary, #6366f1)" : "var(--border-glass, rgba(255,255,255,0.08))"}`,
          background: open ? "rgba(99,102,241,0.14)" : "var(--color-canvas-raised, #111827)",
          color: "var(--color-ink, #f9fafb)",
          cursor: "pointer",
          fontSize: 11.5,
          fontWeight: 600,
          overflow: "hidden",
          transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
          boxShadow: open ? "0 0 12px rgba(99,102,241,0.25)" : "var(--shadow-clay-sm, 0 2px 6px rgba(0,0,0,0.15))",
          animation: !open && agents.length > 1 ? "pillBorderFlash 1.2s ease-out" : "none",
        }}
        title={pillAgent ? `${pillAgent.name} (${pillAgent.model.split("/").pop()}): ${currentTokens.toLocaleString()} / ${pillLimit.toLocaleString()} tokens (${pillPct.toFixed(1)}%). Auto-cycles every 5s.` : "View Context Window & Token Optimization Stats"}
      >
        {/* Subtle 5-second countdown track at bottom */}
        {!open && agents.length > 1 && !isHovered && (
          <div
            key={`timer-${cycleIndex}`}
            style={{
              position: "absolute",
              bottom: 0,
              left: 0,
              height: 2,
              background: `linear-gradient(90deg, ${pillColor}, #a78bfa)`,
              borderRadius: 1,
              animation: "timerCountdown 5s linear forwards",
              pointerEvents: "none",
            }}
          />
        )}

        {/* Agent Profile Picture / Pulse Icon with Spring Spin */}
        <div key={`avatar-${pillAgent?.id || "default"}-${cycleIndex}`} className="pill-avatar-spring" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          {pillAgent ? (
            <AgentAvatar name={pillAgent.name} id={pillAgent.id} role={pillAgent.role} size={18} hideBadge />
          ) : (
            <Activity size={13} style={{ color: pillColor, animation: currentTokens > 0 ? "meterPulse 2.5s infinite ease-in-out" : "none" }} />
          )}
        </div>

        {/* Agent Name + Tokens Slot Ticker */}
        <div
          key={`text-${pillAgent?.id || "default"}-${cycleIndex}`}
          className="pill-ticker-text"
          style={{ display: "flex", alignItems: "center", gap: 5, letterSpacing: "-0.01em" }}
        >
          {pillAgent && (
            <span style={{ fontWeight: 700, color: "var(--color-ink, #f9fafb)", maxWidth: 75, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {pillAgent.name}
            </span>
          )}
          <span style={{ color: pillAgent ? "var(--color-mute, #9ca3af)" : "var(--color-ink, #f9fafb)", fontWeight: 500 }}>
            {pillFormattedTokens}
          </span>
        </div>

        {/* Mini progress bar with glowing liquid gradient */}
        <div
          style={{
            width: 34,
            height: 5,
            background: "rgba(148, 163, 184, 0.15)",
            borderRadius: 3,
            overflow: "hidden",
            position: "relative",
            flexShrink: 0,
          }}
        >
          <div
            className={pillPct > 0 ? "shimmer-progress" : ""}
            style={{
              width: `${Math.min(100, Math.max(4, pillPct))}%`,
              height: "100%",
              borderRadius: 3,
              transition: "width 0.7s cubic-bezier(0.34, 1.56, 0.64, 1), background-color 0.4s ease",
            }}
          />
        </div>

        {/* Agent specific capacity percentage with pulse flash */}
        <span
          key={`pct-${pillAgent?.id || "default"}-${cycleIndex}`}
          className="pill-pct-pulse"
          style={{ fontSize: 10.5, color: pillColor, fontWeight: 700, minWidth: 26, textAlign: "right", flexShrink: 0 }}
        >
          {pillPct.toFixed(0)}%
        </span>
      </button>

      {/* Popover Card */}
      {open && (
        <div
          className="context-meter-popover"
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            right: 0,
            width: 350,
            maxHeight: "calc(100vh - 65px)",
            overflowY: "auto",
            background: "var(--bg-glass-card, #131326)",
            backdropFilter: "blur(24px)",
            WebkitBackdropFilter: "blur(24px)",
            border: "1px solid var(--border-glass, rgba(255,255,255,0.14))",
            borderRadius: "var(--radius-lg, 10px)",
            boxShadow: "0 20px 50px rgba(0,0,0,0.5), 0 0 1px 1px rgba(255,255,255,0.05) inset",
            padding: "12px 14px",
            zIndex: 1000,
            display: "flex",
            flexDirection: "column",
            gap: 10,
            animation: "popoverEnter 0.2s cubic-bezier(0.16, 1, 0.3, 1)",
          }}
        >
          {/* Header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ width: 22, height: 22, borderRadius: 5, background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.3)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Zap size={12} style={{ color: "var(--color-primary, #6366f1)" }} />
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.02em", color: "var(--color-ink, #f9fafb)", display: "flex", alignItems: "center", gap: 5 }}>
                  Context & Token Meter
                  <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 999, background: "rgba(16, 185, 129, 0.12)", color: "#10b981", border: "1px solid rgba(16, 185, 129, 0.25)", fontWeight: 600 }}>
                    LIVE
                  </span>
                </div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <button
                className="btn btn-icon-sm btn-ghost"
                onClick={fetchStats}
                disabled={loading}
                title="Refresh stats"
                style={{ borderRadius: 5, padding: 3 }}
              >
                <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
              </button>
              <button
                className="btn btn-icon-sm btn-ghost"
                onClick={() => setOpen(false)}
                title="Close"
                style={{ borderRadius: 5, padding: 3 }}
              >
                <X size={12} />
              </button>
            </div>
          </div>

          {/* Context Window Utilization Main Gauge */}
          <div
            style={{
              background: "var(--color-canvas-soft, #0a0a1a)",
              padding: "10px 12px",
              borderRadius: "var(--radius-md, 6px)",
              border: "1px solid var(--color-hairline, #2a2a3f)",
              position: "relative",
              overflow: "hidden",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0, maxWidth: "58%" }}>
                {selectedAgent ? (
                  <AgentAvatar name={selectedAgent.name} id={selectedAgent.id} role={selectedAgent.role} size={18} hideBadge />
                ) : (
                  <Zap size={13} style={{ color: "var(--color-primary, #6366f1)", flexShrink: 0 }} />
                )}
                <span style={{ fontSize: 11, color: "var(--color-ink, #f9fafb)", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {selectedAgent ? `${selectedAgent.name} (${selectedAgent.model.split("/").pop()})` : `Active Context (${currentModel.split("/").pop()})`}
                </span>
              </div>
              <span style={{ fontSize: 11, fontWeight: 700, color: gaugeColor }}>
                {currentTokens.toLocaleString()} / {windowLimit.toLocaleString()} ({pct.toFixed(1)}%)
              </span>
            </div>

            {/* Main Progress Bar Container */}
            <div style={{ height: 7, background: "rgba(255,255,255,0.06)", borderRadius: 4, overflow: "hidden", position: "relative", marginBottom: 6 }}>
              <div
                className="shimmer-progress"
                style={{
                  height: "100%",
                  width: `${Math.min(100, Math.max(2, pct))}%`,
                  borderRadius: 4,
                  transition: "width 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)",
                  boxShadow: `0 0 8px ${gaugeColor}88`,
                }}
              />
            </div>

            {/* Bottom Scale Markers */}
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, color: "var(--color-mute, #9ca3af)" }}>
              <span>0k</span>
              <span style={{ color: pct >= 80 ? "#ef4444" : "#10b981", fontWeight: 600 }}>
                {pct >= 80 ? "⚠️ Compaction Trigger (80%)" : "✓ Safe Window (<80%)"}
              </span>
              <span>{(windowLimit / 1000).toFixed(0)}k max</span>
            </div>
          </div>

          {/* Multi-Agent Team Context Breakdown */}
          {agents.length > 0 && (
            <div style={{ borderTop: "1px solid var(--color-hairline, #2a2a3f)", paddingTop: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: "var(--color-mute, #9ca3af)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  Team Models Roster
                </span>
                <span style={{ fontSize: 9, color: "var(--color-mute, #9ca3af)" }}>
                  Click to inspect
                </span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 95, overflowY: "auto", paddingRight: 2 }}>
                {agents.map(ag => {
                  const isSelected = selectedAgent?.id === ag.id;
                  const agLimit = getContextWindow(ag.model);
                  const agPct = agLimit > 0 ? Math.min(100, Math.round((currentTokens / agLimit) * 1000) / 10) : 0;
                  const agColor = getGaugeColor(agPct);

                  return (
                    <button
                      key={ag.id}
                      onClick={() => setSelectedAgentId(ag.id)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        padding: "5px 8px",
                        borderRadius: 5,
                        border: isSelected ? "1px solid var(--color-primary, #6366f1)" : "1px solid var(--color-hairline, #2a2a3f)",
                        background: isSelected ? "rgba(99,102,241,0.12)" : "var(--color-canvas-soft, #0a0a1a)",
                        cursor: "pointer",
                        width: "100%",
                        textAlign: "left",
                        color: "var(--color-ink, #f9fafb)",
                        fontSize: 11,
                        transition: "all 0.15s ease",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0, flex: 1 }}>
                        <AgentAvatar name={ag.name} id={ag.id} role={ag.role} size={18} hideBadge />
                        <span style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {ag.name}
                        </span>
                        <span style={{ fontSize: 9, color: "var(--color-mute, #9ca3af)", background: "rgba(255,255,255,0.04)", padding: "1px 4px", borderRadius: 3, flexShrink: 0 }}>
                          {ag.model.split("/").pop()}
                        </span>
                      </div>

                      {/* Agent context meter mini bar */}
                      <div style={{ display: "flex", alignItems: "center", gap: 5, flexShrink: 0 }}>
                        <div style={{ width: 36, height: 4, background: "rgba(255,255,255,0.08)", borderRadius: 2, overflow: "hidden" }}>
                          <div
                            style={{
                              width: `${Math.min(100, Math.max(4, agPct))}%`,
                              height: "100%",
                              background: agColor,
                              borderRadius: 2,
                              transition: "width 0.4s ease",
                            }}
                          />
                        </div>
                        <span style={{ fontSize: 9.5, fontWeight: 700, color: agColor, minWidth: 40, textAlign: "right" }}>
                          {(agLimit / 1000).toFixed(0)}k ({agPct.toFixed(0)}%)
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>

              {bottleneck && bottleneck.limit < 100000 && (
                <div style={{ marginTop: 6, padding: "5px 8px", background: "rgba(245,158,11,0.09)", border: "1px solid rgba(245,158,11,0.25)", borderRadius: 5, fontSize: 10, color: "#f59e0b", display: "flex", alignItems: "center", gap: 6 }}>
                  <AlertTriangle size={12} style={{ flexShrink: 0 }} />
                  <span>Team bottleneck: <strong>{bottleneck.agent.name}</strong> ({bottleneck.limit / 1000}k window). Rolling micro-compaction is active.</span>
                </div>
              )}
            </div>
          )}

          {/* Real-Time Session Metrics */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div
              style={{
                background: "var(--color-canvas-soft, #0a0a1a)",
                padding: "8px 10px",
                borderRadius: "var(--radius-md, 6px)",
                border: "1px solid var(--color-hairline, #2a2a3f)",
              }}
            >
              <div style={{ fontSize: 9.5, color: "var(--color-mute, #9ca3af)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>
                Total Tokens
              </div>
              <div style={{ fontSize: 15, fontWeight: 800, color: "var(--color-ink, #f9fafb)", marginTop: 2, letterSpacing: "-0.02em" }}>
                {costStats?.total_tokens ? costStats.total_tokens.toLocaleString() : currentTokens.toLocaleString()}
              </div>
              <div style={{ fontSize: 9, color: "var(--color-mute, #9ca3af)", marginTop: 2 }}>
                Prompt: {costStats?.total_prompt_tokens?.toLocaleString() || "—"}
              </div>
            </div>

            <div
              style={{
                background: "var(--color-canvas-soft, #0a0a1a)",
                padding: "8px 10px",
                borderRadius: "var(--radius-md, 6px)",
                border: "1px solid var(--color-hairline, #2a2a3f)",
              }}
            >
              <div style={{ fontSize: 9.5, color: "var(--color-mute, #9ca3af)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>
                Project Spend
              </div>
              <div style={{ fontSize: 15, fontWeight: 800, color: "#10b981", marginTop: 2, letterSpacing: "-0.02em" }}>
                ${costStats?.total_spend_usd ? costStats.total_spend_usd.toFixed(4) : "0.0000"}
              </div>
              <div style={{ fontSize: 9, color: "var(--color-mute, #9ca3af)", marginTop: 2 }}>
                Completion: {costStats?.total_completion_tokens?.toLocaleString() || "—"}
              </div>
            </div>
          </div>

          {/* Token Economy & Compaction Features */}
          <div style={{ borderTop: "1px solid var(--color-hairline, #2a2a3f)", paddingTop: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: "var(--color-mute, #9ca3af)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
              Optimization Engines
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 11 }}>
                <span style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--color-body, #cbd5e1)" }}>
                  <Shield size={11} style={{ color: "#10b981" }} />
                  AST Dead-End Snipping
                </span>
                <span style={{ fontSize: 9.5, fontWeight: 700, color: "#10b981", background: "rgba(16, 185, 129, 0.12)", padding: "1px 6px", borderRadius: 3, border: "1px solid rgba(16, 185, 129, 0.25)" }}>
                  ACTIVE
                </span>
              </div>

              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 11 }}>
                <span style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--color-body, #cbd5e1)" }}>
                  <TrendingDown size={11} style={{ color: "#818cf8" }} />
                  Historical Micro-Compaction
                </span>
                <span style={{ fontSize: 9.5, fontWeight: 700, color: "#818cf8", background: "rgba(129, 140, 248, 0.12)", padding: "1px 6px", borderRadius: 3, border: "1px solid rgba(129, 140, 248, 0.25)" }}>
                  &gt;2 TURNS
                </span>
              </div>

              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 11 }}>
                <span style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--color-body, #cbd5e1)" }}>
                  <Sparkles size={11} style={{ color: "#fbbf24" }} />
                  Prompt Prefix Caching
                </span>
                <span style={{ fontSize: 9.5, fontWeight: 700, color: "#fbbf24", background: "rgba(251, 191, 36, 0.12)", padding: "1px 6px", borderRadius: 3, border: "1px solid rgba(251, 191, 36, 0.25)" }}>
                  ENABLED
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
