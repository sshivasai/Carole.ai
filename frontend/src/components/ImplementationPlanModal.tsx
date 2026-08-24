"use client";
/**
 * ImplementationPlanModal.tsx
 *
 * Antigravity-style implementation plan review modal.
 * Features:
 *  - Markdown plan rendered line-by-line with per-line inline comment anchors
 *  - Inline comment thread per line
 *  - Approve / Reject with feedback
 *  - Admin inline edit mode
 *  - Todo checklist with progress bar
 */
import React, { useState, useEffect, useCallback } from "react";
import {
  Check, X, MessageSquare, Edit2, CornerDownRight,
  ListChecks, Loader2, FileText, ThumbsUp, ThumbsDown, RefreshCw,
} from "lucide-react";
import { api } from "@/hooks/useApi";
import type { PlanInlineComment, TodoItem } from "@/lib/types";
import Modal from "./Modal";

// ─── Types ───────────────────────────────────────────────────────────────────

interface PlanData {
  task_id: string;
  title: string;
  plan_file_path?: string;
  implementation_plan?: string;
  plan_status?: string;
  plan_feedback?: string;
  todo_list?: TodoItem[];
  inline_comments?: PlanInlineComment[];
}

interface Props {
  taskId: string | null;
  taskTitle?: string;
  onClose: () => void;
  /** Called after approve / reject so the parent can refresh the Kanban board */
  onPlanAction?: () => void;
}

// ─── Plan status badge ────────────────────────────────────────────────────────

const STATUS_CFG: Record<string, { label: string; bg: string; fg: string }> = {
  draft:              { label: "Draft",             bg: "#6b728022", fg: "#6b7280" },
  awaiting_approval:  { label: "Awaiting Review",   bg: "#f59e0b22", fg: "#f59e0b" },
  approved:           { label: "Approved",           bg: "#10b98122", fg: "#10b981" },
  revision_requested: { label: "Revision Requested", bg: "#ef444422", fg: "#ef4444" },
};

function PlanStatusBadge({ status }: { status?: string }) {
  const cfg = STATUS_CFG[status ?? "draft"] ?? STATUS_CFG.draft;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 10px",
      borderRadius: 999, fontSize: 11, fontWeight: 600,
      background: cfg.bg, color: cfg.fg,
    }}>
      {cfg.label}
    </span>
  );
}

// ─── Inline comment thread for a single plan line ────────────────────────────

function LineCommentThread({ taskId, lineIndex, comments, onAdded }: {
  taskId: string; lineIndex: number;
  comments: PlanInlineComment[];
  onAdded: (c: PlanInlineComment) => void;
}) {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!text.trim()) return;
    setLoading(true);
    try {
      const c = await api.addPlanInlineComment(taskId, lineIndex, text.trim());
      onAdded(c);
      setText("");
    } catch { /* ignore */ } finally { setLoading(false); }
  };

  return (
    <div style={{ marginLeft: 36, paddingLeft: 12, marginBottom: 8, borderLeft: "2px solid var(--color-accent, #6366f1)" }}>
      {comments.map(c => (
        <div key={c.id} style={{ marginBottom: 6 }}>
          <div style={{ display: "flex", gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--color-accent, #6366f1)" }}>{c.author_name}</span>
            <span style={{ fontSize: 10, color: "var(--color-mute, #9ca3af)" }}>
              {c.created_at ? new Date(c.created_at).toLocaleTimeString() : ""}
            </span>
          </div>
          <div style={{ fontSize: 12, color: "var(--color-body, #d1d5db)", whiteSpace: "pre-wrap" }}>{c.text}</div>
        </div>
      ))}
      <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
        <input
          className="input"
          style={{ flex: 1, fontSize: 12, padding: "4px 8px", height: 30 }}
          placeholder="Add a comment…"
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
        />
        <button
          className="btn btn-sm btn-primary"
          style={{ height: 30, padding: "0 10px" }}
          onClick={submit}
          disabled={loading || !text.trim()}
        >
          {loading ? <Loader2 size={11} className="animate-spin" /> : <CornerDownRight size={11} />}
        </button>
      </div>
    </div>
  );
}

// ─── A single plan line row ───────────────────────────────────────────────────

function PlanLineRow({ taskId, lineIndex, lineText, comments, onAddedComment, editMode, editValue, onEditChange }: {
  taskId: string; lineIndex: number; lineText: string;
  comments: PlanInlineComment[];
  onAddedComment: (c: PlanInlineComment) => void;
  editMode: boolean; editValue: string; onEditChange: (v: string) => void;
}) {
  const [expanded, setExpanded] = useState(comments.length > 0);

  const renderLine = (text: string) => {
    if (text.startsWith("# "))  return <h2 style={{ margin: 0, fontSize: 17, fontWeight: 700 }}>{text.slice(2)}</h2>;
    if (text.startsWith("## ")) return <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700 }}>{text.slice(3)}</h3>;
    if (text.startsWith("### ")) return <h4 style={{ margin: 0, fontSize: 13, fontWeight: 700 }}>{text.slice(4)}</h4>;
    if (text.startsWith("- ") || text.startsWith("* "))
      return <div style={{ display: "flex", gap: 6 }}><span style={{ color: "var(--color-accent, #6366f1)" }}>•</span><span>{text.slice(2)}</span></div>;
    if (/^\d+\.\s/.test(text)) return <div style={{ paddingLeft: 4 }}>{text}</div>;
    if (text.trim() === "" || text === "---")
      return <hr style={{ border: "none", borderTop: "1px solid var(--color-hairline, #374151)", margin: "2px 0" }} />;
    return <span>{text}</span>;
  };

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 6, padding: "3px 6px", borderRadius: 4 }}>
        <span style={{
          fontSize: 10, color: "var(--color-mute, #9ca3af)", width: 28, textAlign: "right",
          paddingTop: 2, flexShrink: 0, userSelect: "none",
        }}>
          {lineIndex + 1}
        </span>
        <div style={{ flex: 1, fontSize: 13, color: "var(--color-body, #d1d5db)", lineHeight: 1.6 }}>
          {editMode
            ? <input className="input" style={{ width: "100%", fontSize: 12, padding: "2px 6px", height: 26 }}
                value={editValue} onChange={e => onEditChange(e.target.value)} />
            : renderLine(lineText)}
        </div>
        {!editMode && (
          <button
            className="btn btn-icon-sm btn-ghost"
            style={{ opacity: comments.length > 0 ? 1 : 0.2, flexShrink: 0 }}
            title="Comment on this line"
            onClick={() => setExpanded(p => !p)}
          >
            <MessageSquare size={11} />
            {comments.length > 0 && <span style={{ fontSize: 9, marginLeft: 2 }}>{comments.length}</span>}
          </button>
        )}
      </div>
      {expanded && !editMode && (
        <LineCommentThread taskId={taskId} lineIndex={lineIndex} comments={comments} onAdded={onAddedComment} />
      )}
    </div>
  );
}

// ─── Todo checklist ───────────────────────────────────────────────────────────

function TodoChecklist({ todos, taskId, onToggle }: {
  todos: TodoItem[]; taskId: string; onToggle: (id: string) => void;
}) {
  const done = todos.filter(t => t.done).length;
  const pct = todos.length > 0 ? Math.round((done / todos.length) * 100) : 0;
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <ListChecks size={13} /> Todo Checklist
        </span>
        <span style={{ fontSize: 11, color: "var(--color-mute, #9ca3af)" }}>{done}/{todos.length} • {pct}%</span>
      </div>
      <div style={{ height: 3, background: "var(--color-hairline, #374151)", borderRadius: 2, marginBottom: 10 }}>
        <div style={{ height: "100%", width: `${pct}%`, background: "var(--color-accent, #6366f1)", borderRadius: 2, transition: "width 0.3s" }} />
      </div>
      {todos.map(item => (
        <label key={item.id} style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", padding: "4px 6px", borderRadius: 4, opacity: item.done ? 0.6 : 1 }}>
          <input type="checkbox" checked={item.done} onChange={() => onToggle(item.id)}
            style={{ accentColor: "var(--color-accent, #6366f1)", width: 14, height: 14 }} />
          <span style={{ fontSize: 13, color: "var(--color-body, #d1d5db)", textDecoration: item.done ? "line-through" : "none" }}>
            {item.text}
          </span>
        </label>
      ))}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function ImplementationPlanModal({ taskId, taskTitle, onClose, onPlanAction }: Props) {
  const [plan, setPlan] = useState<PlanData | null>(null);
  const [loading, setLoading] = useState(false);
  const [acting, setActing] = useState(false);
  const [commentsByLine, setCommentsByLine] = useState<Record<number, PlanInlineComment[]>>({});
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [rejectFeedback, setRejectFeedback] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [editLines, setEditLines] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [todos, setTodos] = useState<TodoItem[]>([]);

  const load = useCallback(async () => {
    if (!taskId) return;
    setLoading(true);
    try {
      const data = await api.getTaskPlan(taskId);
      setPlan(data);
      setTodos(data.todo_list || []);
      const byLine: Record<number, PlanInlineComment[]> = {};
      for (const c of (data.inline_comments || [])) {
        if (!byLine[c.line_index]) byLine[c.line_index] = [];
        byLine[c.line_index].push(c);
      }
      setCommentsByLine(byLine);
      setEditLines((data.implementation_plan || "").split("\n"));
    } catch { /* ignore */ } finally { setLoading(false); }
  }, [taskId]);

  useEffect(() => { load(); }, [load]);

  const handleApprove = async () => {
    if (!taskId) return;
    setActing(true);
    try {
      await api.approvePlan(taskId);
      setPlan(p => p ? { ...p, plan_status: "approved", plan_feedback: undefined } : p);
      onPlanAction?.();
    } catch { /* ignore */ } finally { setActing(false); }
  };

  const handleReject = async () => {
    if (!taskId) return;
    setActing(true);
    try {
      await api.rejectPlan(taskId, rejectFeedback.trim() || undefined);
      setPlan(p => p ? { ...p, plan_status: "revision_requested", plan_feedback: rejectFeedback } : p);
      setShowRejectForm(false);
      setRejectFeedback("");
      onPlanAction?.();
    } catch { /* ignore */ } finally { setActing(false); }
  };

  const handleSaveEdit = async () => {
    if (!taskId) return;
    setSaving(true);
    try {
      const md = editLines.join("\n");
      await api.editPlan(taskId, md);
      setPlan(p => p ? { ...p, implementation_plan: md, plan_status: "awaiting_approval" } : p);
      setEditMode(false);
      onPlanAction?.();
    } catch { /* ignore */ } finally { setSaving(false); }
  };

  const handleTodoToggle = async (id: string) => {
    if (!taskId) return;
    try {
      await api.updateTodos(taskId, { toggle_id: id });
      setTodos(prev => prev.map(t => t.id === id ? { ...t, done: !t.done } : t));
    } catch { /* ignore */ }
  };

  const lines = plan ? (plan.implementation_plan || "").split("\n") : [];

  return (
    <Modal open={!!taskId} onClose={onClose} title="Implementation Plan" maxWidth={860}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-lg, 16px)", maxHeight: "80vh" }}>

        {/* Header: task name + status + action buttons */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
          <div>
            <div className="body-sm-strong" style={{ marginBottom: 4 }}>{plan?.title || taskTitle || "Task"}</div>
            <PlanStatusBadge status={plan?.plan_status} />
          </div>
          {!loading && plan && (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              {plan.plan_status === "awaiting_approval" && (
                <>
                  <button className="btn btn-sm btn-ghost" onClick={() => setShowRejectForm(p => !p)}
                    disabled={acting} style={{ color: "#ef4444" }}>
                    <ThumbsDown size={13} /> Request Revision
                  </button>
                  <button className="btn btn-sm btn-primary" onClick={handleApprove}
                    disabled={acting} style={{ background: "#10b981" }}>
                    {acting ? <Loader2 size={13} className="animate-spin" /> : <ThumbsUp size={13} />} Approve Plan
                  </button>
                </>
              )}
              {plan.plan_status !== "approved" && !editMode && (
                <button className="btn btn-sm btn-ghost" onClick={() => { setEditMode(true); setEditLines(lines); }}>
                  <Edit2 size={13} /> Edit
                </button>
              )}
              {editMode && (
                <>
                  <button className="btn btn-sm btn-ghost" onClick={() => setEditMode(false)}>Cancel</button>
                  <button className="btn btn-sm btn-primary" onClick={handleSaveEdit} disabled={saving}>
                    {saving ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} Save
                  </button>
                </>
              )}
              <button className="btn btn-sm btn-ghost btn-icon-sm" onClick={load} title="Refresh"><RefreshCw size={13} /></button>
            </div>
          )}
        </div>

        {/* Rejection feedback form */}
        {showRejectForm && (
          <div style={{ background: "#ef444408", border: "1px solid #ef444440", borderRadius: "var(--radius-sm, 6px)", padding: "var(--sp-md, 12px)" }}>
            <div className="body-sm-strong" style={{ marginBottom: 8, color: "#ef4444" }}>Request Revision</div>
            <textarea className="input" style={{ width: "100%", minHeight: 80, resize: "vertical", fontSize: 13, marginBottom: 8 }}
              placeholder="Describe what needs to change (shown to the agent)…"
              value={rejectFeedback} onChange={e => setRejectFeedback(e.target.value)} />
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button className="btn btn-sm btn-ghost" onClick={() => setShowRejectForm(false)}>Cancel</button>
              <button className="btn btn-sm btn-primary" style={{ background: "#ef4444" }} onClick={handleReject} disabled={acting}>
                {acting ? <Loader2 size={13} className="animate-spin" /> : <X size={13} />} Send Feedback
              </button>
            </div>
          </div>
        )}

        {/* Feedback banner (when revision was requested) */}
        {plan?.plan_feedback && plan.plan_status === "revision_requested" && (
          <div style={{ background: "#f59e0b08", border: "1px solid #f59e0b40", borderRadius: "var(--radius-sm, 6px)", padding: "var(--sp-sm, 8px) var(--sp-md, 12px)", fontSize: 13, color: "#f59e0b" }}>
            <strong>Review feedback:</strong> {plan.plan_feedback}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div style={{ display: "flex", justifyContent: "center", padding: 40 }}>
            <Loader2 size={24} className="animate-spin" style={{ color: "var(--color-mute, #9ca3af)" }} />
          </div>
        )}

        {/* Empty state */}
        {!loading && !plan?.implementation_plan && (
          <div style={{ textAlign: "center", padding: 40, color: "var(--color-mute, #9ca3af)" }}>
            <FileText size={32} style={{ marginBottom: 12, opacity: 0.4 }} />
            <div className="body-sm">No implementation plan has been written for this task yet.</div>
          </div>
        )}

        {/* Line-by-line plan viewer */}
        {!loading && plan?.implementation_plan && (
          <div style={{
            overflowY: "auto", flex: 1,
            background: "var(--color-canvas-soft, #111827)",
            borderRadius: "var(--radius-sm, 6px)",
            border: "1px solid var(--color-hairline, #374151)",
            padding: "var(--sp-sm, 8px)",
          }}>
            {(editMode ? editLines : lines).map((line, i) => (
              <PlanLineRow
                key={i}
                taskId={taskId!}
                lineIndex={i}
                lineText={line}
                comments={commentsByLine[i] || []}
                onAddedComment={c => setCommentsByLine(prev => ({ ...prev, [i]: [...(prev[i] || []), c] }))}
                editMode={editMode}
                editValue={editLines[i] ?? ""}
                onEditChange={v => setEditLines(prev => { const n = [...prev]; n[i] = v; return n; })}
              />
            ))}
          </div>
        )}

        {/* Todo checklist */}
        {!loading && todos.length > 0 && (
          <>
            <div className="divider" />
            <TodoChecklist todos={todos} taskId={taskId!} onToggle={handleTodoToggle} />
          </>
        )}

      </div>
    </Modal>
  );
}
