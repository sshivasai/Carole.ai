"use client";
import React, { useState, useCallback } from "react";
import type { TaskItem, AgentConfig } from "@/lib/types";
import { CheckCircle2, Clock, PlayCircle, AlertCircle, Lock, Plus, X, Loader2, FileText, ListTodo } from "lucide-react";
import { api } from "@/hooks/useApi";
import TaskDetailModal from "./TaskDetailModal";
import ImplementationPlanModal from "./ImplementationPlanModal";

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
  const [selectedTask, setSelectedTask] = useState<TaskItem | null>(null);
  const [planTaskId, setPlanTaskId] = useState<string | null>(null);
  const [planTaskTitle, setPlanTaskTitle] = useState<string | undefined>(undefined);

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

          return (
            <div key={col.id}
              onDragOver={e => { e.preventDefault(); }}
              onDrop={e => handleDrop(col.id, e)}
              style={{
                flex: "1 0 280px", display: "flex", flexDirection: "column",
                background: "var(--bg-glass-card)", backdropFilter: "var(--blur-md)",
                WebkitBackdropFilter: "var(--blur-md)", border: "1px solid var(--border-glass)",
                borderRadius: "var(--radius-md)", overflow: "hidden",
                boxShadow: "var(--shadow-clay-sm)",
                transition: "border-color var(--t-fast), box-shadow var(--t-fast)",
              }}>
              {/* Header */}
              <div style={{ padding: "var(--sp-md) var(--sp-lg)", borderBottom: "1px solid var(--border-glass)", background: "rgba(255,255,255,0.02)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                  <div style={{ width: 22, height: 22, borderRadius: "50%", background: "var(--color-canvas)", display: "flex", alignItems: "center", justifyContent: "center", border: `1px solid ${col.color}` }}>
                    <col.Icon size={12} color={col.color} />
                  </div>
                  <span className="label" style={{ color: "var(--color-ink)", fontWeight: 600 }}>{col.label}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                  <span className="pill" style={{ fontSize: 10, padding: "1px 7px", background: "var(--color-canvas)", border: "1px solid var(--color-hairline)", fontWeight: 700 }}>
                    {colTasks.length}
                  </span>
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
                {colTasks.map(task => {
                  const assignedAgent = agents.find(a => a.id === task.assigned_agent_id);

                  return (
                    <div key={task.id}
                      draggable onDragStart={() => setDraggingId(task.id)}
                      onClick={() => setSelectedTask(task)}
                      className="card"
                      style={{
                        padding: "var(--sp-md)",
                        cursor: "grab", display: "flex", flexDirection: "column", gap: "var(--sp-sm)",
                        transition: "all var(--t-fast)",
                        opacity: draggingId === task.id ? 0.4 : 1,
                        transform: draggingId === task.id ? "scale(0.98)" : "none",
                        border: "1px solid var(--border-glass)",
                        background: "var(--color-canvas-raised)",
                      }}
                      onMouseEnter={e => {
                        e.currentTarget.style.borderColor = "var(--color-primary-soft)";
                        e.currentTarget.style.transform = "translateY(-2px)";
                      }}
                      onMouseLeave={e => {
                        e.currentTarget.style.borderColor = "var(--border-glass)";
                        e.currentTarget.style.transform = "none";
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                        <span className={`badge ${PRIORITY_BADGE[task.priority] || "badge-gray"}`} style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: 0.3 }}>
                          {task.priority}
                        </span>
                        {task.blocked_by_task_id && (
                          <span className="badge badge-warn" style={{ fontSize: 9, display: "inline-flex", alignItems: "center", gap: 3 }}>
                            <Lock size={9} /> Blocked
                          </span>
                        )}
                      </div>
                      <span className="body-sm-strong" style={{ fontSize: 12, lineHeight: 1.4, color: "var(--color-ink)" }}>{task.title}</span>
                      {task.description && (
                        <p className="caption" style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden", color: "var(--color-mute)", margin: 0, fontSize: 11 }}>
                          {task.description}
                        </p>
                      )}
                      {/* Plan status mini-badge */}
                      {task.plan_status && task.plan_status !== "draft" && (
                        <button
                          className="btn btn-ghost"
                          title="View implementation plan"
                          style={{
                            display: "inline-flex", alignItems: "center", gap: 4,
                            fontSize: 10, padding: "2px 7px", borderRadius: 999,
                            background: task.plan_status === "approved" ? "#10b98122" :
                              task.plan_status === "awaiting_approval" ? "#f59e0b22" : "#ef444422",
                            color: task.plan_status === "approved" ? "#10b981" :
                              task.plan_status === "awaiting_approval" ? "#f59e0b" : "#ef4444",
                            border: "none",
                            alignSelf: "flex-start",
                          }}
                          onClick={e => {
                            e.stopPropagation();
                            setPlanTaskId(task.id);
                            setPlanTaskTitle(task.title);
                          }}
                        >
                          <FileText size={9} />
                          {task.plan_status === "approved" ? "Plan Approved" :
                            task.plan_status === "awaiting_approval" ? "Plan — Review" :
                            "Plan — Revision"}
                        </button>
                      )}
                      
                      {/* Todos status mini-badge */}
                      {task.todo_list && task.todo_list.length > 0 && (
                        <div style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, padding: "2px 7px", borderRadius: 999, background: "rgba(255,255,255,0.05)", color: "var(--color-mute)", border: "1px solid var(--border-glass)", alignSelf: "flex-start", marginTop: 2 }}>
                          <ListTodo size={9} />
                          {task.todo_list.filter((t: any) => t.done).length}/{task.todo_list.length} Todos
                        </div>
                      )}
                      <div className="divider-dashed" style={{ margin: "2px 0" }} />
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 10, color: "var(--color-mute)" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                          {assignedAgent ? (
                            <>
                              <span style={{ fontSize: 10, color: "var(--color-body)", fontWeight: 500 }}>{assignedAgent.name}</span>
                            </>
                          ) : (
                            <span style={{ fontStyle: "italic", opacity: 0.7 }}>Unassigned</span>
                          )}
                        </div>
                        {task.created_at && (
                          <span className="caption" style={{ fontSize: 9 }}>{new Date(task.created_at).toLocaleDateString([], { month: "short", day: "numeric" })}</span>
                        )}
                      </div>
                    </div>
                  );
                })}
                {colTasks.length === 0 && addingCol !== col.id && (
                  <div style={{ textAlign: "center", padding: "var(--sp-xl) 0", color: "var(--color-mute)", fontSize: 11, border: "1px dashed var(--border-glass)", borderRadius: "var(--radius-sm)", margin: "var(--sp-sm)" }}>
                    Drop tasks here
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <TaskDetailModal 
        task={selectedTask} 
        agents={agents} 
        allTasks={tasks}
        onClose={() => setSelectedTask(null)} 
        onUpdate={(t) => {
          onTasksChange(tasks.map(task => task.id === t.id ? t : task));
          setSelectedTask(t);
        }}
        onDelete={(taskId) => {
          onTasksChange(tasks.filter(t => t.id !== taskId));
          setSelectedTask(null);
        }}
      />

      {/* Implementation Plan Modal */}
      <ImplementationPlanModal
        taskId={planTaskId}
        taskTitle={planTaskTitle}
        onClose={() => { setPlanTaskId(null); setPlanTaskTitle(undefined); }}
        onPlanAction={() => {
          // Optionally refresh tasks from parent — for now just close
        }}
      />
    </div>
  );
}
