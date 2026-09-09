"use client";

import React, { useState } from "react";
import { X, FileCode, ChevronRight, ChevronDown, Check, Eye } from "lucide-react";
import { DiffViewer } from "@/components/DiffViewer";

export interface ReviewFile {
  path: string;
  action?: string;
  diff?: string;
  content?: string;
  additions?: number;
  deletions?: number;
}

interface ReviewPaneProps {
  files: ReviewFile[];
  onClose: () => void;
  onOpenFile?: (path: string) => void;
  title?: string;
}

export function ReviewPane({ files, onClose, onOpenFile, title = "Changes to Review" }: ReviewPaneProps) {
  const [selectedPath, setSelectedPath] = useState<string>(files[0]?.path || "");

  const activeFile = files.find(f => f.path === selectedPath) || files[0];

  const totalAdditions = files.reduce((acc, f) => acc + (f.additions ?? 0), 0);
  const totalDeletions = files.reduce((acc, f) => acc + (f.deletions ?? 0), 0);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        width: "100%",
        background: "var(--color-canvas, #0a0a14)",
        borderLeft: "1px solid var(--color-hairline, rgba(255, 255, 255, 0.1))",
        overflow: "hidden"
      }}
    >
      {/* Pane Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 16px",
          borderBottom: "1px solid var(--color-hairline, rgba(255, 255, 255, 0.08))",
          background: "var(--color-canvas-raised, #121222)",
          flexShrink: 0
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <h3 style={{ margin: 0, fontSize: "14px", fontWeight: 600, color: "var(--color-fg-strong, #fff)" }}>
            {title}
          </h3>
          <span style={{ fontSize: "12px", color: "var(--color-mute, #94a3b8)", fontFamily: "var(--font-mono, monospace)" }}>
            ({files.length} {files.length === 1 ? "file" : "files"} ·{" "}
            <span style={{ color: "#4ade80" }}>+{totalAdditions}</span>{" "}
            <span style={{ color: "#f87171" }}>-{totalDeletions}</span>)
          </span>
        </div>

        <button
          onClick={onClose}
          className="btn btn-icon-sm btn-ghost"
          style={{ color: "var(--color-mute, #94a3b8)", cursor: "pointer", background: "none", border: "none" }}
          aria-label="Close review pane"
        >
          <X size={16} />
        </button>
      </div>

      {/* Main Split Layout: File List Sidebar + Active Diff View */}
      <div style={{ display: "flex", flex: 1, minHeight: 0, overflow: "hidden" }}>
        {/* File List */}
        <div
          style={{
            width: "220px",
            minWidth: "180px",
            borderRight: "1px solid var(--color-hairline, rgba(255, 255, 255, 0.08))",
            background: "var(--color-canvas-soft, #0d0d1a)",
            overflowY: "auto",
            flexShrink: 0
          }}
        >
          <div style={{ padding: "8px" }}>
            <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--color-mute, #64748b)", textTransform: "uppercase", padding: "4px 8px" }}>
              Changed Files
            </div>
            {files.map(file => {
              const fileName = file.path.split(/[/\\]/).pop() || file.path;
              const isSelected = file.path === activeFile?.path;

              return (
                <button
                  key={file.path}
                  onClick={() => setSelectedPath(file.path)}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    padding: "6px 8px",
                    borderRadius: "6px",
                    border: "none",
                    background: isSelected ? "rgba(99, 102, 241, 0.15)" : "transparent",
                    color: isSelected ? "var(--color-fg-strong, #fff)" : "var(--color-fg, #cbd5e1)",
                    cursor: "pointer",
                    textAlign: "left",
                    fontSize: "12px"
                  }}
                >
                  <FileCode size={13} color={isSelected ? "#818cf8" : "#94a3b8"} />
                  <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={file.path}>
                    {fileName}
                  </span>
                  {(file.additions !== undefined || file.deletions !== undefined) && (
                    <span style={{ fontSize: "10px", fontFamily: "var(--font-mono, monospace)", color: "var(--color-mute, #94a3b8)" }}>
                      <span style={{ color: "#4ade80" }}>+{file.additions ?? 0}</span>
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Diff View Area */}
        <div style={{ flex: 1, overflowY: "auto", padding: "16px", minWidth: 0 }}>
          {activeFile ? (
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
                <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--color-fg-strong, #fff)" }}>
                  {activeFile.path}
                </div>
                {onOpenFile && (
                  <button
                    onClick={() => onOpenFile(activeFile.path)}
                    style={{
                      fontSize: "11px",
                      color: "var(--color-primary-soft, #818cf8)",
                      background: "none",
                      border: "none",
                      cursor: "pointer"
                    }}
                  >
                    Open in Editor
                  </button>
                )}
              </div>

              {activeFile.diff ? (
                <DiffViewer diff={activeFile.diff} path={activeFile.path} maxLinesVisible={100} />
              ) : activeFile.content ? (
                <div>
                  <div style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "3px 8px",
                    marginBottom: "8px",
                    borderRadius: "4px",
                    background: "rgba(148, 163, 184, 0.12)",
                    color: "var(--color-mute, #94a3b8)",
                    fontSize: "11px"
                  }}>
                    Full file content preview
                  </div>
                  <pre style={{
                    padding: "12px",
                    borderRadius: "8px",
                    background: "var(--color-canvas-soft, #0a0a14)",
                    border: "1px solid var(--color-hairline, rgba(255, 255, 255, 0.08))",
                    color: "var(--color-fg, #cbd5e1)",
                    fontSize: "12px",
                    overflowX: "auto"
                  }}>
                    <code>{activeFile.content}</code>
                  </pre>
                </div>
              ) : (
                <div style={{ padding: "32px", textAlign: "center", color: "var(--color-mute, #94a3b8)" }}>
                  No diff content available for this file.
                </div>
              )}
            </div>
          ) : (
            <div style={{ padding: "32px", textAlign: "center", color: "var(--color-mute, #94a3b8)" }}>
              Select a file from the list to review its diff.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
