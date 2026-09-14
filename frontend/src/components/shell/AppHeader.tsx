"use client";

import React, { useState } from "react";
import {
  GitBranch,
  FolderGit2,
  Users,
  Terminal,
  FileCode2,
  Globe,
  CheckSquare,
  Maximize2,
  Minimize2,
  Command,
  Bell,
  AlertTriangle,
  Loader2,
  ChevronDown,
  Columns3,
  PanelRightClose,
  PanelRightOpen,
  Sparkles,
  Search,
} from "lucide-react";
import NotificationBell from "@/components/NotificationBell";
import ThemeToggle from "@/components/ThemeToggle";
import styles from "./AppHeader.module.css";

interface AppHeaderProps {
  projects: any[];
  projectId: string | null;
  onProjectChange: (id: string) => void;
  teams: any[];
  teamId: string | null;
  onTeamChange: (id: string) => void;
  connected: boolean;
  activeBranch?: string;
  pendingApprovalsCount?: number;
  runningAgentsCount?: number;
  contextPanelOpen: boolean;
  activeContextTab: "files" | "diff" | "terminal" | "browser" | "task";
  onToggleContextPanel: () => void;
  onSelectContextTab: (tab: "files" | "diff" | "terminal" | "browser" | "task") => void;
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
  onOpenCommandPalette?: () => void;
  activeView: string;
  onViewChange: (view: string) => void;
}

export default function AppHeader({
  projects,
  projectId,
  onProjectChange,
  teams,
  teamId,
  onTeamChange,
  connected,
  activeBranch = "main",
  pendingApprovalsCount = 0,
  runningAgentsCount = 0,
  contextPanelOpen,
  activeContextTab,
  onToggleContextPanel,
  onSelectContextTab,
  isFullscreen,
  onToggleFullscreen,
  onOpenCommandPalette,
  activeView,
  onViewChange,
}: AppHeaderProps) {
  const currentProject = projects.find((p) => p.id === projectId);
  const currentTeam = teams.find((t) => t.id === teamId);

  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  const [teamMenuOpen, setTeamMenuOpen] = useState(false);

  return (
    <header className={styles.header}>
      {/* Left section: Breadcrumb / Project & Team selector */}
      <div className={styles.headerLeft}>
        <div className={styles.projectSelector}>
          <div className={styles.selectorGroup}>
            <button
              className={styles.selectorBtn}
              onClick={() => setProjectMenuOpen((v) => !v)}
              title="Switch project"
            >
              <FolderGit2 size={15} className={styles.selectorIcon} />
              <span className={styles.selectorName}>
                {currentProject?.name || "Select Project"}
              </span>
              <ChevronDown size={12} className={styles.chevron} />
            </button>

            {projectMenuOpen && (
              <>
                <div
                  className={styles.dropdownBackdrop}
                  onClick={() => setProjectMenuOpen(false)}
                />
                <div className={styles.dropdownMenu}>
                  <div className={styles.dropdownHeader}>Projects</div>
                  {projects.map((p) => (
                    <button
                      key={p.id}
                      className={`${styles.dropdownItem} ${
                        p.id === projectId ? styles.dropdownItemActive : ""
                      }`}
                      onClick={() => {
                        onProjectChange(p.id);
                        setProjectMenuOpen(false);
                      }}
                    >
                      <FolderGit2 size={14} />
                      <span>{p.name}</span>
                    </button>
                  ))}
                  {projects.length === 0 && (
                    <div className={styles.dropdownEmpty}>No projects found</div>
                  )}
                </div>
              </>
            )}
          </div>

          <span className={styles.divider}>/</span>

          <div className={styles.selectorGroup}>
            <button
              className={styles.selectorBtn}
              onClick={() => setTeamMenuOpen((v) => !v)}
              title="Switch team room"
            >
              <Users size={15} className={styles.selectorIcon} />
              <span className={styles.selectorName}>
                {currentTeam?.name || "Select Team"}
              </span>
              <ChevronDown size={12} className={styles.chevron} />
            </button>

            {teamMenuOpen && (
              <>
                <div
                  className={styles.dropdownBackdrop}
                  onClick={() => setTeamMenuOpen(false)}
                />
                <div className={styles.dropdownMenu}>
                  <div className={styles.dropdownHeader}>Team Rooms</div>
                  {teams.map((t) => (
                    <button
                      key={t.id}
                      className={`${styles.dropdownItem} ${
                        t.id === teamId ? styles.dropdownItemActive : ""
                      }`}
                      onClick={() => {
                        onTeamChange(t.id);
                        setTeamMenuOpen(false);
                      }}
                    >
                      <Users size={14} />
                      <span>{t.name}</span>
                    </button>
                  ))}
                  {teams.length === 0 && (
                    <div className={styles.dropdownEmpty}>No teams found</div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Active branch or workspace badge */}
        <div
          className={styles.branchBadge}
          title={`Active Branch: ${activeBranch}`}
          onClick={() => onViewChange("git")}
        >
          <GitBranch size={13} />
          <span>{activeBranch}</span>
        </div>

        {/* Real-time Connection beacon */}
        <div
          className={styles.connIndicator}
          title={connected ? "Real-time engine connected" : "Connecting to engine..."}
        >
          <span
            className={`${styles.connDot} ${
              connected ? styles.connLive : styles.connOffline
            }`}
          />
          <span className={styles.connLabel}>
            {connected ? "Live" : "Syncing"}
          </span>
        </div>
      </div>

      {/* Center section: Global Search / Command Bar trigger */}
      <div className={styles.headerCenter}>
        <button
          className={styles.commandTrigger}
          onClick={onOpenCommandPalette}
          title="Open Command Palette (Ctrl+K or ⌘K)"
        >
          <Search size={14} className={styles.searchIcon} />
          <span className={styles.searchPlaceholder}>
            Search conversations, files, tasks, symbols...
          </span>
          <kbd className={styles.kbd}>
            <Command size={11} /> K
          </kbd>
        </button>
      </div>

      {/* Right section: Activity badges, Context panel tabs, Fullscreen */}
      <div className={styles.headerRight}>
        {/* Pending approvals badge */}
        {pendingApprovalsCount > 0 && (
          <button
            className={`${styles.activityPill} ${styles.activityWarning} state-waiting`}
            onClick={() => onViewChange("chat")}
            title={`${pendingApprovalsCount} pending human approval requests`}
          >
            <AlertTriangle size={13} />
            <span>{pendingApprovalsCount} Approval{pendingApprovalsCount > 1 ? "s" : ""}</span>
          </button>
        )}

        {/* Running background tasks badge */}
        {runningAgentsCount > 0 && (
          <button
            className={`${styles.activityPill} ${styles.activityWorking} state-background`}
            onClick={() => onViewChange("chat")}
            title={`${runningAgentsCount} background agent tasks active`}
          >
            <Loader2 size={13} className="animate-spin state-indicator" />
            <span>{runningAgentsCount} Running</span>
          </button>
        )}

        {/* Quick context panel tab controls */}
        <div className={styles.contextTabsGroup}>
          <button
            className={`${styles.contextTabBtn} ${
              contextPanelOpen && activeContextTab === "files"
                ? styles.contextTabActive
                : ""
            }`}
            onClick={() => {
              if (contextPanelOpen && activeContextTab === "files") {
                onToggleContextPanel();
              } else {
                onSelectContextTab("files");
              }
            }}
            title="Toggle File Explorer & Editor"
          >
            <FileCode2 size={14} />
            <span className={styles.tabLabel}>Files</span>
          </button>

          <button
            className={`${styles.contextTabBtn} ${
              contextPanelOpen && activeContextTab === "terminal"
                ? styles.contextTabActive
                : ""
            }`}
            onClick={() => {
              if (contextPanelOpen && activeContextTab === "terminal") {
                onToggleContextPanel();
              } else {
                onSelectContextTab("terminal");
              }
            }}
            title="Toggle Context Terminal"
          >
            <Terminal size={14} />
            <span className={styles.tabLabel}>Terminal</span>
          </button>

          <button
            className={`${styles.contextTabBtn} ${
              contextPanelOpen && activeContextTab === "browser"
                ? styles.contextTabActive
                : ""
            }`}
            onClick={() => {
              if (contextPanelOpen && activeContextTab === "browser") {
                onToggleContextPanel();
              } else {
                onSelectContextTab("browser");
              }
            }}
            title="Toggle Browser Inspection"
          >
            <Globe size={14} />
            <span className={styles.tabLabel}>Browser</span>
          </button>

          <button
            className={`${styles.panelToggleBtn} ${
              contextPanelOpen ? styles.panelOpen : ""
            }`}
            onClick={onToggleContextPanel}
            title={contextPanelOpen ? "Collapse Context Panel" : "Expand Context Panel"}
          >
            {contextPanelOpen ? (
              <PanelRightClose size={15} />
            ) : (
              <PanelRightOpen size={15} />
            )}
          </button>
        </div>

        <div className={styles.headerDividers} />

        {/* Notifications & Theme */}
        <NotificationBell />
        <ThemeToggle />

        {/* Fullscreen Toggle */}
        <button
          className={styles.iconBtn}
          onClick={onToggleFullscreen}
          title={isFullscreen ? "Exit Fullscreen" : "Enter Fullscreen"}
          aria-label={isFullscreen ? "Exit Fullscreen" : "Enter Fullscreen"}
        >
          {isFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
        </button>
      </div>
    </header>
  );
}
