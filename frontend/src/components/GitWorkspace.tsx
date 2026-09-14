"use client";

import React, { useState, useEffect } from "react";
import {
  GitBranch,
  GitCommit,
  GitPullRequest,
  RefreshCw,
  Plus,
  Minus,
  Check,
  RotateCcw,
  ArrowUp,
  ArrowDown,
  Clock,
  FileCode,
  MessageSquare,
  ChevronRight,
  Sparkles,
} from "lucide-react";
import { api } from "@/hooks/useApi";
import GitPanel from "./GitPanel";
import { DiffViewer } from "./DiffViewer";
import styles from "./GitWorkspace.module.css";

interface GitWorkspaceProps {
  projectId?: string | null;
  onNavigateToChat?: () => void;
  onOpenFile?: (path: string) => void;
  onOpenDiffFile?: (path: string, originalContent: string) => void;
  lastFileChange?: any;
}

export default function GitWorkspace({
  projectId,
  onNavigateToChat,
  onOpenFile,
  onOpenDiffFile,
  lastFileChange,
}: GitWorkspaceProps) {
  const [activeBranch, setActiveBranch] = useState("main");
  const [aheadBehind, setAheadBehind] = useState({ ahead: 0, behind: 0 });
  const [isSyncing, setIsSyncing] = useState(false);

  return (
    <div className={styles.workspace}>
      {/* Top Header */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.titleGroup}>
            <div className={styles.iconCircle}>
              <GitBranch size={16} />
            </div>
            <div>
              <h2 className={styles.title}>Source Control & Git Workspace</h2>
              <p className={styles.subtitle}>
                Review staging, diffs, branch status, and commit checkpoints
              </p>
            </div>
          </div>

          <div className={styles.branchPill}>
            <GitBranch size={13} />
            <span className={styles.branchName}>{activeBranch}</span>
            <span className={styles.upstreamStatus}>
              {aheadBehind.ahead > 0 && <span>↑{aheadBehind.ahead}</span>}
              {aheadBehind.behind > 0 && <span>↓{aheadBehind.behind}</span>}
              {aheadBehind.ahead === 0 && aheadBehind.behind === 0 && (
                <span className={styles.upToDate}>Up to date with origin</span>
              )}
            </span>
          </div>
        </div>

        <div className={styles.headerActions}>
          {onNavigateToChat && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={onNavigateToChat}
              title="Return to active conversation"
            >
              <MessageSquare size={13} />
              <span>Back to Chat</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Git Content */}
      <div className={styles.body}>
        <GitPanel
          projectId={projectId || undefined}
          onOpenFile={onOpenFile}
          onOpenDiffFile={onOpenDiffFile}
          lastFileChange={lastFileChange}
        />
      </div>
    </div>
  );
}
