"use client";
import React, { useState, useEffect, useCallback } from "react";
import {
  Activity,
  Zap,
  Clock,
  Coins,
  Cpu,
  RefreshCw,
  Trash2,
  CheckCircle2,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Filter,
  Layers,
  Info,
  HelpCircle,
} from "lucide-react";
import { api } from "@/hooks/useApi";
import SettingTooltip from "./SettingTooltip";

interface SpanRecord {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  name: string;
  status: string;
  start_time: string | null;
  end_time: string | null;
  duration_ms: number;
  attributes: Record<string, any>;
  agent_name?: string;
  agent_role?: string;
  model?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  tool_name?: string;
}

interface ObservabilityStats {
  total_spans: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  avg_latency_ms: number;
  error_count: number;
  models_used: string[];
  status: string;
}

interface Props {
  onToast: (msg: string, type: "success" | "error" | "info") => void;
}

export default function ObservabilitySettings({ onToast }: Props) {
  const [stats, setStats] = useState<ObservabilityStats | null>(null);
  const [traces, setTraces] = useState<SpanRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedSpanId, setExpandedSpanId] = useState<string | null>(null);
  const [filterAgent, setFilterAgent] = useState<string>("");
  const [showGuide, setShowGuide] = useState(false);

  const fetchTelemetry = useCallback(async () => {
    setLoading(true);
    try {
      const [statsData, tracesData] = await Promise.all([
        api.getObservabilityStats().catch(() => null),
        api.getObservabilityTraces(filterAgent || undefined).catch(() => null),
      ]);

      if (statsData) {
        setStats(statsData);
      }
      if (tracesData) {
        setTraces(tracesData.traces || []);
      }
    } catch (e) {
      console.warn("Telemetry fetch error:", e);
    } finally {
      setLoading(false);
    }
  }, [filterAgent]);

  useEffect(() => {
    fetchTelemetry();
  }, [fetchTelemetry]);

  const handleClear = async () => {
    try {
      await api.clearObservability();
      setTraces([]);
      setStats((prev) =>
        prev
          ? {
              ...prev,
              total_spans: 0,
              total_prompt_tokens: 0,
              total_completion_tokens: 0,
              avg_latency_ms: 0,
              error_count: 0,
              models_used: [],
            }
          : null
      );
      onToast("Telemetry buffer cleared", "info");
    } catch {
      onToast("Failed to clear telemetry buffer", "error");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* ── Brand Header Banner ── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "16px 20px",
          background: "linear-gradient(135deg, rgba(99, 102, 241, 0.12) 0%, rgba(168, 85, 247, 0.08) 100%)",
          border: "1px solid rgba(99, 102, 241, 0.25)",
          borderRadius: "var(--radius-md, 10px)",
          flexWrap: "wrap",
          gap: 14,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <img
            src="/logos/openllmetry.png"
            alt="OpenLLMetry"
            style={{
              width: 42,
              height: 42,
              borderRadius: "var(--radius-sm, 8px)",
              objectFit: "contain",
              background: "#0a0a1a",
              padding: 5,
              border: "1px solid rgba(0, 0, 0, 0.1)",
              boxShadow: "0 2px 8px rgba(0, 0, 0, 0.08)",
            }}
          />
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <h3
                style={{
                  margin: 0,
                  fontSize: 16,
                  fontWeight: 700,
                  color: "var(--color-fg-strong, #18181b)",
                  fontFamily: "var(--font-family-display, sans-serif)",
                }}
              >
                OpenLLMetry Live Observability
              </h3>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 5,
                  fontSize: 10.5,
                  fontWeight: 600,
                  padding: "2px 8px",
                  borderRadius: 12,
                  background: "rgba(16, 185, 129, 0.15)",
                  color: "#059669",
                  border: "1px solid rgba(16, 185, 129, 0.35)",
                }}
              >
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background: "#10b981",
                    display: "inline-block",
                  }}
                />
                100% Realtime Active
              </span>
            </div>
            <p
              style={{
                margin: "4px 0 0 0",
                fontSize: 12,
                color: "var(--color-body, #52525b)",
                lineHeight: 1.4,
              }}
            >
              Real OpenTelemetry traces, token usage, and latency captured automatically during live agent execution.
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            onClick={() => setShowGuide(!showGuide)}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 5,
              padding: "7px 12px",
              background: showGuide ? "rgba(99, 102, 241, 0.15)" : "var(--color-canvas-raised, #ffffff)",
              color: showGuide ? "#4f46e5" : "var(--color-fg-strong, #18181b)",
              border: "1px solid var(--color-hairline, #d1d5db)",
              borderRadius: "var(--radius-sm, 6px)",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            <HelpCircle size={13} />
            {showGuide ? "Hide Guide" : "Metrics Guide"}
          </button>
          <button
            onClick={fetchTelemetry}
            disabled={loading}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 5,
              padding: "7px 12px",
              background: "var(--color-canvas-raised, #ffffff)",
              color: "var(--color-fg-strong, #18181b)",
              border: "1px solid var(--color-hairline, #d1d5db)",
              borderRadius: "var(--radius-sm, 6px)",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
          <button
            onClick={handleClear}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 5,
              padding: "7px 12px",
              background: "rgba(239, 68, 68, 0.08)",
              color: "var(--color-danger, #dc2626)",
              border: "1px solid rgba(239, 68, 68, 0.25)",
              borderRadius: "var(--radius-sm, 6px)",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
            }}
            title="Clear all recorded traces in buffer"
          >
            <Trash2 size={12} />
            Clear Traces
          </button>
        </div>
      </div>

      {/* ── Collapsible Explainer Guide ── */}
      {showGuide && (
        <div
          style={{
            padding: "16px 18px",
            background: "var(--color-canvas-soft, #f4f4f5)",
            border: "1px solid var(--color-hairline, #d1d5db)",
            borderRadius: "var(--radius-md, 10px)",
            fontSize: 12,
            lineHeight: 1.6,
          }}
        >
          <div style={{ fontWeight: 700, color: "var(--color-fg-strong, #18181b)", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
            <Info size={14} color="#4f46e5" />
            How OpenLLMetry Observability Works in Carole.ai
          </div>
          <p style={{ margin: "0 0 10px 0", color: "var(--color-body, #52525b)" }}>
            OpenLLMetry is built on top of the <strong>OpenTelemetry (OTel)</strong> standard. When you chat with an agent, decompose a task with Archer, or run a tool, the OpenLLMetry SDK intercepts the requests in-process and tracks:
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(220px, 100%), 1fr))", gap: 12 }}>
            <div style={{ padding: "8px 12px", background: "var(--color-canvas-raised, #ffffff)", borderRadius: 6, border: "1px solid var(--color-hairline, #d1d5db)" }}>
              <strong style={{ color: "var(--color-fg-strong, #18181b)" }}>1. Spans</strong>: Each distinct operation (agent goal, planning step, code generation, tool invocation) is tracked with exact start/end times and error statuses.
            </div>
            <div style={{ padding: "8px 12px", background: "var(--color-canvas-raised, #ffffff)", borderRadius: 6, border: "1px solid var(--color-hairline, #d1d5db)" }}>
              <strong style={{ color: "var(--color-fg-strong, #18181b)" }}>2. Tokens</strong>: Input (prompt) and output (completion) tokens are extracted directly from the actual API response headers of OpenAI, Anthropic, Gemini, and Ollama.
            </div>
            <div style={{ padding: "8px 12px", background: "var(--color-canvas-raised, #ffffff)", borderRadius: 6, border: "1px solid var(--color-hairline, #d1d5db)" }}>
              <strong style={{ color: "var(--color-fg-strong, #18181b)" }}>3. Latency</strong>: Exact roundtrip durations in milliseconds so you can easily identify slow models, timeout issues, or sluggish tool operations.
            </div>
          </div>
        </div>
      )}

      {/* ── Metrics Cards Grid with Explanatory Tooltips ── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(min(190px, 100%), 1fr))",
          gap: 12,
        }}
      >
        {/* Card 1: Spans */}
        <div
          style={{
            padding: "16px 18px",
            background: "var(--color-canvas-raised, #ffffff)",
            border: "1px solid var(--color-hairline, #d1d5db)",
            borderRadius: "var(--radius-md, 10px)",
            boxShadow: "var(--shadow-clay-sm, 0 1px 3px rgba(0,0,0,0.05))",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--color-mute, #71717a)", fontSize: 11.5, fontWeight: 600 }}>
              <Activity size={14} color="#4f46e5" />
              Total Recorded Spans
            </div>
            <SettingTooltip
              title="OpenTelemetry Spans"
              why="Measures every discrete execution step executed by your multi-agent swarm."
              how="Each LLM reasoning loop, tool execution (read_file, git_status), and agent step is recorded as an individual OpenTelemetry span."
            />
          </div>
          <div style={{ fontSize: 24, fontWeight: 800, color: "var(--color-fg-strong, #18181b)", marginTop: 6, fontFamily: "var(--font-family-mono, monospace)" }}>
            {stats?.total_spans ?? traces.length}
          </div>
          <div style={{ fontSize: 10.5, color: "var(--color-mute, #71717a)", marginTop: 2 }}>
            Execution units captured in memory
          </div>
        </div>

        {/* Card 2: Tokens */}
        <div
          style={{
            padding: "16px 18px",
            background: "var(--color-canvas-raised, #ffffff)",
            border: "1px solid var(--color-hairline, #d1d5db)",
            borderRadius: "var(--radius-md, 10px)",
            boxShadow: "var(--shadow-clay-sm, 0 1px 3px rgba(0,0,0,0.05))",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--color-mute, #71717a)", fontSize: 11.5, fontWeight: 600 }}>
              <Coins size={14} color="#d97706" />
              Total Tokens Tracked
            </div>
            <SettingTooltip
              title="LLM Token Consumption"
              why="Tracks cumulative prompt and completion tokens to measure API burn and model usage."
              how="Auto-instruments model responses to record prompt tokens (input context) and completion tokens (model output)."
            />
          </div>
          <div style={{ fontSize: 24, fontWeight: 800, color: "var(--color-fg-strong, #18181b)", marginTop: 6, fontFamily: "var(--font-family-mono, monospace)" }}>
            {stats ? (stats.total_prompt_tokens + stats.total_completion_tokens).toLocaleString() : 0}
          </div>
          <div style={{ fontSize: 11, color: "var(--color-mute, #71717a)", marginTop: 2, fontFamily: "var(--font-family-mono, monospace)" }}>
            {stats?.total_prompt_tokens.toLocaleString() ?? 0} in / {stats?.total_completion_tokens.toLocaleString() ?? 0} out
          </div>
        </div>

        {/* Card 3: Latency */}
        <div
          style={{
            padding: "16px 18px",
            background: "var(--color-canvas-raised, #ffffff)",
            border: "1px solid var(--color-hairline, #d1d5db)",
            borderRadius: "var(--radius-md, 10px)",
            boxShadow: "var(--shadow-clay-sm, 0 1px 3px rgba(0,0,0,0.05))",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--color-mute, #71717a)", fontSize: 11.5, fontWeight: 600 }}>
              <Clock size={14} color="#059669" />
              Avg Latency
            </div>
            <SettingTooltip
              title="Average Roundtrip Duration"
              why="Highlights whether agents, models, or tool executions are encountering performance lag."
              how="Calculates the mean duration (end_time - start_time) in milliseconds across all completed spans in the active session."
            />
          </div>
          <div style={{ fontSize: 24, fontWeight: 800, color: "var(--color-fg-strong, #18181b)", marginTop: 6, fontFamily: "var(--font-family-mono, monospace)" }}>
            {stats?.avg_latency_ms ? `${stats.avg_latency_ms} ms` : "—"}
          </div>
          <div style={{ fontSize: 10.5, color: "var(--color-mute, #71717a)", marginTop: 2 }}>
            Per-operation response time
          </div>
        </div>

        {/* Card 4: Active Models */}
        <div
          style={{
            padding: "16px 18px",
            background: "var(--color-canvas-raised, #ffffff)",
            border: "1px solid var(--color-hairline, #d1d5db)",
            borderRadius: "var(--radius-md, 10px)",
            boxShadow: "var(--shadow-clay-sm, 0 1px 3px rgba(0,0,0,0.05))",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--color-mute, #71717a)", fontSize: 11.5, fontWeight: 600 }}>
              <Cpu size={14} color="#7c3aed" />
              Active Swarm Models
            </div>
            <SettingTooltip
              title="Discovered Foundation Models"
              why="Confirms which AI models are actively receiving prompts from your orchestrator and subagents."
              how="Extracted from the 'llm.model' attribute of incoming OpenTelemetry spans during real agent invocations."
            />
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8 }}>
            {stats?.models_used && stats.models_used.length > 0 ? (
              stats.models_used.map((m) => (
                <span
                  key={m}
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    padding: "2px 7px",
                    borderRadius: 4,
                    background: "rgba(124, 58, 237, 0.12)",
                    color: "#7c3aed",
                    border: "1px solid rgba(124, 58, 237, 0.25)",
                    fontFamily: "var(--font-family-mono, monospace)",
                  }}
                >
                  {m}
                </span>
              ))
            ) : (
              <span style={{ fontSize: 12, color: "var(--color-mute, #71717a)" }}>None recorded yet</span>
            )}
          </div>
        </div>
      </div>

      {/* ── Filter Toolbar ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap", marginTop: 4 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13.5, fontWeight: 700, color: "var(--color-fg-strong, #18181b)" }}>
          <Layers size={15} color="#4f46e5" />
          Live Trace Streams ({traces.length})
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Filter size={13} color="var(--color-mute, #71717a)" />
          <input
            type="text"
            placeholder="Filter by agent..."
            value={filterAgent}
            onChange={(e) => setFilterAgent(e.target.value)}
            style={{
              padding: "5px 12px",
              background: "var(--color-canvas-raised, #ffffff)",
              border: "1px solid var(--color-hairline, #d1d5db)",
              borderRadius: "var(--radius-sm, 6px)",
              color: "var(--color-fg-strong, #18181b)",
              fontSize: 12,
              outline: "none",
              width: 170,
            }}
          />
        </div>
      </div>

      {/* ── Trace Waterfall List ── */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 8,
          maxHeight: 520,
          overflowY: "auto",
          paddingRight: 4,
        }}
      >
        {traces.length === 0 ? (
          <div
            style={{
              textAlign: "center",
              padding: "44px 20px",
              background: "var(--color-canvas-raised, #ffffff)",
              border: "1px dashed var(--color-hairline, #d1d5db)",
              borderRadius: "var(--radius-md, 10px)",
              color: "var(--color-mute, #71717a)",
              fontSize: 13,
            }}
          >
            <Activity size={28} style={{ margin: "0 auto 10px", opacity: 0.45, color: "var(--color-primary)" }} />
            <div style={{ fontWeight: 700, color: "var(--color-fg-strong, #18181b)", marginBottom: 4, fontSize: 14 }}>
              Ready &amp; Listening for Agent Activity
            </div>
            <div style={{ fontSize: 12, color: "var(--color-body, #52525b)", maxWidth: 440, margin: "0 auto" }}>
              Send an engineering goal to an agent in the <strong>Team Chat</strong> (e.g. <code>@archer solve issue</code>). OpenLLMetry will automatically stream real-time traces, token metrics, and tool execution spans here.
            </div>
          </div>
        ) : (
          traces.map((trace) => {
            const isExpanded = expandedSpanId === trace.span_id;
            const isChild = Boolean(trace.parent_span_id);

            return (
              <div
                key={trace.span_id}
                style={{
                  marginLeft: isChild ? 16 : 0,
                  padding: "11px 16px",
                  background: isExpanded
                    ? "var(--color-canvas-soft, rgba(0,0,0,0.03))"
                    : "var(--color-canvas-raised, #ffffff)",
                  border: isChild
                    ? "1px solid rgba(79, 70, 229, 0.25)"
                    : "1px solid var(--color-hairline, #d1d5db)",
                  borderLeft: isChild
                    ? "3.5px solid #4f46e5"
                    : "3.5px solid #10b981",
                  borderRadius: "var(--radius-sm, 8px)",
                  boxShadow: "var(--shadow-clay-sm, 0 1px 2px rgba(0,0,0,0.04))",
                  transition: "background 0.15s ease",
                }}
              >
                {/* Span Header Row */}
                <div
                  onClick={() => setExpandedSpanId(isExpanded ? null : trace.span_id)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    cursor: "pointer",
                    gap: 12,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                    {trace.status === "ERROR" ? (
                      <AlertCircle size={15} color="#dc2626" style={{ flexShrink: 0 }} />
                    ) : (
                      <CheckCircle2 size={15} color="#059669" style={{ flexShrink: 0 }} />
                    )}
                    <span
                      style={{
                        fontFamily: "var(--font-family-mono, monospace)",
                        fontSize: 12.5,
                        fontWeight: 700,
                        color: "var(--color-fg-strong, #18181b)",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {trace.name}
                    </span>

                    {trace.agent_role && (
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 700,
                          padding: "2px 7px",
                          borderRadius: 4,
                          background: "rgba(79, 70, 229, 0.1)",
                          color: "#4f46e5",
                          border: "1px solid rgba(79, 70, 229, 0.2)",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {trace.agent_role}
                      </span>
                    )}

                    {trace.model && (
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 700,
                          padding: "2px 7px",
                          borderRadius: 4,
                          background: "rgba(124, 58, 237, 0.1)",
                          color: "#7c3aed",
                          border: "1px solid rgba(124, 58, 237, 0.2)",
                          whiteSpace: "nowrap",
                          fontFamily: "var(--font-family-mono, monospace)",
                        }}
                      >
                        {trace.model}
                      </span>
                    )}
                  </div>

                  {/* Right Metadata */}
                  <div style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
                    {Boolean(trace.prompt_tokens || trace.completion_tokens) && (
                      <span
                        style={{
                          fontSize: 11,
                          fontFamily: "var(--font-family-mono, monospace)",
                          fontWeight: 600,
                          color: "var(--color-mute, #71717a)",
                        }}
                      >
                        {trace.prompt_tokens ?? 0} / {trace.completion_tokens ?? 0} tok
                      </span>
                    )}
                    <span
                      style={{
                        fontSize: 11.5,
                        fontFamily: "var(--font-family-mono, monospace)",
                        fontWeight: 700,
                        color: trace.duration_ms > 1000 ? "#d97706" : "#059669",
                      }}
                    >
                      {trace.duration_ms} ms
                    </span>
                    {isExpanded ? (
                      <ChevronUp size={14} color="var(--color-mute, #71717a)" />
                    ) : (
                      <ChevronDown size={14} color="var(--color-mute, #71717a)" />
                    )}
                  </div>
                </div>

                {/* Expanded Details View */}
                {isExpanded && (
                  <div
                    style={{
                      marginTop: 12,
                      paddingTop: 12,
                      borderTop: "1px solid var(--color-hairline, #d1d5db)",
                      fontSize: 11.5,
                    }}
                  >
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(min(200px, 100%), 1fr))",
                        gap: 8,
                        marginBottom: 10,
                      }}
                    >
                      <div>
                        <span style={{ color: "var(--color-mute, #71717a)", fontWeight: 600 }}>Trace ID:</span>{" "}
                        <code style={{ fontFamily: "var(--font-family-mono, monospace)", color: "#4f46e5", fontWeight: 600 }}>
                          {trace.trace_id || "local"}
                        </code>
                      </div>
                      <div>
                        <span style={{ color: "var(--color-mute, #71717a)", fontWeight: 600 }}>Span ID:</span>{" "}
                        <code style={{ fontFamily: "var(--font-family-mono, monospace)", color: "#7c3aed", fontWeight: 600 }}>
                          {trace.span_id}
                        </code>
                      </div>
                    </div>

                    {/* Raw OpenTelemetry Attributes */}
                    <div style={{ color: "var(--color-mute, #71717a)", marginBottom: 4, fontWeight: 700, fontSize: 11 }}>
                      OpenTelemetry Span Attributes:
                    </div>
                    <pre
                      style={{
                        margin: 0,
                        padding: "10px 12px",
                        background: "var(--color-canvas-soft, #f4f4f5)",
                        border: "1px solid var(--color-hairline, #e4e4e7)",
                        borderRadius: 6,
                        fontFamily: "var(--font-family-mono, monospace)",
                        fontSize: 11,
                        color: "var(--color-ink, #27272a)",
                        overflowX: "auto",
                        maxHeight: 160,
                        lineHeight: 1.45,
                      }}
                    >
                      {JSON.stringify(trace.attributes, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
