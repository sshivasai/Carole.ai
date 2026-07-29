"use client";
import React, { useState, useCallback } from "react";
import { MessageSquare, LayoutGrid, Brain, Globe, Settings, Zap, Plus, X, Loader2, ChevronRight, ChevronLeft, Menu, Code2, Server, BookOpen, StickyNote } from "lucide-react";
import styles from "./Sidebar.module.css";
import { api } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";

interface Props {
  activeView: string;
  onViewChange: (v: string) => void;
  connected: boolean;
  projects: any[];
  projectId: string | null;
  onProjectChange: (id: string) => void;
  onProjectCreated: (p: any) => void;
  teams: any[];
  teamId: string | null;
  onTeamChange: (id: string) => void;
  onTeamCreated: (t: any) => void;
}

const NAV = [
  { id: "chat", label: "Chat Room", Icon: MessageSquare },
  { id: "tasks", label: "Task Board", Icon: LayoutGrid },
  { id: "agents", label: "Agents", Icon: Zap },
  { id: "browser", label: "Browser View", Icon: Globe },
  { id: "memory", label: "Memory & Logs", Icon: Brain },
  { id: "scratchpad", label: "Scratchpad", Icon: StickyNote },
  { id: "plugins", label: "Plugin Studio", Icon: Code2 },
  { id: "skills", label: "Skills Studio", Icon: BookOpen },
  { id: "mcp", label: "MCP Servers", Icon: Server },
  { id: "settings", label: "Settings", Icon: Settings },
];

function InlineForm({ placeholder, onSubmit, onCancel }: {
  label: string; placeholder: string; onSubmit: (val: string) => Promise<void>; onCancel: () => void;
}) {
  const [val, setVal] = useState("");
  const [loading, setLoading] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!val.trim()) return;
    setLoading(true);
    try { await onSubmit(val.trim()); } finally { setLoading(false); }
  };
  return (
    <form onSubmit={submit} className={styles.inlineForm}>
      <input className={styles.inlineInput} placeholder={placeholder} value={val}
        onChange={e => setVal(e.target.value)} autoFocus />
      <div style={{ display: "flex", gap: 6 }}>
        <button type="submit" className={`btn btn-primary btn-sm ${styles.inlineBtn}`} disabled={loading || !val.trim()}>
          {loading ? <Loader2 size={12} className="animate-spin" /> : "Add"}
        </button>
        <button type="button" onClick={onCancel} className={`btn btn-ghost btn-sm ${styles.inlineBtn}`}>
          <X size={12} />
        </button>
      </div>
    </form>
  );
}

export default function Sidebar({
  activeView, onViewChange, connected,
  projects, projectId, onProjectChange, onProjectCreated,
  teams, teamId, onTeamChange, onTeamCreated,
}: Props) {
  const { user, logout } = useAuth();
  const [showAddProject, setShowAddProject] = useState(false);
  const [showAddTeam, setShowAddTeam] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);

  const handleAddProject = useCallback(async (name: string) => {
    const p = await api.createProject(name, user?.id);
    onProjectCreated(p);
    setShowAddProject(false);
  }, [user?.id, onProjectCreated]);

  const handleAddTeam = useCallback(async (name: string) => {
    if (!projectId) return;
    const t = await api.createTeam(name, projectId);
    onTeamCreated(t);
    setShowAddTeam(false);
  }, [projectId, onTeamCreated]);

  const userInitials = user
    ? `${user.first_name?.[0] || ""}${user.last_name?.[0] || ""}`.toUpperCase() || user.email[0].toUpperCase()
    : "?";

  if (isCollapsed) {
    return (
      <nav className={`${styles.sidebar} ${styles.collapsedSidebar}`}>
        <div className={styles.sidebarLogo} style={{ padding: "var(--sp-md) 0", justifyContent: "center" }}>
          <button className={styles.collapseBtn} onClick={() => setIsCollapsed(false)} title="Expand Sidebar">
            <Menu size={20} />
          </button>
        </div>
        <div className={styles.sidebarNav} style={{ padding: "var(--sp-md) 0", display: "flex", flexDirection: "column", alignItems: "center" }}>
          {NAV.map(({ id, label, Icon }) => (
            <button key={id} className={`${styles.navItem} ${activeView === id ? styles.active : ""}`}
              onClick={() => onViewChange(id)} title={label} style={{ justifyContent: "center", padding: "10px 0" }}>
              <Icon size={18} className={styles.navItemIcon} style={{ margin: 0 }} />
            </button>
          ))}
        </div>
      </nav>
    );
  }

  return (
    <nav className={styles.sidebar}>
      {/* Logo */}
      <div className={styles.sidebarLogo}>
        <div className={styles.sidebarLogoMark}>C</div>
        <button className={styles.collapseBtn} onClick={() => setIsCollapsed(true)} title="Collapse Sidebar">
          <ChevronLeft size={16} />
        </button>
      </div>

      {/* Project Selector */}
      <div className={styles.entityBlock}>
        <div className={styles.entityLabel}>Project</div>
        <select className={styles.entitySelect} value={projectId || ""}
          onChange={e => onProjectChange(e.target.value)}>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          {projects.length === 0 && <option value="">No projects</option>}
        </select>
        {showAddProject ? (
          <InlineForm label="New Project" placeholder="Project name..." onSubmit={handleAddProject} onCancel={() => setShowAddProject(false)} />
        ) : (
          <button className={styles.entityAddBtn} onClick={() => setShowAddProject(true)}>
            <Plus size={11} /> New project
          </button>
        )}
      </div>

      {/* Team Selector */}
      <div className={styles.entityBlock}>
        <div className={styles.entityLabel}>Team Room</div>
        <select className={styles.entitySelect} value={teamId || ""}
          onChange={e => onTeamChange(e.target.value)}>
          {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          {teams.length === 0 && <option value="">No teams</option>}
        </select>
        {showAddTeam ? (
          <InlineForm label="New Team" placeholder="Team name..." onSubmit={handleAddTeam} onCancel={() => setShowAddTeam(false)} />
        ) : (
          <button className={styles.entityAddBtn} onClick={() => setShowAddTeam(true)} disabled={!projectId}>
            <Plus size={11} /> New team
          </button>
        )}
      </div>

      {/* Nav */}
      <div className={styles.sidebarNav}>
        <div className={styles.sidebarSection}>
          <span className={styles.sidebarSectionLabel}>Workspace</span>
        </div>
        {NAV.map(({ id, label, Icon }) => (
          <button key={id} className={`${styles.navItem} ${activeView === id ? styles.active : ""}`}
            onClick={() => onViewChange(id)} title={label}>
            <Icon size={15} className={styles.navItemIcon} />
            <span>{label}</span>
            {activeView === id && <ChevronRight size={12} style={{ marginLeft: "auto", opacity: 0.5 }} />}
          </button>
        ))}
      </div>

      {/* User + connection footer */}
      <div className={styles.sidebarFooter}>
        <div className={styles.connBadge}>
          <div className={`${styles.connDot} ${connected ? styles.live : styles.offline}`} />
          <span>{connected ? "Connected" : "Connecting..."}</span>
        </div>
        {user && (
          <div className={styles.userRow}>
            <div className={styles.userAvatar}>{userInitials}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className={styles.userName} title={user.email}>
                {user.first_name ? `${user.first_name} ${user.last_name || ""}`.trim() : user.email}
              </div>
              <div className={styles.userEmail}>{user.email}</div>
            </div>
            <button className={`btn btn-icon-sm btn-ghost ${styles.logoutBtn}`} onClick={logout} title="Sign out">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}
