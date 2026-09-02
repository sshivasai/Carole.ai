"use client";
import React, { useState, useEffect } from "react";
import { Sliders, Shield, Save, Loader2, Info, ChevronDown, ChevronUp } from "lucide-react";
import { api } from "@/hooks/useApi";
import AccessControlMatrix, { DEFAULT_ACCESS_CONTROL } from "../AccessControlMatrix";
import type { AccessControlConfig } from "@/lib/types";
import SettingTooltip from "./SettingTooltip";

interface Props {
  onToast: (msg: string, type: "success" | "error" | "info") => void;
}

const RUNTIME_FIELDS = [
  {
    key: "MAX_LOOPS",
    label: "Max Agent Loops",
    default: 10,
    desc: "Max iterations per prompt before requiring user confirmation.",
    why: "Prevents infinite reasoning loops and runaway API token burn.",
    how: "If an agent executes 10 consecutive action steps without concluding, it pauses and prompts the user to continue.",
  },
  {
    key: "APPROVAL_TIMEOUT_SECS",
    label: "Approval Timeout (sec)",
    default: 300,
    desc: "Seconds to wait for user tool execution approval.",
    why: "Ensures agent runs don't hang indefinitely if you step away during a confirmation request.",
    how: "Carole waits this duration for a 'Permit' or 'Deny' decision before safely timing out.",
  },
  {
    key: "MAX_QUEUE_SIZE",
    label: "Max Event Queue Size",
    default: 500,
    desc: "Buffer size for streaming thought & tool events.",
    why: "Regulates memory consumption during high-throughput parallel tool outputs.",
    how: "Queues incoming streaming events and drops oldest overflow if connection bottlenecks.",
  },
  {
    key: "DREAM_INTERVAL_MINUTES",
    label: "Dream Interval (min)",
    default: 15,
    desc: "Background agent memory reflection & distillation cadence.",
    why: "Synthesizes raw conversation logs into persistent, reusable semantic learnings.",
    how: "The background Dream Worker wakes up every X minutes to distill episodic patterns into long-term memory.",
  },
  {
    key: "MEMORY_RETRIEVAL_LIMIT",
    label: "Memory Retrieval Limit",
    default: 3,
    desc: "Number of past episodic learnings retrieved per turn.",
    why: "Limits prompt bloat while providing relevant past context.",
    how: "Retrieves the top N most semantically relevant memories from vector storage on every user turn.",
  },
  {
    key: "CONTEXT_COMPACTION_THRESHOLD",
    label: "Compaction Threshold",
    default: 15,
    desc: "Turn count before older turns are summarized.",
    why: "Keeps prompt context within token limits and minimizes inference latency.",
    how: "When conversation history exceeds this number of turns, older messages are compacted into a concise summary block.",
  },
];

export default function RuntimeSafetySettings({ onToast }: Props) {
  // ── Runtime Settings State ──
  const [runtimeSettings, setRuntimeSettings] = useState<Record<string, number>>({});
  const [runtimeLoading, setRuntimeLoading] = useState(true);
  const [runtimeSaving, setRuntimeSaving] = useState(false);

  // ── Access Control State ──
  const [acConfig, setAcConfig] = useState<AccessControlConfig>({
    ...DEFAULT_ACCESS_CONTROL,
    categories: { ...DEFAULT_ACCESS_CONTROL.categories },
    overrides: {},
    custom_skip_judge: { file_patterns: [], command_prefixes: [] },
  });
  const [acLoading, setAcLoading] = useState(true);
  const [acSaving, setAcSaving] = useState(false);
  const [acExpanded, setAcExpanded] = useState(true);

  useEffect(() => {
    // Fetch runtime settings
    api.getAppConfig()
      .then((cfg: any) => setRuntimeSettings(cfg.agent_settings || {}))
      .catch(() => {})
      .finally(() => setRuntimeLoading(false));

    // Fetch access control
    api.getSettings()
      .then((s: any) => {
        if (s?.access_control && typeof s.access_control === "object" && "categories" in s.access_control) {
          setAcConfig(s.access_control as AccessControlConfig);
        }
      })
      .catch(() => {})
      .finally(() => setAcLoading(false));
  }, []);

  const handleSaveRuntime = async () => {
    setRuntimeSaving(true);
    try {
      await api.updateAppConfig({ agent_settings: runtimeSettings });
      onToast("Agent runtime settings saved ✓", "success");
    } catch {
      onToast("Failed to save agent runtime settings", "error");
    } finally {
      setRuntimeSaving(false);
    }
  };

  const handleSaveAc = async () => {
    setAcSaving(true);
    try {
      await api.saveSettings({ access_control: acConfig });
      onToast("Access Control defaults saved ✓", "success");
    } catch {
      onToast("Failed to save Access Control settings", "error");
    } finally {
      setAcSaving(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2xl)" }}>
      {/* ── Access Control Card ── */}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div
          style={{
            padding: "var(--sp-xl)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "var(--color-canvas-soft)",
            borderBottom: "1px solid var(--color-hairline)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)" }}>
            <div
              style={{
                width: 38,
                height: 38,
                borderRadius: "var(--radius-sm)",
                background: "rgba(167,139,250,0.12)",
                border: "1px solid rgba(167,139,250,0.3)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#a78bfa",
              }}
            >
              <Shield size={18} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                <h3 className="display-sm" style={{ margin: 0 }}>Global Access Control &amp; Safety Defaults</h3>
                <SettingTooltip
                  title="Access Control Matrix"
                  why="Enforces strict permission boundaries on tool calls (file writes, shell commands, database queries, network requests)."
                  how="Tools marked 'Judge' are evaluated in real-time by the Judge model. Tools marked 'Always Require' trigger a UI approval prompt."
                />
                <span
                  style={{
                    fontSize: 10,
                    padding: "2px 8px",
                    borderRadius: 10,
                    fontWeight: 700,
                    background: acConfig.enable_judge ? "rgba(167,139,250,0.15)" : "rgba(251,191,36,0.15)",
                    color: acConfig.enable_judge ? "#a78bfa" : "#fbbf24",
                    border: `1px solid ${acConfig.enable_judge ? "rgba(167,139,250,0.35)" : "rgba(251,191,36,0.35)"}`,
                  }}
                >
                  {acConfig.enable_judge ? "Judge ON" : "Judge OFF"}
                </span>
              </div>
              <p className="caption text-mute" style={{ margin: 0 }}>
                Global permission matrix for all agents. Per-agent settings override these defaults.
              </p>
            </div>
          </div>
          <button
            className="btn btn-ghost btn-xs"
            onClick={() => setAcExpanded(v => !v)}
            style={{ color: "var(--color-mute)" }}
          >
            {acExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
          </button>
        </div>

        {acExpanded && (
          <div style={{ padding: "var(--sp-xl)" }}>
            {acLoading ? (
              <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", padding: "var(--sp-lg)" }}>
                <Loader2 size={16} className="animate-spin" style={{ color: "var(--color-primary)" }} />
                <span className="caption">Loading access control policy…</span>
              </div>
            ) : (
              <>
                <AccessControlMatrix value={acConfig} onChange={setAcConfig} />
                <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "var(--sp-xl)", paddingTop: "var(--sp-md)", borderTop: "1px solid var(--color-hairline)" }}>
                  <button className="btn btn-primary btn-sm" onClick={handleSaveAc} disabled={acSaving}>
                    {acSaving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                    Save Access Control Defaults
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* ── Runtime & Memory Settings Card ── */}
      <div className="card" style={{ padding: "var(--sp-xl)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)", marginBottom: "var(--sp-lg)" }}>
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: "var(--radius-sm)",
              background: "rgba(59, 130, 246, 0.12)",
              border: "1px solid rgba(59, 130, 246, 0.3)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--color-info)",
            }}
          >
            <Sliders size={18} />
          </div>
          <div>
            <h3 className="display-sm" style={{ margin: 0 }}>Agent Runtime &amp; Memory Limits</h3>
            <p className="caption text-mute" style={{ margin: 0 }}>
              Tune agent decision loops, execution timeouts, dream intervals, and context compaction thresholds.
            </p>
          </div>
        </div>

        {runtimeLoading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {[1, 2, 3].map(i => (
              <div key={i} className="skeleton skeleton-text" style={{ height: 40 }} />
            ))}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "var(--sp-md)" }}>
              {RUNTIME_FIELDS.map(f => (
                <div
                  key={f.key}
                  style={{
                    background: "var(--color-canvas-soft)",
                    border: "1px solid var(--color-hairline)",
                    borderRadius: "var(--radius-sm)",
                    padding: "var(--sp-md) var(--sp-lg)",
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center" }}>
                    <label className="form-label" style={{ fontSize: 11, fontWeight: 600, margin: 0 }}>
                      {f.label}
                    </label>
                    <SettingTooltip title={f.label} why={f.why} how={f.how} />
                  </div>
                  <input
                    type="number"
                    className="input"
                    placeholder={`Default: ${f.default}`}
                    value={runtimeSettings[f.key] ?? ""}
                    onChange={e =>
                      setRuntimeSettings(d => ({
                        ...d,
                        [f.key]: e.target.value === "" ? f.default : parseInt(e.target.value) || f.default,
                      }))
                    }
                    style={{ fontSize: 11 }}
                  />
                  <span className="caption text-mute" style={{ fontSize: 10 }}>
                    {f.desc}
                  </span>
                </div>
              ))}
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "var(--sp-sm)" }}>
              <button className="btn btn-primary btn-sm" onClick={handleSaveRuntime} disabled={runtimeSaving}>
                {runtimeSaving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save Runtime Settings
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
