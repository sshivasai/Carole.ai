"use client";
import React, { useState, useCallback } from "react";
import type { TaskItem, AgentConfig } from "@/lib/types";
import { CheckCircle2, Clock, PlayCircle, AlertCircle, Lock, Plus, X, Loader2, FileText, ListTodo, ChevronDown, Check } from "lucide-react";
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
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "var(--sp-xl)" }}>
        <div>
          <h2 className="display-md">Task Board</h2>
          <p className="body-sm text-mute">Drag cards to change status · click + to add tasks</p>
        </div>
        
        {teamId && <KanbanSyncSchedule teamId={teamId} agents={agents} />}
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

function KanbanSyncSchedule({ teamId, agents }: { teamId: string, agents: AgentConfig[] }) {
  const [loading, setLoading] = useState(true);
  const [schedule, setSchedule] = useState("off");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const menuRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    api.listScheduledTasks(teamId).then(tasks => {
      const syncTask = tasks.find(t => t.name === "kanban_auto_sync");
      if (syncTask) {
        setTaskId(syncTask.id);
        if (syncTask.cron_expression === "*/5 * * * *") setSchedule("5m");
        else if (syncTask.cron_expression === "*/10 * * * *") setSchedule("10m");
        else if (syncTask.cron_expression === "*/30 * * * *") setSchedule("30m");
        else if (syncTask.cron_expression === "0 * * * *") setSchedule("1h");
        else setSchedule("on");
      } else {
        setSchedule("off");
        setTaskId(null);
      }
    }).catch(console.error).finally(() => setLoading(false));
  }, [teamId]);

  // Click outside to close dropdown
  React.useEffect(() => {
    const handleDocClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    if (menuOpen) {
      document.addEventListener("mousedown", handleDocClick);
    }
    return () => document.removeEventListener("mousedown", handleDocClick);
  }, [menuOpen]);

  const selectOption = async (val: string) => {
    setSchedule(val);
    setMenuOpen(false);
    setSaving(true);
    try {
      if (val === "off") {
        if (taskId) {
          await api.deleteScheduledTask(taskId).catch(console.error);
          setTaskId(null);
        }
        return;
      }

      const orchestrator = agents.find(a => a.role?.toLowerCase().includes("orchestrator") || a.role?.toLowerCase().includes("coordinator")) || agents[0];
      
      if (!orchestrator) {
        alert("No agents in the team to run the sync!");
        setSchedule("off");
        return;
      }

      let cron = "*/10 * * * *";
      if (val === "5m") cron = "*/5 * * * *";
      else if (val === "30m") cron = "*/30 * * * *";
      else if (val === "1h") cron = "0 * * * *";

      const prompt = "[SYSTEM CRON] Please review the Kanban board for pending unassigned tasks or stale tasks, and handle them by assigning or commenting.";

      if (taskId) {
        await api.updateScheduledTask(taskId, { cron_expression: cron });
      } else {
        const newTask = await api.createScheduledTask(teamId, {
          name: "kanban_auto_sync",
          agent_id: orchestrator.id,
          cron_expression: cron,
          prompt: prompt
        });
        setTaskId(newTask.id);
      }
    } catch (err) {
      console.error(err);
      setSchedule("off");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return null;

  const OPTIONS = [
    { value: "off", label: "Off", desc: "Manual sync only" },
    { value: "5m", label: "Every 5 mins", desc: "Fast periodic review" },
    { value: "10m", label: "Every 10 mins", desc: "Standard recommended" },
    { value: "30m", label: "Every 30 mins", desc: "Balanced cadence" },
    { value: "1h", label: "Every 1 hour", desc: "Low token usage" },
  ];

  const currentOption = OPTIONS.find(o => o.value === schedule) || OPTIONS[0];
  const isEnabled = schedule !== "off";

  return (
    <div style={{ position: "relative", display: "inline-block" }} ref={menuRef}>
      <style>{`
        @keyframes syncPulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.2); opacity: 0.7; }
        }
      `}</style>
      <button
        onClick={() => setMenuOpen(o => !o)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          background: menuOpen ? "rgba(99, 102, 241, 0.12)" : "var(--color-canvas-raised, #111827)",
          border: `1px solid ${menuOpen ? "var(--color-primary, #6366f1)" : isEnabled ? "rgba(16, 185, 129, 0.35)" : "var(--color-hairline, #2a2a3f)"}`,
          padding: "5px 10px",
          borderRadius: "var(--radius-sm, 6px)",
          cursor: "pointer",
          color: "var(--color-ink, #f9fafb)",
          fontSize: 11.5,
          fontWeight: 500,
          boxShadow: isEnabled ? "0 0 10px rgba(16, 185, 129, 0.12)" : "var(--shadow-clay-sm, 0 1px 3px rgba(0,0,0,0.1))",
          transition: "all 0.15s ease",
        }}
        title="Configure automated background orchestrator check on task board"
      >
        {saving ? (
          <Loader2 size={13} className="animate-spin text-mute" />
        ) : (
          <Clock size={13} style={{ color: isEnabled ? "#10b981" : "var(--color-mute, #9ca3af)" }} />
        )}
        <span style={{ color: "var(--color-mute, #9ca3af)" }}>Auto-Sync:</span>
        <span style={{ fontWeight: 600, color: isEnabled ? "#10b981" : "var(--color-ink, #f9fafb)", display: "flex", alignItems: "center", gap: 4 }}>
          {isEnabled && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#10b981", animation: "syncPulse 2s infinite" }} />}
          {currentOption.label}
        </span>
        <ChevronDown size={12} style={{ color: "var(--color-mute, #9ca3af)", transform: menuOpen ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.15s ease" }} />
      </button>

      {menuOpen && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            right: 0,
            width: 220,
            background: "var(--bg-glass-card, #131326)",
            backdropFilter: "blur(20px)",
            WebkitBackdropFilter: "blur(20px)",
            border: "1px solid var(--border-glass, rgba(255,255,255,0.14))",
            borderRadius: "var(--radius-md, 8px)",
            boxShadow: "0 12px 32px rgba(0,0,0,0.45)",
            padding: 5,
            zIndex: 1000,
            display: "flex",
            flexDirection: "column",
            gap: 2,
            animation: "popoverEnter 0.18s cubic-bezier(0.16, 1, 0.3, 1)",
          }}
        >
          <div style={{ padding: "4px 8px 6px 8px", borderBottom: "1px solid var(--color-hairline, #2a2a3f)", marginBottom: 2 }}>
            <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "var(--color-mute, #9ca3af)", letterSpacing: "0.04em" }}>
              Kanban Auto-Review
            </div>
            <div style={{ fontSize: 9.5, color: "var(--color-mute, #9ca3af)" }}>
              Orchestrator reviews tasks on interval
            </div>
          </div>

          {OPTIONS.map(opt => {
            const isSelected = opt.value === schedule;
            return (
              <button
                key={opt.value}
                onClick={() => selectOption(opt.value)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "6px 8px",
                  borderRadius: 5,
                  background: isSelected ? "rgba(99, 102, 241, 0.12)" : "transparent",
                  border: isSelected ? "1px solid rgba(99, 102, 241, 0.25)" : "1px solid transparent",
                  cursor: "pointer",
                  color: isSelected ? "var(--color-primary, #6366f1)" : "var(--color-ink, #f9fafb)",
                  textAlign: "left",
                  fontSize: 11.5,
                  transition: "background 0.12s ease",
                }}
                onMouseEnter={e => {
                  if (!isSelected) (e.currentTarget as HTMLElement).style.background = "rgba(255, 255, 255, 0.05)";
                }}
                onMouseLeave={e => {
                  if (!isSelected) (e.currentTarget as HTMLElement).style.background = "transparent";
                }}
              >
                <div>
                  <div style={{ fontWeight: isSelected ? 700 : 500 }}>
                    {opt.label}
                  </div>
                  <div style={{ fontSize: 9.5, color: "var(--color-mute, #9ca3af)" }}>
                    {opt.desc}
                  </div>
                </div>
                {isSelected && <Check size={13} style={{ color: "var(--color-primary, #6366f1)", flexShrink: 0 }} />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
