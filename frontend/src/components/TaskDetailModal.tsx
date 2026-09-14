"use client";
import React, { useState, useEffect } from "react";
import type { TaskItem, AgentConfig, TaskComment, TaskActivity } from "@/lib/types";
import { AlignLeft, MessageSquare, Trash2, Edit2, Check, Loader2, FileText, Eye, EyeOff, History, AlertCircle } from "lucide-react";
import { api } from "@/hooks/useApi";
import Modal from "./Modal";
import { useAuth } from "@/hooks/useAuth";
import ImplementationPlanModal from "./ImplementationPlanModal";

interface Props {
  task: TaskItem | null;
  agents: AgentConfig[];
  allTasks?: TaskItem[];
  onClose: () => void;
  onUpdate: (task: TaskItem) => void;
  onDelete: (taskId: string) => void;
  liveComment?: TaskComment | null;
}

const PRIORITY_BADGE: Record<string, string> = {
  critical: "badge-red", high: "badge-red", medium: "badge-yellow", low: "badge-blue",
};

export default function TaskDetailModal({ task, agents, allTasks = [], onClose, onUpdate, onDelete, liveComment }: Props) {
  const { user } = useAuth();
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editPrio, setEditPrio] = useState("medium");
  const [editAgId, setEditAgId] = useState("");
  const [editStatus, setEditStatus] = useState("");
  const [editBlockedBy, setEditBlockedBy] = useState("");

  const [comments, setComments] = useState<TaskComment[]>([]);
  const [newComment, setNewComment] = useState("");
  const [loadingComments, setLoadingComments] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [showPlanModal, setShowPlanModal] = useState(false);

  // Production Kanban features
  const [activeTab, setActiveTab] = useState<"details" | "activities">("details");
  const [activities, setActivities] = useState<TaskActivity[]>([]);
  const [loadingActivities, setLoadingActivities] = useState(false);
  const [isWatching, setIsWatching] = useState(false);
  const [watcherCount, setWatcherCount] = useState(0);
  const [conflictError, setConflictError] = useState<string | null>(null);

  useEffect(() => {
    if (task) {
      setEditTitle(task.title);
      setEditDesc(task.description || "");
      setEditPrio(task.priority);
      setEditAgId(task.assigned_agent_id || "");
      setEditStatus(task.status);
      setEditBlockedBy(task.blocked_by_task_id || "");
      setIsEditing(false);
      setConfirmDelete(false);
      setConflictError(null);
      loadComments(task.id);
      loadActivities(task.id);
      loadWatchers(task.id);
      api.markTaskRead(task.id).catch(() => {});
    }
  }, [task]);

  useEffect(() => {
    if (!task || !liveComment || liveComment.task_id !== task.id) return;
    setComments(prev => prev.some(c => c.id === liveComment.id) ? prev : [...prev, liveComment]);
  }, [liveComment, task]);

  const loadComments = async (taskId: string) => {
    setLoadingComments(true);
    try {
      const data = await api.getTaskComments(taskId);
      setComments(data);
    } catch { /* ignore */ }
    finally { setLoadingComments(false); }
  };

  const loadActivities = async (taskId: string) => {
    setLoadingActivities(true);
    try {
      const data = await api.getTaskActivities(taskId);
      setActivities(data);
    } catch { /* ignore */ }
    finally { setLoadingActivities(false); }
  };

  const loadWatchers = async (taskId: string) => {
    try {
      const watchers = await api.getTaskWatchers(taskId);
      setWatcherCount(watchers.length);
      const currentUserId = user?.id;
      setIsWatching(watchers.some((w: any) => w.user_id === currentUserId));
    } catch { /* ignore */ }
  };

  const handleToggleWatch = async () => {
    if (!task) return;
    try {
      if (isWatching) {
        await api.unwatchTask(task.id);
        setIsWatching(false);
        setWatcherCount(prev => Math.max(0, prev - 1));
      } else {
        await api.watchTask(task.id);
        setIsWatching(true);
        setWatcherCount(prev => prev + 1);
      }
    } catch { /* ignore */ }
  };

  const handleSave = async () => {
    if (!task || !editTitle.trim()) return;
    setSaving(true);
    setConflictError(null);
    try {
      const updates = {
        title: editTitle.trim(),
        description: editDesc.trim(),
        priority: editPrio,
        assigned_agent_id: editAgId || null,
        status: editStatus,
        blocked_by_task_id: editBlockedBy || undefined,
        expected_revision: task.revision || 1,
      };
      const res = await api.updateTask(task.id, updates);
      onUpdate({ ...task, ...updates, revision: (task.revision || 1) + 1 });
      setIsEditing(false);
      loadActivities(task.id);
    } catch (err: any) {
      if (err?.status === 409 || String(err?.message || "").includes("409") || String(err?.message || "").includes("Conflict")) {
        setConflictError("Revision Conflict (409): Another collaborator or agent updated this task. Please reload to review the latest changes before saving.");
      } else {
        setConflictError(err?.message || "Failed to update task.");
      }
    }
    finally { setSaving(false); }
  };

  const handleDelete = async () => {
    if (!task) return;
    setSaving(true);
    try {
      await api.deleteTask(task.id);
      onDelete(task.id);
      onClose();
    } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  const handlePostComment = async () => {
    if (!task || !newComment.trim() || !user) return;
    setSaving(true);
    try {
      const comment = await api.addTaskComment(task.id, newComment.trim());
      setComments(prev => [...prev, comment]);
      setNewComment("");
      loadActivities(task.id);
    } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  if (!task) return null;
  const getAgentName = (id?: string | null) => agents.find(a => a.id === id)?.name || "Unassigned";

  return (
    <>
    <Modal open={!!task} onClose={onClose} title={isEditing ? "Edit Task" : task.title} maxWidth={720}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)", maxHeight: "75vh", overflowY: "auto", paddingRight: "var(--sp-sm)" }}>
        
        {/* Conflict Warning */}
        {conflictError && (
          <div style={{
            display: "flex", alignItems: "center", gap: "var(--sp-sm)",
            padding: "var(--sp-sm) var(--sp-md)", background: "#ef44441a",
            border: "1px solid #ef444444", borderRadius: "var(--radius-sm)", color: "#ef4444",
            fontSize: 12,
          }}>
            <AlertCircle size={15} style={{ flexShrink: 0 }} />
            <div style={{ flex: 1 }}>{conflictError}</div>
          </div>
        )}

        {/* Header / Edit Mode */}
        {isEditing ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
            <input className="input" value={editTitle} onChange={e => setEditTitle(e.target.value)} placeholder="Task Title" />
            <div style={{ display: "flex", gap: "var(--sp-sm)", flexWrap: "wrap" }}>
              <select className="input" style={{ width: 120 }} value={editStatus} onChange={e => setEditStatus(e.target.value)}>
                {["todo", "in_progress", "review", "done", "blocked"].map(s => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
              </select>
              <select className="input" style={{ width: 120 }} value={editPrio} onChange={e => setEditPrio(e.target.value)}>
                {["low", "medium", "high", "critical"].map(p => <option key={p} value={p}>{p}</option>)}
              </select>
              <select className="input" style={{ width: 160 }} value={editAgId} onChange={e => setEditAgId(e.target.value)}>
                <option value="">Unassigned</option>
                {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
              <select className="input" style={{ width: 220 }} value={editBlockedBy} onChange={e => setEditBlockedBy(e.target.value)}>
                <option value="">Not Blocked</option>
                {allTasks.filter(t => t.id !== task.id).map(t => (
                  <option key={t.id} value={t.id}>Blocked by: {t.title}</option>
                ))}
              </select>
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", gap: "var(--sp-sm)", alignItems: "center", flexWrap: "wrap" }}>
            <span className={`badge ${PRIORITY_BADGE[task.priority] || "badge-gray"}`}>{task.priority} priority</span>
            <span className="badge badge-gray">{task.status.replace("_", " ")}</span>
            <span className="badge badge-gray" style={{ fontSize: 10 }}>rev {task.revision || 1}</span>
            {task.blocked_by_task_id && (
              <span className="badge badge-warn">
                🔴 Blocked by: {allTasks.find(t => t.id === task.blocked_by_task_id)?.title || task.blocked_by_task_id.substring(0, 8)}
              </span>
            )}
            <button
              className={`btn btn-xs ${isWatching ? "btn-secondary" : "btn-ghost"}`}
              style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 8px", fontSize: 11 }}
              onClick={handleToggleWatch}
              title={isWatching ? "You are watching this task. Click to stop watching." : "Watch task for updates"}
            >
              {isWatching ? <EyeOff size={12} /> : <Eye size={12} />}
              <span>{watcherCount} {watcherCount === 1 ? "Watcher" : "Watchers"}</span>
            </button>
            <span className="badge badge-gray" style={{ marginLeft: "auto" }}>Assigned to: {getAgentName(task.assigned_agent_id)}</span>
            <button className="btn btn-icon-sm btn-ghost" onClick={() => setIsEditing(true)} title="Edit Task"><Edit2 size={14} /></button>
          </div>
        )}

        {/* Tab Navigation */}
        <div style={{ display: "flex", gap: "var(--sp-xs)", borderBottom: "1px solid var(--color-hairline)", paddingBottom: "var(--sp-xs)" }}>
          <button
            className={`btn btn-sm ${activeTab === 'details' ? 'btn-secondary' : 'btn-ghost'}`}
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
            onClick={() => setActiveTab('details')}
          >
            <AlignLeft size={13} /> Details & Comments
          </button>
          <button
            className={`btn btn-sm ${activeTab === 'activities' ? 'btn-secondary' : 'btn-ghost'}`}
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
            onClick={() => setActiveTab('activities')}
          >
            <History size={13} /> Audit Trail ({activities.length})
          </button>
        </div>

        {activeTab === "activities" ? (
          /* Activities Audit Trail Tab */
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-sm)" }}>
            <div className="caption text-mute" style={{ padding: "var(--sp-xs) 0", fontStyle: "italic" }}>
              Persistent audit trail of task lifecycle events. These logs are stored for human review and never injected into model context windows.
            </div>
            {loadingActivities ? (
              <Loader2 size={16} className="animate-spin text-mute" />
            ) : activities.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-xs)" }}>
                {activities.map(act => (
                  <div key={act.id} style={{
                    display: "flex", flexDirection: "column", gap: 2,
                    background: "var(--color-canvas-soft)", padding: "var(--sp-xs) var(--sp-sm)",
                    borderRadius: "var(--radius-sm)", border: "1px solid var(--color-hairline)",
                    fontSize: 12,
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontWeight: 600, color: "var(--color-ink)" }}>{act.actor_name}</span>
                      <span className="badge badge-gray" style={{ fontSize: 9 }}>{act.activity_type}</span>
                    </div>
                    <div style={{ color: "var(--color-body)" }}>{act.details}</div>
                    {act.created_at && (
                      <span className="caption text-mute" style={{ fontSize: 10, alignSelf: "flex-end" }}>
                        {new Date(act.created_at).toLocaleString()}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="body-sm text-mute">No activity recorded yet.</div>
            )}
          </div>
        ) : (
          /* Details & Comments Tab */
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-lg)" }}>
            {/* Description */}
            <div>
              <h4 className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "var(--sp-xs)", marginBottom: "var(--sp-sm)" }}>
                <AlignLeft size={14} /> Description
              </h4>
              {isEditing ? (
                <textarea className="input" style={{ minHeight: 100, resize: "vertical" }} value={editDesc} onChange={e => setEditDesc(e.target.value)} placeholder="Task description..." />
              ) : (
                <div className="body-md" style={{ color: "var(--color-body)", whiteSpace: "pre-wrap", background: "var(--color-canvas-soft)", padding: "var(--sp-md)", borderRadius: "var(--radius-sm)", border: "1px solid var(--color-hairline)" }}>
                  {task.description || <span className="text-mute italic">No description provided.</span>}
                </div>
              )}
            </div>

            {/* Save / Delete Controls */}
            {isEditing && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                {confirmDelete ? (
                  <div style={{ display: "flex", gap: "var(--sp-sm)", alignItems: "center" }}>
                    <span className="body-sm-strong text-danger">Are you sure?</span>
                    <button className="btn btn-sm btn-danger" onClick={handleDelete} disabled={saving}>Yes, Delete</button>
                    <button className="btn btn-sm btn-ghost" onClick={() => setConfirmDelete(false)}>Cancel</button>
                  </div>
                ) : (
                  <button className="btn btn-sm btn-ghost text-danger" onClick={() => setConfirmDelete(true)}><Trash2 size={14} /> Delete Task</button>
                )}
                
                <div style={{ display: "flex", gap: "var(--sp-sm)" }}>
                  <button className="btn btn-sm btn-ghost" onClick={() => { setIsEditing(false); setConfirmDelete(false); setConflictError(null); }}>Cancel</button>
                  <button className="btn btn-sm btn-primary" onClick={handleSave} disabled={saving || !editTitle.trim()}>
                    {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Save Changes
                  </button>
                </div>
              </div>
            )}

            <div className="divider" />

            {/* Implementation Plan section */}
            {task.plan_status && task.plan_status !== "draft" && (
              <div>
                <h4 className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "var(--sp-xs)", marginBottom: "var(--sp-sm)" }}>
                  <FileText size={14} /> Implementation Plan
                </h4>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                  <span style={{
                    display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 9px",
                    borderRadius: 999, fontSize: 11, fontWeight: 600,
                    background: task.plan_status === "approved" ? "#10b98122" :
                      task.plan_status === "awaiting_approval" ? "#f59e0b22" : "#ef444422",
                    color: task.plan_status === "approved" ? "#10b981" :
                      task.plan_status === "awaiting_approval" ? "#f59e0b" : "#ef4444",
                  }}>
                    {task.plan_status === "approved" ? "Approved" :
                      task.plan_status === "awaiting_approval" ? "Awaiting Review" : "Revision Requested"}
                  </span>
                  <button className="btn btn-sm btn-ghost" onClick={() => setShowPlanModal(true)}>
                    <FileText size={13} /> View Plan
                  </button>
                </div>
              </div>
            )}

            <div className="divider" />

            {/* Comments Section */}
            <div>
              <h4 className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "var(--sp-xs)", marginBottom: "var(--sp-sm)" }}>
                <MessageSquare size={14} /> Comments
              </h4>
              
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)", marginBottom: "var(--sp-md)" }}>
                {loadingComments ? (
                  <Loader2 size={16} className="animate-spin text-mute" />
                ) : comments.length > 0 ? (
                  comments.map(c => (
                    <div key={c.id} style={{ background: "var(--color-canvas-raised)", padding: "var(--sp-sm)", borderRadius: "var(--radius-sm)", border: "1px solid var(--color-hairline)" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "var(--sp-xs)" }}>
                        <strong className="body-sm-strong" style={{ color: "var(--color-ink)" }}>{c.author_name}</strong>
                        {c.created_at && <span className="caption" style={{ color: "var(--color-mute)" }}>{new Date(c.created_at).toLocaleString()}</span>}
                      </div>
                      <div className="body-sm" style={{ color: "var(--color-body)", whiteSpace: "pre-wrap" }}>{c.text}</div>
                    </div>
                  ))
                ) : (
                  <div className="body-sm text-mute">No comments yet.</div>
                )}
              </div>

              <div style={{ display: "flex", gap: "var(--sp-sm)" }}>
                <textarea className="input" style={{ flex: 1, minHeight: 60, resize: "none" }} placeholder="Add a comment… Use @Agent Name to notify teammates" value={newComment} onChange={e => setNewComment(e.target.value)} />
                <button className="btn btn-primary" style={{ alignSelf: "flex-end" }} onClick={handlePostComment} disabled={saving || !newComment.trim()}>
                  Post
                </button>
              </div>
              <div className="caption" style={{ color: "var(--color-mute)", marginTop: "var(--sp-xs)" }}>
                Notify: {agents.map(agent => (
                  <button key={agent.id} className="btn btn-ghost btn-sm" onClick={() => setNewComment(value => `${value}${value && !value.endsWith(" ") ? " " : ""}@${agent.name} `)}>
                    @{agent.name}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

      </div>
    </Modal>

    {/* Plan modal — rendered outside main modal to avoid nesting */}
    <ImplementationPlanModal
      taskId={showPlanModal && task ? task.id : null}
      taskTitle={task?.title}
      onClose={() => setShowPlanModal(false)}
    />
    </>
  );
}
