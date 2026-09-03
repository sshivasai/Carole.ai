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
  Play,
  CheckCircle2,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Filter,
  ShieldCheck,
  Terminal,
  Layers,
} from "lucide-react";

interface SpanRecord {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  name: string;
  status: string;
  start_time: string | null;
  end_time: string | null;
  duration_ms: number;
  attributes: Record<string, string>;
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
  const [emitting, setEmitting] = useState(false);
  const [expandedSpanId, setExpandedSpanId] = useState<string | null>(null);
  const [filterAgent, setFilterAgent] = useState<string>("");

  const fetchTelemetry = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, tracesRes] = await Promise.all([
        fetch("/api/observability/stats").catch(() => null),
        fetch(`/api/observability/traces${filterAgent ? `?agent=${encodeURIComponent(filterAgent)}` : ""}`).catch(() => null),
      ]);

      if (statsRes && statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      }
      if (tracesRes && tracesRes.ok) {
        const tracesData = await tracesRes.json();
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

  const handleEmitSample = async () => {
    setEmitting(true);
    try {
      const res = await fetch("/api/observability/emit-sample", { method: "POST" });
      if (res.ok) {
        onToast("Sample OpenLLMetry swarm trace emitted!", "success");
        await fetchTelemetry();
      } else {
        onToast("Failed to emit sample trace", "error");
      }
    } catch {
      onToast("Network error emitting trace", "error");
    } finally {
      setEmitting(false);
    }
  };

  const handleClear = async () => {
    try {
      const res = await fetch("/api/observability/clear", { method: "POST" });
      if (res.ok) {
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
      }
    } catch {
      onToast("Failed to clear telemetry buffer", "error");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Brand Header Banner */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "16px 20px",
          background: "linear-gradient(135deg, rgba(99, 102, 241, 0.08) 0%, rgba(168, 85, 247, 0.05) 100%)",
          border: "1px solid rgba(168, 85, 247, 0.2)",
          borderRadius: 12,
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <img
            src="/logos/openllmetry.png"
            alt="OpenLLMetry"
            style={{
              width: 38,
              height: 38,
              borderRadius: 10,
              objectFit: "contain",
              background: "#0a0a1a",
              padding: 4,
              border: "1px solid rgba(255, 255, 255, 0.1)",
            }}
          />
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "var(--color-heading, #ffffff)" }}>
                OpenLLMetry Observability
              </h3>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  fontSize: 10.5,
                  fontWeight: 600,
                  padding: "2px 8px",
                  borderRadius: 12,
                  background: "rgba(16, 185, 129, 0.15)",
                  color: "#34d399",
                  border: "1px solid rgba(16, 185, 129, 0.3)",
                }}
              >
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#10b981", animation: "pulse 2s infinite" }} />
                Native Tracing Active
              </span>
            </div>
            <p style={{ margin: "3px 0 0 0", fontSize: 12, color: "var(--color-body, #94a3b8)" }}>
              OpenTelemetry-native span collection for LLM calls, multi-agent swarms, tool executions, and tokens.
            </p>
          </div>
        </div>

        {/* Quick Actions */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            onClick={handleEmitSample}
            disabled={emitting}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "6px 12px",
              background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
              color: "#ffffff",
              border: "none",
              borderRadius: 8,
              fontSize: 12,
              fontWeight: 600,
              cursor: emitting ? "not-allowed" : "pointer",
              opacity: emitting ? 0.7 : 1,
            }}
          >
            <Play size={13} />
            {emitting ? "Emitting..." : "Emit Swarm Trace"}
          </button>
          <button
            onClick={fetchTelemetry}
            disabled={loading}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 5,
              padding: "6px 12px",
              background: "rgba(255, 255, 255, 0.05)",
              color: "var(--color-heading, #ffffff)",
              border: "1px solid var(--color-hairline, #2a2a3f)",
              borderRadius: 8,
              fontSize: 12,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            <RefreshCw size={12} className={loading ? "spin" : ""} />
            Refresh
          </button>
          <button
            onClick={handleClear}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 5,
              padding: "6px 10px",
              background: "rgba(239, 68, 68, 0.1)",
              color: "#f87171",
              border: "1px solid rgba(239, 68, 68, 0.25)",
              borderRadius: 8,
              fontSize: 12,
              cursor: "pointer",
            }}
            title="Clear in-memory buffer"
          >
            <Trash2 size={12} />
          </button>
        </div>
      </div>

      {/* Metrics Cards Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 12,
        }}
      >
        <div
          style={{
            padding: "14px 16px",
            background: "rgba(255, 255, 255, 0.02)",
            border: "1px solid var(--color-hairline, #2a2a3f)",
            borderRadius: 10,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--color-mute, #64748b)", fontSize: 11.5 }}>
            <Activity size={13} color="#6366f1" />
            Total Recorded Spans
          </div>
          <div style={{ fontSize: 22, fontWeight: 800, color: "var(--color-heading, #ffffff)", marginTop: 6 }}>
            {stats?.total_spans ?? traces.length}
          </div>
        </div>

        <div
          style={{
            padding: "14px 16px",
            background: "rgba(255, 255, 255, 0.02)",
            border: "1px solid var(--color-hairline, #2a2a3f)",
            borderRadius: 10,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--color-mute, #64748b)", fontSize: 11.5 }}>
            <Coins size={13} color="#f59e0b" />
            Total Tokens Tracked
          </div>
          <div style={{ fontSize: 22, fontWeight: 800, color: "var(--color-heading, #ffffff)", marginTop: 6 }}>
            {stats ? (stats.total_prompt_tokens + stats.total_completion_tokens).toLocaleString() : 0}
          </div>
          <div style={{ fontSize: 10.5, color: "var(--color-mute, #64748b)", marginTop: 2 }}>
            {stats?.total_prompt_tokens.toLocaleString() ?? 0} in / {stats?.total_completion_tokens.toLocaleString() ?? 0} out
          </div>
        </div>

        <div
          style={{
            padding: "14px 16px",
            background: "rgba(255, 255, 255, 0.02)",
            border: "1px solid var(--color-hairline, #2a2a3f)",
            borderRadius: 10,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--color-mute, #64748b)", fontSize: 11.5 }}>
            <Clock size={13} color="#10b981" />
            Avg Latency
          </div>
          <div style={{ fontSize: 22, fontWeight: 800, color: "var(--color-heading, #ffffff)", marginTop: 6 }}>
            {stats?.avg_latency_ms ? `${stats.avg_latency_ms} ms` : "—"}
          </div>
        </div>

        <div
          style={{
            padding: "14px 16px",
            background: "rgba(255, 255, 255, 0.02)",
            border: "1px solid var(--color-hairline, #2a2a3f)",
            borderRadius: 10,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--color-mute, #64748b)", fontSize: 11.5 }}>
            <Cpu size={13} color="#a855f7" />
            Active Swarm Models
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 8 }}>
            {stats?.models_used && stats.models_used.length > 0 ? (
              stats.models_used.map((m) => (
                <span
                  key={m}
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    padding: "2px 6px",
                    borderRadius: 4,
                    background: "rgba(168, 85, 247, 0.12)",
                    color: "#c084fc",
                    border: "1px solid rgba(168, 85, 247, 0.25)",
                  }}
                >
                  {m}
                </span>
              ))
            ) : (
              <span style={{ fontSize: 12, color: "var(--color-mute, #64748b)" }}>None recorded yet</span>
            )}
          </div>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 600, color: "var(--color-heading, #ffffff)" }}>
          <Layers size={14} color="#6366f1" />
          Live Trace Streams ({traces.length})
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Filter size={12} color="var(--color-mute, #64748b)" />
          <input
            type="text"
            placeholder="Filter by agent..."
            value={filterAgent}
            onChange={(e) => setFilterAgent(e.target.value)}
            style={{
              padding: "4px 10px",
              background: "rgba(255, 255, 255, 0.04)",
              border: "1px solid var(--color-hairline, #2a2a3f)",
              borderRadius: 6,
              color: "var(--color-heading, #ffffff)",
              fontSize: 11.5,
              outline: "none",
              width: 160,
            }}
          />
        </div>
      </div>

      {/* Trace Waterfall List */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 8,
          maxHeight: 480,
          overflowY: "auto",
          paddingRight: 4,
        }}
      >
        {traces.length === 0 ? (
          <div
            style={{
              textAlign: "center",
              padding: "36px 16px",
              background: "rgba(255, 255, 255, 0.01)",
              border: "1px dashed var(--color-hairline, #2a2a3f)",
              borderRadius: 10,
              color: "var(--color-mute, #64748b)",
              fontSize: 13,
            }}
          >
            <Activity size={24} style={{ margin: "0 auto 8px", opacity: 0.4 }} />
            No traces recorded in this session yet.
            <div style={{ fontSize: 11.5, marginTop: 4 }}>
              Click <strong>&quot;Emit Swarm Trace&quot;</strong> above or chat with an agent to see real-time OpenLLMetry telemetry.
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
                  padding: "10px 14px",
                  background: isExpanded ? "rgba(255, 255, 255, 0.04)" : "rgba(255, 255, 255, 0.02)",
                  border: isChild
                    ? "1px solid rgba(99, 102, 241, 0.15)"
                    : "1px solid var(--color-hairline, #2a2a3f)",
                  borderLeft: isChild
                    ? "3px solid #6366f1"
                    : "3px solid #10b981",
                  borderRadius: 8,
                  transition: "background 0.15s ease",
                }}
              >
                {/* Span Header Line */}
                <div
                  onClick={() => setExpandedSpanId(isExpanded ? null : trace.span_id)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    cursor: "pointer",
                    gap: 10,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                    {trace.status === "ERROR" ? (
                      <AlertCircle size={14} color="#f87171" style={{ flexShrink: 0 }} />
                    ) : (
                      <CheckCircle2 size={14} color="#10b981" style={{ flexShrink: 0 }} />
                    )}
                    <span
                      style={{
                        fontFamily: "var(--font-mono, monospace)",
                        fontSize: 12.5,
                        fontWeight: 600,
                        color: "var(--color-heading, #ffffff)",
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
                          fontWeight: 600,
                          padding: "1px 6px",
                          borderRadius: 4,
                          background: "rgba(99, 102, 241, 0.12)",
                          color: "#818cf8",
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
                          fontWeight: 600,
                          padding: "1px 6px",
                          borderRadius: 4,
                          background: "rgba(168, 85, 247, 0.12)",
                          color: "#c084fc",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {trace.model}
                      </span>
                    )}
                  </div>

                  {/* Right Meta (Tokens, Duration, Toggle) */}
                  <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
                    {Boolean(trace.prompt_tokens || trace.completion_tokens) && (
                      <span
                        style={{
                          fontSize: 11,
                          fontFamily: "var(--font-mono, monospace)",
                          color: "var(--color-mute, #64748b)",
                        }}
                      >
                        {trace.prompt_tokens ?? 0} / {trace.completion_tokens ?? 0} tok
                      </span>
                    )}
                    <span
                      style={{
                        fontSize: 11,
                        fontFamily: "var(--font-mono, monospace)",
                        fontWeight: 600,
                        color: trace.duration_ms > 1000 ? "#f59e0b" : "#34d399",
                      }}
                    >
                      {trace.duration_ms} ms
                    </span>
                    {isExpanded ? <ChevronUp size={13} color="#64748b" /> : <ChevronDown size={13} color="#64748b" />}
                  </div>
                </div>

                {/* Expanded Details Drawer */}
                {isExpanded && (
                  <div
                    style={{
                      marginTop: 10,
                      paddingTop: 10,
                      borderTop: "1px solid var(--color-hairline, #2a2a3f)",
                      fontSize: 11,
                    }}
                  >
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
                      <div>
                        <span style={{ color: "var(--color-mute, #64748b)" }}>Trace ID:</span>{" "}
                        <code style={{ fontFamily: "var(--font-mono, monospace)", color: "#a78bfa" }}>
                          {trace.trace_id || "local"}
                        </code>
                      </div>
                      <div>
                        <span style={{ color: "var(--color-mute, #64748b)" }}>Span ID:</span>{" "}
                        <code style={{ fontFamily: "var(--font-mono, monospace)", color: "#a78bfa" }}>
                          {trace.span_id}
                        </code>
                      </div>
                    </div>

                    {/* Raw OpenTelemetry Attributes */}
                    <div style={{ color: "var(--color-mute, #64748b)", marginBottom: 4, fontWeight: 600 }}>
                      OpenTelemetry Attributes:
                    </div>
                    <pre
                      style={{
                        margin: 0,
                        padding: "8px 10px",
                        background: "rgba(0, 0, 0, 0.35)",
                        borderRadius: 6,
                        fontFamily: "var(--font-mono, monospace)",
                        fontSize: 10.5,
                        color: "#94a3b8",
                        overflowX: "auto",
                        maxHeight: 140,
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
