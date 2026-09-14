"use client";
import React, { useState } from "react";
import { ChevronRight, Loader2, AlertCircle, Terminal, FileCode2, Globe, Brain, Wrench, Copy } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./chat-workspace.css";

export interface ActivityStep {
  id?: string; type: "tool" | "thought"; toolName?: string; argsJson?: string;
  argsObj?: Record<string, unknown>; result?: string; isError?: boolean;
  text?: string; duration?: string; pid?: number | null;
}
function describe(step: ActivityStep) {
  const name = step.toolName || "Tool";
  const args = step.argsObj || {};
  const target = args.relative_path || args.path || args.file_path || args.command || args.CommandLine || args.query || args.url;
  const Icon = /command|bash|shell|exec/.test(name) ? Terminal : /file|dir/.test(name) ? FileCode2 : /web|browser|search/.test(name) ? Globe : Wrench;
  return { name: name.replace(/_/g, " "), target: target ? String(target) : "", Icon };
}
export default function AgentActivityStream({ steps, isStreaming = false, elapsedSecs = 0 }: {
  steps: ActivityStep[]; isStreaming?: boolean; elapsedSecs?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const [copyStatus, setCopyStatus] = useState("");
  const visible = steps.filter(s => s.type === "tool" ? s.toolName : s.text?.trim());
  const tools = visible.filter(s => s.type === "tool");
  const failed = tools.filter(s => s.isError).length;
  if (!visible.length) return null;
  return (
    <section className={`cw-activity ${expanded ? "cw-activity-expanded" : ""}`} aria-label="Agent activity">
      <button className="cw-activity-toggle" onClick={() => setExpanded(v => !v)} aria-expanded={expanded}>
        {isStreaming ? <Loader2 size={15} className="cw-spin" /> : failed ? <AlertCircle size={15} /> : <Wrench size={15} />}
        <strong>{isStreaming ? "Working" : "Activity"}</strong>
        <span>{tools.length ? tools.length + " tool " + (tools.length === 1 ? "call" : "calls") : "Reasoning"}{failed ? " · " + failed + " failed" : ""}</span>
        {isStreaming && elapsedSecs > 0 && <span className="cw-duration">{elapsedSecs}s</span>}
        <ChevronRight size={14} className={expanded ? "cw-chevron-open" : ""} />
      </button>
      {expanded && <div className="cw-activity-ledger">
        {visible.map((step, index) => {
          const { name, target, Icon } = describe(step);
          const hasResult = step.result !== undefined && step.result !== "";
          const status = step.isError ? "Failed" : step.pid ? "Background process launched" : hasResult ? "Result received" : isStreaming ? "In progress" : "No result recorded";
          return <details className="cw-tool" key={step.id || step.toolName + "-" + index}>
            <summary>
              {step.type === "thought" ? <Brain size={14} /> : <Icon size={14} />}
              <span className="cw-tool-title">{step.type === "thought" ? "Reasoning" : name}{target && step.type === "tool" && <code>{target}</code>}</span>
              {step.type === "tool" && <span className={"cw-tool-status " + (step.isError ? "cw-danger" : "")}>{status}</span>}
              <ChevronRight size={13} className="cw-detail-chevron" />
            </summary>
            <div className="cw-tool-content">
              {step.type === "thought" ? <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{step.text || ""}</ReactMarkdown></div> : <>
                {(step.argsJson || step.argsObj) && <><span className="cw-detail-label">Input</span><pre>{step.argsJson || JSON.stringify(step.argsObj, null, 2)}</pre></>}
                {hasResult && <><div className="cw-output-heading"><span className="cw-detail-label">Output</span><button className="cw-text-button" onClick={async () => { try { await navigator.clipboard.writeText(step.result!); setCopyStatus(index + ":copied"); } catch { setCopyStatus(index + ":failed"); } }}><Copy size={12} />{copyStatus === index + ":copied" ? "Copied" : copyStatus === index + ":failed" ? "Copy failed" : "Copy"}</button></div><pre>{step.result}</pre></>}
                {!hasResult && <p className="cw-muted">{isStreaming ? "Waiting for the tool to return a result." : "No output was recorded for this call."}</p>}
                {step.pid && <p className="cw-muted">Process {step.pid} was launched. Check Background work for its current state.</p>}
              </>}
            </div>
          </details>;
        })}
      </div>}
    </section>
  );
}
