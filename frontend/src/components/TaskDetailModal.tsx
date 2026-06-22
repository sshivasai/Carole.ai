"use client";
import React, { useState, useEffect } from "react";
import type { TaskItem, AgentConfig, TaskComment } from "@/lib/types";
import { AlignLeft, MessageSquare, Trash2, Edit2, Check, Loader2 } from "lucide-react";
import { api } from "@/hooks/useApi";
import Modal from "./Modal";
import { useAuth } from "@/hooks/useAuth";

interface Props {
  task: TaskItem | null;
  agents: AgentConfig[];
  allTasks?: TaskItem[];
  onClose: () => void;
  onUpdate: (task: TaskItem) => void;
  onDelete: (taskId: string) => void;
}

const PRIORITY_BADGE: Record<string, string> = {
  critical: "badge-red", high: "badge-red", medium: "badge-yellow", low: "badge-blue",
};

export default function TaskDetailModal({ task, agents, allTasks = [], onClose, onUpdate, onDelete }: Props) {
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
      loadComments(task.id);
    }
  }, [task]);

  const loadComments = async (taskId: string) => {
    setLoadingComments(true);
    try {
      const data = await api.getTaskComments(taskId);
      setComments(data);
    } catch { /* ignore */ }
    finally { setLoadingComments(false); }
  };

  const handleSave = async () => {
    if (!task || !editTitle.trim()) return;
    setSaving(true);
    try {
      const updates = {
        title: editTitle.trim(),
        description: editDesc.trim(),
        priority: editPrio,
        assigned_agent_id: editAgId || undefined,
        status: editStatus,
        blocked_by_task_id: editBlockedBy || undefined,
      };
      await api.updateTask(task.id, updates);
      onUpdate({ ...task, ...updates });
      setIsEditing(false);
    } catch { /* ignore */ }
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
      const authorName = `${user.first_name || ""} ${user.last_name || ""}`.trim() || "User";
      const comment = await api.addTaskComment(task.id, user.id, authorName, newComment.trim());
      setComments(prev => [...prev, comment]);
      setNewComment("");
    } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  if (!task) return null;
  const getAgentName = (id?: string) => agents.find(a => a.id === id)?.name || "Unassigned";

  return (
    <Modal open={!!task} onClose={onClose} title={isEditing ? "Edit Task" : task.title} maxWidth={700}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-xl)", maxHeight: "75vh", overflowY: "auto", paddingRight: "var(--sp-sm)" }}>
        
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
            {task.blocked_by_task_id && (
              <span className="badge badge-warn">
                🔴 Blocked by: {allTasks.find(t => t.id === task.blocked_by_task_id)?.title || task.blocked_by_task_id.substring(0, 8)}
              </span>
            )}
            <span className="badge badge-gray" style={{ marginLeft: "auto" }}>Assigned to: {getAgentName(task.assigned_agent_id)}</span>
            <button className="btn btn-icon-sm btn-ghost" onClick={() => setIsEditing(true)} title="Edit Task"><Edit2 size={14} /></button>
          </div>
        )}

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
              <button className="btn btn-sm btn-ghost" onClick={() => { setIsEditing(false); setConfirmDelete(false); }}>Cancel</button>
              <button className="btn btn-sm btn-primary" onClick={handleSave} disabled={saving || !editTitle.trim()}>
                {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Save Changes
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
            <textarea className="input" style={{ flex: 1, minHeight: 60, resize: "none" }} placeholder="Add a comment..." value={newComment} onChange={e => setNewComment(e.target.value)} />
            <button className="btn btn-primary" style={{ alignSelf: "flex-end" }} onClick={handlePostComment} disabled={saving || !newComment.trim()}>
              Post
            </button>
          </div>
        </div>

      </div>
    </Modal>
  );
}
