"use client";

import React, { useState } from "react";
import { Copy, Check, FileCode, ChevronDown, ChevronRight, Eye } from "lucide-react";

interface DiffViewerProps {
  diff: string;
  path?: string;
  maxLinesVisible?: number;
}

export function DiffViewer({ diff, path, maxLinesVisible = 30 }: DiffViewerProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!diff) {
    return null;
  }

  const rawLines = diff.split("\n");
  const isLargeDiff = rawLines.length > maxLinesVisible;
  const visibleLines = isExpanded ? rawLines : rawLines.slice(0, maxLinesVisible);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(diff);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  let oldLineNum = 0;
  let newLineNum = 0;

  return (
    <div 
      style={{
        margin: "6px 0",
        borderRadius: "8px",
        border: "1px solid rgba(255, 255, 255, 0.12)",
        background: "#0a0a10",
        overflow: "hidden",
        fontFamily: "'JetBrains Mono', 'Fira Code', var(--font-mono, monospace)",
        fontSize: "12px",
        boxShadow: "0 4px 20px rgba(0, 0, 0, 0.4)"
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
            background: "#12121c",
            borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
            fontSize: "11.5px",
            color: "#e2e8f0"
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px", fontWeight: 600 }}>
            <FileCode size={13} color="#38bdf8" />
            <span>{path}</span>
          </div>

          <button
            onClick={handleCopy}
            style={{
              background: "none",
              border: "none",
              color: copied ? "#34d399" : "#94a3b8",
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
              fontSize: "10.5px",
              padding: "2px 6px",
              borderRadius: "4px"
            }}
            title="Copy diff"
          >
            {copied ? <Check size={11} /> : <Copy size={11} />}
            {copied ? "Copied" : "Copy Diff"}
          </button>
        </div>
      )}

      {/* Code Diff Body */}
      <div 
        style={{
          overflowX: "auto",
          padding: "4px 0",
          background: "#08080d",
          lineHeight: 1.6
        }}
      >
        {visibleLines.map((line, index) => {
          const isAdded = line.startsWith("+") && !line.startsWith("+++");
          const isDeleted = line.startsWith("-") && !line.startsWith("---");
          const isHunk = line.startsWith("@@");
          const isHeader = line.startsWith("---") || line.startsWith("+++");

          if (isAdded) newLineNum++;
          else if (isDeleted) oldLineNum++;
          else if (!isHunk && !isHeader) {
            oldLineNum++;
            newLineNum++;
          }

          let textColor = "#e2e8f0"; // Bright readable text
          let bgColor = "transparent";
          let gutterColor = "rgba(255, 255, 255, 0.2)";

          if (isAdded) {
            textColor = "#4ade80"; // Bright crisp green
            bgColor = "rgba(34, 197, 94, 0.14)"; // Vibrant soft green tint
            gutterColor = "#22c55e";
          } else if (isDeleted) {
            textColor = "#f87171"; // Bright crisp coral red
            bgColor = "rgba(239, 68, 68, 0.14)"; // Vibrant soft red tint
            gutterColor = "#ef4444";
          } else if (isHunk) {
            textColor = "#93c5fd"; // Soft ice blue
            bgColor = "rgba(59, 130, 246, 0.12)";
            gutterColor = "#3b82f6";
          } else if (isHeader) {
            textColor = "#94a3b8";
            bgColor = "rgba(255, 255, 255, 0.03)";
          }

          return (
            <div
              key={index}
              style={{
                display: "flex",
                alignItems: "stretch",
                background: bgColor,
                minWidth: "100%",
                paddingRight: "16px"
              }}
            >
              {/* Line indicator (+ / - / ' ') */}
              <div
                style={{
                  width: "28px",
                  textAlign: "center",
                  color: gutterColor,
                  userSelect: "none",
                  fontWeight: 700,
                  fontSize: "12px",
                  flexShrink: 0
                }}
              >
                {isAdded ? "+" : isDeleted ? "-" : isHunk ? "@@" : " "}
              </div>

              {/* Line Code Content */}
              <div
                style={{
                  color: textColor,
                  whiteSpace: "pre",
                  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                  fontSize: "11.5px",
                  fontWeight: isAdded || isDeleted ? 500 : 400,
                  flex: 1
                }}
              >
                {isAdded || isDeleted ? line.slice(1) : line}
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
            background: "#12121c",
            border: "none",
            borderTop: "1px solid rgba(255, 255, 255, 0.08)",
            color: "#38bdf8",
            fontSize: "11px",
            fontWeight: 600,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "4px"
          }}
          className="hover:bg-[#1a1a28]"
        >
          {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          {isExpanded ? "Show Less" : `Show Full Diff (${rawLines.length - maxLinesVisible} more lines)`}
        </button>
      )}
    </div>
  );
}
