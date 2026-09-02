"use client";
import React, { useState, useEffect } from "react";
import { MessageSquare, Layers, Save, RotateCcw, ChevronDown, ChevronUp, AlertTriangle, Loader2, ToggleLeft, ToggleRight, Sparkles } from "lucide-react";
import { api } from "@/hooks/useApi";
import PromptsEditor from "./PromptsEditor";
import type { PromptBlock } from "@/lib/types";
import SettingTooltip from "./SettingTooltip";

interface Props {
  onToast: (msg: string, type: "success" | "error" | "info") => void;
}

const CATEGORY_ORDER = ["Memory", "Filesystem", "Automation", "Browser"];

const BLOCK_VARS: Record<string, string[]> = {
  workspace_paths: ["{carole_dir}"],
};

const BLOCK_TOOLTIPS: Record<string, { why: string; how: string }> = {
  episodic_memory: {
    why: "Allows agents to retain learnings and recall previous mistakes across long workflows.",
    how: "Instructs the agent how to format and retrieve short-term and long-term memory notes from vector store.",
  },
  workspace_paths: {
    why: "Restricts and scopes all file writes to the active project folder.",
    how: "Replaces {carole_dir} at runtime with the scoped workspace path to prevent root-directory leaks.",
  },
  bash_execution: {
    why: "Guarantees safe non-interactive command execution in the terminal.",
    how: "Enforces rules like passing non-interactive flags and avoiding blocking commands without timeouts.",
  },
  browser_interaction: {
    why: "Guides the agent on how to interact with web elements, parse DOM trees, and handle CAPTCHAs.",
    how: "Appended to browser-capable agents to enforce XPath targeting and human takeover roadblock rules.",
  },
};

function PromptBlocksEditor({ onToast }: { onToast: (msg: string, type: any) => void }) {
  const [blocks, setBlocks] = useState<PromptBlock[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [dirty, setDirty] = useState<Record<string, { enabled: boolean; content: string }>>({});

  useEffect(() => {
    api.getPromptBlocks()
      .then(setBlocks)
      .catch(() => onToast("Failed to load prompt blocks", "error"))
      .finally(() => setLoading(false));
  }, [onToast]);

  const patch = (key: string, field: "enabled" | "content", value: any) => {
    const block = blocks.find(b => b.key === key);
    if (!block) return;
    setDirty(d => ({
      ...d,
      [key]: {
        enabled: field === "enabled" ? value : (d[key]?.enabled ?? block.enabled),
        content: field === "content" ? value : (d[key]?.content ?? block.content),
      },
    }));
  };

  const handleSaveAll = async () => {
    if (!Object.keys(dirty).length) return;
    setSaving(true);
    try {
      const updates = Object.entries(dirty).map(([key, val]) => ({ key, ...val }));
      const updated = await api.savePromptBlocks(updates);
      setBlocks(updated);
      setDirty({});
      onToast("Prompt blocks saved successfully", "success");
    } catch {
      onToast("Failed to save prompt blocks", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async (key: string) => {
    try {
      const updated = await api.resetPromptBlock(key);
      setBlocks(prev => prev.map(b => b.key === key ? { ...b, ...updated, content: updated.content, enabled: updated.enabled, is_customized: false } : b));
      setDirty(d => { const n = { ...d }; delete n[key]; return n; });
      onToast(`"${key}" reset to default`, "success");
    } catch {
      onToast("Failed to reset block", "error");
    }
  };

  if (loading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: "var(--sp-lg)" }}>
        {[1, 2, 3].map(i => (
          <div key={i} className="skeleton skeleton-text" style={{ height: 44 }} />
        ))}
      </div>
    );
  }

  const grouped = CATEGORY_ORDER.map(cat => ({
    cat,
    items: blocks.filter(b => b.category === cat),
  })).filter(g => g.items.length > 0);

  const hasDirty = Object.keys(dirty).length > 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-xl)" }}>
      <div style={{ background: "var(--color-canvas-soft)", border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-sm)", padding: "var(--sp-md) var(--sp-lg)" }}>
        <p className="caption text-mute" style={{ margin: 0, lineHeight: 1.5 }}>
          ⚙️ <strong>System Capability Blocks</strong> are modular instruction segments automatically appended to every agent&apos;s context. Toggle capabilities on/off with 1 click or click <strong>Customize Prompt</strong>.
        </p>
      </div>

      {grouped.map(({ cat, items }) => (
        <div key={cat}>
          <div style={{ fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--color-mute)", marginBottom: "var(--sp-sm)" }}>
            {cat} Capabilities
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-sm)" }}>
            {items.map(block => {
              const override = dirty[block.key];
              const enabled = override ? override.enabled : block.enabled;
              const content = override ? override.content : block.content;
              const isOpen = !!expanded[block.key];
              const isModified = !!override || block.is_customized;
              const requiredVars = BLOCK_VARS[block.key] || [];
              const missingVars = requiredVars.filter(v => !content.includes(v));
              const blockInfo = BLOCK_TOOLTIPS[block.key] || {
                why: "Provides foundational instructions for this system capability.",
                how: "Appended to the agent prompt when this capability is active.",
              };

              return (
                <div
                  key={block.key}
                  style={{
                    padding: "var(--sp-md) var(--sp-lg)",
                    borderRadius: "var(--radius-sm)",
                    background: "var(--color-canvas-soft)",
                    border: `1px solid ${isModified ? "var(--color-primary)" : "var(--color-hairline)"}`,
                    opacity: enabled ? 1 : 0.65,
                    transition: "all var(--t-fast)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)", justifyContent: "space-between" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)", flex: 1, minWidth: 0 }}>
                      <button
                        onClick={() => patch(block.key, "enabled", !enabled)}
                        style={{
                          background: "none",
                          border: "none",
                          cursor: "pointer",
                          padding: 0,
                          color: enabled ? "var(--color-primary)" : "var(--color-mute)",
                          flexShrink: 0,
                          display: "flex",
                          alignItems: "center",
                        }}
                        title={enabled ? "Disable capability" : "Enable capability"}
                      >
                        {enabled ? <ToggleRight size={26} /> : <ToggleLeft size={26} />}
                      </button>

                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", flexWrap: "wrap" }}>
                          <span style={{ fontWeight: 600, fontSize: 12 }}>{block.display_name}</span>
                          <SettingTooltip title={block.display_name} why={blockInfo.why} how={blockInfo.how} />
                          <span
                            style={{
                              fontSize: 10,
                              padding: "1px 6px",
                              borderRadius: 4,
                              background: enabled ? "rgba(16, 185, 129, 0.15)" : "rgba(107, 114, 128, 0.15)",
                              color: enabled ? "var(--color-success)" : "var(--color-mute)",
                              border: `1px solid ${enabled ? "rgba(16, 185, 129, 0.3)" : "rgba(107, 114, 128, 0.3)"}`,
                              fontWeight: 500,
                            }}
                          >
                            {enabled ? "Active" : "Disabled"}
                          </span>

                          {isModified && (
                            <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 4, background: "var(--color-primary)", color: "#fff", fontWeight: 500 }}>
                              customized
                            </span>
                          )}

                          {requiredVars.map(v => (
                            <span
                              key={v}
                              style={{
                                fontSize: 10,
                                padding: "1px 6px",
                                borderRadius: 4,
                                fontFamily: "var(--font-mono)",
                                background: "rgba(99, 102, 241, 0.12)",
                                color: "var(--color-primary)",
                                border: "1px solid rgba(99, 102, 241, 0.25)",
                              }}
                            >
                              Variable: {v}
                            </span>
                          ))}
                        </div>
                        <div className="caption text-mute" style={{ marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {block.description}
                        </div>
                      </div>
                    </div>

                    <div style={{ display: "flex", gap: "var(--sp-xs)", flexShrink: 0, alignItems: "center" }}>
                      {(block.is_customized || override) && (
                        <button
                          className="btn btn-ghost btn-xs"
                          onClick={() => handleReset(block.key)}
                          title="Reset to default prompt"
                        >
                          <RotateCcw size={11} /> Reset
                        </button>
                      )}
                      <button
                        className={`btn btn-xs ${isOpen ? "btn-outline" : "btn-ghost"}`}
                        onClick={() => setExpanded(e => ({ ...e, [block.key]: !e[block.key] }))}
                      >
                        {isOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                        {isOpen ? "Hide" : "Edit"}
                      </button>
                    </div>
                  </div>

                  {isOpen && (
                    <div style={{ marginTop: "var(--sp-md)", paddingTop: "var(--sp-md)", borderTop: "1px solid var(--color-hairline)" }}>
                      <textarea
                        value={content}
                        onChange={e => patch(block.key, "content", e.target.value)}
                        rows={Math.min(16, Math.max(5, content.split("\n").length + 1))}
                        spellCheck={false}
                        style={{
                          width: "100%",
                          boxSizing: "border-box",
                          fontFamily: "var(--font-mono)",
                          fontSize: 11,
                          lineHeight: 1.5,
                          background: "var(--color-canvas)",
                          border: `1px solid ${missingVars.length > 0 ? "var(--color-warning)" : "var(--color-hairline)"}`,
                          borderRadius: "var(--radius-sm)",
                          padding: "var(--sp-md)",
                          color: "var(--color-ink)",
                          resize: "vertical",
                        }}
                      />
                      {missingVars.length > 0 && (
                        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-xs)", color: "var(--color-warning)", fontSize: 11, marginTop: 4 }}>
                          <AlertTriangle size={12} />
                          <span>Required placeholder <code>{missingVars.join(", ")}</code> is missing from text.</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "var(--sp-sm)" }}>
        <button className="btn btn-primary btn-sm" onClick={handleSaveAll} disabled={saving || !hasDirty}>
          {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
          Save Block Changes{hasDirty ? ` (${Object.keys(dirty).length})` : ""}
        </button>
      </div>
    </div>
  );
}

export default function PromptsSettings({ onToast }: Props) {
  const [subTab, setSubTab] = useState<"roles" | "capabilities">("roles");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2xl)" }}>
      {/* ── Sub-navigation bar ── */}
      <div
        style={{
          display: "inline-flex",
          gap: "var(--sp-xs)",
          background: "var(--color-canvas-soft)",
          padding: 4,
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--color-hairline)",
          alignSelf: "flex-start",
        }}
      >
        <button
          className={`btn btn-xs ${subTab === "roles" ? "btn-primary" : "btn-ghost"}`}
          style={{ borderRadius: "var(--radius-sm)", gap: "var(--sp-xs)" }}
          onClick={() => setSubTab("roles")}
        >
          <MessageSquare size={12} /> Roles &amp; Personas
        </button>
        <button
          className={`btn btn-xs ${subTab === "capabilities" ? "btn-primary" : "btn-ghost"}`}
          style={{ borderRadius: "var(--radius-sm)", gap: "var(--sp-xs)" }}
          onClick={() => setSubTab("capabilities")}
        >
          <Sparkles size={12} /> System Capabilities
        </button>
      </div>

      {subTab === "roles" && <PromptsEditor onToast={onToast} />}

      {subTab === "capabilities" && (
        <div className="card" style={{ padding: "var(--sp-xl)" }}>
          <div style={{ marginBottom: "var(--sp-lg)" }}>
            <div style={{ display: "flex", alignItems: "center" }}>
              <h3 className="display-sm" style={{ margin: 0 }}>System Capabilities</h3>
              <SettingTooltip
                title="System Capabilities"
                why="Encapsulates specialized agent behaviors (memory persistence, filesystem safety, bash execution rules) into modular blocks."
                how="Active blocks are dynamically combined and injected into system prompts during agent initialization."
              />
            </div>
            <p className="caption text-mute" style={{ margin: 0 }}>
              Modular prompt templates injected into agent context. Toggle on/off or fine-tune phrasing.
            </p>
          </div>
          <PromptBlocksEditor onToast={onToast} />
        </div>
      )}
    </div>
  );
}
