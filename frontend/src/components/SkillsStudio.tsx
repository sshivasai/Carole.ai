"use client";
import React, { useState, useEffect } from "react";
import { BookOpen, Plus, Save, Trash2, Loader2 } from "lucide-react";
import { api } from "@/hooks/useApi";
import Modal from "./Modal";
import { useAuth } from "@/hooks/useAuth";

export default function SkillsStudio({ teamId, onToast }: { teamId: string | null; onToast: (msg: string, type: "success" | "error" | "info") => void }) {
  useAuth();
  const [skills, setSkills] = useState<any[]>([]);
  const [activeSkillId, setActiveSkillId] = useState<string | null>(null);

  // Form State
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [tools, setTools] = useState("");
  const [mcpServers, setMcpServers] = useState("");
  const [isActive, setIsActive] = useState(true);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Modal State
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    if (teamId) {
      fetchSkills();
    }
  }, [teamId]);

  const fetchSkills = async () => {
    if (!teamId) return;
    setLoading(true);
    try {
      const data = await api.listSkills(teamId);
      setSkills(data);
      if (data.length > 0 && !activeSkillId) {
        selectSkill(data[0]);
      } else if (data.length === 0) {
        handleNew();
      }
    } catch (err) {
      console.error(err);
      onToast("Failed to load skills", "error");
    } finally {
      setLoading(false);
    }
  };

  const selectSkill = (skill: any) => {
    setActiveSkillId(skill.id);
    setName(skill.name || "");
    setDescription(skill.description || "");
    setSystemPrompt(skill.system_prompt_addendum || "");
    setTools((skill.tools || []).join(", "));
    setMcpServers((skill.mcp_servers || []).join(", "));
    setIsActive(skill.is_active ?? true);
  };

  const handleNew = () => {
    setActiveSkillId(null);
    setName("New Skill");
    setDescription("");
    setSystemPrompt("");
    setTools("");
    setMcpServers("");
    setIsActive(true);
  };

  const handleSave = async () => {
    if (!teamId) return;
    if (!name.trim()) {
      onToast("Skill name is required", "error");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        name,
        description,
        system_prompt_addendum: systemPrompt,
        tools: tools.split(",").map(t => t.trim()).filter(Boolean),
        mcp_servers: mcpServers.split(",").map(m => m.trim()).filter(Boolean),
        is_active: isActive
      };

      if (activeSkillId) {
        const updated = await api.updateSkill(activeSkillId, payload);
        setSkills(prev => prev.map(s => s.id === updated.id ? updated : s));
        onToast("Skill updated successfully", "success");
      } else {
        const created = await api.createSkill({ team_id: teamId, ...payload });
        setSkills([...skills, created]);
        setActiveSkillId(created.id);
        onToast("Skill created successfully", "success");
      }
    } catch (err: any) {
      onToast(`Save error: ${err.message || "Failed"}`, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!activeSkillId) return;
    setSaving(true);
    setConfirmOpen(false);
    try {
      await api.deleteSkill(activeSkillId);
      onToast("Skill deleted", "success");
      setSkills(prev => prev.filter(s => s.id !== activeSkillId));
      handleNew();
    } catch (err: any) {
      onToast(`Delete error: ${err.message || "Failed"}`, "error");
    } finally {
      setSaving(false);
    }
  };

  if (!teamId) {
    return (
      <div style={{ padding: "var(--sp-xl)", textAlign: "center", color: "var(--color-mute)" }}>
        Please select or create a team to manage skills.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", height: "100%", width: "100%", overflow: "hidden", background: "var(--color-canvas)" }}>
      {/* Sidebar */}
      <div style={{ width: 250, borderRight: "1px solid var(--color-hairline)", display: "flex", flexDirection: "column", background: "var(--color-canvas-soft)" }}>
        <div style={{ padding: "var(--sp-md) var(--sp-lg)", borderBottom: "1px solid var(--color-hairline)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", fontWeight: 600 }}>
            <BookOpen size={16} color="var(--color-primary)" />
            <span>Team Skills</span>
          </div>
          <button className="btn btn-icon btn-ghost btn-sm" onClick={handleNew} title="New Skill">
            <Plus size={16} />
          </button>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "var(--sp-sm)" }}>
          {loading ? (
            <div style={{ padding: "var(--sp-md)", color: "var(--color-mute)", fontSize: 13 }}>Loading...</div>
          ) : skills.length === 0 ? (
            <div style={{ padding: "var(--sp-md)", color: "var(--color-mute)", fontSize: 13, textAlign: "center" }}>
              No skills found.<br />Create one to extend agent capabilities.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              {skills.map(s => (
                <button
                  key={s.id}
                  onClick={() => selectSkill(s)}
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--sp-sm)",
                    padding: "8px 12px", width: "100%", textAlign: "left",
                    background: activeSkillId === s.id ? "var(--color-primary-glow)" : "transparent",
                    color: activeSkillId === s.id ? "var(--color-ink-strong)" : "var(--color-ink)",
                    border: activeSkillId === s.id ? "1px solid rgba(167, 139, 250, 0.35)" : "1px solid transparent",
                    borderRadius: "var(--radius-sm, 7px)", cursor: "pointer",
                    fontSize: 13, fontWeight: activeSkillId === s.id ? 700 : 500,
                    transition: "all var(--t-fast)",
                  }}
                >
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</span>
                  {!s.is_active && <span style={{ fontSize: 10, color: "var(--color-danger)", background: "var(--color-danger-glow)", padding: "2px 6px", borderRadius: 4 }}>Off</span>}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Editor Main */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, overflowY: "auto", padding: "var(--sp-xl)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "var(--sp-xl)" }}>
          <div>
            <h2 style={{ fontSize: 20, fontWeight: 600, margin: 0, color: "var(--color-ink)" }}>
              {activeSkillId ? "Edit Skill" : "Create New Skill"}
            </h2>
            <p style={{ fontSize: 13, color: "var(--color-mute)", margin: "4px 0 0 0" }}>
              Package prompts and tools together into reusable capabilities.
            </p>
          </div>
          <div style={{ display: "flex", gap: "var(--sp-sm)" }}>
            {activeSkillId && (
              <button className="btn btn-ghost btn-sm text-danger" onClick={() => setConfirmOpen(true)} disabled={saving}>
                <Trash2 size={14} /> Delete
              </button>
            )}
            <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving || !name.trim()}>
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              {activeSkillId ? "Save Changes" : "Create Skill"}
            </button>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-lg)", maxWidth: 800 }}>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--sp-lg)" }}>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: "var(--sp-xs)" }}>Skill Name</label>
              <input className="input" style={{ width: "100%" }} value={name} onChange={e => setName(e.target.value)} placeholder="e.g., Python Expert" />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: "var(--sp-xs)" }}>Description</label>
              <input className="input" style={{ width: "100%" }} value={description} onChange={e => setDescription(e.target.value)} placeholder="Short description of what this skill does" />
            </div>
          </div>

          <div>
            <label style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", fontSize: 13, fontWeight: 500, cursor: "pointer" }}>
              <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} />
              Active (Agents can use this skill)
            </label>
          </div>

          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: "var(--sp-xs)" }}>
              System Prompt Addendum
              <span style={{ color: "var(--color-mute)", fontWeight: 400, marginLeft: 8 }}>(Appended to agent&apos;s system prompt)</span>
            </label>
            <textarea
              className="input"
              style={{ width: "100%", height: 150, fontFamily: "var(--font-mono)", fontSize: 13, resize: "vertical" }}
              value={systemPrompt}
              onChange={e => setSystemPrompt(e.target.value)}
              placeholder="e.g., You are an expert Python developer. Always write type hints and use pytest for testing..."
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: "var(--sp-xs)" }}>
              Associated Tools (Comma separated)
            </label>
            <input
              className="input"
              style={{ width: "100%" }}
              value={tools}
              onChange={e => setTools(e.target.value)}
              placeholder="e.g., python_repl, write_file, read_file"
            />
            <p style={{ fontSize: 12, color: "var(--color-mute)", margin: "4px 0 0 0" }}>
              If tools are listed here, the agent is explicitly told to use them when this skill is active.
            </p>
          </div>

          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: "var(--sp-xs)" }}>
              Associated MCP Servers (Comma separated)
            </label>
            <input
              className="input"
              style={{ width: "100%" }}
              value={mcpServers}
              onChange={e => setMcpServers(e.target.value)}
              placeholder="e.g., github-mcp, jira-mcp"
            />
          </div>

        </div>
      </div>

      <Modal open={confirmOpen} onClose={() => setConfirmOpen(false)} title="Delete Skill">
        <p className="body-sm">Are you sure you want to delete this skill? This cannot be undone.</p>
        <div style={{ display: "flex", gap: "var(--sp-sm)", justifyContent: "flex-end", marginTop: "var(--sp-xl)" }}>
          <button className="btn btn-ghost" onClick={() => setConfirmOpen(false)}>Cancel</button>
          <button className="btn btn-danger" onClick={handleDelete}>Delete</button>
        </div>
      </Modal>
    </div>
  );
}
