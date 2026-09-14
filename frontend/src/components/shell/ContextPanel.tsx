"use client";

import React, { useState } from "react";
import {
  FileCode2,
  GitCompare,
  Terminal as TerminalIcon,
  Globe,
  X,
  Maximize2,
  Minimize2,
  ExternalLink,
  ChevronRight,
  CheckCircle2,
} from "lucide-react";
import FileExplorerPanel from "@/components/FileExplorerPanel";
import TerminalPanel from "@/components/TerminalPanel";
import BrowserView from "@/components/BrowserView";
import { DiffViewer } from "@/components/DiffViewer";
import type { BrowserScreenshotEvent } from "@/lib/types";
import styles from "./ContextPanel.module.css";

export type ContextPanelTab = "files" | "diff" | "terminal" | "browser" | "task";

interface ContextPanelProps {
  activeTab: ContextPanelTab;
  onSelectTab: (tab: ContextPanelTab) => void;
  onClose: () => void;
  projectId?: string;
  teamId?: string;
  lastFileChange?: any;
  pendingOpenFile?: string | null;
  onPendingOpenConsumed?: () => void;
  pendingOpenDiffFile?: { path: string; originalContent: string; diff?: string } | null;
  onPendingOpenDiffConsumed?: () => void;
  onAppendToChat?: (text: string) => void;
  screenshots?: BrowserScreenshotEvent[];
  isMaximized?: boolean;
  onToggleMaximize?: () => void;
}

export default function ContextPanel({
  activeTab,
  onSelectTab,
  onClose,
  projectId,
  teamId,
  lastFileChange,
  pendingOpenFile,
  onPendingOpenConsumed,
  pendingOpenDiffFile,
  onPendingOpenDiffConsumed,
  onAppendToChat,
  screenshots = [],
  isMaximized = false,
  onToggleMaximize,
}: ContextPanelProps) {
  const [terminalShell, setTerminalShell] = useState<"default" | "bash" | "powershell">("default");

  return (
    <aside className={styles.contextPanel} aria-label="Context Panel">
      {/* Context Panel Top Tab Bar */}
      <div className={styles.tabBar}>
        <div className={styles.tabList}>
          <button
            className={`${styles.tabBtn} ${activeTab === "files" ? styles.tabActive : ""}`}
            onClick={() => onSelectTab("files")}
            title="File Tree and Code Editor"
          >
            <FileCode2 size={13} />
            <span>Files & Code</span>
          </button>

          <button
            className={`${styles.tabBtn} ${activeTab === "diff" ? styles.tabActive : ""}`}
            onClick={() => onSelectTab("diff")}
            title="Diff Review & Changes"
          >
            <GitCompare size={13} />
            <span>Diff Review</span>
            {pendingOpenDiffFile && <span className={styles.activeDot} />}
          </button>

          <button
            className={`${styles.tabBtn} ${activeTab === "terminal" ? styles.tabActive : ""}`}
            onClick={() => onSelectTab("terminal")}
            title="Terminal Workspace"
          >
            <TerminalIcon size={13} />
            <span>Terminal</span>
          </button>

          <button
            className={`${styles.tabBtn} ${activeTab === "browser" ? styles.tabActive : ""}`}
            onClick={() => onSelectTab("browser")}
            title="Browser Work & Checkpoints"
          >
            <Globe size={13} />
            <span>Browser</span>
            {screenshots.length > 0 && (
              <span className={styles.countBadge}>{screenshots.length}</span>
            )}
          </button>
        </div>

        {/* Action Controls: Maximize & Close */}
        <div className={styles.panelActions}>
          {onToggleMaximize && (
            <button
              className={styles.actionBtn}
              onClick={onToggleMaximize}
              title={isMaximized ? "Restore size" : "Maximize panel"}
              aria-label={isMaximized ? "Restore size" : "Maximize panel"}
            >
              {isMaximized ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
            </button>
          )}
          <button
            className={`${styles.actionBtn} ${styles.closeBtn}`}
            onClick={onClose}
            title="Close Context Panel"
            aria-label="Close Context Panel"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Main Content Surface */}
      <div className={styles.contentSurface}>
        {activeTab === "files" && (
          <FileExplorerPanel
            onClose={onClose}
            projectId={projectId}
            teamId={teamId}
            lastFileChange={lastFileChange}
            pendingOpenFile={pendingOpenFile}
            onPendingOpenConsumed={onPendingOpenConsumed}
            pendingOpenDiffFile={pendingOpenDiffFile}
            onPendingOpenDiffConsumed={onPendingOpenDiffConsumed}
            onAppendToChat={onAppendToChat}
          />
        )}

        {activeTab === "diff" && (
          <div className={styles.diffWrapper}>
            {pendingOpenDiffFile?.diff ? (
              <div className={styles.diffContainer}>
                <div className={styles.diffHeader}>
                  <div className={styles.diffPath}>
                    <GitCompare size={14} className={styles.diffIcon} />
                    <span className={styles.diffPathText}>{pendingOpenDiffFile.path}</span>
                  </div>
                  <span className="state-badge state-working">Reviewing changes</span>
                </div>
                <div className={styles.diffScroll}>
                  <DiffViewer
                    diff={pendingOpenDiffFile.diff}
                    path={pendingOpenDiffFile.path}
                    maxLinesVisible={500}
                  />
                </div>
              </div>
            ) : (
              <div className={styles.emptyDiff}>
                <GitCompare size={36} className={styles.emptyIcon} />
                <h4>No Active Diff</h4>
                <p>
                  Click on any file change card in the team conversation to review side-by-side
                  patches and code changes here.
                </p>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => onSelectTab("files")}
                  style={{ marginTop: 12 }}
                >
                  <FileCode2 size={13} /> Open File Explorer
                </button>
              </div>
            )}
          </div>
        )}

        {activeTab === "terminal" && (
          <div className={styles.terminalWrapper}>
            <div className={styles.terminalHeader}>
              <div className={styles.terminalTitle}>
                <TerminalIcon size={14} style={{ color: "var(--color-primary-soft)" }} />
                <span>Agent & Workspace Terminal</span>
              </div>
              <div className={styles.shellSelector}>
                <button
                  className={`${styles.shellPill} ${terminalShell === "default" ? styles.shellActive : ""}`}
                  onClick={() => setTerminalShell("default")}
                >
                  Default
                </button>
                <button
                  className={`${styles.shellPill} ${terminalShell === "bash" ? styles.shellActive : ""}`}
                  onClick={() => setTerminalShell("bash")}
                >
                  Bash
                </button>
                <button
                  className={`${styles.shellPill} ${terminalShell === "powershell" ? styles.shellActive : ""}`}
                  onClick={() => setTerminalShell("powershell")}
                >
                  PowerShell
                </button>
              </div>
            </div>
            <div className={styles.terminalBody}>
              <TerminalPanel
                projectId={projectId}
                onClose={onClose}
                shell={terminalShell}
              />
            </div>
          </div>
        )}

        {activeTab === "browser" && (
          <div className={styles.browserWrapper}>
            <BrowserView screenshots={screenshots} />
          </div>
        )}
      </div>
    </aside>
  );
}
