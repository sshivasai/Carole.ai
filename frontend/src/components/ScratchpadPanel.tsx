"use client";
import React, { useEffect, useMemo, useState } from "react";
import {
  StickyNote, Users, User as UserIcon, Edit2, Save, Plus, Trash2,
  Loader2, RefreshCw, X, FileText,
} from "lucide-react";
import type { AgentConfig, ScratchpadItem } from "@/lib/types";
import { api } from "@/hooks/useApi";
import Modal from "./Modal";

interface Props {
  teamId: string | null;
  agents: AgentConfig[];
  scratchpads: ScratchpadItem[];
  onScratchpadsChange: (pads: ScratchpadItem[]) => void;
  onToast: (msg: string, type: "success" | "error") => void;
}

const padKey = (p: Pick<ScratchpadItem, "target" | "agent_name">) =>
  `${p.target}|${p.target === "team" ? "TEAM" : p.agent_name}`;

function relativeTime(iso?: string): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diff = Math.max(0, Date.now() - then);
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function ScratchpadPanel({ teamId, agents, scratchpads, onScratchpadsChange, onToast }: Props) {
  // Build the pad list from props (which page.tsx keeps in sync via REST + WS).
  // Always show the team pad + one personal pad per known agent, even if empty.
  const pads = useMemo<ScratchpadItem[]>(() => {
    const byKey = new Map<string, ScratchpadItem>();
    for (const p of scratchpads) byKey.set(padKey(p), p);

    const list: ScratchpadItem[] = [];
    const teamPad = byKey.get("team|TEAM") ?? {
      target: "team", agent_name: "Team", label: "Team Scratchpad", content: "",
    };
    list.push(teamPad);

    for (const a of agents) {
      const k = `personal|${a.name}`;
      list.push(byKey.get(k) ?? {
        target: "personal", agent_name: a.name, agent_id: a.id,
        label: `${a.name}'s Scratchpad`, content: "",
      });
    }
    // Any on-disk pads whose agent is no longer in the roster
    for (const p of scratchpads) {
      if (p.target === "personal" && !agents.some(a => a.name === p.agent_name)) {
        list.push(p);
      }
    }
    return list;
  }, [scratchpads, agents]);

  const [selectedKey, setSelectedKey] = useState<string>("team|TEAM");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [appendText, setAppendText] = useState("");
  const [showAppend, setShowAppend] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);
  const [staleRemote, setStaleRemote] = useState(false);
  // Tracks the server content snapshot when an edit session began.
  const [editBase, setEditBase] = useState("");

  const selected = pads.find(p => padKey(p) === selectedKey) ?? pads[0];

  // Reset edit state when switching pads
  useEffect(() => {
    setEditing(false);
    setDraft("");
    setShowAppend(false);
    setAppendText("");
    setStaleRemote(false);
  }, [selectedKey]);

  // Detect remote updates while editing
  useEffect(() => {
    if (!editing || !selected) return;
    if (selected.content !== editBase) {
      setStaleRemote(true);
    }
  }, [selected, editing, editBase]);

  if (!teamId) {
    return (
      <div style={{ padding: "var(--sp-2xl)", color: "var(--color-text-mute)" }} className="body-sm">
        Select a team to view scratchpads.
      </div>
    );
  }

  const upsert = (updated: ScratchpadItem) => {
    const k = padKey(updated);
    const idx = scratchpads.findIndex(p => padKey(p) === k);
    if (idx >= 0) {
      const copy = [...scratchpads];
      copy[idx] = { ...copy[idx], ...updated };
      onScratchpadsChange(copy);
    } else {
      onScratchpadsChange([...scratchpads, updated]);
    }
  };

  const startEdit = () => {
    setDraft(selected.content);
    setEditBase(selected.content);
    setStaleRemote(false);
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setDraft("");
    setStaleRemote(false);
  };

  const reloadFromRemote = () => {
    setDraft(selected.content);
    setEditBase(selected.content);
    setStaleRemote(false);
  };

  const handleSave = async () => {
    if (!teamId || !selected) return;
    setBusy(true);
    try {
      const res = await api.updateScratchpad(teamId, {
        content: draft,
        target: selected.target,
        agent_name: selected.target === "team" ? "Team" : selected.agent_name,
        agent_id: selected.agent_id,
        author: "admin",
      });
      upsert({
        ...selected,
        content: draft,
        updated_at: res?.updated_at ?? new Date().toISOString(),
        size_bytes: draft.length,
      });
      setEditing(false);
      onToast("Scratchpad saved", "success");
    } catch {
      onToast("Failed to save scratchpad", "error");
    } finally {
      setBusy(false);
    }
  };

  const handleAppend = async () => {
    if (!teamId || !selected || !appendText.trim()) return;
    setBusy(true);
    try {
      const res = await api.writeScratchpad(teamId, {
        content: appendText,
        target: selected.target,
        mode: "append",
        agent_name: selected.target === "team" ? "Team" : selected.agent_name,
        agent_id: selected.agent_id,
        author: "admin",
      });
      const newContent = res?.content ?? selected.content + `\n<!-- admin -->\n${appendText}\n`;
      upsert({
        ...selected,
        content: newContent,
        updated_at: res?.updated_at ?? new Date().toISOString(),
        size_bytes: newContent.length,
      });
      setAppendText("");
      setShowAppend(false);
      onToast("Note appended", "success");
    } catch {
      onToast("Failed to append note", "error");
    } finally {
      setBusy(false);
    }
  };


  const executeClear = async () => {
    if (!teamId || !selected) return;
    setBusy(true);
    try {
      await api.clearScratchpad(
        teamId,
        selected.target,
        selected.target === "team" ? "" : selected.agent_name,
      );
      upsert({ ...selected, content: "", updated_at: new Date().toISOString(), size_bytes: 0 });
      if (editing) cancelEdit();
      onToast("Scratchpad cleared", "success");
    } catch {
      onToast("Failed to clear scratchpad", "error");
    } finally {
      setBusy(false);
      setConfirmClearOpen(false);
    }
  };

  return (
    <div style={{ display: "flex", height: "100%", width: "100%", overflow: "hidden" }}>
      {/* Left rail */}
      <aside style={{
        width: 240, flexShrink: 0, borderRight: "1px solid var(--color-hairline)",
        overflowY: "auto", padding: "var(--sp-md)", background: "var(--color-surface)",
      }}>
        <div className="caption" style={{ padding: "var(--sp-xs) var(--sp-sm)", textTransform: "uppercase", letterSpacing: 0.5 }}>
          Scratchpads
        </div>
        {pads.map(p => {
          const k = padKey(p);
          const active = k === selectedKey;
          const empty = !p.content?.trim();
          const Icon = p.target === "team" ? Users : UserIcon;
          return (
            <button
              key={k}
              onClick={() => setSelectedKey(k)}
              className={active ? "active" : ""}
              style={{
                display: "flex",
                width: "100%",
                alignItems: "center",
                gap: "var(--sp-sm)",
                padding: "8px 12px",
                borderRadius: 8,
                marginBottom: 3,
                textAlign: "left",
                cursor: "pointer",
                background: active
                  ? "var(--color-primary-glow)"
                  : "transparent",
                border: active
                  ? "1px solid rgba(167, 139, 250, 0.35)"
                  : "1px solid transparent",
                color: active
                  ? "var(--color-primary)"
                  : "var(--color-ink)",
                fontWeight: active ? 700 : 500,
                transition: "all var(--t-fast)",
              }}
            >
              <Icon
                size={15}
                style={{
                  flexShrink: 0,
                  color: active ? "var(--color-primary)" : "var(--color-mute)",
                }}
              />
              <span
                style={{
                  flex: 1,
                  minWidth: 0,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  fontSize: 13,
                  fontWeight: active ? 700 : 500,
                  color: active ? "var(--color-ink-strong)" : "var(--color-ink)",
                }}
              >
                {p.target === "team" ? "Team (Common)" : p.agent_name}
              </span>
              {empty ? (
                <span
                  style={{
                    fontSize: 10,
                    fontFamily: "var(--font-mono, monospace)",
                    color: "var(--color-mute)",
                    padding: "1px 5px",
                    borderRadius: 4,
                    background: "var(--color-canvas-raised)",
                  }}
                >
                  empty
                </span>
              ) : (
                <span
                  style={{
                    fontSize: 10,
                    fontFamily: "var(--font-mono, monospace)",
                    color: active ? "var(--color-primary)" : "var(--color-mute)",
                  }}
                >
                  {relativeTime(p.updated_at)}
                </span>
              )}
            </button>
          );
        })}
      </aside>

      {/* Main pane */}
      <section style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div className="flex-between" style={{
          padding: "var(--sp-md) var(--sp-xl)", borderBottom: "1px solid var(--color-hairline)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
            <StickyNote size={18} color="var(--color-primary)" />
            <div>
              <div className="body-sm" style={{ fontWeight: 600 }}>{selected?.label}</div>
              <div className="caption">
                {selected?.content?.trim()
                  ? `Updated ${relativeTime(selected.updated_at)} · ${selected.size_bytes ?? selected.content.length} bytes`
                  : "Empty"}
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: "var(--sp-xs)" }}>
            {!editing ? (
              <>
                <button className="btn-ghost" onClick={() => setShowAppend(s => !s)} disabled={busy}
                  style={iconBtn}><Plus size={14} /> Append</button>
                <button className="btn-ghost" onClick={startEdit} disabled={busy}
                  style={iconBtn}><Edit2 size={14} /> Edit</button>
                <button className="btn-ghost" onClick={() => setConfirmClearOpen(true)} disabled={busy}
                  style={iconBtn}><Trash2 size={14} /> Clear</button>
              </>
            ) : (
              <>
                <button className="btn-primary" onClick={handleSave} disabled={busy}
                  style={iconBtn}>{busy ? <Loader2 size={14} className="spin" /> : <Save size={14} />} Save</button>
                <button className="btn-ghost" onClick={cancelEdit} disabled={busy}
                  style={iconBtn}><X size={14} /> Cancel</button>
              </>
            )}
          </div>
        </div>

        {staleRemote && editing && (
          <div style={{
            display: "flex", alignItems: "center", gap: "var(--sp-sm)",
            padding: "var(--sp-xs) var(--sp-xl)", fontSize: 12,
            background: "rgba(245,158,11,0.12)", color: "#b45309", borderBottom: "1px solid var(--color-hairline)",
          }}>
            <RefreshCw size={13} />
            <span>This pad was updated remotely. Your draft is stale.</span>
            <button onClick={reloadFromRemote} style={{ marginLeft: "auto", fontSize: 12, cursor: "pointer", border: "none", background: "transparent", color: "#b45309", textDecoration: "underline" }}>
              Reload remote
            </button>
          </div>
        )}

        <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column", padding: "var(--sp-md) var(--sp-xl)" }}>
          {showAppend && !editing && (
            <div style={{ marginBottom: "var(--sp-md)", padding: "var(--sp-sm)", border: "1px solid var(--color-hairline)", borderRadius: 8 }}>
              <textarea
                value={appendText}
                onChange={e => setAppendText(e.target.value)}
                placeholder="Add a short note to append…"
                style={textareaStyle}
                rows={3}
              />
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--sp-xs)", marginTop: "var(--sp-xs)" }}>
                <button className="btn-ghost" onClick={() => { setShowAppend(false); setAppendText(""); }} disabled={busy} style={iconBtn}>Cancel</button>
                <button className="btn-primary" onClick={handleAppend} disabled={busy || !appendText.trim()} style={iconBtn}>
                  {busy ? <Loader2 size={14} className="spin" /> : <Plus size={14} />} Append note
                </button>
              </div>
            </div>
          )}

          {editing ? (
            <textarea
              value={draft}
              onChange={e => setDraft(e.target.value)}
              style={{ ...textareaStyle, flex: 1 }}
              placeholder="Scratchpad contents…"
            />
          ) : (
            <div style={{ flex: 1, overflowY: "auto" }}>
              {selected?.content?.trim() ? (
                <pre style={{
                  whiteSpace: "pre-wrap", wordBreak: "break-word", fontFamily: "var(--font-mono, ui-monospace, monospace)",
                  fontSize: 13, lineHeight: 1.6, margin: 0, color: "var(--color-text)",
                }}>{selected.content}</pre>
              ) : (
                <div style={{
                  display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                  height: "100%", color: "var(--color-text-mute)", gap: "var(--sp-sm)",
                }}>
                  <FileText size={28} opacity={0.4} />
                  <span className="body-sm">This scratchpad is empty.</span>
                  <button className="btn-ghost" onClick={startEdit} style={iconBtn}><Edit2 size={14} /> Start writing</button>
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Clear Scratchpad Confirmation Modal */}
      {confirmClearOpen && selected && (
        <Modal open={true} onClose={() => setConfirmClearOpen(false)} title="Clear Scratchpad" maxWidth={400}>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
            <p className="body-sm" style={{ color: "var(--color-body)", margin: 0 }}>
              Are you sure you want to clear <strong>"{selected.label}"</strong>? This will remove all contents from the scratchpad.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--sp-sm)", marginTop: "var(--sp-sm)" }}>
              <button className="btn btn-ghost btn-sm" onClick={() => setConfirmClearOpen(false)}>Cancel</button>
              <button className="btn btn-danger btn-sm" onClick={executeClear} disabled={busy}>
                {busy ? "Clearing…" : "Clear Scratchpad"}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

const iconBtn: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 10px",
  fontSize: 13, borderRadius: 8, cursor: "pointer",
};

const textareaStyle: React.CSSProperties = {
  width: "100%", resize: "none", fontFamily: "var(--font-mono, ui-monospace, monospace)",
  fontSize: 13, lineHeight: 1.6, padding: "var(--sp-sm) var(--sp-md)",
  borderRadius: 8, border: "1px solid var(--color-hairline)",
  background: "var(--color-surface)", color: "var(--color-text)",
};
