"use client";
import React, { useState, useEffect, useCallback } from "react";
import { Save, Loader2, RotateCcw, ChevronDown, ChevronUp, Info, AlertTriangle } from "lucide-react";
import { api } from "@/hooks/useApi";

interface Props {
  onToast: (msg: string, type: "success" | "error" | "info") => void;
}

// ── Prompt metadata — groups + human-readable labels ──────────────────────────

const PROMPT_META: Record<string, { label: string; group: string; description: string; vars?: string[] }> = {
  "personality.professional": {
    group: "Personality Styles",
    label: "Professional",
    description: "Default style — senior engineer in a Slack channel.",
    vars: ["name", "role"],
  },
  "personality.casual": {
    group: "Personality Styles",
    label: "Casual",
    description: "Relaxed standup style — 'yo, let me handle that'.",
    vars: ["name", "role"],
  },
  "personality.witty": {
    group: "Personality Styles",
    label: "Witty / Dev",
    description: "Clean code + dry one-liners — the dev with good variable names.",
    vars: ["name", "role"],
  },
  "personality.mentor": {
    group: "Personality Styles",
    label: "Mentor / Senior",
    description: "Thoughtful PR reviewer — constructive, never condescending.",
    vars: ["name", "role"],
  },
  "system.tool_use": {
    group: "Agent Behavior",
    label: "Tool Use Instructions",
    description: "How agents are told to invoke tools via [ACTION]...[/ACTION].",
  },
  "system.reasoning_rules": {
    group: "Agent Behavior",
    label: "Reasoning Rules",
    description: "Core thinking rules: simplicity first, surgical changes, goal-driven.",
  },
  "system.markdown_rules": {
    group: "Agent Behavior",
    label: "Markdown Rules",
    description: "Forces agents to link code symbols to file paths.",
  },
  "system.behavioral_rules": {
    group: "Agent Behavior",
    label: "Behavioral Rules",
    description: "Team communication norms — address teammates, summarize work, etc.",
  },
  "system.coordinator_directives": {
    group: "Agent Behavior",
    label: "Coordinator Directives",
    description: "Instructions injected into coordinator agents for task delegation.",
  },
  "system.judge": {
    group: "System Prompts",
    label: "Judge / Security Prompt",
    description: "Governs the AI security judge that approves or denies tool calls.",
  },
  "system.consolidation": {
    group: "System Prompts",
    label: "Memory Consolidation",
    description: "Extracts lessons from conversation logs into long-term memory.",
    vars: ["conversation"],
  },
  "system.compaction_system": {
    group: "System Prompts",
    label: "Context Compactor (System)",
    description: "System message for the context compaction agent.",
  },
  "system.compaction_user": {
    group: "System Prompts",
    label: "Context Compactor (User)",
    description: "Summarize request sent when conversation history is too long.",
    vars: ["context"],
  },
  "system.keyword_extraction": {
    group: "System Prompts",
    label: "Keyword Extraction",
    description: "Extracts search keywords from a task description.",
    vars: ["task"],
  },
};

const GROUPS = ["Personality Styles", "Agent Behavior", "System Prompts"];

// ── Single prompt editor row ───────────────────────────────────────────────────

function PromptRow({
  slug,
  value,
  defaultValue,
  onChange,
}: {
  slug: string;
  value: string;
  defaultValue: string;
  onChange: (slug: string, v: string) => void;
}) {
  const meta = PROMPT_META[slug] ?? { label: slug, group: "Other", description: "" };
  const [expanded, setExpanded] = useState(false);
  const isDirty = value !== defaultValue;

  return (
    <div
      style={{
        border: `1px solid ${isDirty ? "rgba(0,217,146,0.4)" : "var(--color-hairline)"}`,
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
        transition: "border-color 0.2s",
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-md)",
          padding: "var(--sp-md) var(--sp-lg)",
          background: "var(--color-canvas-raised)",
          cursor: "pointer",
          userSelect: "none",
        }}
        onClick={() => setExpanded(e => !e)}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
            <span className="body-sm-strong">{meta.label}</span>
            {isDirty && (
              <span style={{ fontSize: 10, color: "var(--color-primary)", background: "rgba(0,217,146,0.12)", border: "1px solid rgba(0,217,146,0.3)", borderRadius: 4, padding: "1px 5px" }}>
                modified
              </span>
            )}
            {meta.vars && meta.vars.length > 0 && (
              <span style={{ fontSize: 10, color: "var(--color-mute)" }}>
                vars: {meta.vars.map(v => `{${v}}`).join(", ")}
              </span>
            )}
          </div>
          {meta.description && (
            <p className="caption" style={{ marginTop: 2, color: "var(--color-mute)" }}>{meta.description}</p>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", flexShrink: 0 }}>
          {isDirty && (
            <button
              type="button"
              title="Reset to default"
              className="btn btn-icon btn-ghost btn-sm"
              style={{ color: "var(--color-mute)" }}
              onClick={e => { e.stopPropagation(); onChange(slug, defaultValue); }}
            >
              <RotateCcw size={12} />
            </button>
          )}
          {expanded ? <ChevronUp size={14} color="var(--color-mute)" /> : <ChevronDown size={14} color="var(--color-mute)" />}
        </div>
      </div>

      {/* Editor */}
      {expanded && (
        <div style={{ padding: "var(--sp-md)" }}>
          <textarea
            className="input"
            style={{
              minHeight: 140,
              fontFamily: "monospace",
              fontSize: 12,
              lineHeight: 1.6,
              resize: "vertical",
            }}
            value={value}
            onChange={e => onChange(slug, e.target.value)}
            spellCheck={false}
          />
        </div>
      )}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function PromptsEditor({ onToast }: Props) {
  const [prompts, setPrompts]         = useState<Record<string, string>>({});
  const [defaults, setDefaults]       = useState<Record<string, string>>({});
  const [loading, setLoading]         = useState(true);
  const [saving, setSaving]           = useState(false);
  const [resetting, setResetting]     = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [activeGroup, setActiveGroup] = useState(GROUPS[0]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getPrompts();
      setPrompts(data);
      setDefaults(data); // First load becomes the "default" baseline in UI
    } catch {
      onToast("Failed to load prompts", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleChange = (slug: string, value: string) => {
    setPrompts(p => ({ ...p, [slug]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.savePrompts(prompts);
      setDefaults({ ...prompts });
      onToast("Prompts saved to .carole/prompts.json ✓", "success");
    } catch {
      onToast("Failed to save prompts", "error");
    } finally { setSaving(false); }
  };

  const handleResetAll = () => {
    setPrompts({ ...defaults });
    onToast("All prompts reset to last-saved values", "info");
  };

  const handleResetToDefaults = async () => {
    setResetting(true);
    try {
      const factoryDefaults = await api.resetPrompts();
      setPrompts(factoryDefaults);
      setDefaults(factoryDefaults);
      setConfirmReset(false);
      onToast("Prompts reset to factory defaults ✓", "success");
    } catch {
      onToast("Failed to reset prompts", "error");
    } finally { setResetting(false); }
  };

  const dirtyCount = Object.keys(prompts).filter(k => prompts[k] !== defaults[k]).length;

  // Prompts in active group
  const groupSlugs = Object.keys(PROMPT_META).filter(
    k => PROMPT_META[k].group === activeGroup
  );
  // Unknown slugs not in PROMPT_META go into their own group
  const unknownSlugs = Object.keys(prompts).filter(k => !PROMPT_META[k] && !k.startsWith("_"));

  return (
    <div className="card" style={{ marginBottom: "var(--sp-xl)" }}>
      {/* Header */}
      <div className="flex-between" style={{ marginBottom: "var(--sp-lg)" }}>
        <div>
          <h3 className="display-sm">System Prompts</h3>
          <p className="caption" style={{ marginTop: 2 }}>
            Stored in{" "}
            <code style={{ background: "var(--color-canvas-raised)", padding: "1px 5px", borderRadius: 4, fontSize: 11 }}>
              .carole/prompts.json
            </code>
            {" "}— no restart needed.
            {dirtyCount > 0 && (
              <span style={{ marginLeft: 8, color: "var(--color-primary)" }}>
                {dirtyCount} unsaved change{dirtyCount > 1 ? "s" : ""}
              </span>
            )}
          </p>
        </div>
        <div style={{ display: "flex", gap: "var(--sp-sm)", flexWrap: "wrap", justifyContent: "flex-end" }}>
          {dirtyCount > 0 && (
            <button className="btn btn-ghost btn-sm" onClick={handleResetAll}>
              <RotateCcw size={13} /> Reset unsaved
            </button>
          )}
          {/* Reset to factory defaults */}
          {!confirmReset ? (
            <button
              className="btn btn-ghost btn-sm"
              style={{ color: "var(--color-danger)", borderColor: "rgba(248,113,113,0.3)" }}
              onClick={() => setConfirmReset(true)}
              disabled={resetting}
            >
              <RotateCcw size={13} /> Reset to Defaults
            </button>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.3)", borderRadius: "var(--radius-sm)", padding: "4px 10px" }}>
              <AlertTriangle size={12} color="var(--color-danger)" />
              <span style={{ fontSize: 12 }}>Overwrite all prompts?</span>
              <button className="btn btn-danger btn-sm" onClick={handleResetToDefaults} disabled={resetting}>
                {resetting ? <Loader2 size={12} className="animate-spin" /> : null} Yes, reset
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => setConfirmReset(false)}>Cancel</button>
            </div>
          )}
          <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving || loading}>
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            Save Prompts
          </button>
        </div>
      </div>

      {/* Info banner */}
      <div style={{ display: "flex", gap: "var(--sp-sm)", alignItems: "flex-start", padding: "var(--sp-md)", background: "rgba(0,217,146,0.06)", border: "1px solid rgba(0,217,146,0.15)", borderRadius: "var(--radius-sm)", marginBottom: "var(--sp-lg)" }}>
        <Info size={14} color="var(--color-primary)" style={{ flexShrink: 0, marginTop: 2 }} />
        <p className="caption">
          Variables in <code style={{ fontSize: 11 }}>{"{braces}"}</code> are auto-filled at runtime (e.g. <code style={{ fontSize: 11 }}>{"{name}"}</code>, <code style={{ fontSize: 11 }}>{"{role}"}</code>).
          Click any row to expand and edit. <strong>Resets</strong> go back to last-saved state, not factory defaults.
        </p>
      </div>

      {/* Group tabs */}
      <div style={{ display: "flex", gap: "var(--sp-sm)", marginBottom: "var(--sp-lg)", borderBottom: "1px solid var(--color-hairline)", paddingBottom: "var(--sp-sm)" }}>
        {GROUPS.map(g => (
          <button
            key={g}
            className={`btn btn-sm ${activeGroup === g ? "btn-primary" : "btn-ghost"}`}
            onClick={() => setActiveGroup(g)}
            style={{ fontSize: 12 }}
          >
            {g}
          </button>
        ))}
        {unknownSlugs.length > 0 && (
          <button
            className={`btn btn-sm ${activeGroup === "Other" ? "btn-primary" : "btn-ghost"}`}
            onClick={() => setActiveGroup("Other")}
            style={{ fontSize: 12 }}
          >
            Other
          </button>
        )}
      </div>

      {/* Prompt rows */}
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-sm)" }}>
          {[1, 2, 3].map(i => (
            <div key={i} className="skeleton" style={{ height: 56, borderRadius: "var(--radius-md)" }} />
          ))}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-sm)" }}>
          {(activeGroup === "Other" ? unknownSlugs : groupSlugs).map(slug => (
            <PromptRow
              key={slug}
              slug={slug}
              value={prompts[slug] ?? ""}
              defaultValue={defaults[slug] ?? ""}
              onChange={handleChange}
            />
          ))}
          {(activeGroup === "Other" ? unknownSlugs : groupSlugs).length === 0 && (
            <p className="caption" style={{ textAlign: "center", padding: "var(--sp-xl)", color: "var(--color-mute)" }}>
              No prompts in this group yet.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
