"use client";
import React from "react";
import type { TaskItem, AgentConfig } from "@/lib/types";
import { CheckCircle2, Clock, PlayCircle, AlertCircle } from "lucide-react";

interface Props {
  tasks: TaskItem[];
  agents: AgentConfig[];
  teamId: string | null;
}

const COLUMNS = [
  { id: "todo", label: "To Do", Icon: Clock, color: "var(--color-mute)" },
  { id: "in_progress", label: "In Progress", Icon: PlayCircle, color: "var(--accent-blue)" },
  { id: "review", label: "Review", Icon: AlertCircle, color: "var(--accent-orange)" },
  { id: "done", label: "Done", Icon: CheckCircle2, color: "var(--color-primary)" },
];

export default function KanbanBoard({ tasks, agents }: Props) {
  const getAgentName = (id?: string) => agents.find(a => a.id === id)?.name || "Unassigned";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "var(--sp-2xl)", overflow: "hidden" }}>
      <header style={{ marginBottom: "var(--sp-2xl)" }}>
        <h2 className="display-lg">Task Board</h2>
        <p className="body-md" style={{ color: "var(--color-mute)" }}>Real-time coordination of agent tasks.</p>
      </header>

      <div style={{ display: "flex", gap: "var(--sp-xl)", flex: 1, overflowX: "auto", paddingBottom: "var(--sp-sm)" }}>
        {COLUMNS.map(col => {
          const columnTasks = tasks.filter(t => t.status === col.id);
          
          return (
            <div key={col.id} style={{ flex: "1 0 300px", display: "flex", flexDirection: "column", background: "var(--color-canvas-soft)", border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-md)" }}>
              {/* Column Header */}
              <div style={{ padding: "var(--sp-lg)", borderBottom: "1px solid var(--color-hairline)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", color: col.color }}>
                  <col.Icon size={16} />
                  <span className="eyebrow" style={{ color: "var(--color-ink)", letterSpacing: "1px" }}>{col.label}</span>
                </div>
                <span className="pill pill-idle" style={{ zoom: 0.8 }}>{columnTasks.length}</span>
              </div>

              {/* Column Body */}
              <div style={{ padding: "var(--sp-md)", display: "flex", flexDirection: "column", gap: "var(--sp-md)", flex: 1, overflowY: "auto" }}>
                {columnTasks.map(task => (
                  <div key={task.id} className="card" style={{ padding: "var(--sp-lg)", display: "flex", flexDirection: "column", gap: "var(--sp-sm)", cursor: "pointer" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                      <span className={`badge ${task.priority === "high" ? "badge-red" : task.priority === "medium" ? "badge-yellow" : "badge-blue"}`}>
                        {task.priority}
                      </span>
                    </div>
                    <h4 className="body-sm-strong">{task.title}</h4>
                    {task.description && (
                      <p className="caption" style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                        {task.description}
                      </p>
                    )}
                    <div className="divider-dashed" style={{ margin: "var(--sp-sm) 0" }} />
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "11px", color: "var(--color-mute)" }}>
                      <span>Agent:</span>
                      <span style={{ color: "var(--color-ink)" }}>{getAgentName(task.assigned_agent_id)}</span>
                    </div>
                  </div>
                ))}
                {columnTasks.length === 0 && (
                  <div style={{ textAlign: "center", padding: "var(--sp-2xl) 0", color: "var(--color-hairline-soft)" }}>
                    <span className="caption">No tasks</span>
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
