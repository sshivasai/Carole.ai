"use client";

import React, { useState } from "react";
import { 
  FileCode, FileText, Code2, ChevronDown, ChevronRight, 
  ExternalLink, Eye, EyeOff, FileSpreadsheet, Sparkles 
} from "lucide-react";
import { DiffViewer } from "./DiffViewer";

export interface ChangedFileItem {
  path: string;
  diff?: string;
  content?: string;
  action?: string;
  additions?: number;
  deletions?: number;
}

interface FileChangeCardProps {
  files?: ChangedFileItem[] | ChangedFileItem;
  senderName?: string;
  path?: string;
  diff?: string;
  content?: string;
  action?: string;
  timestamp?: string | number;
  onOpenFile?: (path: string) => void;
  onOpenDiffFile?: (path: string) => void;
}

function getFileExtensionIcon(path: string) {
  const ext = (path.split('.').pop() || "").toLowerCase();
  switch (ext) {
    case "tsx":
    case "jsx":
    case "ts":
    case "js":
      return { icon: Code2, color: "#60a5fa", bg: "rgba(96, 165, 250, 0.15)", label: "TSX" };
    case "py":
      return { icon: FileCode, color: "#38bdf8", bg: "rgba(56, 189, 248, 0.15)", label: "PY" };
    case "json":
    case "yaml":
    case "yml":
      return { icon: FileSpreadsheet, color: "#f59e0b", bg: "rgba(245, 158, 11, 0.15)", label: "JSON" };
    case "md":
    case "txt":
      return { icon: FileText, color: "#34d399", bg: "rgba(52, 211, 153, 0.15)", label: "DOC" };
    default:
      return { icon: FileCode, color: "#a78bfa", bg: "rgba(167, 139, 250, 0.15)", label: "FILE" };
  }
}

export default function FileChangeCard({
  files,
  senderName,
  path,
  diff,
  content,
  action = "modified",
  timestamp,
  onOpenFile,
  onOpenDiffFile
}: FileChangeCardProps) {
  // Normalize input into an array of file change items
  const fileList: ChangedFileItem[] = React.useMemo(() => {
    if (Array.isArray(files)) return files;
    if (files && typeof files === "object") return [files];
    if (path) return [{ path, diff, content, action }];
    return [];
  }, [files, path, diff, content, action]);

  const [expandedFiles, setExpandedFiles] = useState<Record<string, boolean>>({});
  const [isAllExpanded, setIsAllExpanded] = useState(false);

  if (fileList.length === 0) return null;

  // Calculate additions/deletions per file and totals truthfully
  const enrichedFiles = fileList.map(f => {
    const isRealDiff = Boolean(f.diff && (f.diff.includes("@@") || f.diff.startsWith("---") || f.diff.startsWith("+++") || f.diff.includes("\n+") || f.diff.includes("\n-")));
    const diffLines = f.diff ? f.diff.split('\n') : [];
    
    let additions = f.additions ?? 0;
    let deletions = f.deletions ?? 0;

    if (f.additions === undefined && isRealDiff) {
      additions = diffLines.filter(l => l.startsWith('+') && !l.startsWith('+++')).length;
    } else if (f.additions === undefined && f.action === "create" && f.content) {
      additions = f.content.split('\n').length;
    }

    if (f.deletions === undefined && isRealDiff) {
      deletions = diffLines.filter(l => l.startsWith('-') && !l.startsWith('---')).length;
    }

    const changeKind: "patch" | "content_preview" | "unavailable" = isRealDiff 
      ? "patch" 
      : (f.content ? "content_preview" : "unavailable");

    return {
      ...f,
      additions,
      deletions,
      changeKind,
      displayDiff: f.diff || f.content || ""
    };
  });

  const totalAdditions = enrichedFiles.reduce((acc, f) => acc + f.additions, 0);
  const totalDeletions = enrichedFiles.reduce((acc, f) => acc + f.deletions, 0);

  const toggleFileDiff = (filePath: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setExpandedFiles(prev => ({
      ...prev,
      [filePath]: !prev[filePath]
    }));
  };

  const toggleAll = (e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const nextState = !isAllExpanded;
    setIsAllExpanded(nextState);
    const updated: Record<string, boolean> = {};
    enrichedFiles.forEach(f => {
      updated[f.path] = nextState;
    });
    setExpandedFiles(updated);
  };

  const fileCount = enrichedFiles.length;

  return (
    <div 
      style={{
        margin: "8px 0 4px 0",
        borderRadius: "10px",
        background: "#13131c",
        border: "1px solid rgba(255, 255, 255, 0.1)",
        overflow: "hidden",
        boxShadow: "0 4px 16px rgba(0, 0, 0, 0.3)",
        fontFamily: "var(--font-sans, system-ui, -apple-system, sans-serif)",
        color: "#f1f5f9"
      }}
      className="file-change-card"
    >
      {/* Header Summary Bar (Antigravity Style) */}
      <div 
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "8px 14px",
          background: "#181824",
          borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
          fontSize: "12px",
          userSelect: "none"
        }}
      >
        <div 
          onClick={toggleAll}
          style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}
        >
          <span style={{ color: "#f8fafc", fontWeight: 700 }}>
            {fileCount} {fileCount === 1 ? "file changed" : "files changed"}
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", fontSize: "11.5px", fontWeight: 700, fontFamily: "var(--font-mono, monospace)" }}>
            <span style={{ color: "#4ade80" }}>+{totalAdditions}</span>
            <span style={{ color: "#f87171" }}>-{totalDeletions}</span>
          </span>
          <span style={{ color: "#94a3b8", display: "flex", alignItems: "center" }}>
            {isAllExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {senderName && (
            <span style={{ fontSize: "11px", color: "#94a3b8" }}>
              by <strong style={{ color: "#c4b5fd" }}>{senderName}</strong>
            </span>
          )}
          <button
            onClick={toggleAll}
            style={{
              padding: "3px 10px",
              height: "25px",
              fontSize: "11px",
              fontWeight: 600,
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
              background: isAllExpanded ? "rgba(167, 139, 250, 0.25)" : "rgba(255, 255, 255, 0.08)",
              border: "1px solid rgba(255, 255, 255, 0.15)",
              color: isAllExpanded ? "#c4b5fd" : "#f1f5f9",
              borderRadius: "6px",
              cursor: "pointer",
              transition: "all 0.15s"
            }}
            className="hover:bg-[rgba(255,255,255,0.12)]"
          >
            {isAllExpanded ? <EyeOff size={12} /> : <Eye size={12} />}
            {isAllExpanded ? "Hide All Diffs" : (fileCount > 1 ? "Review All" : "Review")}
          </button>
        </div>
      </div>

      {/* List of Changed Files */}
      <div style={{ display: "flex", flexDirection: "column" }}>
        {enrichedFiles.map((file, idx) => {
          const fileName = file.path.split(/[/\\]/).pop() || file.path;
          const dirPath = file.path.includes('/') || file.path.includes('\\') 
            ? file.path.substring(0, Math.max(file.path.lastIndexOf('/'), file.path.lastIndexOf('\\')))
            : "";
          const extInfo = getFileExtensionIcon(fileName);
          const ExtIcon = extInfo.icon;
          const isFileOpen = Boolean(expandedFiles[file.path]);

          return (
            <div 
              key={idx}
              style={{
                borderBottom: idx < enrichedFiles.length - 1 ? "1px solid rgba(255, 255, 255, 0.06)" : "none"
              }}
            >
              {/* File Item Row */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "8px 14px",
                  background: isFileOpen ? "rgba(255, 255, 255, 0.02)" : "transparent",
                  transition: "background 0.15s"
                }}
                className="hover:bg-[rgba(255,255,255,0.03)]"
              >
                <div 
                  onClick={() => onOpenFile?.(file.path)}
                  style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: 0, flex: 1, cursor: onOpenFile ? "pointer" : "default" }}
                  title={onOpenFile ? `Click to open ${fileName} in editor` : undefined}
                >
                  <div 
                    style={{
                      width: 26,
                      height: 26,
                      borderRadius: 6,
                      background: extInfo.bg,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0
                    }}
                  >
                    <ExtIcon size={14} color={extInfo.color} />
                  </div>

                  <div style={{ display: "flex", alignItems: "baseline", gap: "8px", minWidth: 0, overflow: "hidden" }}>
                    <span style={{ fontSize: "12.5px", fontWeight: 600, color: "#f8fafc", whiteSpace: "nowrap" }}>
                      {fileName}
                    </span>
                    {dirPath && (
                      <span style={{ fontSize: "11px", color: "#94a3b8", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {dirPath}
                      </span>
                    )}
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "8px", flexShrink: 0 }}>
                  <span style={{ fontSize: "11px", fontFamily: "var(--font-mono, monospace)", fontWeight: 600 }}>
                    <span style={{ color: "#4ade80" }}>+{file.additions}</span>{" "}
                    <span style={{ color: "#f87171" }}>-{file.deletions}</span>
                  </span>

                  <button
                    onClick={(e) => toggleFileDiff(file.path, e)}
                    style={{
                      background: isFileOpen ? "rgba(56, 189, 248, 0.15)" : "rgba(255, 255, 255, 0.05)",
                      border: "1px solid rgba(255, 255, 255, 0.1)",
                      color: isFileOpen ? "#38bdf8" : "#cbd5e1",
                      fontSize: "10.5px",
                      fontWeight: 600,
                      padding: "2px 8px",
                      height: "22px",
                      borderRadius: "4px",
                      cursor: "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "4px"
                    }}
                    className="hover:bg-[rgba(255,255,255,0.1)]"
                  >
                    <Eye size={11} />
                    {isFileOpen ? "Hide" : "Review"}
                  </button>

                  <div style={{ display: "flex", gap: "6px" }}>
                      {(onOpenFile || onOpenDiffFile) && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            if (onOpenDiffFile) onOpenDiffFile(file.path);
                            else if (onOpenFile) onOpenFile(file.path);
                          }}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            background: "rgba(255,255,255,0.06)",
                            border: "1px solid rgba(255,255,255,0.1)",
                            borderRadius: "4px",
                            padding: "4px",
                            color: "#94a3b8",
                            cursor: "pointer"
                          }}
                          className="hover:bg-[rgba(255,255,255,0.15)] hover:text-white"
                          title="Open in diff editor"
                        >
                          <ExternalLink size={12} />
                        </button>
                      )}
                    </div>
                </div>
              </div>

              {/* Per-File Diff Section */}
              {isFileOpen && (
                <div 
                  style={{
                    borderTop: "1px solid rgba(255, 255, 255, 0.06)",
                    background: "var(--color-canvas-soft, #08080d)",
                    padding: "8px 12px",
                    maxHeight: "380px",
                    overflowY: "auto"
                  }}
                >
                  {file.changeKind === "content_preview" && (
                    <div style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "6px",
                      padding: "3px 8px",
                      marginBottom: "6px",
                      borderRadius: "4px",
                      background: "rgba(148, 163, 184, 0.12)",
                      border: "1px solid rgba(148, 163, 184, 0.2)",
                      color: "var(--color-mute, #94a3b8)",
                      fontSize: "11px",
                      fontWeight: 500
                    }}>
                      Full content preview (patch diff unavailable)
                    </div>
                  )}
                  {file.changeKind === "unavailable" ? (
                    <div style={{
                      padding: "16px 12px",
                      textAlign: "center",
                      color: "var(--color-mute, #94a3b8)",
                      fontSize: "12px"
                    }}>
                      Diff preview not available for this operation.
                    </div>
                  ) : (
                    <DiffViewer diff={file.displayDiff} path={file.path} maxLinesVisible={40} />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
