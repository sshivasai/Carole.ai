"use client";
import React, { useState, useCallback, useEffect } from "react";
import type { AgentConfig } from "@/lib/types";
import { Zap, Plus, Edit2, Trash2, Loader2, X, Bot, ChevronDown, ChevronUp, Cpu } from "lucide-react";
import { api } from "@/hooks/useApi";
import Modal from "./Modal";

interface Props {
  agents: AgentConfig[];
  teamId: string | null;
  streamingAgents: Set<string>; // agent IDs currently streaming/thinking
  onAgentsChange: (agents: AgentConfig[]) => void;
  onToast: (msg: string, type: "success" | "error") => void;
}

const ROLE_COLORS: Record<string, string> = {
  orchestrator: "#00d992", researcher: "#60a5fa", coder: "#a78bfa",
  writer: "#fb923c", analyst: "#fbbf24", default: "#6b7280",
};

function AgentCard({ agent, isThinking, onEdit, onDelete }: {
  agent: AgentConfig; isThinking: boolean;
  onEdit: () => void; onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const roleColor = ROLE_COLORS[agent.role] || ROLE_COLORS.default;

  return (
    <div className="card" style={{ padding: "var(--sp-lg)", display: "flex", flexDirection: "column", gap: "var(--sp-md)", position: "relative", transition: "all var(--t-fast)" }}>
      <div style={{ position: "absolute", top: 10, right: 10, display: "flex", gap: 4 }}>
        <button className="btn btn-icon-sm btn-ghost" onClick={onEdit} title="Edit agent"><Edit2 size={12} /></button>
        <button className="btn btn-icon-sm btn-ghost" style={{ color: "var(--color-danger)" }} onClick={onDelete} title="Delete agent"><Trash2 size={12} /></button>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)" }}>
        <div style={{ width: 38, height: 38, borderRadius: "var(--radius-md)", background: `${roleColor}22`, border: `1px solid ${roleColor}44`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <Bot size={18} color={roleColor} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
            <span className="body-sm-strong">{agent.name}</span>
            {isThinking && <span className="pill pill-thinking" style={{ fontSize: 10 }}><span className="animate-pulse" style={{ display: "inline-block", width: 5, height: 5, borderRadius: "50%", background: "currentColor" }} /> thinking</span>}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginTop: 2 }}>
            <span className="badge badge-gray" style={{ fontSize: 9 }}>{agent.role}</span>
            <span className="caption" style={{ fontFamily: "monospace", fontSize: 11 }}>{agent.model}</span>
          </div>
          {agent.fallback_model && (
            <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 2 }}>
              <span style={{ fontSize: 10, color: "var(--color-mute)" }}>↩ fallback:</span>
              <span className="caption" style={{ fontFamily: "monospace", fontSize: 10, color: "var(--color-mute)" }}>{agent.fallback_model}</span>
            </div>
          )}
        </div>
      </div>

      {agent.skills && agent.skills.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {agent.skills.map(s => <span key={s} className="code-inline" style={{ fontSize: 11 }}>{s}</span>)}
        </div>
      )}

      {agent.personality && (
        <button onClick={() => setExpanded(e => !e)} className="btn btn-ghost btn-sm" style={{ justifyContent: "flex-start", padding: "2px 0", gap: 4, fontSize: 11, color: "var(--color-mute)" }}>
          {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          {expanded ? "Hide" : "Show"} personality
        </button>
      )}
      {expanded && agent.personality && (
        <p className="caption" style={{ borderLeft: "2px solid var(--color-hairline)", paddingLeft: "var(--sp-sm)", color: "var(--color-body)" }}>
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
  if (model.startsWith("nvidia/"))     return "nvidia";
  if (model.startsWith("ollama/"))     return "ollama";
  if (model.startsWith("gemini"))      return "google";
  if (model.startsWith("claude"))      return "anthropic";
  if (model.startsWith("gpt") || model.startsWith("o4") || model.startsWith("o3")) return "openai";
  return Object.keys(catalog)[0] || "openrouter";
}

/** Label badge for special OpenRouter router models */
function SpecialBadge({ value }: { value: string }) {
  if (value === "openrouter/auto")
    return <span style={{ fontSize: 10, background: "#7c3aed22", color: "#a78bfa", border: "1px solid #7c3aed44", borderRadius: 4, padding: "1px 5px", marginLeft: 4 }}>NotDiamond</span>;
  if (value === "openrouter/free")
    return <span style={{ fontSize: 10, background: "#05966922", color: "#00d992", border: "1px solid #05966944", borderRadius: 4, padding: "1px 5px", marginLeft: 4 }}>Reasoning</span>;
  return null;
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
          <p style={{ margin: "4px 0 0", fontSize: 11, color: "#a78bfa" }}>
            🔀 <strong>Auto Router</strong> — NotDiamond picks the best model per prompt.
          </p>
        )}
        {model === "openrouter/free" && (
          <p style={{ margin: "4px 0 0", fontSize: 11, color: "#00d992" }}>
            ⚡ <strong>Auto Free</strong> — Randomly selects a free model. Reasoning is automatically enabled.
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
  const [name,          setName]          = useState(initial?.name || "");
  const [role,          setRole]          = useState(initial?.role || "researcher");
  const [persona,       setPersona]       = useState(initial?.personality || "");
  const [skills,        setSkills]        = useState((initial?.skills || []).join(", "));
  const [loading,       setLoading]       = useState(false);
  const [catalog,       setCatalog]       = useState<Record<string, any>>({});
  const [catalogLoaded, setCatalogLoaded] = useState(false);

  // Primary model state
  const [primProvider, setPrimProvider] = useState("openrouter");
  const [primModel,    setPrimModel]    = useState(initial?.model || "openrouter/free");

  // Fallback model state
  const [showFallback, setShowFallback] = useState(!!(initial?.fallback_model));
  const [fallProvider, setFallProvider] = useState("openrouter");
  const [fallModel,    setFallModel]    = useState(initial?.fallback_model || "");

  // Reasoning state
  const [reasoning,    setReasoning]    = useState(initial?.reasoning_effort || "none");

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
    try {
      const tmpl = await api.getRoleTemplate(r);
      setPersona(tmpl.personality || "");
      setSkills((tmpl.skills || []).join(", "));
      if (tmpl.recommended_model && catalogLoaded) {
        const prov = detectProvider(tmpl.recommended_model, catalog);
        setPrimProvider(prov);
        setPrimModel(tmpl.recommended_model);
      }
      if (!name) setName(tmpl.suggested_names?.[0] || "");
    } catch {}
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    try {
      const data = {
        name: name.trim(),
        role,
        model: primModel,
        fallback_model: showFallback && fallModel.trim() ? fallModel.trim() : null,
        reasoning_effort: reasoning,
        personality: persona,
        skills: skills.split(",").map(s => s.trim()).filter(Boolean),
        team_id: teamId,
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
      {roleTemplates.length > 0 && (
        <div className="form-group">
          <label className="form-label">Quick Template</label>
          <select className="input" onChange={e => e.target.value && applyTemplate(e.target.value)} defaultValue="">
            <option value="">Choose a template…</option>
            {roleTemplates.map(t => <option key={t.role} value={t.role}>{t.display_name}</option>)}
          </select>
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--sp-md)" }}>
        <div className="form-group">
          <label className="form-label">Name *</label>
          <input className="input" placeholder="Agent Alpha" value={name} onChange={e => setName(e.target.value)} required />
        </div>
        <div className="form-group">
          <label className="form-label">Role</label>
          <select className="input" value={role} onChange={e => { setRole(e.target.value); applyTemplate(e.target.value); }}>
            {["orchestrator","researcher","coder","writer","analyst","custom"].map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
      </div>

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
            <p className="caption" style={{ marginBottom: "var(--sp-sm)", color: "var(--color-mute)" }}>
              ⚡ Used automatically if the primary model returns an error (e.g. quota, bad key, outage).
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

      <div className="form-group">
        <label className="form-label">Personality / System Prompt</label>
        <textarea className="input" style={{ minHeight: 80 }} placeholder="You are a helpful research assistant…" value={persona} onChange={e => setPersona(e.target.value)} />
      </div>
      <div className="form-group">
        <label className="form-label">Skills (comma-separated)</label>
        <input className="input" placeholder="web_search, code_execution, browser" value={skills} onChange={e => setSkills(e.target.value)} />
      </div>
      <div style={{ display: "flex", gap: "var(--sp-md)", justifyContent: "flex-end" }}>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
        <button type="submit" className="btn btn-primary btn-sm" disabled={loading || !name.trim()}>
          {loading ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
          {initial ? "Save Changes" : "Create Agent"}
        </button>
      </div>
    </form>
  );
}

export default function AgentPanel({ agents, teamId, streamingAgents, onAgentsChange, onToast }: Props) {
  const [modalOpen,    setModalOpen]    = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentConfig | undefined>(undefined);
  const [templates,    setTemplates]    = useState<any[]>([]);
  const [deletingId,   setDeletingId]   = useState<string | null>(null);

  useEffect(() => { api.listRoleTemplates().then(setTemplates).catch(() => {}); }, []);

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
    finally { setDeletingId(null); }
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
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "var(--sp-lg)", overflowY: "auto" }}>
          {agents.map(agent => (
            <AgentCard
              key={agent.id}
              agent={agent}
              isThinking={streamingAgents.has(agent.id)}
              onEdit={() => { setEditingAgent(agent); setModalOpen(true); }}
              onDelete={() => handleDelete(agent.id)}
            />
          ))}
        </div>
      )}

      <Modal open={modalOpen} onClose={() => { setModalOpen(false); setEditingAgent(undefined); }}
        title={editingAgent ? "Edit Agent" : "New Agent"} maxWidth={520}>
        <AgentForm initial={editingAgent} teamId={teamId} roleTemplates={templates} onSave={handleSaved} onClose={() => { setModalOpen(false); setEditingAgent(undefined); }} />
      </Modal>
    </div>
  );
}
