import React, { useState, useEffect } from "react";
import { Folder, File, ChevronRight, ChevronDown, RefreshCw, X, Terminal as TerminalIcon, Maximize2, Minimize2, Search, GitBranch, LayoutList, Activity, Eye, Pencil, RefreshCcwDot } from "lucide-react";
import { PanelGroup, Panel, PanelResizeHandle } from "react-resizable-panels";
import { api } from "@/hooks/useApi";
import Editor from "@monaco-editor/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import TerminalPanel from "./TerminalPanel";
import GitPanel from "./GitPanel";
import SearchPanel from "./SearchPanel";
import ActivityLogPanel from "./ActivityLogPanel";
import Modal from "./Modal";
import { useToast } from "@/hooks/useToast";

function getLanguageFromPath(path: string): string {
  const extension = path.split('.').pop()?.toLowerCase();
  switch (extension) {
    case 'ts':
    case 'tsx':
      return 'typescript';
    case 'js':
    case 'jsx':
      return 'javascript';
    case 'py':
      return 'python';
    case 'json':
      return 'json';
    case 'html':
      return 'html';
    case 'css':
      return 'css';
    case 'md':
      return 'markdown';
    case 'yml':
    case 'yaml':
      return 'yaml';
    case 'sh':
      return 'shell';
    case 'rs':
      return 'rust';
    case 'go':
      return 'go';
    case 'java':
      return 'java';
    case 'c':
    case 'cpp':
    case 'h':
    case 'hpp':
      return 'cpp';
    default:
      return 'plaintext';
  }
}

interface FileItem {
  name: string;
  is_dir: boolean;
  size: number;
  path: string;
}

interface FileExplorerPanelProps {
  onClose?: () => void;
  projectId?: string;
  teamId?: string;
  /** Latest file_change WS event (agent wrote a file). Drives realtime sync. */
  lastFileChange?: { path: string; after_content?: string; action?: string; sender_name?: string; _seq?: number } | null;
  /** A path to open automatically (e.g. user clicked a file-change card in chat). */
  pendingOpenFile?: string | null;
  /** Called after pendingOpenFile has been consumed. */
  onPendingOpenConsumed?: () => void;
}

interface ContextMenuState {
  x: number;
  y: number;
  path: string;
  isDir: boolean;
}

interface OpenFile {
  path: string;
  content: string;
  isDirty: boolean;
  /** When a remote update arrives while the file is dirty, stash it here. */
  staleRemote?: { content: string; sender: string } | null;
}

const isMarkdownPath = (path: string) => /\.(md|markdown|txt|docx|pdf)$/i.test(path);

export default function FileExplorerPanel({ onClose, projectId, teamId, lastFileChange, pendingOpenFile, onPendingOpenConsumed }: FileExplorerPanelProps) {
  const { addToast } = useToast();
  // Tabs and Layout State
  const [activeLeftTab, setActiveLeftTab] = useState<"explorer" | "search" | "git" | "activity">("explorer");
  const [isFullScreen, setIsFullScreen] = useState(false);

  // Editor State
  const [openFiles, setOpenFiles] = useState<OpenFile[]>([]);
  const [activeFilePath, setActiveFilePath] = useState<string | null>(null);
  const [loadingContent, setLoadingContent] = useState(false);
  const [saving, setSaving] = useState(false);
  // "preview" renders rendered markdown; "edit" shows the Monaco editor. Only
  // meaningful for .md/.txt files — code files always use the editor.
  const [viewMode, setViewMode] = useState<"preview" | "edit">("preview");

  // Explorer State
  const [refreshKey, setRefreshKey] = useState(0);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);

  // Terminal State
  const [showTerminal, setShowTerminal] = useState(false);
  const [terminalCmd, setTerminalCmd] = useState<{ cmd: string; ts: number } | null>(null);

  // Project State
  const [projectName, setProjectName] = useState<string | null>(null);

  // Dialog State
  const [dialog, setDialog] = useState<{
    visible: boolean;
    type: "delete" | "rename" | "new_file" | "new_folder";
    path: string;
    inputValue: string;
  }>({
    visible: false,
    type: "delete",
    path: "",
    inputValue: "",
  });

  useEffect(() => {
    if (projectId) {
      api.getProject(projectId)
        .then(res => setProjectName(res.name))
        .catch(() => setProjectName("project"));
    } else {
      setProjectName(null);
    }
  }, [projectId]);

  useEffect(() => {
    const closeContextMenu = () => setContextMenu(null);
    document.addEventListener("click", closeContextMenu);
    return () => document.removeEventListener("click", closeContextMenu);
  }, []);

  // Realtime sync: when an agent (or another client) writes a file, the
  // backend broadcasts a file_change event with the full after_content. If that
  // file is open here, refresh it — unless the user has unsaved edits, in which
  // case stash the remote update and surface a "reload" banner so we never
  // clobber in-progress work. Also bump the tree so newly created files appear.
  useEffect(() => {
    if (!lastFileChange?.path) return;
    const remotePath = lastFileChange.path.replace(/\\/g, "/");
    const newContent = lastFileChange.after_content ?? "";
    const sender = lastFileChange.sender_name || "Agent";

    setOpenFiles(prev => prev.map(f => {
      if (f.path.replace(/\\/g, "/") !== remotePath) return f;
      if (f.isDirty) {
        // Don't clobber unsaved local edits — stash and notify.
        return { ...f, staleRemote: { content: newContent, sender } };
      }
      return { ...f, content: newContent, isDirty: false, staleRemote: null };
    }));

    // Refresh the tree so newly created/changed files show up.
    setRefreshKey(k => k + 1);
  }, [lastFileChange]);

  // Open a file requested from outside (e.g. clicked a file-change card in chat).
  useEffect(() => {
    if (!pendingOpenFile) return;
    void openFile(pendingOpenFile);
    onPendingOpenConsumed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingOpenFile]);

  const openFile = async (path: string) => {
    // Check if already open
    const existing = openFiles.find(f => f.path === path);
    if (existing) {
      setActiveFilePath(path);
      setViewMode(isMarkdownPath(path) ? "preview" : "edit");
      return;
    }

    setLoadingContent(true);
    try {
      const res = await api.readFile(path, projectId);
      setOpenFiles(prev => {
        if (prev.some(f => f.path === path)) return prev;
        return [...prev, { path, content: res.content, isDirty: false }];
      });
      setActiveFilePath(path);
      setViewMode(isMarkdownPath(path) ? "preview" : "edit");
    } catch (error) {
      const err = error as Error;
      addToast({ type: "error", message: `Error reading file: ${err.message}` });
    } finally {
      setLoadingContent(false);
    }
  };

  const applyStaleRemote = (path: string) => {
    setOpenFiles(prev => prev.map(f => {
      if (f.path !== path || !f.staleRemote) return f;
      return { ...f, content: f.staleRemote.content, isDirty: false, staleRemote: null };
    }));
  };

  const closeFile = (path: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();

    setOpenFiles(prev => {
      const filtered = prev.filter(f => f.path !== path);
      // If we are closing the active file, switch to the next available one
      if (activeFilePath === path) {
        if (filtered.length > 0) {
          setActiveFilePath(filtered[filtered.length - 1].path);
        } else {
          setActiveFilePath(null);
        }
      }
      return filtered;
    });
  };

  const updateFileContent = (path: string, newContent: string) => {
    setOpenFiles(prev => prev.map(f => {
      if (f.path === path) {
        return { ...f, content: newContent, isDirty: true };
      }
      return f;
    }));
  };

  const handleSave = async () => {
    if (!activeFilePath) return;
    const file = openFiles.find(f => f.path === activeFilePath);
    if (!file || !file.isDirty) return;

    setSaving(true);
    try {
      await api.writeFile(file.path, file.content, projectId);
      setOpenFiles(prev => prev.map(f => f.path === activeFilePath ? { ...f, isDirty: false } : f));
      setRefreshKey(k => k + 1);
    } catch (error) {
      const err = error as Error;
      addToast({ type: "error", message: `Failed to save: ${err.message}` });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = (path: string) => {
    setDialog({ visible: true, type: "delete", path, inputValue: "" });
  };

  const handleRename = (path: string) => {
    setDialog({ visible: true, type: "rename", path, inputValue: path });
  };

  const handleCreateFile = (parentPath: string) => {
    setDialog({ visible: true, type: "new_file", path: parentPath, inputValue: "" });
  };

  const handleCreateFolder = (parentPath: string) => {
    setDialog({ visible: true, type: "new_folder", path: parentPath, inputValue: "" });
  };

  const submitDialog = async (e: React.FormEvent) => {
    e.preventDefault();
    const { type, path, inputValue } = dialog;
    setDialog({ ...dialog, visible: false });

    if (type === "delete") {
      try {
        await api.deleteFile(path, projectId);
        if (openFiles.some(f => f.path === path || f.path.startsWith(path + "/"))) {
          setOpenFiles(prev => prev.filter(f => !(f.path === path || f.path.startsWith(path + "/"))));
          if (activeFilePath === path || activeFilePath?.startsWith(path + "/")) {
            setActiveFilePath(null);
          }
        }
        setRefreshKey(k => k + 1);
      } catch (error) {
        const err = error as Error;
        addToast({ type: "error", message: `Failed to delete: ${err.message}` });
      }
    } else if (type === "rename") {
      if (inputValue && inputValue !== path) {
        try {
          await api.renameFile(path, inputValue, projectId);
          setOpenFiles(prev => prev.map(f => {
            if (f.path === path) return { ...f, path: inputValue };
            if (f.path.startsWith(path + "/")) return { ...f, path: f.path.replace(path, inputValue) };
            return f;
          }));
          if (activeFilePath === path) setActiveFilePath(inputValue);
          else if (activeFilePath?.startsWith(path + "/")) setActiveFilePath(activeFilePath.replace(path, inputValue));
          setRefreshKey(k => k + 1);
        } catch (error) {
          const err = error as Error;
          addToast({ type: "error", message: `Failed to rename: ${err.message}` });
        }
      }
    } else if (type === "new_file") {
      if (inputValue) {
        const fullPath = path === "." ? inputValue : `${path}/${inputValue}`;
        try {
          await api.writeFile(fullPath, "", projectId);
          openFile(fullPath);
          setRefreshKey(k => k + 1);
        } catch (error) {
          const err = error as Error;
          addToast({ type: "error", message: `Failed to create file: ${err.message}` });
        }
      }
    } else if (type === "new_folder") {
      if (inputValue) {
        const fullPath = path === "." ? inputValue : `${path}/${inputValue}`;
        try {
          await api.createFolder(fullPath, projectId);
          setRefreshKey(k => k + 1);
        } catch (error) {
          const err = error as Error;
          addToast({ type: "error", message: `Failed to create folder: ${err.message}` });
        }
      }
    }
  };

  const handleExecuteFile = (path: string) => {
    const ext = path.split('.').pop()?.toLowerCase();
    let cmd = '';

    if (ext === 'js' || ext === 'ts') cmd = `node ${path}`;
    else if (ext === 'py') cmd = `python ${path}`;
    else if (ext === 'sh') cmd = `bash ${path}`;
    else if (ext === 'rb') cmd = `ruby ${path}`;
    else if (ext === 'php') cmd = `php ${path}`;
    else {
      addToast({ type: "warning", message: `Execution not supported for .${ext} files yet.` });
      return;
    }

    setShowTerminal(true);
    setTerminalCmd({ cmd, ts: Date.now() });
  };

  const handleContextMenu = (e: React.MouseEvent, path: string, isDir: boolean) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, path, isDir });
  };

  // Keyboard shortcut for saving
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeFilePath, openFiles]);

  const activeFile = openFiles.find(f => f.path === activeFilePath);

  const containerStyle: React.CSSProperties = isFullScreen
    ? {
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      zIndex: 9999,
      display: "flex",
      background: "var(--color-canvas)",
      width: "100%",
      maxWidth: "none",
    }
    : {
      display: "flex",
      height: "100%",
      borderLeft: "1px solid var(--border-subtle)",
      background: "var(--bg-app)",
      width: "100%",
      maxWidth: 800,
    };

  return (
    <div style={containerStyle}>
      {/* Activity Bar */}
      <div style={{ width: 48, borderRight: "1px solid var(--color-hairline)", background: "var(--bg-glass-card)", display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 8, gap: 8, flexShrink: 0 }}>
        <button
          onClick={() => setActiveLeftTab("explorer")}
          style={{ padding: 10, borderRadius: "var(--radius-sm)", color: activeLeftTab === "explorer" ? "var(--color-primary)" : "var(--color-body)", background: activeLeftTab === "explorer" ? "var(--color-primary-glow-sm)" : "transparent" }}
          className="hover:text-white transition-colors"
          title="Explorer"
        >
          <LayoutList size={20} />
        </button>
        <button
          onClick={() => setActiveLeftTab("search")}
          style={{ padding: 10, borderRadius: "var(--radius-sm)", color: activeLeftTab === "search" ? "var(--color-primary)" : "var(--color-body)", background: activeLeftTab === "search" ? "var(--color-primary-glow-sm)" : "transparent" }}
          className="hover:text-white transition-colors"
          title="Search"
        >
          <Search size={20} />
        </button>
        <button
          onClick={() => setActiveLeftTab("git")}
          style={{ padding: 10, borderRadius: "var(--radius-sm)", color: activeLeftTab === "git" ? "var(--color-primary)" : "var(--color-body)", background: activeLeftTab === "git" ? "var(--color-primary-glow-sm)" : "transparent" }}
          className="hover:text-white transition-colors"
          title="Source Control"
        >
          <GitBranch size={20} />
        </button>
        <button
          onClick={() => setActiveLeftTab("activity")}
          style={{ padding: 10, borderRadius: "var(--radius-sm)", color: activeLeftTab === "activity" ? "var(--color-primary)" : "var(--color-body)", background: activeLeftTab === "activity" ? "var(--color-primary-glow-sm)" : "transparent" }}
          className="hover:text-white transition-colors"
          title="Activity Log"
        >
          <Activity size={20} />
        </button>
      </div>

      <PanelGroup direction="horizontal" autoSaveId="file-explorer-horizontal">
        {/* Left Pane - Sidebar Content */}
        <Panel id="file-explorer-left" order={1} defaultSize={25} minSize={15} maxSize={40} style={{ display: "flex", flexDirection: "column", background: "var(--bg-surface)", borderRight: "1px solid var(--border-subtle)" }}>
        {activeLeftTab === "explorer" && (
          <>
            <div style={{ padding: "var(--sp-sm) var(--sp-md)", borderBottom: "1px solid var(--color-hairline)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="body-sm-strong" style={{ textTransform: "uppercase", fontSize: "11px", letterSpacing: "0.5px", color: "var(--color-mute)" }}>Explorer</span>
              <div style={{ display: "flex", gap: "4px" }}>
                <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setRefreshKey(k => k + 1)} title="Refresh">
                  <RefreshCw size={14} />
                </button>
                <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setIsFullScreen(!isFullScreen)} title={isFullScreen ? "Restore" : "Full Screen"}>
                  {isFullScreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                </button>
                {onClose && (
                  <button className="btn btn-ghost btn-icon btn-sm" onClick={onClose} title="Close IDE">
                    <X size={14} />
                  </button>
                )}
              </div>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
              {projectId ? (
                <>
                  <div style={{ display: "flex", alignItems: "center", padding: "2px 8px", color: "var(--color-body)", userSelect: "none" }}>
                    <span style={{ width: 16, display: "flex", justifyContent: "center", marginRight: 2 }}>
                      <ChevronDown size={14} color="var(--color-mute)" />
                    </span>
                    <Folder size={14} color="var(--color-primary-soft)" style={{ marginRight: 8 }} />
                    <span className="body-sm truncate" style={{ fontSize: "13px", fontWeight: "bold" }}>workspaces</span>
                  </div>
                  <div style={{ paddingLeft: 12 }}>
                    <TreeNode
                      path="."
                      name={projectName || "loading..."}
                      isDir={true}
                      onFileSelect={openFile}
                      selectedPath={activeFilePath}
                      defaultExpanded={true}
                      projectId={projectId}
                      refreshKey={refreshKey}
                      onContextMenu={handleContextMenu}
                    />
                  </div>
                </>
              ) : (
                <TreeNode
                  path="."
                  name="workspaces"
                  isDir={true}
                  onFileSelect={openFile}
                  selectedPath={activeFilePath}
                  defaultExpanded={true}
                  projectId={undefined}
                  refreshKey={refreshKey}
                  onContextMenu={handleContextMenu}
                />
              )}
            </div>
          </>
        )}
        {activeLeftTab === "search" && (
          <SearchPanel projectId={projectId} onFileSelect={openFile} />
        )}
        {activeLeftTab === "git" && (
          <GitPanel projectId={projectId} />
        )}
        {activeLeftTab === "activity" && teamId && (
          <ActivityLogPanel teamId={teamId} />
        )}
        </Panel>
        <PanelResizeHandle className="resize-handle" style={{ width: "4px", cursor: "col-resize", background: "var(--border-subtle)", flexShrink: 0 }} />
        
        {/* Right Pane - Content View */}
        <Panel id="file-explorer-right" order={2} style={{ display: "flex", flexDirection: "column", minWidth: 0, background: "transparent" }}>
          {openFiles.length > 0 ? (
          <>
            {/* Editor Tabs */}
            <div style={{ display: "flex", background: "var(--bg-glass-card)", overflowX: "auto", overflowY: "hidden", height: 35, flexShrink: 0 }} className="scrollbar-hide">
              {openFiles.map(file => {
                const isActive = file.path === activeFilePath;
                const fileName = file.path.split('/').pop() || file.path;
                return (
                  <div
                    key={file.path}
                    onClick={() => setActiveFilePath(file.path)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      padding: "0 10px 0 16px",
                      background: isActive ? "var(--bg-glass-panel)" : "transparent",
                      color: isActive ? "var(--color-primary)" : "var(--color-mute)",
                      borderRight: "1px solid var(--color-hairline)",
                      borderTop: isActive ? "1px solid var(--color-primary)" : "1px solid transparent",
                      cursor: "pointer",
                      minWidth: 120,
                      maxWidth: 200,
                      height: "100%",
                      userSelect: "none"
                    }}
                    className="hover:bg-[#2a2d2e] transition-colors"
                  >
                    <File size={12} color={isActive ? "var(--color-primary)" : "var(--color-body)"} style={{ marginRight: 6 }} />
                    <span className="truncate body-sm font-mono" style={{ fontSize: "12px", flex: 1, marginRight: 6 }}>
                      {fileName}
                    </span>
                    {file.isDirty && (
                      <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#fff", marginRight: 6 }} />
                    )}
                    <button
                      onClick={(e) => closeFile(file.path, e)}
                      style={{ padding: 2, borderRadius: 3 }}
                      className="hover:bg-gray-600 text-transparent hover:text-white group-hover:text-gray-400"
                    >
                      <X size={12} />
                    </button>
                  </div>
                );
              })}
            </div>

            {/* Editor Toolbar */}
            {activeFile && (
              <div style={{ padding: "4px 16px", borderBottom: "1px solid var(--color-hairline)", background: "var(--bg-glass-panel)", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                  <span className="body-sm text-mute" style={{ fontFamily: "var(--font-mono)", fontSize: "11px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{activeFile.path}</span>
                  {isMarkdownPath(activeFile.path) && (
                    <div style={{ display: "flex", gap: 2, background: "var(--color-surface)", borderRadius: 4, padding: 2 }}>
                      <button
                        className="btn btn-sm"
                        onClick={() => setViewMode("preview")}
                        style={{ padding: "1px 8px", fontSize: 11, background: viewMode === "preview" ? "var(--color-primary)" : "transparent", color: viewMode === "preview" ? "#fff" : "var(--color-body)", border: "none" }}
                        title="Rendered markdown preview"
                      >
                        <Eye size={11} className="mr-1" />Preview
                      </button>
                      <button
                        className="btn btn-sm"
                        onClick={() => setViewMode("edit")}
                        style={{ padding: "1px 8px", fontSize: 11, background: viewMode === "edit" ? "var(--color-primary)" : "transparent", color: viewMode === "edit" ? "#fff" : "var(--color-body)", border: "none" }}
                        title="Edit raw markdown"
                      >
                        <Pencil size={11} className="mr-1" />Edit
                      </button>
                    </div>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <button
                    className={`btn btn-sm ${showTerminal ? "btn-secondary" : "btn-ghost"}`}
                    onClick={() => setShowTerminal(s => !s)}
                    title="Toggle Terminal"
                    style={{ padding: "2px 8px", fontSize: 11 }}
                  >
                    <TerminalIcon size={12} className="mr-1" />
                    Terminal
                  </button>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleSave}
                    disabled={saving || !activeFile.isDirty}
                    style={{ padding: "2px 8px", fontSize: 11 }}
                  >
                    {saving ? "Saving..." : "Save"}
                  </button>
                </div>
              </div>
            )}

            {/* Stale remote-update banner — don't clobber unsaved edits. */}
            {activeFile?.staleRemote && (
              <div style={{ padding: "6px 16px", borderBottom: "1px solid var(--color-hairline)", background: "var(--color-warning-bg, rgba(234,179,8,0.12))", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexShrink: 0 }}>
                <span className="caption" style={{ color: "var(--color-warning, #eab308)" }}>
                  ⚠ {activeFile.staleRemote.sender} updated this file remotely. Reload to see it (your unsaved edits will be discarded).
                </span>
                <button className="btn btn-sm btn-secondary" onClick={() => applyStaleRemote(activeFile.path)} style={{ padding: "2px 8px", fontSize: 11 }}>
                  <RefreshCcwDot size={12} className="mr-1" />Reload
                </button>
              </div>
            )}

            <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
              {loadingContent ? (
                <div className="text-mute body-sm p-4">Loading...</div>
              ) : (
                <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
                  <PanelGroup direction="vertical" autoSaveId="file-explorer-vertical">
                    <Panel defaultSize={showTerminal ? 60 : 100} minSize={20} style={{ display: "flex", flexDirection: "column", overflow: "hidden", paddingTop: 8 }}>
                      {activeFile ? (
                        isMarkdownPath(activeFile.path) && viewMode === "preview" ? (
                          <div style={{ height: "100%", overflowY: "auto", padding: "8px 24px 32px" }} className="markdown-body">
                            {activeFile.content.trim() ? (
                              <ReactMarkdown
                                remarkPlugins={[remarkGfm]}
                                // HTML is NOT enabled (no rehype-raw), so raw HTML
                                // in agent-authored markdown is escaped — safe.
                                components={{
                                  a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
                                }}
                              >
                                {activeFile.content}
                              </ReactMarkdown>
                            ) : (
                              <div className="body-sm" style={{ color: "var(--color-mute)", fontStyle: "italic" }}>
                                This file is empty. Switch to <strong>Edit</strong> to add content.
                              </div>
                            )}
                          </div>
                        ) : (
                          <Editor
                            height="100%"
                            language={getLanguageFromPath(activeFile.path)}
                            theme="vs-dark"
                            value={activeFile.content}
                            onChange={(value) => updateFileContent(activeFile.path, value || "")}
                            options={{
                              minimap: { enabled: false },
                              fontSize: 13,
                              fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace",
                              wordWrap: "on",
                              padding: { top: 8, bottom: 16 },
                            }}
                          />
                        )
                      ) : (
                        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-mute)" }} className="body-sm">
                          Select a file to view its content
                        </div>
                      )}
                    </Panel>
                    {showTerminal && (
                      <>
                        <PanelResizeHandle className="resize-handle" />
                        <Panel defaultSize={40} minSize={20} style={{ display: "flex", flexDirection: "column", borderTop: "1px solid var(--color-hairline)", overflow: "hidden" }}>
                          <TerminalPanel
                            projectId={projectId}
                            onClose={() => setShowTerminal(false)}
                            triggerCommand={terminalCmd}
                          />
                        </Panel>
                      </>
                    )}
                  </PanelGroup>
                </div>
              )}
            </div>
          </>
        ) : (
          <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
            <div style={{ padding: "8px 16px", borderBottom: "1px solid var(--color-hairline)", background: "var(--bg-glass-panel)", display: "flex", alignItems: "center", justifyContent: "flex-end" }}>
              <button
                className={`btn btn-sm ${showTerminal ? "btn-secondary" : "btn-ghost"}`}
                onClick={() => setShowTerminal(s => !s)}
                title="Toggle Terminal"
              >
                <TerminalIcon size={14} className="mr-1" />
                Terminal
              </button>
            </div>
            <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
              {!showTerminal ? (
                <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-mute)" }} className="body-sm">
                  Select a file from the explorer to open
                </div>
              ) : (
                <TerminalPanel projectId={projectId} onClose={() => setShowTerminal(false)} triggerCommand={terminalCmd} />
              )}
            </div>
          </div>
        )}
        </Panel>
      </PanelGroup>

      {contextMenu && (
        <div
          style={{
            position: "fixed",
            top: contextMenu.y,
            left: contextMenu.x,
            background: "var(--color-surface)",
            border: "1px solid var(--color-hairline)",
            borderRadius: "4px",
            boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
            padding: "4px 0",
            zIndex: 9999,
            minWidth: "150px",
            display: "flex",
            flexDirection: "column",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {contextMenu.isDir && (
            <>
              <ContextMenuItem onClick={() => { handleCreateFile(contextMenu.path); setContextMenu(null); }}>New File</ContextMenuItem>
              <ContextMenuItem onClick={() => { handleCreateFolder(contextMenu.path); setContextMenu(null); }}>New Folder</ContextMenuItem>
            </>
          )}
          {!contextMenu.isDir && (
            <ContextMenuItem onClick={() => { handleExecuteFile(contextMenu.path); setContextMenu(null); }}>Execute File</ContextMenuItem>
          )}
          <ContextMenuItem onClick={() => { handleRename(contextMenu.path); setContextMenu(null); }}>Rename</ContextMenuItem>
          <div style={{ height: "1px", background: "var(--color-hairline)", margin: "4px 0" }} />
          <ContextMenuItem
            onClick={() => { handleDelete(contextMenu.path); setContextMenu(null); }}
            style={{ color: "var(--color-error)" }}
          >
            Delete
          </ContextMenuItem>
        </div>
      )}

      {dialog.visible && (
        <Modal open={dialog.visible} onClose={() => setDialog({ ...dialog, visible: false })} title={
          dialog.type === "delete" ? "Delete Item" :
            dialog.type === "rename" ? "Rename Item" :
              dialog.type === "new_file" ? "New File" : "New Folder"
        } maxWidth={400}>
          <form onSubmit={submitDialog} style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
            <p className="body-sm">
              {dialog.type === "delete" ? `Are you sure you want to delete ${dialog.path}?` :
                dialog.type === "rename" ? `Rename ${dialog.path} to:` :
                  dialog.type === "new_file" ? `Create new file in ${dialog.path}:` :
                    `Create new folder in ${dialog.path}:`}
            </p>
            {dialog.type !== "delete" && (
              <input
                className="input"
                autoFocus
                value={dialog.inputValue}
                onChange={e => setDialog({ ...dialog, inputValue: e.target.value })}
              />
            )}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--sp-sm)", marginTop: "var(--sp-md)" }}>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setDialog({ ...dialog, visible: false })}>Cancel</button>
              <button type="submit" className={`btn btn-sm ${dialog.type === "delete" ? "btn-danger" : "btn-primary"}`} disabled={dialog.type !== "delete" && !dialog.inputValue.trim()}>
                {dialog.type === "delete" ? "Delete" : "Confirm"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

function ContextMenuItem({ children, onClick, style }: { children: React.ReactNode; onClick: () => void; style?: React.CSSProperties }) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: "6px 16px",
        cursor: "pointer",
        fontSize: "12px",
        fontFamily: "var(--font-sans)",
        ...style
      }}
      className="hover:bg-gray-800 transition-colors"
    >
      {children}
    </div>
  );
}

function TreeNode({ path, name, isDir, onFileSelect, selectedPath, defaultExpanded = false, projectId, refreshKey, onContextMenu }: {
  path: string;
  name: string;
  isDir: boolean;
  onFileSelect: (path: string) => void;
  selectedPath: string | null;
  defaultExpanded?: boolean;
  projectId?: string;
  refreshKey: number;
  onContextMenu: (e: React.MouseEvent, path: string, isDir: boolean) => void;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [children, setChildren] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(false);

  const loadChildren = async () => {
    if (!isDir) return;
    setLoading(true);
    try {
      const items = await api.listFiles(path, projectId);
      items.sort((a, b) => {
        if (a.is_dir === b.is_dir) return a.name.localeCompare(b.name);
        return a.is_dir ? -1 : 1;
      });
      setChildren(items);
    } catch (err: any) {
      if (err.status === 404) {
        setExpanded(false);
        setChildren([]);
      } else {
        console.warn(`Failed to list files for ${path}:`, err.message || err);
      }
    } finally {
      setLoading(false);
    }
  };

  const toggleExpand = () => {
    if (!isDir) {
      onFileSelect(path);
      return;
    }
    if (!expanded) {
      setExpanded(true);
      loadChildren();
    } else {
      setExpanded(false);
    }
  };

  useEffect(() => {
    if (expanded && isDir) {
      void loadChildren();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  useEffect(() => {
    if (defaultExpanded && isDir && children.length === 0) {
      void loadChildren();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultExpanded, isDir, path, children.length]);

  const isSelected = path === selectedPath && !isDir;

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          padding: "2px 8px",
          background: isSelected ? "var(--color-primary-glow-sm)" : "transparent",
          color: isSelected ? "var(--color-primary)" : "var(--color-body)",
          cursor: "pointer",
          userSelect: "none"
        }}
        className={`hover:bg-gray-800 transition-colors ${isSelected ? "border-l-2 border-blue-500" : "border-l-2 border-transparent"}`}
        onClick={toggleExpand}
        onContextMenu={(e) => onContextMenu(e, path, isDir)}
      >
        <span style={{ width: 16, display: "flex", justifyContent: "center", marginRight: 2 }}>
          {isDir ? (
            expanded ? <ChevronDown size={14} color="var(--color-mute)" /> : <ChevronRight size={14} color="var(--color-mute)" />
          ) : (
            <span />
          )}
        </span>
        {isDir ? <Folder size={14} color="var(--color-primary-soft)" style={{ marginRight: 8 }} /> : <File size={14} color="var(--color-body)" style={{ marginRight: 8 }} />}
        <span className="body-sm truncate" style={{ fontSize: "13px" }}>{name}</span>
        {loading && <RefreshCw size={10} className="animate-spin ml-2 text-mute" />}
      </div>

      {expanded && isDir && (
        <div style={{ paddingLeft: 12 }}>
          {children.map(child => (
            <TreeNode
              key={child.path}
              path={child.path}
              name={child.name}
              isDir={child.is_dir}
              onFileSelect={onFileSelect}
              selectedPath={selectedPath}
              projectId={projectId}
              refreshKey={refreshKey}
              onContextMenu={onContextMenu}
            />
          ))}
          {children.length === 0 && !loading && (
            <div style={{ padding: "4px 28px", color: "var(--color-mute)", fontSize: "12px", fontStyle: "italic" }}>
              Empty
            </div>
          )}
        </div>
      )}
    </div>
  );
}
