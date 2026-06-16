import React, { useState } from "react";

interface DiffViewerProps {
  diff: string;
  path?: string;
  maxLinesVisible?: number;
}

export function DiffViewer({ diff, path, maxLinesVisible = 20 }: DiffViewerProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!diff) {
    return null;
  }

  const lines = diff.split("\n");
  const isLargeDiff = lines.length > maxLinesVisible;
  const visibleLines = isExpanded ? lines : lines.slice(0, maxLinesVisible);

  return (
    <div className="my-2 rounded border border-gray-700 bg-[#1e1e1e] text-sm overflow-hidden font-mono text-gray-300">
      {path && (
        <div className="bg-gray-800 px-3 py-1.5 border-b border-gray-700 font-semibold text-gray-200">
          {path}
        </div>
      )}
      <div className="overflow-x-auto p-2">
        {visibleLines.map((line, index) => {
          let lineClass = "";
          let bgColor = "transparent";

          if (line.startsWith("+") && !line.startsWith("+++")) {
            lineClass = "text-green-400";
            bgColor = "rgba(34, 197, 94, 0.1)"; // faint green
          } else if (line.startsWith("-") && !line.startsWith("---")) {
            lineClass = "text-red-400";
            bgColor = "rgba(239, 68, 68, 0.1)"; // faint red
          } else if (line.startsWith("@@")) {
            lineClass = "text-blue-400";
            bgColor = "rgba(59, 130, 246, 0.1)"; // faint blue
          }

          return (
            <div
              key={index}
              className={`whitespace-pre px-2 py-0.5 ${lineClass}`}
              style={{ backgroundColor: bgColor }}
            >
              {line || " "}
            </div>
          );
        })}
      </div>
      {isLargeDiff && (
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full text-center py-1.5 bg-gray-800 hover:bg-gray-700 text-xs font-semibold text-gray-400 transition-colors"
        >
          {isExpanded ? "Show Less" : `Show Full Diff (${lines.length - maxLinesVisible} more lines)`}
        </button>
      )}
    </div>
  );
}
