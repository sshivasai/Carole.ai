"use client";
import React, { useState, useEffect } from "react";
import type { AgentConfig, ScheduledTask, AccessControlConfig } from "@/lib/types";
import { Zap, Plus, Edit2, Trash2, Loader2, Bot, ChevronDown, ChevronUp, Cpu, Clock, Shield, Shuffle, Sparkles, RefreshCw, FileText } from "lucide-react";
import { api } from "@/hooks/useApi";
import Modal from "./Modal";
import AgentAvatar from "./AgentAvatar";
import AgentHoverCard from "./AgentHoverCard";
import CronTaskModal from "./CronTaskModal";
import AccessControlMatrix, { DEFAULT_ACCESS_CONTROL } from "./AccessControlMatrix";

interface Props {
  agents: AgentConfig[];
  teamId: string | null;
  streamingAgents: Set<string>; // agent IDs currently streaming/thinking
  agentQueues?: Record<string, number>; // agent_id -> pending task count
  onAgentsChange: (agents: AgentConfig[]) => void;
  onToast: (msg: string, type: "success" | "error") => void;
}

const ROLE_COLORS: Record<string, string> = {
  orchestrator: "#00d992", researcher: "#60a5fa", coder: "#a78bfa",
  writer: "#fb923c", analyst: "#fbbf24", default: "#6b7280",
};

function AgentCard({ agent, isThinking, queueDepth, onEdit, onDelete }: {
  agent: AgentConfig; isThinking: boolean; queueDepth: number;
  onEdit: () => void; onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const roleColor = ROLE_COLORS[agent.role] || ROLE_COLORS.default;
  const isSubagent = agent.name.startsWith("Sub-") || agent.name.startsWith("Subagent-") || agent.role === "subagent";

  return (
    <div 
      className={`card ${isThinking ? "status-ring-thinking" : ""}`} 
      style={{ 
        padding: "var(--sp-lg)", 
        display: "flex", 
        flexDirection: "column", 
        gap: "var(--sp-md)", 
        position: "relative", 
        transition: "all var(--t-fast)",
        border: isSubagent ? "1px solid rgba(251, 191, 36, 0.45)" : isThinking ? "1px solid var(--color-primary)" : "1px solid var(--border-subtle)",
        background: isSubagent ? "linear-gradient(135deg, rgba(251, 191, 36, 0.04), var(--bg-surface))" : "var(--bg-surface)",
      }}
    >
      <div style={{ position: "absolute", top: 10, right: 10, display: "flex", gap: 4 }}>
        <button className="btn btn-icon-sm btn-ghost" onClick={onEdit} title="Edit agent"><Edit2 size={12} /></button>
        <button className="btn btn-icon-sm btn-ghost" style={{ color: "var(--color-danger)" }} onClick={onDelete} title="Delete agent"><Trash2 size={12} /></button>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)" }}>
        <AgentHoverCard agent={agent} isThinking={isThinking}>
          <AgentAvatar name={agent.name} id={agent.id} role={agent.role} size={40} isThinking={isThinking} isSubagent={isSubagent} />
        </AgentHoverCard>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", flexWrap: "wrap" }}>
            <AgentHoverCard agent={agent} isThinking={isThinking}>
              <span className="body-sm-strong" style={{ fontSize: 13, cursor: "pointer" }}>{agent.name}</span>
            </AgentHoverCard>
            {isSubagent && (
              <span className="subagent-chip" style={{ fontSize: 9, padding: "1px 5px" }}>
                SUBAGENT
              </span>
            )}
            {isThinking && (
              <span className="pill pill-thinking" style={{ fontSize: 10 }}>
                <span className="animate-pulse" style={{ display: "inline-block", width: 5, height: 5, borderRadius: "50%", background: "currentColor" }} />
                working
              </span>
            )}
            {!isThinking && queueDepth > 0 && (
              <span style={{
                fontSize: 10, padding: "1px 6px", borderRadius: 8,
                background: "rgba(251,191,36,0.15)", color: "#FBBF24",
                border: "1px solid rgba(251,191,36,0.3)", fontWeight: 600,
              }}>
                ⏳ {queueDepth} queued
              </span>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginTop: 4, flexWrap: "wrap" }}>
            <span className="badge badge-gray" style={{ fontSize: 9, textTransform: "capitalize" }}>{agent.role}</span>
            <span className="caption" style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11, color: "var(--color-primary-soft)" }}>{agent.model}</span>
          </div>
          {agent.fallback_model && (
            <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 2 }}>
              <span style={{ fontSize: 10, color: "var(--color-mute)" }}>↩ fallback:</span>
              <span className="caption" style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 10, color: "var(--color-mute)" }}>{agent.fallback_model}</span>
            </div>
          )}
        </div>
      </div>

      {agent.skills && agent.skills.length > 0 ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {agent.skills.map(s => <span key={s} className="code-inline" style={{ fontSize: 10, padding: "2px 6px" }}>{s}</span>)}
        </div>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          <span className="code-inline" style={{ fontSize: 10, padding: "2px 6px", opacity: 0.85 }}>
            {agent.role}
          </span>
        </div>
      )}

      {isThinking && (
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "4px 8px",
          background: "rgba(168, 85, 247, 0.08)",
          border: "1px solid rgba(168, 85, 247, 0.25)",
          borderRadius: "var(--radius-xs)",
          fontSize: 10,
          color: "#c084fc",
        }}>
          <span className="animate-pulse" style={{ display: "inline-block", width: 5, height: 5, borderRadius: "50%", background: "#c084fc" }} />
          <span style={{ fontWeight: 500 }}>Actively executing tasks...</span>
        </div>
      )}

      {agent.personality && (
        <button onClick={() => setExpanded(e => !e)} className="btn btn-ghost btn-sm" style={{ justifyContent: "flex-start", padding: "2px 0", gap: 4, fontSize: 11, color: "var(--color-mute)" }}>
          {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          {expanded ? "Hide" : "Show"} instructions
        </button>
      )}
      {expanded && agent.personality && (
        <p className="caption" style={{ borderLeft: "2px solid var(--color-primary)", paddingLeft: "var(--sp-sm)", color: "var(--color-body)", background: "var(--color-canvas)", padding: "6px 8px", borderRadius: "0 var(--radius-xs) var(--radius-xs) 0", margin: 0 }}>
          {agent.personality}
        </p>
      )}
    </div>
  );
}

/** Detect which provider key a stored model string belongs to. */
function detectProvider(model: string, catalog: Record<string, any>): string {
  if (!model) return Object.keys(catalog)[0] || "openrouter";
  for (const [id, data] of Object.entries(catalog)) {
    if ((data.models as any[]).some((m: any) => m.value === model)) return id;
  }
  // Fallback: infer by prefix
  if (model.startsWith("openrouter/")) return "openrouter";
  if (model.startsWith("nvidia/")) return "nvidia";
  if (model.startsWith("ollama/")) return "ollama";
  if (model.startsWith("gemini")) return "google";
  if (model.startsWith("claude")) return "anthropic";
  if (model.startsWith("gpt") || model.startsWith("o4") || model.startsWith("o3")) return "openai";
  return Object.keys(catalog)[0] || "openrouter";
}

/** Single model selector (provider dropdown + model select + custom text input) */
function ModelSelector({
  label, catalog, provider, model,
  onProviderChange, onModelChange,
}: {
  label: string;
  catalog: Record<string, any>;
  provider: string;
  model: string;
  onProviderChange: (p: string) => void;
  onModelChange: (m: string) => void;
}) {
  const providerData = catalog[provider];
  const models = providerData?.models || [];

  // If the current model isn't in the provider's known list, we treat it as "custom"
  const isKnown = models.some((m: any) => m.value === model);
  const showCustom = !isKnown && model !== "";

  return (
    <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: "var(--sp-md)" }}>
      <div className="form-group" style={{ marginBottom: 0 }}>
        <label className="form-label">{label} — Provider</label>
        <select className="input" value={provider} onChange={e => onProviderChange(e.target.value)}>
          {Object.entries(catalog).map(([k, v]: [string, any]) => (
            <option key={k} value={k}>{v.label}</option>
          ))}
        </select>
      </div>
      <div className="form-group" style={{ marginBottom: 0 }}>
        <label className="form-label">
          Model
        </label>
        <select
          className="input"
          value={isKnown ? model : "custom"}
          onChange={e => {
            if (e.target.value === "custom") {
              onModelChange("");
            } else {
              onModelChange(e.target.value);
            }
          }}
        >
          {models.map((m: any) => (
            <option key={m.value} value={m.value}>
              {m.label}{m.special ? (m.value === "openrouter/auto" ? " (Auto-router)" : " (Random Free + Reasoning)") : ""}
            </option>
          ))}
          <option value="custom">Custom... (Type manually)</option>
        </select>

        {(!isKnown || showCustom) && (
          <input
            className="input"
            style={{ marginTop: "var(--sp-xs)" }}
            value={model}
            onChange={e => onModelChange(e.target.value)}
            placeholder="Type custom model ID..."
          />
        )}

        {/* Special model info banners */}
        {model === "openrouter/auto" && (
          <p style={{ margin: "4px 0 0", fontSize: 11, color: "#a78bfa", display: "flex", alignItems: "center", gap: 5 }}>
            <Shuffle size={12} /> <strong>Auto Router</strong> — NotDiamond picks the best model per prompt.
          </p>
        )}
        {model === "openrouter/free" && (
          <p style={{ margin: "4px 0 0", fontSize: 11, color: "#00d992", display: "flex", alignItems: "center", gap: 5 }}>
            <Sparkles size={12} /> <strong>Auto Free</strong> — Randomly selects a free model. Reasoning is automatically enabled.
          </p>
        )}
      </div>
    </div>
  );
}

function AgentForm({ initial, teamId, roleTemplates, onSave, onClose }: {
  initial?: AgentConfig; teamId: string; roleTemplates: any[];
  onSave: (a: AgentConfig) => void; onClose: () => void;
}) {
  const [activeTab, setActiveTab] = useState<"general" | "access">("general");
  const [selectedTemplate, setSelectedTemplate] = useState<string>("");
  const [name, setName] = useState(initial?.name || "");
  const [role, setRole] = useState(initial?.role || (roleTemplates?.[0]?.role ?? "Coder"));
  const [customRole, setCustomRole] = useState("");
  const [persona, setPersona] = useState(initial?.personality || "");
  const [skills, setSkills] = useState((initial?.skills || []).join(", "));
  const [loading, setLoading] = useState(false);
  const [catalog, setCatalog] = useState<Record<string, any>>({});
  const [catalogLoaded, setCatalogLoaded] = useState(false);

  // Access Control state
  const [accessControl, setAccessControl] = useState<AccessControlConfig>(() => {
    const tp = initial?.tool_permissions;
    if (tp && typeof tp === "object" && "categories" in tp) return tp as AccessControlConfig;
    return { ...DEFAULT_ACCESS_CONTROL, categories: { ...DEFAULT_ACCESS_CONTROL.categories }, overrides: {}, custom_skip_judge: { file_patterns: [], command_prefixes: [] } };
  });

  // Primary model state
  const [primProvider, setPrimProvider] = useState("openrouter");
  const [primModel, setPrimModel] = useState(initial?.model || "openrouter/free");

  // Fallback model state
  const [showFallback, setShowFallback] = useState(!!(initial?.fallback_model));
  const [fallProvider, setFallProvider] = useState("openrouter");
  const [fallModel, setFallModel] = useState(initial?.fallback_model || "");

  // Reasoning state
  const [reasoning, setReasoning] = useState(initial?.reasoning_effort || "none");

  // Implementation plan auto-approval state
  const [autoApprovePlans, setAutoApprovePlans] = useState(initial?.auto_approve_plans ?? false);

  // Load model catalog from backend on mount
  useEffect(() => {
    api.listModels().then(cat => {
      setCatalog(cat);
      setCatalogLoaded(true);
      if (initial?.model) {
        setPrimProvider(detectProvider(initial.model, cat));
      } else {
        // Default: first provider in catalog
        const firstProv = Object.keys(cat)[0];
        if (firstProv) {
          setPrimProvider(firstProv);
          setPrimModel(cat[firstProv]?.models?.[0]?.value || "");
        }
      }
      if (initial?.fallback_model) {
        setFallProvider(detectProvider(initial.fallback_model, cat));
      }
    }).catch(() => {
      // Fallback: show empty catalog with manual entry still possible
      setCatalogLoaded(true);
    });
  }, []);

  // When primary provider changes, auto-select first model of that provider
  const handlePrimProviderChange = (p: string) => {
    setPrimProvider(p);
    const first = catalog[p]?.models?.[0]?.value || "";
    setPrimModel(first);
  };

  // When fallback provider changes, auto-select first model
  const handleFallProviderChange = (p: string) => {
    setFallProvider(p);
    const first = catalog[p]?.models?.[0]?.value || "";
    setFallModel(first);
  };

  const applyTemplate = async (r: string) => {
    if (!r) return;
    try {
      const tmpl = await api.getRoleTemplate(r);
      if (!tmpl) return;

      const templateRole = tmpl.role || r;
      setRole(templateRole);
      setSelectedTemplate(templateRole);

      if (tmpl.suggested_names && tmpl.suggested_names.length > 0) {
        setName(tmpl.suggested_names[0]);
      } else if (tmpl.display_name) {
        setName(tmpl.display_name);
      }

      setPersona(tmpl.personality || "");
      setSkills((tmpl.skills || []).join(", "));

      if (tmpl.recommended_model && catalogLoaded) {
        const prov = detectProvider(tmpl.recommended_model, catalog);
        setPrimProvider(prov);
        setPrimModel(tmpl.recommended_model);
      }
    } catch (err) {
      console.error("Failed to apply role template:", err);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    const finalRole = (role === "custom" ? customRole.trim() : role) || "Coder";
    setLoading(true);
    try {
      const data = {
        name: name.trim(),
        role: finalRole,
        model: primModel,
        fallback_model: showFallback && fallModel.trim() ? fallModel.trim() : null,
        reasoning_effort: reasoning,
        personality: persona,
        skills: skills.split(",").map(s => s.trim()).filter(Boolean),
        team_id: teamId,
        tool_permissions: accessControl,
        auto_approve_plans: autoApprovePlans,
      };
      const saved = initial
        ? await api.updateAgent(initial.id, data)
        : await api.createAgent({ ...data, team_id: teamId });
      onSave(saved);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  if (!catalogLoaded) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "var(--sp-2xl)", gap: "var(--sp-md)" }}>
        <Loader2 size={18} className="animate-spin" style={{ color: "var(--color-primary)" }} />
        <span className="caption">Loading model catalog…</span>
      </div>
    );
  }

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: "var(--sp-lg)" }}>
      {/* Tab switcher */}
      <div style={{ display: "flex", gap: 4, background: "var(--color-canvas-raised)", padding: 4, borderRadius: "var(--radius-md)", border: "1px solid var(--color-hairline)" }}>
        {(["general", "access"] as const).map(tab => (
          <button key={tab} type="button" onClick={() => setActiveTab(tab)}
            style={{ flex: 1, padding: "6px 12px", borderRadius: "var(--radius-sm)", border: "none", cursor: "pointer", fontSize: 12, fontWeight: 600, transition: "all 0.15s",
              background: activeTab === tab ? "var(--color-primary)" : "transparent",
              color: activeTab === tab ? "#000" : "var(--color-mute)",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
            {tab === "general" ? <Cpu size={12} /> : <Shield size={12} />}
            {tab === "general" ? "General & Models" : "Access Control"}
          </button>
        ))}
      </div>

      {/* Access Control tab */}
      {activeTab === "access" && (
        <div style={{ overflowY: "auto", maxHeight: 500, paddingRight: 2 }}>
          <p className="caption" style={{ margin: "0 0 var(--sp-md)" }}>
            Configure per-agent permissions. These override global defaults and control which tools this agent can use without friction.
          </p>
          <AccessControlMatrix value={accessControl} onChange={setAccessControl} />
          <div style={{ display: "flex", gap: "var(--sp-md)", justifyContent: "flex-end", marginTop: "var(--sp-xl)", paddingTop: "var(--sp-md)", borderTop: "1px solid var(--color-hairline)" }}>
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary btn-sm" disabled={loading || !name.trim()}>
              {loading ? <Loader2 size={13} className="animate-spin" /> : <Shield size={13} />}
              {initial ? "Save Changes" : "Create Agent"}
            </button>
          </div>
        </div>
      )}

      {/* General tab */}
      {activeTab === "general" && roleTemplates.length > 0 && (
        <div className="form-group">
          <label className="form-label">Quick Template</label>
          <select
            className="input"
            value={selectedTemplate}
            onChange={e => {
              const val = e.target.value;
              setSelectedTemplate(val);
              if (val) applyTemplate(val);
            }}
          >
            <option value="">Choose a template…</option>
            {roleTemplates.map(t => (
              <option key={t.role} value={t.role}>
                {t.display_name || t.role}
              </option>
            ))}
          </select>
        </div>
      )}
      {activeTab === "general" && (
        <>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--sp-md)" }}>
          <div className="form-group">
            <label className="form-label">Name *</label>
            <input
              className="input"
              placeholder="Agent Name"
              value={name}
              onChange={e => setName(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label">Role</label>
            <select
              className="input"
              value={role}
              onChange={e => {
                const val = e.target.value;
                setRole(val);
                if (val && val !== "custom") {
                  applyTemplate(val);
                }
              }}
            >
              {roleTemplates.map(t => (
                <option key={t.role} value={t.role}>
                  {t.role}
                </option>
              ))}
              {!roleTemplates.some(t => t.role.toLowerCase() === role.toLowerCase()) && role && (
                <option value={role}>{role}</option>
              )}
              <option value="custom">Custom...</option>
            </select>
          </div>
        </div>

        {role === "custom" && (
          <div className="form-group">
            <label className="form-label">Custom Role Title</label>
            <input
              className="input"
              placeholder="e.g. Lead QA Specialist"
              value={customRole}
              onChange={e => setCustomRole(e.target.value)}
              required
            />
          </div>
        )}

        {/* Primary model */}
        <div>
          <p className="form-label" style={{ marginBottom: "var(--sp-sm)" }}>Primary Model</p>
          <ModelSelector
            label="Primary"
            catalog={catalog}
            provider={primProvider}
            model={primModel}
            onProviderChange={handlePrimProviderChange}
            onModelChange={setPrimModel}
          />
        </div>

        {/* Fallback model toggle */}
        <div>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            style={{ gap: "var(--sp-sm)", fontSize: 12 }}
            onClick={() => { setShowFallback(f => !f); if (!showFallback && !fallModel) { const first = catalog[fallProvider]?.models?.[0]?.value || ""; setFallModel(first); } }}
          >
            {showFallback ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            {showFallback ? "Remove fallback model" : "＋ Add fallback model"}
          </button>
          {showFallback && (
            <div style={{ marginTop: "var(--sp-sm)", padding: "var(--sp-md)", border: "1px dashed var(--color-hairline)", borderRadius: "var(--radius-md)" }}>
              <p className="caption" style={{ marginBottom: "var(--sp-sm)", color: "var(--color-mute)", display: "flex", alignItems: "center", gap: 5 }}>
                <RefreshCw size={11} /> Used automatically if the primary model returns an error (e.g. quota, bad key, outage).
              </p>
              <ModelSelector
                label="Fallback"
                catalog={catalog}
                provider={fallProvider}
                model={fallModel}
                onProviderChange={handleFallProviderChange}
                onModelChange={setFallModel}
              />
            </div>
          )}
        </div>

        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label" style={{ display: "flex", alignItems: "center", gap: "var(--sp-xs)" }}>
            Reasoning Effort
            <span style={{ fontSize: 11, color: "var(--color-mute)", fontWeight: "normal" }}>
              (For OpenAI o-series, Anthropic Claude 3.7+, and OpenRouter models)
            </span>
          </label>
          <select className="input" value={reasoning} onChange={e => setReasoning(e.target.value)}>
            <option value="none">Disabled (Standard completion)</option>
            <option value="low">Low (Fast, less detailed)</option>
            <option value="medium">Medium (Balanced)</option>
            <option value="high">High (Deep thinking, expensive)</option>
          </select>
        </div>
        </>
      )}

      {activeTab === "general" && (
        <>
          <div className="form-group">
            <label className="form-label">Personality / System Prompt</label>
            <textarea className="input" style={{ minHeight: 80 }} placeholder="You are a helpful research assistant…" value={persona} onChange={e => setPersona(e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">Skills (comma-separated)</label>
            <input className="input" placeholder="web_search, code_execution, browser" value={skills} onChange={e => setSkills(e.target.value)} />
          </div>

          {/* Implementation Plan Auto-Approval toggle */}
          <div className="form-group" style={{ background: "var(--color-canvas-raised)", padding: "var(--sp-md)", borderRadius: "var(--radius-md)", border: "1px solid var(--color-hairline)" }}>
            <label style={{ display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer", userSelect: "none" }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--color-ink)", display: "flex", alignItems: "center", gap: 6 }}>
                  <FileText size={14} style={{ color: "var(--color-accent, #6366f1)" }} />
                  Implementation Plan Auto-Approval
                </div>
                <div className="caption" style={{ color: "var(--color-mute)", marginTop: 2 }}>
                  Automatically approve this agent&apos;s implementation plans without requiring manual review.
                </div>
              </div>
              <input
                type="checkbox"
                checked={autoApprovePlans}
                onChange={e => setAutoApprovePlans(e.target.checked)}
                style={{ width: 16, height: 16, accentColor: "var(--color-primary)" }}
              />
            </label>
          </div>
          <div style={{ display: "flex", gap: "var(--sp-md)", justifyContent: "flex-end" }}>
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary btn-sm" disabled={loading || !name.trim()}>
              {loading ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
              {initial ? "Save Changes" : "Create Agent"}
            </button>
          </div>
        </>
      )}
    </form>
  );
}

export default function AgentPanel({ agents, teamId, streamingAgents, agentQueues = {}, onAgentsChange, onToast }: Props) {
  const [modalOpen, setModalOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentConfig | undefined>(undefined);
  const [templates, setTemplates] = useState<any[]>([]);
  const [, setDeletingId] = useState<string | null>(null);

  const [scheduledTasks, setScheduledTasks] = useState<ScheduledTask[]>([]);
  const [cronModalOpen, setCronModalOpen] = useState(false);
  const [editingCronTask, setEditingCronTask] = useState<ScheduledTask | undefined>(undefined);
  const [agentToDelete, setAgentToDelete] = useState<AgentConfig | null>(null);
  const [taskToDelete, setTaskToDelete] = useState<ScheduledTask | null>(null);

  useEffect(() => {
    api.listRoleTemplates().then(setTemplates).catch(() => { });
  }, []);

  useEffect(() => {
    if (teamId) {
      api.listScheduledTasks(teamId).then(setScheduledTasks).catch(() => { });
    } else {
      setScheduledTasks([]);
    }
  }, [teamId]);

  const handleSaved = (saved: AgentConfig) => {
    const existing = agents.find(a => a.id === saved.id);
    if (existing) onAgentsChange(agents.map(a => a.id === saved.id ? saved : a));
    else onAgentsChange([saved, ...agents]);
    setModalOpen(false);
    setEditingAgent(undefined);
    onToast(existing ? "Agent updated" : "Agent created", "success");
  };

  const handleDelete = async (agentId: string) => {
    setDeletingId(agentId);
    try {
      await api.deleteAgent(agentId);
      onAgentsChange(agents.filter(a => a.id !== agentId));
      onToast("Agent deleted", "success");
    } catch { onToast("Failed to delete agent", "error"); }
    finally { setDeletingId(null); setAgentToDelete(null); }
  };

  if (!teamId) return (
    <div className="empty-state" style={{ height: "100%" }}>
      <Cpu size={36} className="empty-state-icon" />
      <h3>No team selected</h3>
      <p>Select a team from the sidebar to manage its agents</p>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "var(--sp-2xl)" }}>
      <div className="flex-between" style={{ marginBottom: "var(--sp-2xl)" }}>
        <div>
          <h2 className="display-md">Agents</h2>
          <p className="caption">{agents.length} agent{agents.length !== 1 ? "s" : ""} in this team</p>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => { setEditingAgent(undefined); setModalOpen(true); }}>
          <Plus size={14} /> New Agent
        </button>
      </div>

      {agents.length === 0 ? (
        <div className="empty-state" style={{ flex: 1 }}>
          <Bot size={40} className="empty-state-icon" />
          <h3>No agents yet</h3>
          <p>Create your first AI agent to get started</p>
          <button className="btn btn-primary btn-sm" onClick={() => setModalOpen(true)}>
            <Plus size={13} /> Create Agent
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-xl)", overflowY: "auto" }}>
          {/* Primary Core Team Agents */}
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: "var(--sp-md)" }}>
              <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.5px", color: "var(--color-mute)", textTransform: "uppercase" }}>
                CORE AGENTS ({agents.filter(a => !a.name.startsWith("Sub-") && !a.name.startsWith("Subagent-")).length})
              </span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "var(--sp-lg)", alignItems: "start" }}>
              {agents.filter(a => !a.name.startsWith("Sub-") && !a.name.startsWith("Subagent-")).map(a => (
                <AgentCard
                  key={a.id}
                  agent={a}
                  isThinking={streamingAgents.has(a.id)}
                  queueDepth={agentQueues?.[a.id] || 0}
                  onEdit={() => { setEditingAgent(a); setModalOpen(true); }}
                  onDelete={() => setAgentToDelete(a)}
                />
              ))}
            </div>
          </div>

          {/* Active Temporary Subagents (if any) */}
          {agents.some(a => a.name.startsWith("Sub-") || a.name.startsWith("Subagent-")) && (
            <div style={{ borderTop: "1px dashed var(--border-glass)", paddingTop: "var(--sp-lg)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: "var(--sp-md)" }}>
                <span className="subagent-chip" style={{ fontSize: 10 }}>🤖 TEMPORARY SUBAGENTS</span>
                <span className="caption" style={{ color: "var(--color-mute)" }}>Specialist workers spawned for specific subtasks (Depth 1 guarded)</span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "var(--sp-lg)", alignItems: "start" }}>
                {agents.filter(a => a.name.startsWith("Sub-") || a.name.startsWith("Subagent-")).map(a => (
                  <AgentCard
                    key={a.id}
                    agent={a}
                    isThinking={streamingAgents.has(a.id)}
                    queueDepth={agentQueues?.[a.id] || 0}
                    onEdit={() => { setEditingAgent(a); setModalOpen(true); }}
                    onDelete={() => setAgentToDelete(a)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {agents.length > 0 && (
        <div style={{ marginTop: "var(--sp-2xl)" }}>
          <div className="flex-between" style={{ marginBottom: "var(--sp-lg)" }}>
            <div>
              <h2 className="display-sm">Scheduled Tasks</h2>
              <p className="caption">Automate agents to run periodically via cron schedules</p>
            </div>
            <button className="btn btn-secondary btn-sm" onClick={() => { setEditingCronTask(undefined); setCronModalOpen(true); }}>
              <Clock size={13} /> New Task
            </button>
          </div>

          {scheduledTasks.length === 0 ? (
            <div className="empty-state" style={{ padding: "var(--sp-xl)" }}>
              <p className="caption">No scheduled tasks yet.</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-sm)" }}>
              {scheduledTasks.map(task => (
                <div key={task.id} className="card" style={{ padding: "var(--sp-md)", display: "flex", alignItems: "center", gap: "var(--sp-md)" }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                      <span className="body-sm-strong">{task.name}</span>
                      <span className={`badge ${task.is_active ? 'badge-primary' : 'badge-gray'}`}>
                        {task.is_active ? "Active" : "Inactive"}
                      </span>
                    </div>
                    <div className="caption" style={{ marginTop: 4, display: "flex", gap: 12 }}>
                      <span style={{ fontFamily: "monospace" }}>{task.cron_expression}</span>
                      <span>Agent: {agents.find(a => a.id === task.agent_id)?.name || "Unknown"}</span>
                      {task.last_run_at && <span>Last run: {new Date(task.last_run_at).toLocaleString()}</span>}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: "var(--sp-sm)" }}>
                    <button
                      className="btn btn-outline btn-sm"
                      onClick={async () => {
                        try {
                          const res = await api.updateScheduledTask(task.id, { is_active: !task.is_active });
                          setScheduledTasks(prev => prev.map(t => t.id === task.id ? res : t));
                          onToast(`Task ${res.is_active ? 'activated' : 'paused'}`, "success");
                        } catch {
                          onToast("Failed to update task", "error");
                        }
                      }}
                    >
                      {task.is_active ? "Pause" : "Activate"}
                    </button>
                    <button className="btn btn-icon-sm btn-ghost" onClick={() => { setEditingCronTask(task); setCronModalOpen(true); }}><Edit2 size={13} /></button>
                    <button
                      className="btn btn-icon-sm btn-ghost"
                      style={{ color: "var(--color-danger)" }}
                      onClick={() => setTaskToDelete(task)}
                      title="Delete scheduled task"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <Modal open={modalOpen} onClose={() => { setModalOpen(false); setEditingAgent(undefined); }}
        title={editingAgent ? "Edit Agent" : "New Agent"} maxWidth={520}>
        <AgentForm initial={editingAgent} teamId={teamId} roleTemplates={templates} onSave={handleSaved} onClose={() => { setModalOpen(false); setEditingAgent(undefined); }} />
      </Modal>

      {/* Delete Agent Confirmation */}
      {agentToDelete && (
        <Modal open={true} onClose={() => setAgentToDelete(null)} title="Delete Agent" maxWidth={400}>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
            <p className="body-sm" style={{ color: "var(--color-body)", margin: 0 }}>
              Are you sure you want to delete agent <strong>"{agentToDelete.name}"</strong>? This will remove all their system prompts and history.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--sp-sm)", marginTop: "var(--sp-sm)" }}>
              <button className="btn btn-ghost btn-sm" onClick={() => setAgentToDelete(null)}>Cancel</button>
              <button className="btn btn-danger btn-sm" onClick={() => handleDelete(agentToDelete.id)}>Delete Agent</button>
            </div>
          </div>
        </Modal>
      )}

      {/* Delete Scheduled Task Confirmation */}
      {taskToDelete && (
        <Modal open={true} onClose={() => setTaskToDelete(null)} title="Delete Scheduled Task" maxWidth={400}>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
            <p className="body-sm" style={{ color: "var(--color-body)", margin: 0 }}>
              Are you sure you want to delete scheduled task <strong>"{taskToDelete.name}"</strong>? This will stop all future automated runs.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--sp-sm)", marginTop: "var(--sp-sm)" }}>
              <button className="btn btn-ghost btn-sm" onClick={() => setTaskToDelete(null)}>Cancel</button>
              <button className="btn btn-danger btn-sm" onClick={async () => {
                try {
                  await api.deleteScheduledTask(taskToDelete.id);
                  setScheduledTasks(prev => prev.filter(t => t.id !== taskToDelete.id));
                  onToast("Task deleted", "success");
                } catch {
                  onToast("Failed to delete task", "error");
                } finally {
                  setTaskToDelete(null);
                }
              }}>
                Delete Task
              </button>
            </div>
          </div>
        </Modal>
      )}

      <CronTaskModal
        open={cronModalOpen}
        onClose={() => { setCronModalOpen(false); setEditingCronTask(undefined); }}
        teamId={teamId}
        agents={agents}
        existingTask={editingCronTask}
        onSave={(saved) => {
          if (editingCronTask) {
            setScheduledTasks(prev => prev.map(t => t.id === saved.id ? saved : t));
            onToast("Scheduled task updated", "success");
          } else {
            setScheduledTasks(prev => [saved, ...prev]);
            onToast("Scheduled task created", "success");
          }
        }}
      />
    </div>
  );
}
