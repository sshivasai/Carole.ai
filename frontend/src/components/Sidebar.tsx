"use client";
import React, { useState, useCallback, useRef, useEffect } from "react";
import { MessageSquare, LayoutGrid, Brain, Globe, Settings, Zap, Plus, X, Loader2, ChevronRight, ChevronLeft, Menu, Code2, Server, BookOpen, StickyNote, Network, GitBranch } from "lucide-react";
import styles from "./Sidebar.module.css";
import { api } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import AgentAvatar from "./AgentAvatar";

import NotificationBell from "./NotificationBell";
import ThemeToggle from "./ThemeToggle";
import { useTheme } from "@/hooks/useTheme";

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
  isCollapsed?: boolean;
  onToggleCollapse?: (collapsed?: boolean) => void;
  width?: number;
  onWidthChange?: (width: number) => void;
}

const NAV = [
  { id: "chat", label: "Chat Room", Icon: MessageSquare },
  { id: "tasks", label: "Task Board", Icon: LayoutGrid },
  { id: "agents", label: "Agents", Icon: Zap },
  { id: "workflow_dag", label: "Swarm Topology", Icon: Network },
  { id: "code_graph", label: "Code Graph", Icon: GitBranch },
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
  isCollapsed: controlledCollapsed,
  onToggleCollapse,
  width = 260,
  onWidthChange,
}: Props) {
  const { user, logout } = useAuth();
  const { theme } = useTheme();
  const [showAddProject, setShowAddProject] = useState(false);
  const [showAddTeam, setShowAddTeam] = useState(false);
  const [internalCollapsed, setInternalCollapsed] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const sidebarRef = useRef<HTMLElement>(null);

  const isCollapsed = controlledCollapsed !== undefined ? controlledCollapsed : internalCollapsed;
  const toggleCollapse = useCallback((forceState?: boolean) => {
    if (onToggleCollapse) {
      onToggleCollapse(forceState);
    } else {
      setInternalCollapsed(prev => forceState !== undefined ? forceState : !prev);
    }
  }, [onToggleCollapse]);

  // Auto-close sidebar on click outside when expanded
  useEffect(() => {
    if (isCollapsed) return;
    const handleOutsideClick = (e: MouseEvent) => {
      if (sidebarRef.current && !sidebarRef.current.contains(e.target as Node)) {
        toggleCollapse(true);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [isCollapsed, toggleCollapse]);

  const handleNavClick = useCallback((id: string) => {
    onViewChange(id);
    if (!isCollapsed) {
      toggleCollapse(true);
    }
  }, [onViewChange, isCollapsed, toggleCollapse]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
    const startX = e.clientX;
    const startWidth = isCollapsed ? 64 : width;

    const onMouseMove = (moveEvent: MouseEvent) => {
      const delta = moveEvent.clientX - startX;
      const targetWidth = startWidth + delta;
      if (targetWidth < 180) {
        if (!isCollapsed) toggleCollapse(true);
      } else {
        if (isCollapsed) toggleCollapse(false);
        const clamped = Math.max(250, Math.min(360, targetWidth));
        onWidthChange?.(clamped);
      }
    };

    const onMouseUp = () => {
      setIsResizing(false);
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }, [isCollapsed, width, toggleCollapse, onWidthChange]);

  const handleDoubleClickHandle = useCallback(() => {
    if (isCollapsed) {
      toggleCollapse(false);
    } else if (width !== 260) {
      onWidthChange?.(260);
    } else {
      toggleCollapse(true);
    }
  }, [isCollapsed, width, toggleCollapse, onWidthChange]);

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

  const effectiveWidth = isCollapsed ? 64 : Math.max(250, Math.min(360, width || 260));
  const transitionStyle = isResizing ? "none" : "width 0.2s cubic-bezier(0.4, 0, 0.2, 1), min-width 0.2s cubic-bezier(0.4, 0, 0.2, 1), max-width 0.2s cubic-bezier(0.4, 0, 0.2, 1)";

  if (isCollapsed) {
    return (
      <nav
        className={`${styles.sidebar} ${styles.collapsedSidebar}`}
        style={{
          width: 64, minWidth: 64, maxWidth: 64,
          transition: transitionStyle
        }}
      >
        <div className={styles.sidebarLogoCollapsed}>
          <button
            className={styles.collapsedLogoBtn}
            onClick={() => toggleCollapse(false)}
            title="Expand Sidebar"
          >
            <img
              src="/branding/logo-mark-animated.webp"
              alt="Carole.ai"
              width={28}
              height={28}
              style={{ objectFit: "contain", filter: "drop-shadow(0 0 8px rgba(131, 118, 244, 0.45))" }}
            />
          </button>
        </div>
        <div className={styles.sidebarNav} style={{ padding: "var(--sp-sm) 0", display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
          {NAV.map(({ id, label, Icon }) => (
            <button key={id} className={`${styles.navItem} ${activeView === id ? styles.active : ""}`}
              onClick={() => onViewChange(id)} title={label} style={{ justifyContent: "center", padding: "10px 0", width: 44, borderRadius: "var(--radius-sm)" }}>
              <Icon size={18} className={styles.navItemIcon} style={{ margin: 0 }} />
            </button>
          ))}
        </div>
        <div className={styles.sidebarFooter} style={{ padding: "var(--sp-sm) 0", display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
          <div className={`${styles.connDot} ${connected ? styles.live : styles.offline}`} title={connected ? "Connected" : "Connecting..."} />
          {user && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
              <AgentAvatar name={user.first_name ? `${user.first_name} ${user.last_name || ""}`.trim() : user.email} id={user.id || user.email} role="human" size={28} />
              <button className={`btn btn-icon-sm btn-ghost ${styles.footerActionBtn}`} onClick={() => toggleCollapse(false)} title="Expand sidebar">
                <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>
        <div
          className={`${styles.resizeHandle} ${isResizing ? styles.isResizing : ""}`}
          onMouseDown={handleMouseDown}
          onDoubleClick={handleDoubleClickHandle}
          title="Drag to resize sidebar · Double click to expand"
        />
      </nav>
    );
  }

  return (
    <nav
      ref={sidebarRef}
      className={styles.sidebar}
      style={{
        width: effectiveWidth,
        minWidth: effectiveWidth,
        maxWidth: effectiveWidth,
        transition: transitionStyle
      }}
    >
      {/* Logo */}
      <div className={styles.sidebarLogo}>
        <div className={styles.sidebarLogoBrand}>
          <img src="/branding/logo-mark-animated.webp" alt="Carole.ai Logo" className={styles.sidebarLogoImg} />
          <img
            src={theme === "dark" ? "/branding/logo-wordmark-dark.png" : "/branding/logo-wordmark.png"}
            alt="Carole.ai: AI Agents. Real Work."
            className={styles.sidebarLogoWordmark}
          />
        </div>
        <button className={styles.collapseBtn} onClick={() => toggleCollapse(true)} title="Collapse Sidebar">
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
            onClick={() => handleNavClick(id)} title={label}>
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
            <AgentAvatar name={user.first_name ? `${user.first_name} ${user.last_name || ""}`.trim() : user.email} id={user.id || user.email} role="human" size={26} />
            <div style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>
              <div className={styles.userName} title={user.email}>
                {user.first_name ? `${user.first_name} ${user.last_name || ""}`.trim() : user.email}
              </div>
              <div className={styles.userEmail}>{user.email}</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 2, flexShrink: 0 }}>
              <ThemeToggle className={styles.footerActionBtn} />
              <NotificationBell className={styles.footerActionBtn} />
              <button className={`btn btn-icon-sm btn-ghost ${styles.footerActionBtn} ${styles.logoutBtn}`} onClick={logout} title="Sign out">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
                </svg>
              </button>
            </div>
          </div>
        )}
      </div>
      <div
        className={`${styles.resizeHandle} ${isResizing ? styles.isResizing : ""}`}
        onMouseDown={handleMouseDown}
        onDoubleClick={handleDoubleClickHandle}
        title="Drag to resize sidebar · Double click to reset width"
      />
    </nav>
  );
}
