"use client";
import React, { useState, useEffect } from "react";
import { Cpu, Save, Loader2, Sparkles, Layers } from "lucide-react";
import { api } from "@/hooks/useApi";
import ModelCatalogEditor from "./ModelCatalogEditor";
import SettingTooltip from "./SettingTooltip";

interface Props {
  onToast: (msg: string, type: "success" | "error" | "info") => void;
}

const DEFAULT_MODEL_ROLES = [
  {
    key: "DEFAULT_FAST_MODEL",
    label: "Fast / Small Model (Flush, Compaction & Dreaming)",
    fallbackModel: "openrouter/free",
    desc: "Used for Pre-Compaction Memory Flush, Rolling Compaction, Memory Consolidation ('Dreaming'), GraphRAG Extraction, and Fast Routing.",
    why: "Minimizes latency and token cost for high-frequency internal operations: extracting durable facts before context truncation, compacting chat history, and extracting search keywords.",
    how: "Executed automatically by Pre-Compaction Flush & Rolling Compaction (react_agent.py), AutoDream Worker (auto_dream.py), Meeting Tool (meeting_tool.py), and Sub-agents.",
    subsystems: ["Pre-Compaction Memory Flush", "Rolling Context Compaction", "Memory Consolidation (Dreaming)", "GraphRAG Triples Extraction", "Fast Sub-Agents"],
  },
  {
    key: "DEFAULT_SMART_MODEL",
    label: "Smart / Reasoning Model (Orchestration & Planning)",
    fallbackModel: "openrouter/auto",
    desc: "Used for deep analysis, multi-step orchestration, complex reasoning, and system architecture planning.",
    why: "Provides deep reasoning, architectural planning, and high-context problem solving across complex multi-step workflows.",
    how: "Used by the Orchestrator, Architect, and Research agents when planning execution paths and evaluating tool outcomes.",
    subsystems: ["ReAct Agent Orchestration", "Architect & Research Planning", "Multi-step Tool Synthesis"],
  },
  {
    key: "DEFAULT_CODER_MODEL",
    label: "Software Engineer Model (CodeGraph & Refactoring)",
    fallbackModel: "openrouter/free",
    desc: "Specialized model for code generation, AST analysis, syntax validation, bug fixing, test writing, and repo refactoring.",
    why: "Tuned for high-precision syntax generation, Workspace Symbol Call Graph queries, and repository-wide refactoring across multi-language codebases.",
    how: "Assigned to the Software Engineer (SWE) and Debugger agents to write, test, and commit code on disk.",
    subsystems: ["SWE Code Generator", "CodeGraph Caller/Callee Queries", "Debugger & Patch Creation", "Automated Test Suite Runner"],
  },
  {
    key: "DEFAULT_JUDGE_MODEL",
    label: "Autonomous Judge Model (Safety & Verification)",
    fallbackModel: "openrouter/free",
    desc: "High-integrity safety arbiter reviewing tool calls, data deletion, shell commands, and risk gates.",
    why: "Guards against unintended data loss, dangerous terminal commands, or harmful API actions.",
    how: "Invoked asynchronously prior to executing risky tool calls to confirm parameters, blast radius, and safety constraints.",
    subsystems: ["Tool Call Pre-Flight Judge", "Terminal Blast-Radius Guard", "Data Loss Interception"],
  },
  {
    key: "DEFAULT_EMBEDDING_MODEL",
    label: "Fixed 1536-Dim Vector Embedding Model (RAG & LanceDB)",
    fallbackModel: "auto",
    desc: "Standardized 1536-dimensional vector embedding model for document chunks, conversation recall, and code search.",
    why: "Guarantees mathematically uniform 1536-dimensional semantic vectors with zero zero-padding distortion across knowledge files and auto-dream learnings.",
    how: "Executed across knowledge_ingestor.py, lancedb_client.py, and auto_dream.py to generate 1536-dim vector embeddings.",
    subsystems: ["1536-Dim LanceDB Search", "Semantic & AST Ingestion", "Multi-Hop Graph Memory", "Auto-Dream Embeddings"],
    isEmbedding: true,
  },
];

export default function ModelsSettings({ onToast }: Props) {
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [catalog, setCatalog] = useState<Record<string, any>>({});
  const [activeSubTab, setActiveSubTab] = useState<"defaults" | "catalog">("defaults");

  useEffect(() => {
    Promise.all([api.getAppConfig(), api.getModelCatalog()])
      .then(([cfg, cat]: [any, any]) => {
        setDefaults(cfg.default_models || {});
        setCatalog(cat);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleSaveDefaults = async () => {
    setSaving(true);
    try {
      await api.updateAppConfig({ default_models: defaults });
      onToast("Default system models saved ✓", "success");
    } catch {
      onToast("Failed to save default models", "error");
    } finally {
      setSaving(false);
    }
  };

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
          className={`btn btn-xs ${activeSubTab === "defaults" ? "btn-primary" : "btn-ghost"}`}
          style={{ borderRadius: "var(--radius-sm)", gap: "var(--sp-xs)" }}
          onClick={() => setActiveSubTab("defaults")}
        >
          <Sparkles size={12} /> System Defaults
        </button>
        <button
          className={`btn btn-xs ${activeSubTab === "catalog" ? "btn-primary" : "btn-ghost"}`}
          style={{ borderRadius: "var(--radius-sm)", gap: "var(--sp-xs)" }}
          onClick={() => setActiveSubTab("catalog")}
        >
          <Layers size={12} /> Model Catalog &amp; Providers
        </button>
      </div>

      {activeSubTab === "defaults" && (
        <div className="card" style={{ padding: "var(--sp-xl)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)", marginBottom: "var(--sp-lg)" }}>
            <div
              style={{
                width: 38,
                height: 38,
                borderRadius: "var(--radius-sm)",
                background: "rgba(99, 102, 241, 0.12)",
                border: "1px solid rgba(99, 102, 241, 0.3)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--color-primary)",
              }}
            >
              <Cpu size={18} />
            </div>
            <div>
              <h3 className="display-sm" style={{ margin: 0 }}>Global Model Defaults</h3>
              <p className="caption text-mute" style={{ margin: 0 }}>
                System-wide default model assignments for agent roles and fallback routines.
              </p>
            </div>
          </div>

          {loading ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {[1, 2, 3, 4].map(i => (
                <div key={i} className="skeleton skeleton-text" style={{ height: 40 }} />
              ))}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(280px, 100%), 1fr))", gap: "var(--sp-md)" }}>
                {DEFAULT_MODEL_ROLES.map(({ key, label, fallbackModel, desc, why, how, subsystems }) => (
                  <div
                    key={key}
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
                        {label}
                      </label>
                      <SettingTooltip title={label} why={why} how={how} />
                    </div>
                    {(key === "DEFAULT_EMBEDDING_MODEL") ? (
                      <select
                        className="input"
                        value={defaults[key] || "auto"}
                        onChange={e => setDefaults(d => ({ ...d, [key]: e.target.value }))}
                        style={{ fontSize: 11 }}
                      >
                        <option value="auto">-- Auto Waterfall (Default: OpenAI 1536 → OpenRouter → Ollama) --</option>
                        <optgroup label="OpenAI Native 1536-Dim Embeddings">
                          <option value="openai/text-embedding-3-small">OpenAI text-embedding-3-small (Standard / Fast — 1536-dim)</option>
                          <option value="openai/text-embedding-3-large">OpenAI text-embedding-3-large (High-Accuracy — 1536-dim)</option>
                        </optgroup>
                        <optgroup label="OpenRouter 1536-Dim Embeddings">
                          <option value="openrouter/nvidia/nemotron-3-embed-1b">NVIDIA Nemotron 3 Embed 1B (Free — 1536-dim)</option>
                        </optgroup>
                        <optgroup label="Local Ollama 1536-Dim Embeddings (Privacy)">
                          <option value="ollama/nomic-embed-text">Ollama nomic-embed-text (1536-dim)</option>
                          <option value="ollama/mxbai-embed-large">Ollama mxbai-embed-large (1536-dim)</option>
                        </optgroup>
                      </select>
                    ) : (
                      <select
                        className="input"
                        value={defaults[key] || ""}
                        onChange={e => setDefaults(d => ({ ...d, [key]: e.target.value }))}
                        style={{ fontSize: 11 }}
                      >
                        <option value="">-- Auto Dynamic Fallback (Default: {fallbackModel}) --</option>
                        {defaults[key] && !Object.values(catalog).some((p: any) => p.models?.some((m: any) => m.value === defaults[key])) && (
                          <option value={defaults[key]}>Custom: {defaults[key]}</option>
                        )}
                        {Object.entries(catalog).map(([providerId, provider]: [string, any]) => (
                          <optgroup key={providerId} label={provider.label || providerId}>
                            {provider.models?.map((m: any, idx: number) => (
                              <option key={`${m.value}-${idx}`} value={m.value}>
                                {m.label || m.value}
                              </option>
                            ))}
                          </optgroup>
                        ))}
                      </select>
                    )}
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 2 }}>
                      <span className="caption text-mute" style={{ fontSize: 10 }}>
                        Active: <strong style={{ color: defaults[key] ? "var(--color-primary)" : "var(--color-text-secondary)" }}>{defaults[key] || `${fallbackModel} (auto-fallback)`}</strong>
                      </span>
                      <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: "var(--radius-xs)", background: "rgba(255, 255, 255, 0.05)", border: "1px solid var(--color-hairline)", color: "var(--color-text-muted)" }}>
                        Fallback: {fallbackModel}
                      </span>
                    </div>
                    <span className="caption text-mute" style={{ fontSize: 10 }}>
                      {desc}
                    </span>
                    {subsystems && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 2 }}>
                        {subsystems.map(sub => (
                          <span
                            key={sub}
                            style={{
                              fontSize: 9,
                              fontWeight: 600,
                              padding: "2px 6px",
                              borderRadius: "var(--radius-xs)",
                              background: "rgba(99, 102, 241, 0.08)",
                              border: "1px solid rgba(99, 102, 241, 0.2)",
                              color: "var(--color-primary)",
                            }}
                          >
                            {sub}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "var(--sp-sm)" }}>
                <button className="btn btn-primary btn-sm" onClick={handleSaveDefaults} disabled={saving}>
                  {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save Defaults
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {activeSubTab === "catalog" && (
        <ModelCatalogEditor onToast={onToast} />
      )}
    </div>
  );
}
