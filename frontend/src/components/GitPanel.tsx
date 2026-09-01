"use client";

import React, { useState, useEffect, useRef } from "react";
import { api } from "@/hooks/useApi";
import { 
  GitBranch, 
  RefreshCw, 
  Check, 
  AlertCircle, 
  X, 
  ChevronDown, 
  ChevronRight,
  Plus, 
  Minus, 
  Trash2, 
  FileText, 
  User, 
  Calendar,
  Eye,
  FileCode
} from "lucide-react";

interface GitPanelProps {
  projectId?: string;
  onClose?: () => void;
  onOpenFile?: (path: string) => void;
  onOpenDiffFile?: (path: string, originalContent: string) => void;
  lastFileChange?: any;
}

interface GitChange {
  file: string;
  status: string;
  staged: boolean;
  unstaged: boolean;
  raw_x?: string;
  raw_y?: string;
}

interface CommitItem {
  hash: string;
  author: string;
  date: string;
  message: string;
}

interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  change: GitChange;
}

export default function GitPanel({ projectId, onClose, onOpenFile, onOpenDiffFile, lastFileChange }: GitPanelProps) {
  const [changes, setChanges] = useState<GitChange[]>([]);
  const [commits, setCommits] = useState<CommitItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingCommits, setLoadingCommits] = useState(false);
  const [commitMessage, setCommitMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  // Collapse sections
  const [stagedCollapsed, setStagedCollapsed] = useState(false);
  const [changesCollapsed, setChangesCollapsed] = useState(false);
  const [historyCollapsed, setHistoryCollapsed] = useState(false);

  const [projectName, setProjectName] = useState<string | null>(null);

  // Custom Context Menu State
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (projectId) {
      api.getProject(projectId)
        .then(res => {
          let slug = res.name.replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
          if (!slug) slug = projectId.substring(0, 8);
          setProjectName(slug);
        })
        .catch(() => setProjectName("project"));
    } else {
      setProjectName(null);
    }
  }, [projectId]);

  const fetchCommits = async () => {
    if (!projectName) return;
    setLoadingCommits(true);
    try {
      const res = await api.getGitLog(projectName);
      if (res.status === "success") {
        setCommits(res.commits || []);
      }
    } catch (err) {
      console.error("Error fetching git commits:", err);
    } finally {
      setLoadingCommits(false);
    }
  };

  const fetchStatus = async () => {
    if (!projectName) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.getGitStatus(projectName);
      if (res.status === "success") {
        setChanges(res.changes || []);
        if (res.message && res.changes?.length === 0) {
           setError(res.message);
        }
      } else {
        setError(res.message || "Failed to fetch git status");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Error fetching git status";
      setError(msg);
    } finally {
      setLoading(false);
      void fetchCommits();
    }
  };

  useEffect(() => {
    if (projectName) {
      void fetchStatus();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectName, lastFileChange]);

  // Click outside to close context menu
  useEffect(() => {
    const handleGlobalClick = (e: MouseEvent) => {
      if (contextMenu && menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setContextMenu(null);
      }
    };
    document.addEventListener("click", handleGlobalClick);
    return () => document.removeEventListener("click", handleGlobalClick);
  }, [contextMenu]);

  const handleInit = async () => {
    if (!projectName) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.initGit(projectName);
      if (res.status === "success") {
        setSuccess("Repository initialized!");
        await fetchStatus();
      } else {
        setError(res.message || "Init failed");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error initializing repository");
    } finally {
      setLoading(false);
    }
  };

  const handleStage = async (file: string) => {
    if (!projectName) return;
    setLoading(true);
    try {
      const res = await api.stageFile(file, projectName);
      if (res.status === "success") {
        setSuccess(`Staged ${file}`);
        await fetchStatus();
      } else {
        setError(res.message || "Stage failed");
      }
    } catch (err: any) {
      setError(err.message || "Failed to stage file");
    } finally {
      setLoading(false);
    }
  };

  const handleUnstage = async (file: string) => {
    if (!projectName) return;
    setLoading(true);
    try {
      const res = await api.unstageFile(file, projectName);
      if (res.status === "success") {
        setSuccess(`Unstaged ${file}`);
        await fetchStatus();
      } else {
        setError(res.message || "Unstage failed");
      }
    } catch (err: any) {
      setError(err.message || "Failed to unstage file");
    } finally {
      setLoading(false);
    }
  };

  const handleDiscard = async (file: string) => {
    if (!projectName) return;
    if (!confirm(`Are you sure you want to discard all changes in ${file}? This cannot be undone.`)) return;
    
    setLoading(true);
    try {
      const res = await api.discardChanges(file, projectName);
      if (res.status === "success") {
        setSuccess(`Discarded changes in ${file}`);
        await fetchStatus();
      } else {
        setError(res.message || "Discard failed");
      }
    } catch (err: any) {
      setError(err.message || "Failed to discard changes");
    } finally {
      setLoading(false);
    }
  };

  const handleIgnore = async (file: string) => {
    if (!projectName) return;
    setLoading(true);
    try {
      const res = await api.ignoreFile(file, projectName);
      if (res.status === "success") {
        setSuccess(`Added ${file} to .gitignore`);
        await fetchStatus();
      } else {
        setError(res.message || "Failed to ignore");
      }
    } catch (err: any) {
      setError(err.message || "Failed to ignore file");
    } finally {
      setLoading(false);
    }
  };

  const handleStageAll = async () => {
    await handleStage(".");
  };

  const handleDiscardAll = async () => {
    if (!confirm("Are you sure you want to discard ALL unstaged changes? This cannot be undone.")) return;
    const unstaged = changes.filter(c => c.unstaged);
    setLoading(true);
    try {
      for (const item of unstaged) {
        await api.discardChanges(item.file, projectName!);
      }
      setSuccess("Discarded all changes.");
      await fetchStatus();
    } catch (err: any) {
      setError(err.message || "Failed to discard all changes");
    } finally {
      setLoading(false);
    }
  };

  const handleCommit = async () => {
    if (!commitMessage.trim() || !projectName) return;
    
    setLoading(true);
    setError(null);
    setSuccess(null);
    
    try {
      const res = await api.commitChanges(commitMessage, projectName);
      if (res.status === "success") {
        setSuccess("Committed successfully!");
        setCommitMessage("");
        await fetchStatus();
      } else {
        setError(res.message || "Commit failed");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Error committing changes";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenFile = (file: string) => {
    if (onOpenFile) {
      onOpenFile(file);
    }
  };

  const openDiffView = async (change: GitChange) => {
    if (!projectName) return;
    try {
       // Load original content
       let original = "";
       if (!(change.status.includes('A') || change.raw_x === "?" || change.raw_y === "?")) {
         const origRes = await api.getGitFileContent(change.file, projectName);
         original = origRes.content || "";
       }
       if (onOpenDiffFile) {
         onOpenDiffFile(change.file, original);
       }
    } catch (err) {
       console.error("Failed to load diff original:", err);
       if (onOpenDiffFile) {
         onOpenDiffFile(change.file, "Error loading original git revision.");
       }
    }
  };

  const handleRightClick = (e: React.MouseEvent, change: GitChange) => {
    e.preventDefault();
    setContextMenu({
      visible: true,
      x: e.clientX,
      y: e.clientY,
      change
    });
  };

  const stagedChanges = changes.filter(c => c.staged);
  const unstagedChanges = changes.filter(c => c.unstaged);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "transparent", color: "var(--color-ink)", fontFamily: "var(--font-mono, monospace)", fontSize: 12, position: "relative", width: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 12px", background: "var(--bg-glass-card)", borderBottom: "1px solid var(--border-glass)", backdropFilter: "var(--blur-md)", WebkitBackdropFilter: "var(--blur-md)", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1 }}>
          <GitBranch size={14} className="text-gray-400" />
          <span style={{ fontWeight: 600, fontSize: 11 }}>Source Control</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button 
            onClick={() => void fetchStatus()}
            className="text-gray-400 hover:text-white"
            title="Refresh"
            style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 4, background: "none", border: "none", cursor: "pointer", color: "var(--color-mute)" }}
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
          {onClose && (
            <button 
              onClick={onClose}
              className="text-gray-400 hover:text-white"
              title="Close Panel"
              style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 4, background: "none", border: "none", cursor: "pointer", color: "var(--color-mute)" }}
            >
              <X size={13} />
            </button>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div style={{ flex: 1, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 14 }}>
      
        {/* Commit Input Area */}
        <div style={{ display: "flex", flexDirection: "column", gap: 6, background: "var(--bg-glass-card)", border: "1px solid var(--border-glass)", borderRadius: "var(--radius-md)", padding: 8 }}>
          <textarea 
            value={commitMessage}
            onChange={e => setCommitMessage(e.target.value)}
            placeholder="Commit message (Ctrl+Enter to commit)"
            style={{
              width: "100%",
              minHeight: "50px",
              background: "var(--bg-glass-panel)",
              border: "1px solid var(--border-glass)",
              color: "var(--color-ink)",
              padding: "6px",
              borderRadius: "4px",
              resize: "vertical",
              outline: "none",
              fontFamily: "inherit",
              fontSize: "11px"
            }}
            disabled={loading || changes.length === 0}
            onKeyDown={e => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                void handleCommit();
              }
            }}
          />
          <button
            onClick={() => void handleCommit()}
            disabled={loading || changes.length === 0 || !commitMessage.trim()}
            style={{
              background: changes.length === 0 || !commitMessage.trim() ? "var(--bg-glass-panel)" : "var(--color-primary)",
              color: changes.length === 0 || !commitMessage.trim() ? "var(--color-mute)" : "var(--color-on-primary)",
              border: "1px solid var(--border-glass)",
              padding: "5px 10px",
              borderRadius: "4px",
              cursor: changes.length === 0 || !commitMessage.trim() ? "not-allowed" : "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 5,
              fontWeight: "bold",
              fontSize: "11px"
            }}
          >
            <Check size={12} />
            Commit
          </button>
        </div>

        {/* Status Messages */}
        {error && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, color: "#f87171", background: "rgba(239, 68, 68, 0.15)", border: "1px solid rgba(239, 68, 68, 0.3)", padding: "6px 8px", borderRadius: "4px" }}>
              <AlertCircle size={13} style={{ flexShrink: 0 }} />
              <span>{error}</span>
            </div>
            {error.includes("Not a git repository") && (
              <button
                onClick={() => void handleInit()}
                disabled={loading}
                style={{
                  background: "var(--color-primary)", color: "var(--color-on-primary)", border: "none", padding: "6px 12px",
                  borderRadius: "4px", cursor: "pointer", fontWeight: "bold", fontSize: 11
                }}
              >
                Initialize Repository
              </button>
            )}
          </div>
        )}
        {success && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, color: "#34d399", background: "rgba(52, 211, 153, 0.15)", border: "1px solid rgba(52, 211, 153, 0.3)", padding: "6px 8px", borderRadius: "4px" }}>
            <Check size={13} style={{ flexShrink: 0 }} />
            <span>{success}</span>
          </div>
        )}

        {/* Staged Changes List */}
        {projectName && !error && (
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontWeight: "bold", marginBottom: 6, color: "var(--color-body)", borderBottom: "1px solid var(--border-glass)", paddingBottom: 4 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer", flex: 1 }} onClick={() => setStagedCollapsed(!stagedCollapsed)}>
                {stagedCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                <span>Staged Changes ({stagedChanges.length})</span>
              </div>
              {stagedChanges.length > 0 && (
                <button 
                  onClick={async () => {
                    setLoading(true);
                    for (const c of stagedChanges) {
                      await api.unstageFile(c.file, projectName!);
                    }
                    await fetchStatus();
                  }}
                  style={{ background: "none", border: "none", color: "var(--color-mute)", cursor: "pointer", display: "flex", padding: 2 }}
                  title="Unstage All Changes"
                >
                  <Minus size={13} />
                </button>
              )}
            </div>
            
            {!stagedCollapsed && (
              stagedChanges.length === 0 ? (
                <div style={{ color: "var(--color-mute)", fontStyle: "italic", padding: "6px 0", fontSize: 11 }}>
                  No staged changes.
                </div>
              ) : (
                <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 3 }}>
                  {stagedChanges.map((change, idx) => (
                    <li 
                      key={idx} 
                      onClick={() => openDiffView(change)}
                      onContextMenu={(e) => handleRightClick(e, change)}
                      style={{ display: "flex", alignItems: "center", justifyItems: "center", gap: 6, padding: "4px 8px", background: "var(--bg-glass-card)", border: "1px solid var(--border-glass)", borderRadius: "4px", cursor: "pointer" }}
                      className="hover:bg-[#2a2d2e] transition-colors"
                    >
                      <span style={{ 
                        color: change.status === "A" ? "#34d399" : change.status === "D" ? "#f87171" : "#fbbf24",
                        fontWeight: "bold",
                        width: "12px",
                        textAlign: "center"
                      }}>
                        {change.status}
                      </span>
                      <span className="truncate" style={{ flex: 1 }}>{change.file}</span>
                    </li>
                  ))}
                </ul>
              )
            )}
          </div>
        )}

        {/* Unstaged Changes List */}
        {projectName && !error && (
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontWeight: "bold", marginBottom: 6, color: "var(--color-body)", borderBottom: "1px solid var(--border-glass)", paddingBottom: 4 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer", flex: 1 }} onClick={() => setChangesCollapsed(!changesCollapsed)}>
                {changesCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                <span>Changes ({unstagedChanges.length})</span>
              </div>
              {unstagedChanges.length > 0 && (
                <div style={{ display: "flex", gap: 6 }}>
                  <button 
                    onClick={handleStageAll}
                    style={{ background: "none", border: "none", color: "var(--color-mute)", cursor: "pointer", display: "flex", padding: 2 }}
                    title="Stage All Changes"
                  >
                    <Plus size={13} />
                  </button>
                  <button 
                    onClick={handleDiscardAll}
                    style={{ background: "none", border: "none", color: "var(--color-mute)", cursor: "pointer", display: "flex", padding: 2 }}
                    title="Discard All Changes"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              )}
            </div>
            
            {!changesCollapsed && (
              unstagedChanges.length === 0 ? (
                <div style={{ color: "var(--color-mute)", fontStyle: "italic", padding: "6px 0", fontSize: 11 }}>
                  No unstaged changes.
                </div>
              ) : (
                <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 3 }}>
                  {unstagedChanges.map((change, idx) => (
                    <li 
                      key={idx} 
                      onClick={() => openDiffView(change)}
                      onContextMenu={(e) => handleRightClick(e, change)}
                      style={{ display: "flex", alignItems: "center", justifyItems: "center", gap: 6, padding: "4px 8px", background: "var(--bg-glass-card)", border: "1px solid var(--border-glass)", borderRadius: "4px", cursor: "pointer" }}
                      className="hover:bg-[#2a2d2e] transition-colors"
                    >
                      <span style={{ 
                        color: change.status === "A" ? "#34d399" : change.status === "D" ? "#f87171" : "#fbbf24",
                        fontWeight: "bold",
                        width: "12px",
                        textAlign: "center"
                      }}>
                        {change.status === "A" ? "U" : change.status}
                      </span>
                      <span className="truncate" style={{ flex: 1 }}>{change.file}</span>
                    </li>
                  ))}
                </ul>
              )
            )}
          </div>
        )}

        {/* Commit History (Timeline Graph) */}
        {projectName && !error && (
          <div>
            <div 
              style={{ display: "flex", alignItems: "center", gap: 4, fontWeight: "bold", marginBottom: 6, color: "var(--color-body)", borderBottom: "1px solid var(--border-glass)", paddingBottom: 4, cursor: "pointer" }} 
              onClick={() => setHistoryCollapsed(!historyCollapsed)}
            >
              {historyCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
              <span>Commit History ({commits.length})</span>
            </div>
            
            {!historyCollapsed && (
              loadingCommits ? (
                <div style={{ color: "var(--color-mute)", fontStyle: "italic", padding: "6px 0", fontSize: 11 }}>
                  Loading commit logs...
                </div>
              ) : commits.length === 0 ? (
                <div style={{ color: "var(--color-mute)", fontStyle: "italic", padding: "6px 0", fontSize: 11 }}>
                  No commits yet.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingLeft: 6, borderLeft: "1px solid var(--border-glass)", marginLeft: 6 }}>
                  {commits.map((commit, idx) => (
                    <div key={idx} style={{ position: "relative", display: "flex", flexDirection: "column", gap: 2 }}>
                      {/* Timeline Node Icon */}
                      <div style={{ position: "absolute", left: -12, top: 4, width: 10, height: 10, borderRadius: "50%", background: "var(--color-primary)", border: "2px solid var(--bg-app)" }}></div>
                      
                      <div style={{ display: "flex", justifyItems: "center", gap: 6, fontSize: "11px", fontWeight: "bold", color: "var(--color-body)" }}>
                        <span className="truncate" style={{ flex: 1 }} title={commit.message}>{commit.message}</span>
                        <span style={{ color: "var(--color-mute)", opacity: 0.6 }}>{commit.hash}</span>
                      </div>
                      
                      <div style={{ display: "flex", gap: 8, fontSize: "10px", color: "var(--color-mute)", opacity: 0.8 }}>
                        <span style={{ display: "flex", alignItems: "center", gap: 3 }}><User size={10} />{commit.author}</span>
                        <span style={{ display: "flex", alignItems: "center", gap: 3 }}><Calendar size={10} />{commit.date}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )
            )}
          </div>
        )}

      </div>

      {/* Floating Custom Context Menu */}
      {contextMenu && (
        <div 
          ref={menuRef}
          style={{
            position: "fixed",
            top: contextMenu.y,
            left: contextMenu.x,
            background: "#1e1e2e",
            border: "1px solid var(--border-glass)",
            borderRadius: "4px",
            boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
            padding: "4px 0",
            zIndex: 9999,
            minWidth: 150,
            display: "flex",
            flexDirection: "column"
          }}
        >
          <button 
            onClick={() => {
              openDiffView(contextMenu.change);
              setContextMenu(null);
            }}
            style={{
              padding: "6px 12px",
              textAlign: "left",
              background: "none",
              border: "none",
              color: "#fff",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontSize: 11
            }}
            className="hover:bg-[#2d2d3f]"
          >
            <Eye size={12} />
            Open Changes
          </button>
          
          <button 
            onClick={() => {
              handleOpenFile(contextMenu.change.file);
              setContextMenu(null);
            }}
            style={{
              padding: "6px 12px",
              textAlign: "left",
              background: "none",
              border: "none",
              color: "#fff",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontSize: 11
            }}
            className="hover:bg-[#2d2d3f]"
          >
            <FileCode size={12} />
            Open File
          </button>

          <hr style={{ border: "none", borderTop: "1px solid #2d2d3f", margin: "4px 0" }} />

          {contextMenu.change.unstaged && (
            <button 
              onClick={() => {
                void handleStage(contextMenu.change.file);
                setContextMenu(null);
              }}
              style={{
                padding: "6px 12px",
                textAlign: "left",
                background: "none",
                border: "none",
                color: "#fff",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 11
              }}
              className="hover:bg-[#2d2d3f]"
            >
              <Plus size={12} />
              Stage Changes
            </button>
          )}

          {contextMenu.change.staged && (
            <button 
              onClick={() => {
                void handleUnstage(contextMenu.change.file);
                setContextMenu(null);
              }}
              style={{
                padding: "6px 12px",
                textAlign: "left",
                background: "none",
                border: "none",
                color: "#fff",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 11
              }}
              className="hover:bg-[#2d2d3f]"
            >
              <Minus size={12} />
              Unstage Changes
            </button>
          )}

          {contextMenu.change.unstaged && (
            <>
              <button 
                onClick={() => {
                  void handleDiscard(contextMenu.change.file);
                  setContextMenu(null);
                }}
                style={{
                  padding: "6px 12px",
                  textAlign: "left",
                  background: "none",
                  border: "none",
                  color: "#f87171",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  fontSize: 11
                }}
                className="hover:bg-[#2d2d3f]"
              >
                <Trash2 size={12} />
                Discard Changes
              </button>
              
              <button 
                onClick={() => {
                  void handleIgnore(contextMenu.change.file);
                  setContextMenu(null);
                }}
                style={{
                  padding: "6px 12px",
                  textAlign: "left",
                  background: "none",
                  border: "none",
                  color: "#fff",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  fontSize: 11
                }}
                className="hover:bg-[#2d2d3f]"
              >
                <FileText size={12} />
                Add to .gitignore
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
