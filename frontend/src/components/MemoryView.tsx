"use client";
import React, { useState } from "react";
import type { LearningItem } from "@/lib/types";
import { BrainCircuit, Database, Search, Edit2, Trash2, Plus, Loader2, X, Check } from "lucide-react";
import { api } from "@/hooks/useApi";
import Modal from "./Modal";

interface Props {
  learnings: LearningItem[];
  projectId: string | null;
  teamId: string | null;
  onLearningsChange: (l: LearningItem[]) => void;
  onToast: (msg: string, type: "success"|"error") => void;
}

export default function MemoryView({ learnings, projectId, teamId, onLearningsChange, onToast }: Props) {
  const [query,   setQuery]   = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [editItem, setEditItem] = useState<LearningItem | null>(null);
  const [form, setForm] = useState({ task_summary: "", lesson_rule: "" });
  const [saving,   setSaving]   = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const filtered = learnings.filter(l =>
    !query || l.task_summary.toLowerCase().includes(query.toLowerCase()) || l.lesson_rule.toLowerCase().includes(query.toLowerCase())
  );

  const handleSave = async () => {
    if (!projectId || !form.task_summary.trim() || !form.lesson_rule.trim()) return;
    setSaving(true);
    try {
      if (editItem) {
        const updated = await api.updateLearning(editItem.id, { task_summary: form.task_summary, lesson_rule: form.lesson_rule });
        onLearningsChange(learnings.map(l => l.id === editItem.id ? { ...l, ...updated } : l));
        onToast("Memory updated", "success");
      } else {
        const created = await api.createLearning({ project_id: projectId, task_summary: form.task_summary, lesson_rule: form.lesson_rule, team_id: teamId || undefined });
        onLearningsChange([created, ...learnings]);
        onToast("Memory created", "success");
      }
      setAddOpen(false); setEditItem(null); setForm({ task_summary: "", lesson_rule: "" });
    } catch { onToast("Failed to save memory", "error"); }
    finally { setSaving(false); }
  };

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try {
      await api.deleteLearning(id);
      onLearningsChange(learnings.filter(l => l.id !== id));
      onToast("Memory deleted", "success");
    } catch { onToast("Failed to delete memory", "error"); }
    finally { setDeletingId(null); }
  };

  const openEdit = (l: LearningItem) => {
    setEditItem(l);
    setForm({ task_summary: l.task_summary, lesson_rule: l.lesson_rule });
    setAddOpen(true);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "var(--sp-2xl)", overflowY: "auto" }}>
      {/* Header */}
      <div className="flex-between" style={{ marginBottom: "var(--sp-2xl)" }}>
        <div>
          <h2 className="display-md" style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
            <BrainCircuit size={22} color="var(--color-primary)" /> Long-Term Memory
          </h2>
          <p className="body-sm text-mute" style={{ marginTop: "var(--sp-xs)" }}>
            Rules automatically extracted by AutoDream and stored in vector storage.
          </p>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => { setEditItem(null); setForm({ task_summary: "", lesson_rule: "" }); setAddOpen(true); }}>
          <Plus size={13} /> Add Memory
        </button>
      </div>

      {/* Search */}
      <div style={{ position: "relative", marginBottom: "var(--sp-xl)" }}>
        <Search size={14} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--color-mute)" }} />
        <input className="input" style={{ paddingLeft: 36 }} placeholder="Search memories…" value={query} onChange={e => setQuery(e.target.value)} />
        {query && <button onClick={() => setQuery("")} style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "var(--color-mute)" }}><X size={14} /></button>}
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state" style={{ flex: 1 }}>
          <Database size={36} className="empty-state-icon" />
          <h3>{query ? "No matching memories" : "Memory Bank Empty"}</h3>
          <p>{query ? "Try a different search term" : "The AutoDream worker consolidates memories automatically after conversations."}</p>
        </div>
      ) : (
        <div style={{ display: "grid", gap: "var(--sp-lg)", gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))" }}>
          {filtered.map(l => (
            <div key={l.id} className="card" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)", position: "relative" }}>
              <div style={{ position: "absolute", top: 10, right: 10, display: "flex", gap: 4 }}>
                <button className="btn btn-icon-sm btn-ghost" onClick={() => openEdit(l)}><Edit2 size={11} /></button>
                <button className="btn btn-icon-sm btn-ghost" style={{ color: "var(--color-danger)" }}
                  onClick={() => handleDelete(l.id)} disabled={deletingId === l.id}>
                  {deletingId === l.id ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
                </button>
              </div>
              <div className="flex-between">
                <span className="eyebrow" style={{ color: "var(--color-primary-soft)" }}>Lesson</span>
                <span className="caption">{new Date(l.created_at || "").toLocaleDateString()}</span>
              </div>
              <div>
                <h4 className="body-sm-strong text-mute" style={{ marginBottom: "var(--sp-xs)" }}>Context:</h4>
                <p className="body-sm">{l.task_summary}</p>
              </div>
              <div className="green-divider" style={{ opacity: 0.3 }} />
              <div>
                <h4 className="body-sm-strong text-primary-color" style={{ marginBottom: "var(--sp-xs)" }}>Rule Applied:</h4>
                <div className="code-block" style={{ borderLeft: "2px solid var(--color-primary)", background: "rgba(0,217,146,0.04)", fontSize: 12 }}>
                  {l.lesson_rule}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal open={addOpen} onClose={() => { setAddOpen(false); setEditItem(null); }} title={editItem ? "Edit Memory" : "Add Memory"}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-lg)" }}>
          <div className="form-group">
            <label className="form-label">Task Context</label>
            <textarea className="input" style={{ minHeight: 80 }} placeholder="What task or situation generated this lesson?" value={form.task_summary} onChange={e => setForm(f => ({ ...f, task_summary: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Rule / Lesson</label>
            <textarea className="input" style={{ minHeight: 80 }} placeholder="The rule or lesson to apply in future…" value={form.lesson_rule} onChange={e => setForm(f => ({ ...f, lesson_rule: e.target.value }))} />
          </div>
          <div style={{ display: "flex", gap: "var(--sp-md)", justifyContent: "flex-end" }}>
            <button className="btn btn-ghost btn-sm" onClick={() => { setAddOpen(false); setEditItem(null); }}>Cancel</button>
            <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving || !form.task_summary.trim() || !form.lesson_rule.trim()}>
              {saving ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} Save
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
