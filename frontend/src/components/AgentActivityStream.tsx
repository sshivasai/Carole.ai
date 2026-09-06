"use client";

import React, { useState } from "react";
import { 
  FileCode, Terminal, Globe, ChevronDown, ChevronRight, 
  Sparkles, Check, AlertTriangle, Copy, Search, Eye, 
  Bot, Layers, BrainCircuit
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export interface ActivityStep {
  id?: string;
  type: "tool" | "thought";
  toolName?: string;
  argsJson?: string;
  argsObj?: any;
  result?: string;
  isError?: boolean;
  text?: string;
  duration?: string;
  pid?: number | null;
}

interface AgentActivityStreamProps {
  steps: ActivityStep[];
  isStreaming?: boolean;
  elapsedSecs?: number;
}

function isObservationStep(text?: string): boolean {
  if (!text) return false;
  return (
    text.includes("[OBSERVATION]") ||
    text.includes("💭 **Observation:**") ||
    text.includes("💭 **System Note:**") ||
    text.includes("Plan Without Execution") ||
    text.includes("Unexecuted Promise") ||
    text.includes("Incomplete Response")
  );
}

function getStepIcon(step: ActivityStep) {
  if (step.type === "thought" && isObservationStep(step.text)) {
    return { icon: AlertTriangle, color: "#f59e0b" };
  }
  if (!step.toolName) return { icon: BrainCircuit, color: "#a78bfa" };
  const name = step.toolName.toLowerCase();
  if (name.includes("write") || name.includes("edit")) return { icon: FileCode, color: "#38bdf8" };
  if (name.includes("read") || name.includes("list") || name.includes("view")) return { icon: Eye, color: "#94a3b8" };
  if (name.includes("command") || name.includes("bash") || name.includes("exec") || name.includes("terminal")) return { icon: Terminal, color: "#34d399" };
  if (name.includes("search") || name.includes("fetch") || name.includes("browse")) return { icon: Search, color: "#f59e0b" };
  if (name.includes("subagent") || name.includes("spawn") || name.includes("hire")) return { icon: Bot, color: "#c084fc" };
  return { icon: Layers, color: "#818cf8" };
}

function cleanThoughtText(raw?: string): string {
  if (!raw) return "";
  let text = raw;
  // Clean observation and system note wrappers without destroying content
  text = text.replace(/\[OBSERVATION\]/g, "");
  text = text.replace(/\[\/OBSERVATION\]/g, "");
  text = text.replace(/💭\s*\*\*(?:Observation|System Note):\*\*/g, "");
  // Clean raw trace markers and tool artifacts if present in text
  text = text.replace(/🛠️\s*\*\*[^\*]+\*\*[\s\S]*?(?=📄|🛠️|$)/g, "");
  text = text.replace(/📄\s*(?:\*\*)?Result:(?:\*\*)?[\s\S]*?(?=🛠️|$)/g, "");
  text = text.replace(/\[ACTION\]([\s\S]*?)\[\/ACTION\]/g, "\n```json\n$1\n```\n");
  text = text.replace(/<tool_call>[\s\S]*?<\/tool_call>/g, "");
  text = text.replace(/```(?:json)?\s*\{[\s\S]*?\}\s*```/g, "");
  return text.trim();
}

function getStepTitle(step: ActivityStep) {
  if (step.type === "thought") {
    const raw = step.text || "";
    if (raw.includes("Plan Without Execution")) {
      return "Self-Correction: Plan Execution Protocol";
    }
    if (raw.includes("Incomplete Response") || raw.includes("Unexecuted Promise")) {
      return "Self-Correction: Action Execution Check";
    }
    if (isObservationStep(raw)) {
      return "System Guidance: Execution Check";
    }
    const cleaned = cleanThoughtText(step.text);
    const firstLine = (cleaned || step.text || "")
      .split("\n")
      .map(l => l.trim())
      .filter(Boolean)[0]
      ?.replace(/[`*#_]/g, "")
      .trim();
    if (!firstLine) return "Reasoning & Planning";
    return firstLine.length > 55 ? `${firstLine.slice(0, 52)}...` : firstLine;
  }

  const name = (step.toolName || "").toLowerCase();
  const args = step.argsObj || {};

  if (name === "write_file" || name === "edit_file") {
    const p = args.relative_path || args.path || args.TargetFile || "file";
    const base = p.split(/[/\\]/).pop() || p;
    const lines = (args.content || "").split("\n").length || 1;
    return `Edited ${base} +${lines} -0`;
  }
  if (name === "read_file" || name === "view_file") {
    const p = args.relative_path || args.path || args.AbsolutePath || "file";
    const base = p.split(/[/\\]/).pop() || p;
    return `Read ${base}`;
  }
  if (name === "list_dir") {
    const p = args.path || args.DirectoryPath || ".";
    return `Explored directory ${p}`;
  }
  if (name === "execute_command" || name === "run_command") {
    const cmd = args.command || args.CommandLine || "command";
    const shortCmd = cmd.length > 40 ? `${cmd.slice(0, 37)}...` : cmd;
    return `Ran ${shortCmd}`;
  }
  if (name === "web_search" || name === "search_web") {
    const q = args.query || "query";
    return `Searched web for "${q}"`;
  }
  if (name === "hire_subagent" || name === "spawn_agent") {
    const target = args.target || args.role || "subagent";
    return `Spawned worker ${target}`;
  }
  return `Executed ${step.toolName || "action"}`;
}

export default function AgentActivityStream({ steps, isStreaming = false, elapsedSecs = 0 }: AgentActivityStreamProps) {
  const [isTimelineOpen, setIsTimelineOpen] = useState(false);
  const [openStepIdx, setOpenStepIdx] = useState<number | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  if (!steps || steps.length === 0) return null;

  // Filter out redundant empty steps
  const validSteps = steps.filter(s => {
    if (s.type === "tool") return Boolean(s.toolName);
    const cleaned = cleanThoughtText(s.text);
    return Boolean(cleaned || s.text?.trim());
  });

  if (validSteps.length === 0) return null;

  const handleCopy = (key: string, text: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 1500);
  };

  const killTask = async (pid: number, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const token = localStorage.getItem("carole_token");
      const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
      await fetch(`${base}/api/tasks/${pid}/kill`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      alert(`Sent kill signal for PID ${pid}`);
    } catch (err) {
      console.error(err);
    }
  };

  const totalActions = validSteps.filter(s => s.type === "tool").length;

  return (
    <div
      style={{
        margin: "6px 0",
        fontFamily: "var(--font-sans, system-ui, -apple-system, sans-serif)",
        userSelect: "none",
        position: "relative",
        width: "100%"
      }}
    >
      {/* Antigravity Pill Header: "Worked for 24s ⌄" */}
      <button
        onClick={() => setIsTimelineOpen(o => !o)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "8px",
          padding: "4px 10px",
          borderRadius: "20px",
          background: isTimelineOpen ? "rgba(255, 255, 255, 0.08)" : "rgba(255, 255, 255, 0.04)",
          border: "1px solid rgba(255, 255, 255, 0.1)",
          color: "var(--color-ink, #e2e8f0)",
          fontSize: "11px",
          fontWeight: 600,
          cursor: "pointer",
          transition: "all 0.15s ease"
        }}
        className="hover:bg-[rgba(255,255,255,0.08)]"
      >
        <span style={{ color: "var(--color-primary-soft, #a78bfa)" }}>
          Worked for {elapsedSecs > 0 ? `${elapsedSecs}s` : `${Math.max(1, validSteps.length * 4)}s`}
        </span>
        {validSteps.length > 0 && (
          <span style={{ fontSize: "10px", color: "var(--color-mute, #64748b)", fontWeight: 500 }}>
            • {validSteps.length} {validSteps.length === 1 ? "step" : "steps"}
          </span>
        )}
        <span style={{ color: "var(--color-mute, #64748b)", display: "flex", alignItems: "center" }}>
          {isTimelineOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>
      </button>

      {/* Expanded Antigravity Activity Timeline */}
      {isTimelineOpen && (
        <div
          style={{
            marginTop: "8px",
            background: "#111116",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "10px",
            padding: "6px 8px",
            maxHeight: "360px",
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            gap: "4px",
            position: "relative",
            width: "100%",
            boxSizing: "border-box"
          }}
        >
          {validSteps.map((step, idx) => {
            const isObs = step.type === "thought" && isObservationStep(step.text);
            const { icon: StepIcon, color: iconColor } = getStepIcon(step);
            const title = getStepTitle(step);
            const isOpen = openStepIdx === idx;
            const cleanedText = cleanThoughtText(step.text);

            return (
              <div 
                key={idx}
                style={{
                  position: "relative",
                  width: "100%",
                  borderRadius: "6px",
                  background: isOpen ? "rgba(255, 255, 255, 0.04)" : "transparent",
                  border: isOpen ? "1px solid rgba(255, 255, 255, 0.08)" : "1px solid transparent",
                  boxSizing: "border-box",
                  transition: "background 0.12s",
                  display: "block"
                }}
              >
                {/* Step Header Button */}
                <div
                  onClick={() => setOpenStepIdx(isOpen ? null : idx)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "7px 10px",
                    cursor: "pointer",
                    gap: "8px",
                    width: "100%",
                    boxSizing: "border-box"
                  }}
                  className="hover:bg-[rgba(255,255,255,0.03)]"
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0, flex: 1 }}>
                    <StepIcon size={13} color={iconColor} />
                    <span 
                      style={{ 
                        fontSize: "11.5px", 
                        color: isObs ? "#fbbf24" : step.isError ? "#f87171" : "#cbd5e1", 
                        overflow: "hidden", 
                        textOverflow: "ellipsis", 
                        whiteSpace: "nowrap",
                        fontFamily: step.type === "tool" ? "var(--font-mono, monospace)" : "inherit"
                      }}
                    >
                      {title}
                    </span>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: "6px", flexShrink: 0 }}>
                    {step.pid && (
                      <span style={{ fontSize: "9px", color: "#38bdf8", background: "rgba(56, 189, 248, 0.12)", border: "1px solid rgba(56, 189, 248, 0.25)", padding: "1px 5px", borderRadius: "3px", fontWeight: 500 }}>
                        PID: {step.pid}
                      </span>
                    )}
                    {isObs && (
                      <span style={{ fontSize: "9px", color: "#f59e0b", background: "rgba(245, 158, 11, 0.12)", border: "1px solid rgba(245, 158, 11, 0.25)", padding: "1px 5px", borderRadius: "3px", fontWeight: 500 }}>
                        Guidance
                      </span>
                    )}
                    {step.isError && (
                      <span style={{ fontSize: "9px", color: "#f87171", background: "rgba(239, 68, 68, 0.1)", padding: "1px 5px", borderRadius: "3px" }}>
                        Error
                      </span>
                    )}
                    <span style={{ color: "var(--color-mute, #64748b)", display: "flex", alignItems: "center" }}>
                      {isOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                    </span>
                  </div>
                </div>

                {/* Step Details Drawer */}
                {isOpen && (
                  <div 
                    style={{ 
                      padding: "8px 12px 12px 12px", 
                      borderTop: "1px solid rgba(255, 255, 255, 0.05)", 
                      fontSize: "11px", 
                      display: "flex", 
                      flexDirection: "column", 
                      gap: "8px",
                      position: "relative",
                      width: "100%",
                      boxSizing: "border-box"
                    }}
                  >
                    {step.argsJson && (
                      <div>
                        <div style={{ display: "flex", justifyContent: "space-between", color: "#64748b", fontSize: "9.5px", textTransform: "uppercase", marginBottom: "3px" }}>
                          <span>Parameters</span>
                          <button
                            onClick={(e) => handleCopy(`args-${idx}`, step.argsJson!, e)}
                            style={{ background: "none", border: "none", color: copied === `args-${idx}` ? "#34d399" : "#64748b", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "2px", fontSize: "10px" }}
                          >
                            {copied === `args-${idx}` ? <Check size={10} /> : <Copy size={10} />}
                            {copied === `args-${idx}` ? "Copied" : "Copy"}
                          </button>
                        </div>
                        <pre style={{ margin: 0, padding: "6px 8px", background: "#0c0c10", borderRadius: "4px", color: "#e2e8f0", fontSize: "10.5px", maxHeight: "120px", overflowX: "auto" }}>
                          {step.argsJson}
                        </pre>
                      </div>
                    )}

                    {step.result && (
                      <div>
                        <div style={{ display: "flex", justifyContent: "space-between", color: step.isError ? "#f87171" : "#64748b", fontSize: "9.5px", textTransform: "uppercase", marginBottom: "3px" }}>
                          <span>{step.isError ? "Error Output" : "Observation"}</span>
                          <button
                            onClick={(e) => handleCopy(`res-${idx}`, step.result!, e)}
                            style={{ background: "none", border: "none", color: copied === `res-${idx}` ? "#34d399" : "#64748b", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "2px", fontSize: "10px" }}
                          >
                            {copied === `res-${idx}` ? <Check size={10} /> : <Copy size={10} />}
                            {copied === `res-${idx}` ? "Copied" : "Copy"}
                          </button>
                        </div>
                        <pre style={{ margin: 0, padding: "6px 8px", background: step.isError ? "rgba(239,68,68,0.06)" : "#0c0c10", borderRadius: "4px", color: step.isError ? "#fca5a5" : "#cbd5e1", fontSize: "10.5px", maxHeight: "140px", overflowX: "auto" }}>
                          {step.result}
                        </pre>
                      </div>
                    )}

                    {isObs ? (
                      <div 
                        style={{ 
                          background: "rgba(245, 158, 11, 0.04)", 
                          border: "1px solid rgba(245, 158, 11, 0.2)", 
                          borderRadius: "6px", 
                          padding: "10px 12px",
                          display: "flex",
                          flexDirection: "column",
                          gap: "6px"
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#fbbf24", fontSize: "11px", fontWeight: 600 }}>
                            <AlertTriangle size={13} />
                            <span>System Guidance & Correction</span>
                          </div>
                          <span style={{ fontSize: "9px", color: "#f59e0b", background: "rgba(245, 158, 11, 0.1)", padding: "1px 5px", borderRadius: "3px" }}>
                            Protocol Check
                          </span>
                        </div>
                        <div style={{ color: "#cbd5e1", fontSize: "11px", lineHeight: 1.55 }}>
                          <ReactMarkdown 
                            skipHtml={true} 
                            remarkPlugins={[remarkGfm]}
                            components={{
                              p: ({ children }) => <p style={{ margin: "2px 0 6px 0", lineHeight: 1.55 }}>{children}</p>,
                              pre: ({ children }) => <pre style={{ margin: "4px 0", padding: "6px 8px", background: "#0c0c10", borderRadius: 4, overflowX: "auto", border: "1px solid rgba(255,255,255,0.06)" }}>{children}</pre>,
                              code: ({ children, className }) => className ? <code>{children}</code> : <code style={{ padding: "1px 4px", background: "rgba(255,255,255,0.08)", borderRadius: 3, color: "#38bdf8" }}>{children}</code>
                            }}
                          >
                            {cleanedText}
                          </ReactMarkdown>
                        </div>
                      </div>
                    ) : (cleanedText || (step.text && !step.result)) && (
                      <div 
                        style={{ 
                          color: "#cbd5e1", 
                          lineHeight: 1.5, 
                          fontSize: "11px",
                          overflowWrap: "anywhere",
                          wordBreak: "break-word"
                        }}
                      >
                        <ReactMarkdown 
                          skipHtml={true} 
                          remarkPlugins={[remarkGfm]}
                          components={{
                            p: ({ children }) => <p style={{ margin: "2px 0 6px 0", lineHeight: 1.5 }}>{children}</p>,
                            pre: ({ children }) => <pre style={{ margin: "4px 0", padding: "6px", background: "#0c0c10", borderRadius: 4, overflowX: "auto" }}>{children}</pre>,
                            code: ({ children, className }) => className ? <code>{children}</code> : <code style={{ padding: "1px 4px", background: "rgba(255,255,255,0.08)", borderRadius: 3, color: "#38bdf8" }}>{children}</code>
                          }}
                        >
                          {cleanedText || step.text || ""}
                        </ReactMarkdown>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
