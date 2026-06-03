"use client";

import React, { useEffect, useState, useCallback } from "react";
import { api } from "@/hooks/useApi";
import { useWebSocket } from "@/hooks/useWebSocket";
import type { TaskItem } from "@/lib/types";
import styles from "./KanbanBoard.module.css";

interface KanbanBoardProps {
  teamId: string | null;
}

const COLUMNS = [
  { id: "todo", label: "Todo" },
  { id: "in_progress", label: "In Progress" },
  { id: "review", label: "Review" },
  { id: "done", label: "Done" },
];

export default function KanbanBoard({ teamId }: KanbanBoardProps) {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const { events } = useWebSocket(teamId);

  const [showForm, setShowForm] = useState(false);
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [newTaskDesc, setNewTaskDesc] = useState("");
  const [newTaskAgent, setNewTaskAgent] = useState("");

  // Fetch initial tasks
  useEffect(() => {
    if (!teamId) {
      setTasks([]);
      setAgents([]);
      return;
    }
    setLoading(true);
    
    Promise.all([
      api.listTasks(teamId),
      api.listAgents(teamId)
    ])
      .then(([tasksData, agentsData]) => {
        setTasks(tasksData);
        setAgents(agentsData);
      })
      .catch((err) => console.error("Failed to load tasks/agents:", err))
      .finally(() => setLoading(false));
  }, [teamId]);

  // Handle WS task_update events
  useEffect(() => {
    if (events.length === 0) return;
    const latest = events[events.length - 1];
    
    if (latest.type === "task_update" && latest.task) {
      const activeTask = latest.task;
      if (latest.action === "created") {
        setTasks((prev) => [activeTask, ...prev.filter(t => t.id !== activeTask.id)]);
      } else if (latest.action === "updated") {
        setTasks((prev) => prev.map((t) => t.id === activeTask.id ? { ...t, ...activeTask } : t));
      } else if (latest.action === "deleted") {
        setTasks((prev) => prev.filter((t) => t.id !== activeTask.id));
      }
    }
  }, [events]);

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTaskTitle.trim() || !teamId) return;

    try {
      await api.createTask({
        team_id: teamId,
        title: newTaskTitle,
        description: newTaskDesc,
        assigned_agent_id: newTaskAgent || undefined,
        created_by: "human"
      });
      setNewTaskTitle("");
      setNewTaskDesc("");
      setNewTaskAgent("");
      setShowForm(false);
    } catch (err) {
      console.error("Failed to create task:", err);
    }
  };

  if (!teamId) {
    return (
      <div className={styles.kanbanEmpty}>
        <p>Select a team to view tasks.</p>
      </div>
    );
  }

  return (
    <div className={styles.kanbanContainer}>
      <div className={styles.kanbanHeader}>
        <h3>Project Board</h3>
        {loading && <span className={styles.loadingSpinner}>Loading...</span>}
      </div>
      <div className={styles.kanbanBoard}>
        {COLUMNS.map((col) => {
          const colTasks = tasks.filter((t) => t.status === col.id);
          return (
            <div key={col.id} className={styles.kanbanColumn}>
              <div className={styles.columnHeader}>
                <span className={styles.columnTitle}>{col.label}</span>
                <span className={styles.columnCount}>{colTasks.length}</span>
              </div>
              <div className={styles.columnBody}>
                {col.id === "todo" && (
                  <div className={styles.addTaskSection}>
                    {!showForm ? (
                      <button className={styles.addTaskBtn} onClick={() => setShowForm(true)}>
                        + Add Task
                      </button>
                    ) : (
                      <form className={styles.addTaskForm} onSubmit={handleCreateTask}>
                        <input
                          type="text"
                          placeholder="Task title..."
                          value={newTaskTitle}
                          onChange={(e) => setNewTaskTitle(e.target.value)}
                          className={styles.taskInput}
                          autoFocus
                        />
                        <textarea
                          placeholder="Description (optional)"
                          value={newTaskDesc}
                          onChange={(e) => setNewTaskDesc(e.target.value)}
                          className={styles.taskTextarea}
                        />
                        <select
                          value={newTaskAgent}
                          onChange={(e) => setNewTaskAgent(e.target.value)}
                          className={styles.taskSelect}
                        >
                          <option value="">Unassigned</option>
                          {agents.map((a) => (
                            <option key={a.id} value={a.id}>
                              Assign: {a.name}
                            </option>
                          ))}
                        </select>
                        <div className={styles.formActions}>
                          <button type="button" onClick={() => setShowForm(false)} className={styles.cancelBtn}>Cancel</button>
                          <button type="submit" disabled={!newTaskTitle.trim()} className={styles.submitBtn}>Save</button>
                        </div>
                      </form>
                    )}
                  </div>
                )}
                {colTasks.length === 0 ? (
                  <div className={styles.emptyCard}>No tasks</div>
                ) : (
                  colTasks.map((task) => (
                    <div key={task.id} className={styles.taskCard}>
                      <div className={styles.taskTitle}>{task.title}</div>
                      {task.description && (
                        <div className={styles.taskDesc}>{task.description}</div>
                      )}
                      <div className={styles.taskFooter}>
                        <span className={`${styles.badge} ${styles[`priority-${task.priority}`]}`}>
                          {task.priority}
                        </span>
                        {task.assigned_agent_id && (
                          <span className={styles.assignee}>👤 Assigned</span>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
