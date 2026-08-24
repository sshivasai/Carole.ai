"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Folder,
  ChevronRight,
  ChevronDown,
  RefreshCw,
  X,
  Terminal as TerminalIcon,
  Maximize2,
  Minimize2,
  Search,
  GitBranch,
  LayoutList,
  Activity,
  Eye,
  Pencil,
  RefreshCcwDot,
  Play,
  ChevronsUpDown,
  History,
  Filter,
  Copy,
  Scissors,
  ClipboardPaste,
  Trash2,
  Download,
  FilePlus,
  FolderPlus,
  Files,
  CheckSquare,
  Plus,
} from "lucide-react";
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
  const ext = path.split(".").pop()?.toLowerCase();
  const MAP: Record<string, string> = {
    ts: "typescript",
    tsx: "typescript",
    js: "javascript",
    jsx: "javascript",
    py: "python",
    json: "json",
    html: "html",
    css: "css",
    scss: "scss",
    sass: "scss",
    md: "markdown",
    yml: "yaml",
    yaml: "yaml",
    sh: "shell",
    bash: "shell",
    rs: "rust",
    go: "go",
    java: "java",
    c: "cpp",
    cpp: "cpp",
    h: "cpp",
    hpp: "cpp",
    sql: "sql",
    toml: "toml",
    xml: "xml",
  };
  return (ext && MAP[ext]) || "plaintext";
}

function getFileIcon(name: string, isDir = false): string {
  if (isDir) return "📁";
  const lower = name.toLowerCase();
  const ext = lower.split(".").pop() || "";
  if (lower === "dockerfile") return "🐳";
  if (lower === ".gitignore" || lower === ".gitattributes") return "🙈";
  if (lower === ".env" || lower.startsWith(".env.")) return "🔑";
  if (lower === "readme.md") return "📖";
  if (lower === "package.json" || lower === "package-lock.json") return "📦";
  if (lower === "tsconfig.json" || lower === "jsconfig.json") return "⚙️";
  if (lower === "requirements.txt") return "🐍";
  if (lower === "makefile") return "🔨";
  const M: Record<string, string> = {
    py: "🐍",
    ts: "📘",
    tsx: "⚛️",
    js: "📜",
    jsx: "⚛️",
    json: "📋",
    md: "📝",
    yml: "⚙️",
    yaml: "⚙️",
    sh: "🖥️",
    bash: "🖥️",
    css: "🎨",
    scss: "🎨",
    html: "🌐",
    rs: "🦀",
    go: "🔵",
    java: "☕",
    rb: "💎",
    php: "🐘",
    sql: "🗄️",
    toml: "⚙️",
    xml: "🔖",
    lock: "🔒",
    env: "🔑",
    png: "🖼️",
    jpg: "🖼️",
    jpeg: "🖼️",
    svg: "🖼️",
    pdf: "📕",
    txt: "📄",
    csv: "📊",
    zip: "📦",
    tar: "📦",
    gz: "📦",
    c: "⚙️",
    cpp: "⚙️",
    h: "⚙️",
    hpp: "⚙️",
  };
  return M[ext] || "📄";
}

const EXEC_EXTS = new Set(["py", "js", "ts", "sh", "bash", "rb", "php"]);
function isExecutable(path: string) {
  return EXEC_EXTS.has(path.split(".").pop()?.toLowerCase() || "");
}
const isMarkdownPath = (p: string) => /\.(md|markdown|txt)$/i.test(p);

interface FileItem {
  name: string;
  is_dir: boolean;
  size: number;
  mtime?: number;
  path: string;
}

interface FileExplorerPanelProps {
  onClose?: () => void;
  projectId?: string;
  teamId?: string;
  lastFileChange?: {
    path?: string;
    paths?: string[];
    after_content?: string;
    action?: string;
    sender_name?: string;
    _seq?: number;
  } | null;
  pendingOpenFile?: string | null;
  onPendingOpenConsumed?: () => void;
}

interface ContextMenuState {
  x: number;
  y: number;
  path: string;
  isDir: boolean;
  isMulti: boolean;
}

interface OpenFile {
  path: string;
  content: string;
  isDirty: boolean;
  staleRemote?: { content: string; sender: string } | null;
}

interface TerminalTab {
  id: string;
  label: string;
  cmd: { cmd: string; ts: number } | null;
}

interface ClipboardState {
  items: string[];
  isCut: boolean;
}

function Breadcrumb({ path }: { path: string }) {
  const parts = path.split("/").filter(Boolean);
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 2,
        fontFamily: "var(--font-mono)",
        fontSize: 11,
        color: "var(--color-mute)",
        overflow: "hidden",
        flexShrink: 1,
        minWidth: 0,
      }}
    >
      {parts.map((part, i) => {
        const isLast = i === parts.length - 1;
        return (
          <React.Fragment key={i}>
            {i > 0 && <span style={{ opacity: 0.4, flexShrink: 0 }}>/</span>}
            <span
              style={{
                color: isLast ? "var(--color-body)" : "var(--color-mute)",
                whiteSpace: "nowrap",
                flexShrink: isLast ? 1 : 0,
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {part}
            </span>
          </React.Fragment>
        );
      })}
    </div>
  );
}

function FileHistoryPanel({
  filePath,
  projectId,
  onRestored,
}: {
  filePath: string;
  projectId?: string;
  onRestored: () => void;
}) {
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState<string | null>(null);
  const { addToast } = useToast();

  useEffect(() => {
    if (!filePath) return;
    setLoading(true);
    (api as any)
      .getFileHistory?.(filePath, projectId)
      .then((d: any[]) => setHistory(d))
      .catch(() => setHistory([]))
      .finally(() => setLoading(false));
  }, [filePath, projectId]);

  const restore = async (id: string) => {
    setRestoring(id);
    try {
      await (api as any).restoreFileBackup?.(id, projectId);
      addToast({ type: "success", message: "Restored!" });
      onRestored();
    } catch (e) {
      addToast({ type: "error", message: `Restore failed: ${(e as Error).message}` });
    } finally {
      setRestoring(null);
    }
  };

  if (loading)
    return (
      <div className="body-sm text-mute" style={{ padding: 16 }}>
        Loading…
      </div>
    );
  if (!history.length)
    return (
      <div className="body-sm" style={{ color: "var(--color-mute)", padding: 16, fontStyle: "italic" }}>
        No history.
      </div>
    );
  return (
    <div style={{ flex: 1, overflowY: "auto" }}>
      {history.map((e: any) => (
        <div
          key={e.id}
          style={{
            padding: "8px 12px",
            borderBottom: "1px solid var(--color-hairline)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div className="body-sm" style={{ fontSize: 12 }}>
              {e.operation || "modified"}
            </div>
            <div className="caption" style={{ color: "var(--color-mute)", fontSize: 11 }}>
              {e.created_at ? new Date(e.created_at).toLocaleString() : "Unknown"}
            </div>
          </div>
          {e.has_content && (
            <button
              className="btn btn-sm btn-ghost"
              style={{ fontSize: 11, padding: "2px 8px", flexShrink: 0 }}
              onClick={() => restore(e.id)}
              disabled={restoring === e.id}
            >
              {restoring === e.id ? "…" : "↩ Restore"}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function ContextMenuItem({
  children,
  onClick,
  style,
}: {
  children: React.ReactNode;
  onClick: () => void;
  style?: React.CSSProperties;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: "6px 14px",
        cursor: "pointer",
        fontSize: "12px",
        display: "flex",
        alignItems: "center",
        gap: 8,
        ...style,
      }}
      className="hover:bg-gray-800 transition-colors"
    >
      {children}
    </div>
  );
}

export default function FileExplorerPanel({
  onClose,
  projectId,
  teamId,
  lastFileChange,
  pendingOpenFile,
  onPendingOpenConsumed,
}: FileExplorerPanelProps) {
  const { addToast } = useToast();
  const [activeLeftTab, setActiveLeftTab] = useState<"explorer" | "search" | "git" | "activity" | "history">("explorer");
  const [isFullScreen, setIsFullScreen] = useState(false);
  const [openFiles, setOpenFiles] = useState<OpenFile[]>([]);
  const [activeFilePath, setActiveFilePath] = useState<string | null>(null);
  const [loadingContent, setLoadingContent] = useState(false);
  const [saving, setSaving] = useState(false);
  const [viewMode, setViewMode] = useState<"preview" | "edit">("preview");
  const [refreshKey, setRefreshKey] = useState(0);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [filterText, setFilterText] = useState("");
  const [collapseSignal, setCollapseSignal] = useState(0);
  const [showTerminal, setShowTerminal] = useState(false);
  const [terminalTabs, setTerminalTabs] = useState<TerminalTab[]>([{ id: "t1", label: "Terminal 1", cmd: null }]);
  const [activeTerminalTabId, setActiveTerminalTabId] = useState("t1");
  const [projectName, setProjectName] = useState<string | null>(null);

  // Multi-Selection & Clipboard State
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [lastSelectedPath, setLastSelectedPath] = useState<string | null>(null);
  const [clipboard, setClipboard] = useState<ClipboardState | null>(null);
  const visiblePathsRef = useRef<string[]>([]);
  const dragRef = useRef<string[]>([]);

  // Dialog State
  const [dialog, setDialog] = useState<{
    visible: boolean;
    type: "delete" | "batch_delete" | "rename" | "new_file" | "new_folder";
    path: string;
    paths?: string[];
    inputValue: string;
  }>({ visible: false, type: "delete", path: "", inputValue: "" });

  // Root directory items
  const [rootItems, setRootItems] = useState<FileItem[]>([]);
  const [rootLoading, setRootLoading] = useState(false);

  // Load project name
  useEffect(() => {
    if (projectId) {
      api
        .getProject(projectId)
        .then((r) => setProjectName(r.name))
        .catch(() => setProjectName("project"));
    } else {
      setProjectName(null);
    }
  }, [projectId]);

  // Load root items
  const loadRootItems = useCallback(async () => {
    if (!projectId) {
      setRootItems([]);
      return;
    }
    setRootLoading(true);
    try {
      const items = await api.listFiles(".", projectId);
      items.sort((a, b) => (a.is_dir === b.is_dir ? a.name.localeCompare(b.name) : a.is_dir ? -1 : 1));
      setRootItems(items);
    } catch (err) {
      console.warn("Failed to load root files:", err);
      setRootItems([]);
    } finally {
      setRootLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void loadRootItems();
  }, [loadRootItems, refreshKey]);

  // Global click to close context menu
  useEffect(() => {
    const close = () => setContextMenu(null);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);

  // Real-time Live Synchronization (WebSocket events)
  useEffect(() => {
    if (!lastFileChange) return;
    
    // Auto-refresh file tree immediately
    setRefreshKey((k) => k + 1);

    if (lastFileChange.path) {
      const rp = lastFileChange.path.replace(/\\/g, "/");
      const nc = lastFileChange.after_content ?? "";
      const sender = lastFileChange.sender_name || "Agent";
      
      setOpenFiles((prev) =>
        prev.map((f) => {
          if (f.path.replace(/\\/g, "/") !== rp) return f;
          if (f.isDirty) return { ...f, staleRemote: { content: nc, sender } };
          return { ...f, content: nc, isDirty: false, staleRemote: null };
        })
      );
    }
  }, [lastFileChange]);

  // Open file requested externally
  useEffect(() => {
    if (!pendingOpenFile) return;
    void openFile(pendingOpenFile);
    onPendingOpenConsumed?.();
  }, [pendingOpenFile]);

  // Dirty file unload protection
  useEffect(() => {
    const h = (e: BeforeUnloadEvent) => {
      if (openFiles.some((f) => f.isDirty)) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [openFiles]);

  const openFile = async (path: string) => {
    const ex = openFiles.find((f) => f.path === path);
    if (ex) {
      setActiveFilePath(path);
      setViewMode(isMarkdownPath(path) ? "preview" : "edit");
      return;
    }
    setLoadingContent(true);
    try {
      const res = await api.readFile(path, projectId);
      setOpenFiles((prev) =>
        prev.some((f) => f.path === path) ? prev : [...prev, { path, content: res.content, isDirty: false }]
      );
      setActiveFilePath(path);
      setViewMode(isMarkdownPath(path) ? "preview" : "edit");
    } catch (e) {
      addToast({ type: "error", message: `Error: ${(e as Error).message}` });
    } finally {
      setLoadingContent(false);
    }
  };

  const applyStaleRemote = (path: string) => {
    setOpenFiles((prev) =>
      prev.map((f) => (f.path !== path || !f.staleRemote ? f : { ...f, content: f.staleRemote.content, isDirty: false, staleRemote: null }))
    );
  };

  const closeFile = (path: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setOpenFiles((prev) => {
      const f = prev.filter((x) => x.path !== path);
      if (activeFilePath === path) setActiveFilePath(f.length ? f[f.length - 1].path : null);
      return f;
    });
  };

  const updateFileContent = (path: string, val: string) => {
    setOpenFiles((prev) => prev.map((f) => (f.path === path ? { ...f, content: val, isDirty: true } : f)));
  };

  const handleSave = useCallback(async () => {
    if (!activeFilePath) return;
    const file = openFiles.find((f) => f.path === activeFilePath);
    if (!file || !file.isDirty) return;
    setSaving(true);
    try {
      await api.writeFile(file.path, file.content, projectId);
      setOpenFiles((prev) => prev.map((f) => (f.path === activeFilePath ? { ...f, isDirty: false } : f)));
      setRefreshKey((k) => k + 1);
      addToast({ type: "success", message: `Saved ${file.path}` });
    } catch (e) {
      addToast({ type: "error", message: `Save failed: ${(e as Error).message}` });
    } finally {
      setSaving(false);
    }
  }, [activeFilePath, openFiles, projectId, addToast]);

  // Selection Handler
  const handleItemSelect = (path: string, isDir: boolean, event: React.MouseEvent) => {
    if (event.ctrlKey || event.metaKey) {
      // Toggle individual selection
      setSelectedPaths((prev) => {
        const next = new Set(prev);
        if (next.has(path)) next.delete(path);
        else next.add(path);
        return next;
      });
      setLastSelectedPath(path);
    } else if (event.shiftKey && lastSelectedPath) {
      // Range selection
      const list = visiblePathsRef.current;
      const idxA = list.indexOf(lastSelectedPath);
      const idxB = list.indexOf(path);
      if (idxA !== -1 && idxB !== -1) {
        const start = Math.min(idxA, idxB);
        const end = Math.max(idxA, idxB);
        const range = list.slice(start, end + 1);
        setSelectedPaths(new Set(range));
      }
    } else {
      // Single selection
      setSelectedPaths(new Set([path]));
      setLastSelectedPath(path);
      if (!isDir) {
        void openFile(path);
      }
    }
  };

  // Clipboard Actions
  const handleCut = (paths?: string[]) => {
    const targets = paths || Array.from(selectedPaths);
    if (!targets.length) return;
    setClipboard({ items: targets, isCut: true });
    addToast({ type: "info", message: `Cut ${targets.length} item(s)` });
  };

  const handleCopy = (paths?: string[]) => {
    const targets = paths || Array.from(selectedPaths);
    if (!targets.length) return;
    setClipboard({ items: targets, isCut: false });
    addToast({ type: "info", message: `Copied ${targets.length} item(s)` });
  };

  const handlePaste = async (targetDir: string = ".") => {
    if (!clipboard || !clipboard.items.length) return;
    try {
      if (clipboard.isCut) {
        await api.batchMoveFiles(clipboard.items, targetDir, projectId);
        addToast({ type: "success", message: `Moved ${clipboard.items.length} item(s) into ${targetDir === "." ? "root" : targetDir}` });
        setClipboard(null);
      } else {
        await api.batchCopyFiles(clipboard.items, targetDir, projectId);
        addToast({ type: "success", message: `Pasted ${clipboard.items.length} item(s) into ${targetDir === "." ? "root" : targetDir}` });
      }
      setRefreshKey((k) => k + 1);
    } catch (e) {
      addToast({ type: "error", message: `Paste failed: ${(e as Error).message}` });
    }
  };

  const handleDuplicate = async (path: string) => {
    try {
      const res = await api.duplicateFile(path, projectId);
      addToast({ type: "success", message: `Duplicated to ${res.new_path}` });
      setRefreshKey((k) => k + 1);
    } catch (e) {
      addToast({ type: "error", message: `Duplicate failed: ${(e as Error).message}` });
    }
  };

  const handleDownloadZip = async (paths?: string[]) => {
    const targets = paths || (selectedPaths.size > 0 ? Array.from(selectedPaths) : undefined);
    try {
      addToast({ type: "info", message: "Preparing zip download..." });
      await api.downloadZip(targets, projectId, `workspace_${projectName || "export"}.zip`);
      addToast({ type: "success", message: "Download complete!" });
    } catch (e) {
      addToast({ type: "error", message: `Download failed: ${(e as Error).message}` });
    }
  };

  // Bulk / Single Delete
  const handleDeletePrompt = (paths: string[]) => {
    if (paths.length === 1) {
      setDialog({ visible: true, type: "delete", path: paths[0], inputValue: "" });
    } else {
      setDialog({ visible: true, type: "batch_delete", path: "", paths, inputValue: "" });
    }
  };

  const handleRenamePrompt = (p: string) => {
    setDialog({ visible: true, type: "rename", path: p, inputValue: p });
  };

  const handleCreateFilePrompt = (p: string = ".") => {
    setDialog({ visible: true, type: "new_file", path: p, inputValue: "" });
  };

  const handleCreateFolderPrompt = (p: string = ".") => {
    setDialog({ visible: true, type: "new_folder", path: p, inputValue: "" });
  };

  const submitDialog = async (e: React.FormEvent) => {
    e.preventDefault();
    const { type, path, paths, inputValue } = dialog;
    setDialog({ ...dialog, visible: false });

    if (type === "delete") {
      try {
        await api.deleteFile(path, projectId);
        setOpenFiles((prev) => prev.filter((f) => !(f.path === path || f.path.startsWith(path + "/"))));
        if (activeFilePath === path || activeFilePath?.startsWith(path + "/")) setActiveFilePath(null);
        setSelectedPaths((prev) => {
          const next = new Set(prev);
          next.delete(path);
          return next;
        });
        setRefreshKey((k) => k + 1);
        addToast({ type: "success", message: `Deleted ${path}` });
      } catch (err) {
        addToast({ type: "error", message: `Delete failed: ${(err as Error).message}` });
      }
    } else if (type === "batch_delete" && paths) {
      try {
        await api.batchDeleteFiles(paths, projectId);
        setOpenFiles((prev) =>
          prev.filter((f) => !paths.some((p) => f.path === p || f.path.startsWith(p + "/")))
        );
        if (paths.some((p) => activeFilePath === p || activeFilePath?.startsWith(p + "/"))) setActiveFilePath(null);
        setSelectedPaths(new Set());
        setRefreshKey((k) => k + 1);
        addToast({ type: "success", message: `Deleted ${paths.length} item(s)` });
      } catch (err) {
        addToast({ type: "error", message: `Delete failed: ${(err as Error).message}` });
      }
    } else if (type === "rename" && inputValue && inputValue !== path) {
      try {
        await api.renameFile(path, inputValue, projectId);
        setOpenFiles((prev) =>
          prev.map((f) => {
            if (f.path === path) return { ...f, path: inputValue };
            if (f.path.startsWith(path + "/")) return { ...f, path: f.path.replace(path, inputValue) };
            return f;
          })
        );
        if (activeFilePath === path) setActiveFilePath(inputValue);
        else if (activeFilePath?.startsWith(path + "/"))
          setActiveFilePath(activeFilePath.replace(path, inputValue));
        setRefreshKey((k) => k + 1);
        addToast({ type: "success", message: `Renamed to ${inputValue}` });
      } catch (err) {
        addToast({ type: "error", message: `Rename failed: ${(err as Error).message}` });
      }
    } else if (type === "new_file" && inputValue) {
      const fp = path === "." ? inputValue : `${path}/${inputValue}`;
      try {
        await api.writeFile(fp, "", projectId);
        void openFile(fp);
        setRefreshKey((k) => k + 1);
        addToast({ type: "success", message: `Created file ${fp}` });
      } catch (err) {
        addToast({ type: "error", message: `Create failed: ${(err as Error).message}` });
      }
    } else if (type === "new_folder" && inputValue) {
      const fp = path === "." ? inputValue : `${path}/${inputValue}`;
      try {
        await api.createFolder(fp, projectId);
        setRefreshKey((k) => k + 1);
        addToast({ type: "success", message: `Created folder ${fp}` });
      } catch (err) {
        addToast({ type: "error", message: `Folder failed: ${(err as Error).message}` });
      }
    }
  };

  const handleExecuteFile = (path: string) => {
    const ext = path.split(".").pop()?.toLowerCase();
    let cmd = "";
    if (ext === "js" || ext === "ts") cmd = `node ${path}`;
    else if (ext === "py") cmd = `python ${path}`;
    else if (ext === "sh" || ext === "bash") cmd = `bash ${path}`;
    else if (ext === "rb") cmd = `ruby ${path}`;
    else if (ext === "php") cmd = `php ${path}`;
    else {
      addToast({ type: "warning", message: `Not executable: .${ext}` });
      return;
    }
    setShowTerminal(true);
    setTerminalTabs((prev) =>
      prev.map((t) => (t.id === activeTerminalTabId ? { ...t, cmd: { cmd, ts: Date.now() } } : t))
    );
  };

  const addTerminalTab = () => {
    const id = `t${Date.now()}`;
    setTerminalTabs((prev) => [...prev, { id, label: `Terminal ${prev.length + 1}`, cmd: null }]);
    setActiveTerminalTabId(id);
    setShowTerminal(true);
  };

  const closeTerminalTab = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setTerminalTabs((prev) => {
      const f = prev.filter((t) => t.id !== id);
      if (!f.length) {
        setShowTerminal(false);
        return [{ id: "t1", label: "Terminal 1", cmd: null }];
      }
      if (activeTerminalTabId === id) setActiveTerminalTabId(f[f.length - 1].id);
      return f;
    });
  };

  const handleContextMenu = (e: React.MouseEvent, path: string, isDir: boolean) => {
    e.preventDefault();
    e.stopPropagation();
    const isMulti = selectedPaths.size > 1 && selectedPaths.has(path);
    if (!selectedPaths.has(path)) {
      setSelectedPaths(new Set([path]));
      setLastSelectedPath(path);
    }
    setContextMenu({ x: e.clientX, y: e.clientY, path, isDir, isMulti });
  };

  const copyRelPath = (path: string) => {
    navigator.clipboard.writeText(path).then(() => addToast({ type: "success", message: "Path copied!" }));
  };

  const openTerminalHere = (folder: string) => {
    setShowTerminal(true);
    setTerminalTabs((prev) =>
      prev.map((t) => (t.id === activeTerminalTabId ? { ...t, cmd: { cmd: `cd ${folder}`, ts: Date.now() } } : t))
    );
  };

  const handleDrop = async (targetDir: string) => {
    if (!dragRef.current.length) return;
    const sources = dragRef.current.filter((s) => s !== targetDir);
    if (!sources.length) return;

    try {
      await api.batchMoveFiles(sources, targetDir, projectId);
      setRefreshKey((k) => k + 1);
      addToast({ type: "success", message: `Moved ${sources.length} item(s) into ${targetDir === "." ? "root" : targetDir}` });
    } catch (e) {
      addToast({ type: "error", message: `Move failed: ${(e as Error).message}` });
    }
    dragRef.current = [];
  };

  // Keyboard Shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.closest(".monaco-editor")) {
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        handleSave();
      } else if ((e.ctrlKey || e.metaKey) && e.key === "c" && selectedPaths.size > 0) {
        e.preventDefault();
        handleCopy();
      } else if ((e.ctrlKey || e.metaKey) && e.key === "x" && selectedPaths.size > 0) {
        e.preventDefault();
        handleCut();
      } else if ((e.ctrlKey || e.metaKey) && e.key === "v" && clipboard) {
        e.preventDefault();
        const targetDir = selectedPaths.size === 1 ? Array.from(selectedPaths)[0] : ".";
        handlePaste(targetDir);
      } else if ((e.ctrlKey || e.metaKey) && e.key === "d" && selectedPaths.size === 1) {
        e.preventDefault();
        handleDuplicate(Array.from(selectedPaths)[0]);
      } else if ((e.ctrlKey || e.metaKey) && e.key === "a") {
        e.preventDefault();
        setSelectedPaths(new Set(visiblePathsRef.current));
      } else if (e.key === "Delete" && selectedPaths.size > 0) {
        e.preventDefault();
        handleDeletePrompt(Array.from(selectedPaths));
      } else if (e.key === "F2" && selectedPaths.size === 1) {
        e.preventDefault();
        handleRenamePrompt(Array.from(selectedPaths)[0]);
      } else if (e.key === "Escape") {
        setSelectedPaths(new Set());
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedPaths, clipboard, handleSave]);

  const activeFile = openFiles.find((f) => f.path === activeFilePath);
  const activeTermTab = terminalTabs.find((t) => t.id === activeTerminalTabId);
  const containerStyle: React.CSSProperties = isFullScreen
    ? { position: "fixed", top: 0, left: 0, right: 0, bottom: 0, zIndex: 9999, display: "flex", background: "var(--color-canvas)", width: "100%", maxWidth: "none" }
    : { display: "flex", height: "100%", borderLeft: "1px solid var(--border-subtle)", background: "var(--bg-app)", width: "100%", maxWidth: 840 };

  const TAB_BTNS = [
    { key: "explorer", icon: <LayoutList size={18} />, title: "Explorer" },
    { key: "search", icon: <Search size={18} />, title: "Search" },
    { key: "git", icon: <GitBranch size={18} />, title: "Source Control" },
    { key: "activity", icon: <Activity size={18} />, title: "Activity Log" },
    { key: "history", icon: <History size={18} />, title: "File History" },
  ];

  const lf = (filterText || "").toLowerCase();
  const filteredRootItems = rootItems.filter((c) => !lf || c.name.toLowerCase().includes(lf) || c.is_dir);

  return (
    <div style={containerStyle} tabIndex={0}>
      {/* Left Navigation Bar */}
      <div
        style={{
          width: 44,
          borderRight: "1px solid var(--color-hairline)",
          background: "var(--bg-glass-card)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          paddingTop: 8,
          gap: 6,
          flexShrink: 0,
        }}
      >
        {TAB_BTNS.map(({ key, icon, title }) => (
          <button
            key={key}
            onClick={() => setActiveLeftTab(key as any)}
            title={title}
            style={{
              padding: 8,
              borderRadius: "var(--radius-sm)",
              color: activeLeftTab === key ? "var(--color-primary)" : "var(--color-body)",
              background: activeLeftTab === key ? "var(--color-primary-glow-sm)" : "transparent",
            }}
            className="hover:text-white transition-colors"
          >
            {icon}
          </button>
        ))}
      </div>

      <PanelGroup direction="horizontal" autoSaveId="fe-h">
        {/* Left Side Explorer View */}
        <Panel
          id="fe-left"
          order={1}
          defaultSize={32}
          minSize={20}
          maxSize={50}
          style={{
            display: "flex",
            flexDirection: "column",
            background: "var(--bg-surface)",
            borderRight: "1px solid var(--border-subtle)",
            position: "relative",
          }}
        >
          {/* Header Bar */}
          <div
            style={{
              padding: "8px 12px",
              borderBottom: "1px solid var(--color-hairline)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexShrink: 0,
            }}
          >
            <span
              className="body-sm-strong"
              style={{
                textTransform: "uppercase",
                fontSize: "11px",
                letterSpacing: "0.5px",
                color: "var(--color-mute)",
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              {activeLeftTab === "explorer"
                ? "Workspace Explorer"
                : activeLeftTab === "search"
                ? "Search"
                : activeLeftTab === "git"
                ? "Source Control"
                : activeLeftTab === "activity"
                ? "Activity Log"
                : "File History"}
            </span>

            <div style={{ display: "flex", gap: "2px", alignItems: "center" }}>
              {activeLeftTab === "explorer" && (
                <>
                  <button
                    className="btn btn-ghost btn-icon btn-sm"
                    onClick={() => handleCreateFilePrompt(".")}
                    title="New File at Root"
                  >
                    <FilePlus size={13} />
                  </button>
                  <button
                    className="btn btn-ghost btn-icon btn-sm"
                    onClick={() => handleCreateFolderPrompt(".")}
                    title="New Folder at Root"
                  >
                    <FolderPlus size={13} />
                  </button>
                  {clipboard && (
                    <button
                      className="btn btn-ghost btn-icon btn-sm"
                      onClick={() => handlePaste(".")}
                      title={`Paste (${clipboard.items.length} items in clipboard)`}
                      style={{ color: "#a855f7" }}
                    >
                      <ClipboardPaste size={13} />
                    </button>
                  )}
                  <button
                    className="btn btn-ghost btn-icon btn-sm"
                    onClick={() => handleDownloadZip()}
                    title="Download Workspace as Zip"
                  >
                    <Download size={13} />
                  </button>
                  <button
                    className="btn btn-ghost btn-icon btn-sm"
                    onClick={() => setCollapseSignal((s) => s + 1)}
                    title="Collapse All Folders"
                  >
                    <ChevronsUpDown size={13} />
                  </button>
                  <button
                    className="btn btn-ghost btn-icon btn-sm"
                    onClick={() => setRefreshKey((k) => k + 1)}
                    title="Refresh Tree"
                  >
                    <RefreshCw size={13} />
                  </button>
                </>
              )}
              <button
                className="btn btn-ghost btn-icon btn-sm"
                onClick={() => setIsFullScreen(!isFullScreen)}
                title={isFullScreen ? "Restore" : "Full Screen"}
              >
                {isFullScreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
              </button>
              {onClose && (
                <button className="btn btn-ghost btn-icon btn-sm" onClick={onClose} title="Close Explorer">
                  <X size={13} />
                </button>
              )}
            </div>
          </div>

          {activeLeftTab === "explorer" && (
            <>
              {/* Quick Filter Search */}
              <div style={{ padding: "4px 8px", borderBottom: "1px solid var(--color-hairline)" }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    background: "var(--bg-glass-panel)",
                    borderRadius: 4,
                    padding: "3px 8px",
                  }}
                >
                  <Filter size={11} color="var(--color-mute)" style={{ flexShrink: 0 }} />
                  <input
                    placeholder="Filter files by name…"
                    value={filterText}
                    onChange={(e) => setFilterText(e.target.value)}
                    style={{
                      flex: 1,
                      background: "transparent",
                      border: "none",
                      outline: "none",
                      fontSize: 12,
                      color: "var(--color-body)",
                    }}
                  />
                  {filterText && (
                    <button
                      onClick={() => setFilterText("")}
                      style={{ background: "none", border: "none", cursor: "pointer", color: "var(--color-mute)", padding: 0 }}
                    >
                      <X size={10} />
                    </button>
                  )}
                </div>
              </div>

              {/* Tree View Canvas */}
              <div
                style={{ flex: 1, overflowY: "auto", padding: "4px 0" }}
                onClick={() => setSelectedPaths(new Set())}
                onContextMenu={(e) => {
                  e.preventDefault();
                  setContextMenu({ x: e.clientX, y: e.clientY, path: ".", isDir: true, isMulti: false });
                }}
              >
                {projectId ? (
                  <>
                    {/* Workspace Header Row */}
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        padding: "5px 10px",
                        userSelect: "none",
                        fontSize: "11px",
                        fontWeight: 700,
                        textTransform: "uppercase",
                        letterSpacing: "0.6px",
                        color: "var(--color-mute)",
                        background: "rgba(255, 255, 255, 0.02)",
                        borderBottom: "1px solid var(--color-hairline)",
                        marginBottom: 4,
                      }}
                    >
                      <span style={{ marginRight: 6, fontSize: 13 }}>📁</span>
                      <span className="truncate">{projectName || "Workspace"}</span>
                    </div>

                    {/* Direct Top-Level Items (Clean VS Code Style) */}
                    <div style={{ paddingLeft: 4 }}>
                      {rootLoading && !rootItems.length && (
                        <div className="body-sm text-mute" style={{ padding: "8px 16px", fontSize: 12 }}>
                          Loading files…
                        </div>
                      )}
                      {filteredRootItems.map((child) => (
                        <TreeNode
                          key={child.path}
                          path={child.path}
                          name={child.name}
                          isDir={child.is_dir}
                          selectedPaths={selectedPaths}
                          onItemSelect={handleItemSelect}
                          projectId={projectId}
                          refreshKey={refreshKey}
                          onContextMenu={handleContextMenu}
                          filterText={filterText}
                          collapseSignal={collapseSignal}
                          dragRef={dragRef}
                          onDrop={handleDrop}
                          clipboard={clipboard}
                          visiblePathsRef={visiblePathsRef}
                          onCreateFile={handleCreateFilePrompt}
                          onCreateFolder={handleCreateFolderPrompt}
                          onDuplicate={handleDuplicate}
                          onDelete={handleDeletePrompt}
                          onRename={handleRenamePrompt}
                        />
                      ))}
                      {!filteredRootItems.length && !rootLoading && (
                        <div style={{ padding: "16px 20px", color: "var(--color-mute)", fontSize: "12px", fontStyle: "italic" }}>
                          No files in workspace
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      justifyContent: "center",
                      padding: "48px 16px",
                      textAlign: "center",
                      color: "var(--color-mute)",
                    }}
                  >
                    <Folder size={32} style={{ marginBottom: 12, opacity: 0.4 }} />
                    <div className="body-sm-strong" style={{ marginBottom: 8, color: "var(--color-body)" }}>
                      No Project Selected
                    </div>
                    <div className="caption" style={{ lineHeight: 1.5 }}>
                      Please select a project to view workspace files.
                    </div>
                  </div>
                )}
              </div>

              {/* Floating Multi-Selection Action Pill */}
              {selectedPaths.size > 1 && (
                <div
                  style={{
                    position: "absolute",
                    bottom: 12,
                    left: 12,
                    right: 12,
                    background: "rgba(18, 18, 36, 0.95)",
                    border: "1px solid rgba(168, 85, 247, 0.4)",
                    backdropFilter: "blur(12px)",
                    borderRadius: 10,
                    padding: "6px 12px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 6,
                    boxShadow: "0 8px 32px rgba(0,0,0,0.6)",
                    zIndex: 20,
                    animation: "fadeIn 0.15s ease-out",
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: "#c084fc",
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                    }}
                  >
                    <CheckSquare size={13} /> {selectedPaths.size} selected
                  </span>
                  <div style={{ display: "flex", gap: 4 }}>
                    <button
                      className="btn btn-ghost btn-sm"
                      style={{ fontSize: 11, padding: "2px 6px" }}
                      onClick={() => handleCut()}
                      title="Cut selected"
                    >
                      <Scissors size={12} className="mr-1" /> Cut
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      style={{ fontSize: 11, padding: "2px 6px" }}
                      onClick={() => handleCopy()}
                      title="Copy selected"
                    >
                      <Copy size={12} className="mr-1" /> Copy
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      style={{ fontSize: 11, padding: "2px 6px" }}
                      onClick={() => handleDownloadZip()}
                      title="Download zip of selected"
                    >
                      <Download size={12} className="mr-1" /> Zip
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      style={{ fontSize: 11, padding: "2px 6px", color: "var(--color-error)" }}
                      onClick={() => handleDeletePrompt(Array.from(selectedPaths))}
                      title="Delete selected"
                    >
                      <Trash2 size={12} className="mr-1" /> Delete
                    </button>
                    <button
                      className="btn btn-ghost btn-icon btn-sm"
                      style={{ padding: "2px 4px" }}
                      onClick={() => setSelectedPaths(new Set())}
                      title="Clear selection"
                    >
                      <X size={12} />
                    </button>
                  </div>
                </div>
              )}
            </>
          )}

          {activeLeftTab === "search" && <SearchPanel projectId={projectId} onFileSelect={openFile} />}
          {activeLeftTab === "git" && <GitPanel projectId={projectId} />}
          {activeLeftTab === "activity" && (
            teamId ? (
              <ActivityLogPanel teamId={teamId} />
            ) : (
              <div className="body-sm" style={{ color: "var(--color-mute)", padding: 16, fontStyle: "italic" }}>
                Please select a team room to view activity logs.
              </div>
            )
          )}
          {activeLeftTab === "history" && (
            <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
              {activeFilePath ? (
                <FileHistoryPanel
                  filePath={activeFilePath}
                  projectId={projectId}
                  onRestored={() => {
                    void openFile(activeFilePath);
                    setRefreshKey((k) => k + 1);
                  }}
                />
              ) : (
                <div className="body-sm" style={{ color: "var(--color-mute)", padding: 16, fontStyle: "italic" }}>
                  Open a file in the editor to see its version history.
                </div>
              )}
            </div>
          )}
        </Panel>

        <PanelResizeHandle className="resize-handle" style={{ width: "4px", cursor: "col-resize", background: "var(--border-subtle)", flexShrink: 0 }} />

        {/* Right Side Editor / Terminal View */}
        <Panel id="fe-right" order={2} style={{ display: "flex", flexDirection: "column", minWidth: 0, background: "transparent" }}>
          {openFiles.length > 0 ? (
            <>
              {/* File Tabs */}
              <div
                style={{
                  display: "flex",
                  background: "var(--bg-glass-card)",
                  overflowX: "auto",
                  overflowY: "hidden",
                  height: 35,
                  flexShrink: 0,
                }}
                className="scrollbar-hide"
              >
                {openFiles.map((file) => {
                  const isActive = file.path === activeFilePath;
                  const fname = file.path.split("/").pop() || file.path;
                  return (
                    <div
                      key={file.path}
                      onClick={() => setActiveFilePath(file.path)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        padding: "0 8px 0 12px",
                        gap: 4,
                        background: isActive ? "var(--bg-glass-panel)" : "transparent",
                        color: isActive ? "var(--color-primary)" : "var(--color-mute)",
                        borderRight: "1px solid var(--color-hairline)",
                        borderTop: isActive ? "1px solid var(--color-primary)" : "1px solid transparent",
                        cursor: "pointer",
                        minWidth: 100,
                        maxWidth: 180,
                        height: "100%",
                        userSelect: "none",
                      }}
                      className="hover:bg-[#2a2d2e] transition-colors"
                    >
                      <span style={{ fontSize: 12, flexShrink: 0 }}>{getFileIcon(fname)}</span>
                      <span className="truncate body-sm font-mono" style={{ fontSize: "12px", flex: 1 }}>
                        {fname}
                      </span>
                      {file.isDirty && <div style={{ width: 7, height: 7, borderRadius: "50%", background: "#fff", flexShrink: 0 }} />}
                      <button
                        onClick={(e) => closeFile(file.path, e)}
                        style={{
                          padding: 2,
                          borderRadius: 3,
                          flexShrink: 0,
                          background: "none",
                          border: "none",
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          color: "var(--color-mute)",
                        }}
                        className="hover:text-white transition-colors"
                        title="Close"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  );
                })}
              </div>

              {/* Breadcrumb & Action Toolbar */}
              {activeFile && (
                <div
                  style={{
                    padding: "3px 12px",
                    borderBottom: "1px solid var(--color-hairline)",
                    background: "var(--bg-glass-panel)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    flexShrink: 0,
                    gap: 8,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0, flex: 1 }}>
                    <Breadcrumb path={activeFile.path} />
                    {isMarkdownPath(activeFile.path) && (
                      <div style={{ display: "flex", gap: 2, background: "var(--color-surface)", borderRadius: 4, padding: 2, flexShrink: 0 }}>
                        <button
                          className="btn btn-sm"
                          onClick={() => setViewMode("preview")}
                          style={{
                            padding: "1px 7px",
                            fontSize: 11,
                            background: viewMode === "preview" ? "var(--color-primary)" : "transparent",
                            color: viewMode === "preview" ? "#fff" : "var(--color-body)",
                            border: "none",
                          }}
                        >
                          <Eye size={11} className="mr-1" />
                          Preview
                        </button>
                        <button
                          className="btn btn-sm"
                          onClick={() => setViewMode("edit")}
                          style={{
                            padding: "1px 7px",
                            fontSize: 11,
                            background: viewMode === "edit" ? "var(--color-primary)" : "transparent",
                            color: viewMode === "edit" ? "#fff" : "var(--color-body)",
                            border: "none",
                          }}
                        >
                          <Pencil size={11} className="mr-1" />
                          Edit
                        </button>
                      </div>
                    )}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                    {isExecutable(activeFile.path) && (
                      <button
                        onClick={() => handleExecuteFile(activeFile.path)}
                        style={{
                          padding: "2px 8px",
                          fontSize: 11,
                          background: "rgba(34,197,94,0.15)",
                          color: "#4ade80",
                          border: "1px solid rgba(74,222,128,0.3)",
                          borderRadius: 4,
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          gap: 4,
                        }}
                        title="Run"
                      >
                        <Play size={11} />
                        Run
                      </button>
                    )}
                    <button
                      className={`btn btn-sm ${showTerminal ? "btn-secondary" : "btn-ghost"}`}
                      onClick={() => setShowTerminal((s) => !s)}
                      style={{ padding: "2px 8px", fontSize: 11 }}
                    >
                      <TerminalIcon size={11} className="mr-1" />
                      Terminal
                    </button>
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={handleSave}
                      disabled={saving || !activeFile.isDirty}
                      style={{ padding: "2px 8px", fontSize: 11 }}
                    >
                      {saving ? "Saving…" : "Save"}
                    </button>
                  </div>
                </div>
              )}

              {/* Remote change alert banner */}
              {activeFile?.staleRemote && (
                <div
                  style={{
                    padding: "5px 16px",
                    borderBottom: "1px solid var(--color-hairline)",
                    background: "rgba(234,179,8,0.12)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 8,
                    flexShrink: 0,
                  }}
                >
                  <span className="caption" style={{ color: "#eab308" }}>
                    ⚠ {activeFile.staleRemote.sender} updated this file remotely.
                  </span>
                  <button
                    className="btn btn-sm btn-secondary"
                    onClick={() => applyStaleRemote(activeFile.path)}
                    style={{ padding: "2px 8px", fontSize: 11 }}
                  >
                    <RefreshCcwDot size={11} className="mr-1" />
                    Reload
                  </button>
                </div>
              )}

              {/* Editor Workspace */}
              <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
                {loadingContent ? (
                  <div className="text-mute body-sm p-4">Loading…</div>
                ) : (
                  <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
                    <PanelGroup direction="vertical" autoSaveId="fe-v">
                      <Panel defaultSize={showTerminal ? 60 : 100} minSize={20} style={{ display: "flex", flexDirection: "column", overflow: "hidden", paddingTop: 4 }}>
                        {activeFile ? (
                          isMarkdownPath(activeFile.path) && viewMode === "preview" ? (
                            <div style={{ height: "100%", overflowY: "auto", padding: "8px 24px 32px" }} className="markdown-body">
                              {activeFile.content.trim() ? (
                                <ReactMarkdown
                                  remarkPlugins={[remarkGfm]}
                                  components={{
                                    a: ({ node, ...p }) => <a {...p} target="_blank" rel="noopener noreferrer" />,
                                  }}
                                >
                                  {activeFile.content}
                                </ReactMarkdown>
                              ) : (
                                <div className="body-sm" style={{ color: "var(--color-mute)", fontStyle: "italic" }}>
                                  Empty — switch to Edit.
                                </div>
                              )}
                            </div>
                          ) : (
                            <Editor
                              height="100%"
                              language={getLanguageFromPath(activeFile.path)}
                              theme="vs-dark"
                              value={activeFile.content}
                              onChange={(v) => updateFileContent(activeFile.path, v || "")}
                              options={
                                {
                                  minimap: { enabled: true, maxColumn: 80, renderCharacters: false },
                                  fontSize: 13,
                                  fontFamily: "'JetBrains Mono','Fira Code',Consolas,monospace",
                                  wordWrap: "on",
                                  padding: { top: 8, bottom: 16 },
                                  scrollBeyondLastLine: false,
                                  quickSuggestions: true,
                                  suggestOnTriggerCharacters: true,
                                  hover: { enabled: true, delay: 500 },
                                  renderWhitespace: "boundary",
                                  smoothScrolling: true,
                                } as any
                              }
                            />
                          )
                        ) : (
                          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-mute)" }} className="body-sm">
                            Select a file to view
                          </div>
                        )}
                      </Panel>
                      {showTerminal && (
                        <>
                          <PanelResizeHandle className="resize-handle" />
                          <Panel defaultSize={40} minSize={20} style={{ display: "flex", flexDirection: "column", borderTop: "1px solid var(--color-hairline)", overflow: "hidden" }}>
                            <div style={{ display: "flex", alignItems: "center", background: "var(--bg-glass-card)", borderBottom: "1px solid var(--color-hairline)", height: 30, flexShrink: 0 }}>
                              {terminalTabs.map((tab) => (
                                <div
                                  key={tab.id}
                                  onClick={() => setActiveTerminalTabId(tab.id)}
                                  style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 4,
                                    padding: "0 10px",
                                    height: "100%",
                                    cursor: "pointer",
                                    borderRight: "1px solid var(--color-hairline)",
                                    background: activeTerminalTabId === tab.id ? "var(--bg-glass-panel)" : "transparent",
                                    color: activeTerminalTabId === tab.id ? "var(--color-body)" : "var(--color-mute)",
                                    fontSize: 12,
                                    userSelect: "none",
                                  }}
                                  className="hover:bg-gray-800 transition-colors"
                                >
                                  <TerminalIcon size={11} />
                                  <span>{tab.label}</span>
                                  {terminalTabs.length > 1 && (
                                    <button
                                      onClick={(e) => closeTerminalTab(tab.id, e)}
                                      style={{ background: "none", border: "none", cursor: "pointer", padding: "0 2px", color: "var(--color-mute)" }}
                                      className="hover:text-white"
                                    >
                                      <X size={10} />
                                    </button>
                                  )}
                                </div>
                              ))}
                              <button onClick={addTerminalTab} title="New Terminal" style={{ padding: "0 10px", height: "100%", background: "none", border: "none", cursor: "pointer", color: "var(--color-mute)" }} className="hover:text-white">
                                <Plus size={12} />
                              </button>
                              <div style={{ flex: 1 }} />
                              <button onClick={() => setShowTerminal(false)} style={{ padding: "0 8px", height: "100%", background: "none", border: "none", cursor: "pointer", color: "var(--color-mute)" }} className="hover:text-white">
                                <X size={12} />
                              </button>
                            </div>
                            {terminalTabs.map((tab) => (
                              <div key={tab.id} style={{ flex: 1, display: activeTerminalTabId === tab.id ? "flex" : "none", flexDirection: "column", overflow: "hidden" }}>
                                <TerminalPanel projectId={projectId} onClose={() => setShowTerminal(false)} triggerCommand={tab.cmd} />
                              </div>
                            ))}
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
                <button className={`btn btn-sm ${showTerminal ? "btn-secondary" : "btn-ghost"}`} onClick={() => setShowTerminal((s) => !s)}>
                  <TerminalIcon size={13} className="mr-1" />
                  Terminal
                </button>
              </div>
              <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
                {!showTerminal ? (
                  <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-mute)" }} className="body-sm">
                    Select a file from the explorer
                  </div>
                ) : (
                  <TerminalPanel projectId={projectId} onClose={() => setShowTerminal(false)} triggerCommand={activeTermTab?.cmd ?? null} />
                )}
              </div>
            </div>
          )}
        </Panel>
      </PanelGroup>

      {/* Context Menu */}
      {contextMenu && (
        <div
          style={{
            position: "fixed",
            top: contextMenu.y,
            left: contextMenu.x,
            background: "var(--color-surface)",
            border: "1px solid var(--color-hairline)",
            borderRadius: "6px",
            boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
            padding: "4px 0",
            zIndex: 9999,
            minWidth: "195px",
            display: "flex",
            flexDirection: "column",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {contextMenu.isMulti ? (
            <>
              <div style={{ padding: "4px 14px", fontSize: "11px", fontWeight: 700, color: "var(--color-mute)", textTransform: "uppercase" }}>
                {selectedPaths.size} Items Selected
              </div>
              <ContextMenuItem onClick={() => { handleCut(); setContextMenu(null); }}>
                <Scissors size={13} /> Cut ({selectedPaths.size})
              </ContextMenuItem>
              <ContextMenuItem onClick={() => { handleCopy(); setContextMenu(null); }}>
                <Copy size={13} /> Copy ({selectedPaths.size})
              </ContextMenuItem>
              <ContextMenuItem onClick={() => { void handleDownloadZip(); setContextMenu(null); }}>
                <Download size={13} /> Download .zip
              </ContextMenuItem>
              <div style={{ height: "1px", background: "var(--color-hairline)", margin: "4px 0" }} />
              <ContextMenuItem
                onClick={() => { handleDeletePrompt(Array.from(selectedPaths)); setContextMenu(null); }}
                style={{ color: "var(--color-error)" }}
              >
                <Trash2 size={13} /> Delete All ({selectedPaths.size})
              </ContextMenuItem>
            </>
          ) : (
            <>
              {contextMenu.isDir && (
                <>
                  <ContextMenuItem onClick={() => { handleCreateFilePrompt(contextMenu.path); setContextMenu(null); }}>
                    <FilePlus size={13} /> New File
                  </ContextMenuItem>
                  <ContextMenuItem onClick={() => { handleCreateFolderPrompt(contextMenu.path); setContextMenu(null); }}>
                    <FolderPlus size={13} /> New Folder
                  </ContextMenuItem>
                  {clipboard && (
                    <ContextMenuItem onClick={() => { handlePaste(contextMenu.path); setContextMenu(null); }}>
                      <ClipboardPaste size={13} /> Paste ({clipboard.items.length} items)
                    </ContextMenuItem>
                  )}
                  <ContextMenuItem onClick={() => { openTerminalHere(contextMenu.path); setContextMenu(null); }}>
                    <TerminalIcon size={13} /> Open Terminal Here
                  </ContextMenuItem>
                  <ContextMenuItem onClick={() => { void handleDownloadZip([contextMenu.path]); setContextMenu(null); }}>
                    <Download size={13} /> Download Folder as Zip
                  </ContextMenuItem>
                  <div style={{ height: "1px", background: "var(--color-hairline)", margin: "4px 0" }} />
                </>
              )}

              {!contextMenu.isDir && (
                <>
                  <ContextMenuItem onClick={() => { openFile(contextMenu.path); setContextMenu(null); }}>
                    <Eye size={13} /> Open / Edit
                  </ContextMenuItem>
                  {isExecutable(contextMenu.path) && (
                    <ContextMenuItem onClick={() => { handleExecuteFile(contextMenu.path); setContextMenu(null); }}>
                      <Play size={13} /> Run File
                    </ContextMenuItem>
                  )}
                  <div style={{ height: "1px", background: "var(--color-hairline)", margin: "4px 0" }} />
                </>
              )}

              <ContextMenuItem onClick={() => { handleCut([contextMenu.path]); setContextMenu(null); }}>
                <Scissors size={13} /> Cut
              </ContextMenuItem>
              <ContextMenuItem onClick={() => { handleCopy([contextMenu.path]); setContextMenu(null); }}>
                <Copy size={13} /> Copy
              </ContextMenuItem>
              {!contextMenu.isDir && (
                <ContextMenuItem onClick={() => { handleDuplicate(contextMenu.path); setContextMenu(null); }}>
                  <Files size={13} /> Duplicate
                </ContextMenuItem>
              )}
              <ContextMenuItem onClick={() => { handleRenamePrompt(contextMenu.path); setContextMenu(null); }}>
                <Pencil size={13} /> Rename
              </ContextMenuItem>
              <ContextMenuItem onClick={() => { copyRelPath(contextMenu.path); setContextMenu(null); }}>
                <Copy size={13} /> Copy Relative Path
              </ContextMenuItem>
              <div style={{ height: "1px", background: "var(--color-hairline)", margin: "4px 0" }} />
              <ContextMenuItem
                onClick={() => { handleDeletePrompt([contextMenu.path]); setContextMenu(null); }}
                style={{ color: "var(--color-error)" }}
              >
                <Trash2 size={13} /> Delete
              </ContextMenuItem>
            </>
          )}
        </div>
      )}

      {/* Confirmation & Input Dialogs */}
      {dialog.visible && (
        <Modal
          open={dialog.visible}
          onClose={() => setDialog({ ...dialog, visible: false })}
          title={
            dialog.type === "delete"
              ? "Delete Item"
              : dialog.type === "batch_delete"
              ? "Delete Multiple Items"
              : dialog.type === "rename"
              ? "Rename Item"
              : dialog.type === "new_file"
              ? "Create New File"
              : "Create New Folder"
          }
          maxWidth={420}
        >
          <form onSubmit={submitDialog} style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
            <p className="body-sm">
              {dialog.type === "delete"
                ? `Are you sure you want to permanently delete "${dialog.path}"?`
                : dialog.type === "batch_delete"
                ? `Are you sure you want to permanently delete these ${dialog.paths?.length || 0} selected items?`
                : dialog.type === "rename"
                ? `Rename "${dialog.path}" to:`
                : dialog.type === "new_file"
                ? `Enter name for new file in "${dialog.path}":`
                : `Enter name for new folder in "${dialog.path}":`}
            </p>
            {dialog.type === "batch_delete" && dialog.paths && (
              <div
                style={{
                  maxHeight: 120,
                  overflowY: "auto",
                  background: "var(--bg-glass-panel)",
                  borderRadius: 6,
                  padding: "6px 10px",
                  fontSize: 11,
                  fontFamily: "var(--font-mono)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 3,
                }}
              >
                {dialog.paths.map((p) => (
                  <span key={p} className="truncate">
                    • {p}
                  </span>
                ))}
              </div>
            )}
            {dialog.type !== "delete" && dialog.type !== "batch_delete" && (
              <input
                className="input"
                autoFocus
                value={dialog.inputValue}
                onChange={(e) => setDialog({ ...dialog, inputValue: e.target.value })}
              />
            )}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--sp-sm)", marginTop: "var(--sp-md)" }}>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setDialog({ ...dialog, visible: false })}>
                Cancel
              </button>
              <button
                type="submit"
                className={`btn btn-sm ${dialog.type === "delete" || dialog.type === "batch_delete" ? "btn-danger" : "btn-primary"}`}
                disabled={dialog.type !== "delete" && dialog.type !== "batch_delete" && !dialog.inputValue.trim()}
              >
                {dialog.type === "delete" || dialog.type === "batch_delete" ? "Delete" : "Confirm"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

function TreeNode({
  path,
  name,
  isDir,
  selectedPaths,
  onItemSelect,
  defaultExpanded = false,
  projectId,
  refreshKey,
  onContextMenu,
  filterText,
  collapseSignal,
  dragRef,
  onDrop,
  clipboard,
  visiblePathsRef,
  onCreateFile,
  onCreateFolder,
  onDuplicate,
  onDelete,
  onRename,
}: {
  path: string;
  name: string;
  isDir: boolean;
  selectedPaths: Set<string>;
  onItemSelect: (p: string, isDir: boolean, event: React.MouseEvent) => void;
  defaultExpanded?: boolean;
  projectId?: string;
  refreshKey: number;
  onContextMenu: (e: React.MouseEvent, p: string, d: boolean) => void;
  filterText?: string;
  collapseSignal?: number;
  dragRef: React.MutableRefObject<string[]>;
  onDrop: (dir: string) => void;
  clipboard: ClipboardState | null;
  visiblePathsRef: React.MutableRefObject<string[]>;
  onCreateFile: (p: string) => void;
  onCreateFolder: (p: string) => void;
  onDuplicate: (p: string) => void;
  onDelete: (paths: string[]) => void;
  onRename: (p: string) => void;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [children, setChildren] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState(name);
  const [isDragOver, setIsDragOver] = useState(false);
  const editRef = useRef<HTMLInputElement>(null);
  const { addToast } = useToast();

  const loadChildren = async () => {
    if (!isDir) return;
    setLoading(true);
    try {
      const items = await api.listFiles(path, projectId);
      items.sort((a, b) => (a.is_dir === b.is_dir ? a.name.localeCompare(b.name) : a.is_dir ? -1 : 1));
      setChildren(items);
    } catch (err: any) {
      if (err.status === 404) {
        setExpanded(false);
        setChildren([]);
      } else console.warn(`Failed:${path}`, err);
    } finally {
      setLoading(false);
    }
  };

  const toggleExpand = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!isDir) {
      onItemSelect(path, false, e);
      return;
    }
    onItemSelect(path, true, e);
    if (!expanded) {
      setExpanded(true);
      loadChildren();
    } else {
      setExpanded(false);
    }
  };

  useEffect(() => {
    if (expanded && isDir) void loadChildren();
  }, [refreshKey]);

  useEffect(() => {
    if (defaultExpanded && expanded && isDir && children.length === 0) void loadChildren();
  }, []);

  useEffect(() => {
    if ((collapseSignal || 0) > 0 && !defaultExpanded) setExpanded(false);
  }, [collapseSignal]);

  const commitRename = async () => {
    setIsEditing(false);
    const n = editName.trim();
    if (!n || n === name) return;
    const parent = path.includes("/") ? path.substring(0, path.lastIndexOf("/")) : ".";
    const np = parent === "." ? n : `${parent}/${n}`;
    try {
      await api.renameFile(path, np, projectId);
      addToast({ type: "success", message: `Renamed to ${n}` });
    } catch (e) {
      addToast({ type: "error", message: `Rename failed: ${(e as Error).message}` });
      setEditName(name);
    }
  };

  // Register in visible paths for range selection
  useEffect(() => {
    if (path !== "." && !visiblePathsRef.current.includes(path)) {
      visiblePathsRef.current.push(path);
    }
    return () => {
      visiblePathsRef.current = visiblePathsRef.current.filter((p) => p !== path);
    };
  }, [path]);

  const lf = (filterText || "").toLowerCase();
  if (lf && !name.toLowerCase().includes(lf) && !isDir) return null;

  const isSelected = selectedPaths.has(path);
  const isCut = clipboard?.isCut && clipboard.items.includes(path);
  const folderIcon = isDir ? (expanded ? "📂" : "📁") : getFileIcon(name);

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          padding: "3px 8px",
          backgroundColor: isDragOver
            ? "rgba(168, 85, 247, 0.25)"
            : isSelected
            ? "rgba(168, 85, 247, 0.2)"
            : "transparent",
          color: isSelected ? "#c084fc" : "var(--color-body)",
          cursor: "pointer",
          userSelect: "none",
          borderLeftWidth: "2px",
          borderLeftStyle: isCut ? "dashed" : "solid",
          borderLeftColor: isSelected ? "#a855f7" : "transparent",
          opacity: isCut ? 0.45 : 1,
          borderRadius: "0 4px 4px 0",
          transition: "background-color 0.12s ease",
        }}
        className="hover:bg-gray-800 transition-colors"
        onClick={toggleExpand}
        onContextMenu={(e) => onContextMenu(e, path, isDir)}
        onDoubleClick={(e) => {
          if (!isDir) {
            e.stopPropagation();
            setIsEditing(true);
            setEditName(name);
            setTimeout(() => editRef.current?.select(), 50);
          }
        }}
        draggable={!defaultExpanded}
        onDragStart={(e) => {
          if (isSelected && selectedPaths.size > 1) {
            dragRef.current = Array.from(selectedPaths);
          } else {
            dragRef.current = [path];
          }
          e.dataTransfer.effectAllowed = "move";
        }}
        onDragEnd={() => {
          dragRef.current = [];
          setIsDragOver(false);
        }}
        onDragOver={(e) => {
          if (isDir) {
            e.preventDefault();
            setIsDragOver(true);
          }
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragOver(false);
          if (isDir) onDrop(path);
        }}
      >
        <span style={{ width: 16, display: "flex", justifyContent: "center", marginRight: 2, flexShrink: 0 }}>
          {isDir ? (
            expanded ? (
              <ChevronDown size={13} color="var(--color-mute)" />
            ) : (
              <ChevronRight size={13} color="var(--color-mute)" />
            )
          ) : (
            <span />
          )}
        </span>
        <span style={{ marginRight: 6, fontSize: 13, flexShrink: 0 }}>{folderIcon}</span>
        {isEditing ? (
          <input
            ref={editRef}
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                commitRename();
              }
              if (e.key === "Escape") {
                setIsEditing(false);
                setEditName(name);
              }
            }}
            onClick={(e) => e.stopPropagation()}
            style={{
              flex: 1,
              background: "var(--bg-glass-panel)",
              border: "1px solid var(--color-primary)",
              borderRadius: 3,
              padding: "0 4px",
              fontSize: 13,
              color: "var(--color-body)",
              outline: "none",
            }}
          />
        ) : (
          <span className="body-sm truncate" style={{ fontSize: "12.5px", flex: 1 }}>
            {name}
          </span>
        )}
        {loading && <RefreshCw size={10} className="animate-spin ml-1" style={{ color: "var(--color-mute)", flexShrink: 0 }} />}
      </div>

      {expanded && isDir && (
        <div style={{ paddingLeft: 12 }}>
          {children
            .filter((c) => !lf || c.name.toLowerCase().includes(lf) || c.is_dir)
            .map((child) => (
              <TreeNode
                key={child.path}
                path={child.path}
                name={child.name}
                isDir={child.is_dir}
                selectedPaths={selectedPaths}
                onItemSelect={onItemSelect}
                projectId={projectId}
                refreshKey={refreshKey}
                onContextMenu={onContextMenu}
                filterText={filterText}
                collapseSignal={collapseSignal}
                dragRef={dragRef}
                onDrop={onDrop}
                clipboard={clipboard}
                visiblePathsRef={visiblePathsRef}
                onCreateFile={onCreateFile}
                onCreateFolder={onCreateFolder}
                onDuplicate={onDuplicate}
                onDelete={onDelete}
                onRename={onRename}
              />
            ))}
          {!children.length && !loading && (
            <div style={{ padding: "4px 28px", color: "var(--color-mute)", fontSize: "12px", fontStyle: "italic" }}>
              Empty
            </div>
          )}
        </div>
      )}
    </div>
  );
}
