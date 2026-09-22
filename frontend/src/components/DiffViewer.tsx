"use client";

import React, { useState, useMemo } from "react";
import { Copy, Check, FileCode, ChevronDown, ChevronRight } from "lucide-react";

interface DiffViewerProps {
  diff: string;
  path?: string;
  maxLinesVisible?: number;
}

interface ParsedDiffLine {
  type: "header" | "hunk" | "add" | "delete" | "context";
  oldLineNumber?: number;
  newLineNumber?: number;
  content: string;
}

export function DiffViewer({ diff, path, maxLinesVisible = 40 }: DiffViewerProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);

  const parsedLines = useMemo(() => {
    if (!diff) return [];
    const lines = diff.split("\n");
    const result: ParsedDiffLine[] = [];

    let currentOld = 0;
    let currentNew = 0;

    const hunkRegex = /^@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@(.*)$/;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      if (line.startsWith("--- ") || line.startsWith("+++ ") || line.startsWith("diff --git") || line.startsWith("index ") || line.startsWith("\\ No newline")) {
        result.push({
          type: "header",
          content: line
        });
        continue;
      }

      const hunkMatch = line.match(hunkRegex);
      if (hunkMatch) {
        currentOld = parseInt(hunkMatch[1], 10);
        currentNew = parseInt(hunkMatch[2], 10);
        result.push({
          type: "hunk",
          content: line
        });
        continue;
      }

      if (line.startsWith("+")) {
        result.push({
          type: "add",
          newLineNumber: currentNew,
          content: line.slice(1)
        });
        currentNew++;
      } else if (line.startsWith("-")) {
        result.push({
          type: "delete",
          oldLineNumber: currentOld,
          content: line.slice(1)
        });
        currentOld++;
      } else {
        // Context line
        const content = line.startsWith(" ") ? line.slice(1) : line;
        result.push({
          type: "context",
          oldLineNumber: currentOld > 0 ? currentOld : undefined,
          newLineNumber: currentNew > 0 ? currentNew : undefined,
          content
        });
        if (currentOld > 0) currentOld++;
        if (currentNew > 0) currentNew++;
      }
    }

    return result;
  }, [diff]);

  if (!diff || parsedLines.length === 0) {
    return null;
  }

  const isLargeDiff = parsedLines.length > maxLinesVisible;
  const visibleLines = isExpanded ? parsedLines : parsedLines.slice(0, maxLinesVisible);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try { await navigator.clipboard.writeText(diff); setCopied(true); setCopyError(false); }
    catch { setCopied(false); setCopyError(true); }
  };

  return (
    <div
      style={{
        margin: "8px 0",
        borderRadius: "8px",
        border: "1px solid var(--color-hairline, rgba(255, 255, 255, 0.12))",
        background: "var(--color-canvas-soft, #0d0d18)",
        overflow: "hidden",
        fontSize: "12px",
        fontFamily: "'JetBrains Mono', 'Fira Code', var(--font-mono, monospace)",
        boxShadow: "0 2px 10px rgba(0, 0, 0, 0.2)"
      }}
    >
      {/* Path / Header Toolbar */}
      {path && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "6px 12px",
            background: "var(--color-canvas-raised, #131322)",
            borderBottom: "1px solid var(--color-hairline, rgba(255, 255, 255, 0.08))",
            fontSize: "12px",
            color: "var(--color-fg-strong, #e2e8f0)"
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px", fontWeight: 600 }}>
            <FileCode size={14} color="#38bdf8" />
            <span style={{ overflowWrap: "anywhere", minWidth: 0 }}>{path}</span>
          </div>

          <button
            onClick={handleCopy}
            style={{
              background: "none",
              border: "none",
              color: copied ? "#34d399" : "var(--color-mute, #94a3b8)",
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
              fontSize: "11px",
              padding: "2px 6px",
              borderRadius: "4px"
            }}
            title="Copy diff patch"
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? "Copied" : "Copy Diff"}
          </button>
        </div>
      )}

      {copyError && <p role="status" style={{ padding: "8px 12px", color: "var(--color-danger)" }}>Could not copy. Select the patch text to copy it manually.</p>}
      {/* Code Diff Body */}
      <div
        style={{
          overflowX: "auto",
          padding: "2px 0",
          lineHeight: 1.5,
          background: "var(--color-canvas, #08080f)"
        }}
      >
        {visibleLines.map((line, index) => {
          let bgColor = "transparent";
          let textColor = "var(--color-fg, #e2e8f0)";
          let marker = " ";
          let markerColor = "transparent";

          if (line.type === "add") {
            bgColor = "rgba(34, 197, 94, 0.12)";
            textColor = "var(--color-diff-add-text)";
            marker = "+";
            markerColor = "#22c55e";
          } else if (line.type === "delete") {
            bgColor = "rgba(239, 68, 68, 0.12)";
            textColor = "var(--color-diff-del-text)";
            marker = "-";
            markerColor = "#ef4444";
          } else if (line.type === "hunk") {
            bgColor = "rgba(59, 130, 246, 0.10)";
            textColor = "#93c5fd";
            marker = "@@";
            markerColor = "#3b82f6";
          } else if (line.type === "header") {
            bgColor = "rgba(255, 255, 255, 0.03)";
            textColor = "var(--color-mute, #94a3b8)";
          }

          return (
            <div
              key={index}
              style={{
                display: "flex",
                alignItems: "stretch",
                background: bgColor,
                minWidth: "100%",
                userSelect: line.type === "hunk" || line.type === "header" ? "none" : "text"
              }}
            >
              {/* Old Line Number */}
              <div
                style={{
                  width: "36px",
                  textAlign: "right",
                  paddingRight: "8px",
                  color: "var(--color-mute, #64748b)",
                  userSelect: "none",
                  fontSize: "11px",
                  opacity: 0.7,
                  flexShrink: 0
                }}
              >
                {line.oldLineNumber ?? ""}
              </div>

              {/* New Line Number */}
              <div
                style={{
                  width: "36px",
                  textAlign: "right",
                  paddingRight: "8px",
                  color: "var(--color-mute, #64748b)",
                  userSelect: "none",
                  fontSize: "11px",
                  opacity: 0.7,
                  flexShrink: 0
                }}
              >
                {line.newLineNumber ?? ""}
              </div>

              {/* Marker (+ / -) */}
              <div
                style={{
                  width: "20px",
                  textAlign: "center",
                  color: markerColor,
                  userSelect: "none",
                  fontWeight: 700,
                  fontSize: "12px",
                  flexShrink: 0
                }}
              >
                {marker}
              </div>

              {/* Content */}
              <div
                style={{
                  color: textColor,
                  whiteSpace: "pre",
                  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                  fontSize: "11.5px",
                  flex: 1,
                  paddingRight: "16px"
                }}
              >
                {line.content}
              </div>
            </div>
          );
        })}
      </div>

      {/* Show More / Show Less Toggle */}
      {isLargeDiff && (
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          style={{
            width: "100%",
            textAlign: "center",
            padding: "6px 0",
            background: "var(--color-canvas-raised, #131322)",
            border: "none",
            borderTop: "1px solid var(--color-hairline, rgba(255, 255, 255, 0.08))",
            color: "var(--color-primary-soft, #818cf8)",
            fontSize: "11.5px",
            fontWeight: 600,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "4px"
          }}
        >
          {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          {isExpanded ? "Show Less" : `Show Full Diff (${parsedLines.length - maxLinesVisible} more lines)`}
        </button>
      )}
    </div>
  );
}
