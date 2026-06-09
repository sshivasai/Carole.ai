"use client";
import React from "react";
import {
  MessageSquare, LayoutGrid, Brain, Globe, Settings,
  Zap, Plus, ChevronDown,
} from "lucide-react";
import styles from "./Sidebar.module.css";

interface Props {
  activeView: string;
  onViewChange: (v: string) => void;
  connected: boolean;
  projects: any[];
  projectId: string | null;
  onProjectChange: (id: string) => void;
  onAddProject: () => void;
  teams: any[];
  teamId: string | null;
  onTeamChange: (id: string) => void;
  onAddTeam: () => void;
}

const NAV = [
  { id: "chat",     label: "Chat Room",      Icon: MessageSquare },
  { id: "tasks",    label: "Task Board",     Icon: LayoutGrid },
  { id: "browser",  label: "Browser View",   Icon: Globe },
  { id: "memory",   label: "Memory & Logs",  Icon: Brain },
  { id: "agents",   label: "Agents",         Icon: Zap },
  { id: "settings", label: "Settings",       Icon: Settings },
];

export default function Sidebar({
  activeView, onViewChange, connected,
  projects, projectId, onProjectChange, onAddProject,
  teams, teamId, onTeamChange, onAddTeam,
}: Props) {
  return (
    <nav className={styles.sidebar}>
      {/* Logo */}
      <div className={styles.sidebarLogo}>
        <div className={styles.sidebarLogoMark}>C</div>
        <div>
          <div className={styles.sidebarLogoText}>Carole.ai</div>
          <div className={styles.sidebarLogoSub}>v0.2 · multi-agent</div>
        </div>
      </div>

      {/* Project Selector */}
      <div className={styles.entityBlock}>
        <div className={styles.entityLabel}>Project</div>
        <select
          className={styles.entitySelect}
          value={projectId || ""}
          onChange={e => onProjectChange(e.target.value)}
        >
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          {projects.length === 0 && <option value="">No projects</option>}
        </select>
        <button className={styles.entityAddBtn} onClick={onAddProject}>
          <Plus size={12} /> New project
        </button>
      </div>

      {/* Team Selector */}
      <div className={styles.entityBlock}>
        <div className={styles.entityLabel}>Team Room</div>
        <select
          className={styles.entitySelect}
          value={teamId || ""}
          onChange={e => onTeamChange(e.target.value)}
        >
          {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          {teams.length === 0 && <option value="">No teams</option>}
        </select>
        <button className={styles.entityAddBtn} onClick={onAddTeam}>
          <Plus size={12} /> New team
        </button>
      </div>

      {/* Nav */}
      <div className={styles.sidebarNav}>
        <div className={styles.sidebarSection}>
          <span className={styles.sidebarSectionLabel}>Workspace</span>
        </div>
        {NAV.map(({ id, label, Icon }) => (
          <button
            key={id}
            className={`${styles.navItem} ${activeView === id ? styles.active : ""}`}
            onClick={() => onViewChange(id)}
          >
            <Icon className={styles.navItemIcon} size={16} />
            {label}
          </button>
        ))}
      </div>

      {/* Connection Badge */}
      <div className={styles.connBadge}>
        <div className={`${styles.connDot} ${connected ? styles.live : styles.offline}`} />
        {connected ? "Live connection" : "Connecting..."}
      </div>
    </nav>
  );
}
