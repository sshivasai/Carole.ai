"use client";
import React, { useState, useCallback } from "react";
import type { TaskItem, AgentConfig } from "@/lib/types";
import { CheckCircle2, Clock, PlayCircle, AlertCircle, Lock, Plus, X, Loader2 } from "lucide-react";
import { api } from "@/hooks/useApi";

interface Props { tasks: TaskItem[]; agents: AgentConfig[]; teamId: string | null; onTasksChange: (tasks: TaskItem[]) => void; }

const COLS = [
  { id: "todo",        label: "To Do",       Icon: Clock,         color: "var(--color-mute)" },
  { id: "in_progress", label: "In Progress",  Icon: PlayCircle,    color: "var(--color-info)" },
  { id: "review",      label: "Review",       Icon: AlertCircle,   color: "var(--accent-orange)" },
  { id: "done",        label: "Done",         Icon: CheckCircle2,  color: "var(--color-primary)" },
  { id: "blocked",     label: "Blocked",      Icon: Lock,          color: "var(--color-danger)" },
];

const PRIORITY_BADGE: Record<string, string> = {
  critical: "badge-red", high: "badge-red", medium: "badge-yellow", low: "badge-blue",
};

function AddTaskForm({ colId, teamId, agents, onAdded, onCancel }: {
  colId: string; teamId: string; agents: AgentConfig[]; onAdded: (t: TaskItem) => void; onCancel: () => void;
}) {
  const [title, setTitle] = useState("");
  const [desc,  setDesc]  = useState("");
  const [prio,  setPrio]  = useState("medium");
  const [agId,  setAgId]  = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!title.trim()) return;
    setLoading(true);
    try {
      const t = await api.createTask({ team_id: teamId, title: title.trim(), description: desc.trim() || undefined, status: colId, priority: prio, assigned_agent_id: agId || undefined });
      onAdded(t);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  return (
    <div style={{ background: "var(--color-canvas-raised)", border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-md)", padding: "var(--sp-md)", display: "flex", flexDirection: "column", gap: "var(--sp-sm)" }}>
      <input className="input" style={{ minHeight: 32, fontSize: 13 }} placeholder="Task title…" value={title} onChange={e => setTitle(e.target.value)} autoFocus />
      <textarea className="input" style={{ minHeight: 56, fontSize: 12, resize: "none" }} placeholder="Description (optional)" value={desc} onChange={e => setDesc(e.target.value)} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--sp-sm)" }}>
        <select className="input" style={{ minHeight: 32, fontSize: 12 }} value={prio} onChange={e => setPrio(e.target.value)}>
          {["low","medium","high","critical"].map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <select className="input" style={{ minHeight: 32, fontSize: 12 }} value={agId} onChange={e => setAgId(e.target.value)}>
          <option value="">Unassigned</option>
          {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </div>
      <div style={{ display: "flex", gap: "var(--sp-sm)" }}>
        <button className="btn btn-primary btn-sm" onClick={submit} disabled={loading || !title.trim()} style={{ flex: 1 }}>
          {loading ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Add Task
        </button>
        <button className="btn btn-ghost btn-sm" onClick={onCancel}><X size={12} /></button>
      </div>
    </div>
  );
}

export default function KanbanBoard({ tasks, agents, teamId, onTasksChange }: Props) {
  const [addingCol, setAddingCol] = useState<string | null>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);

  const getAgentName = (id?: string) => agents.find(a => a.id === id)?.name || "Unassigned";

  const handleDrop = useCallback(async (colId: string, e: React.DragEvent) => {
    e.preventDefault();
    if (!draggingId) return;
    setDraggingId(null);
    const task = tasks.find(t => t.id === draggingId);
    if (!task || task.status === colId) return;
    onTasksChange(tasks.map(t => t.id === draggingId ? { ...t, status: colId } : t));
    try { await api.updateTask(draggingId, { status: colId }); }
    catch { onTasksChange(tasks); /* revert */ }
  }, [draggingId, tasks, onTasksChange]);

  const handleTaskAdded = (colId: string, t: TaskItem) => {
    onTasksChange([t, ...tasks]);
    setAddingCol(null);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "var(--sp-2xl)", overflow: "hidden" }}>
      <header style={{ marginBottom: "var(--sp-xl)" }}>
        <h2 className="display-md">Task Board</h2>
        <p className="body-sm text-mute">Drag cards to change status · click + to add tasks</p>
      </header>

      <div style={{ display: "flex", gap: "var(--sp-lg)", flex: 1, overflowX: "auto", paddingBottom: "var(--sp-sm)" }}>
        {COLS.map(col => {
          const colTasks = tasks.filter(t => t.status === col.id);
          const isDropTarget = true;

          return (
            <div key={col.id}
              onDragOver={e => { e.preventDefault(); }}
              onDrop={e => handleDrop(col.id, e)}
              style={{
                flex: "1 0 260px", display: "flex", flexDirection: "column",
                background: "var(--color-canvas-soft)", border: "1px solid var(--color-hairline)",
                borderRadius: "var(--radius-md)", overflow: "hidden",
                transition: "border-color var(--t-fast)",
              }}>
              {/* Header */}
              <div style={{ padding: "var(--sp-md) var(--sp-lg)", borderBottom: "1px solid var(--color-hairline)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                  <col.Icon size={14} color={col.color} />
                  <span className="label" style={{ color: "var(--color-ink)" }}>{col.label}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                  <span className="pill pill-idle" style={{ fontSize: 10, padding: "1px 7px" }}>{colTasks.length}</span>
                  {teamId && (
                    <button className="btn btn-icon-sm btn-ghost" onClick={() => setAddingCol(addingCol === col.id ? null : col.id)} title="Add task">
                      <Plus size={12} />
                    </button>
                  )}
                </div>
              </div>

              {/* Body */}
              <div style={{ padding: "var(--sp-sm)", display: "flex", flexDirection: "column", gap: "var(--sp-sm)", flex: 1, overflowY: "auto" }}>
                {addingCol === col.id && teamId && (
                  <AddTaskForm colId={col.id} teamId={teamId} agents={agents}
                    onAdded={t => handleTaskAdded(col.id, t)}
                    onCancel={() => setAddingCol(null)} />
                )}
                {colTasks.map(task => (
                  <div key={task.id}
                    draggable onDragStart={() => setDraggingId(task.id)}
                    style={{
                      background: "var(--color-canvas-raised)", border: "1px solid var(--color-hairline)",
                      borderRadius: "var(--radius-sm)", padding: "var(--sp-md)",
                      cursor: "grab", display: "flex", flexDirection: "column", gap: "var(--sp-sm)",
                      transition: "transform var(--t-fast), border-color var(--t-fast)",
                      opacity: draggingId === task.id ? 0.5 : 1,
                    }}
                    onMouseEnter={e => (e.currentTarget.style.borderColor = "rgba(255,255,255,0.12)")}
                    onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--color-hairline)")}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                      <span className={`badge ${PRIORITY_BADGE[task.priority] || "badge-gray"}`}>{task.priority}</span>
                    </div>
                    <span className="body-sm-strong">{task.title}</span>
                    {task.description && (
                      <p className="caption" style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                        {task.description}
                      </p>
                    )}
                    <div className="divider-dashed" style={{ margin: "2px 0" }} />
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--color-mute)" }}>
                      <span>{getAgentName(task.assigned_agent_id)}</span>
                    </div>
                  </div>
                ))}
                {colTasks.length === 0 && addingCol !== col.id && (
                  <div style={{ textAlign: "center", padding: "var(--sp-xl) 0", color: "var(--color-mute)", fontSize: 12, border: "1px dashed var(--color-hairline)", borderRadius: "var(--radius-sm)", margin: "var(--sp-sm)" }}>
                    Drop tasks here
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
