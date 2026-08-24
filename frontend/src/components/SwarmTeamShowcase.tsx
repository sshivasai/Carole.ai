"use client";

import React, { useState, useEffect } from "react";
import PrettyAvatar, { PrettyAvatarPreset } from "./PrettyAvatar";
import MagneticCard from "./MagneticCard";
import {
  Sparkles,
  Bot,
  Code2,
  ShieldCheck,
  Brain,
  CheckCircle2,
  Terminal,
  Activity,
  Zap,
  Play,
  Pause,
  Layers,
  Cpu,
} from "lucide-react";

interface TeamMember {
  id: string;
  name: string;
  role: string;
  preset: PrettyAvatarPreset;
  model: string;
  skills: string[];
  persona: string;
  permissions: string;
  liveAction: string;
  quote: string;
  toolCall: string;
  color: string;
}

const TEAM_MEMBERS: TeamMember[] = [
  {
    id: "archer",
    name: "Archer",
    role: "Team Coordinator & Lead Architect",
    preset: "archer",
    model: "anthropic/claude-3-7-sonnet",
    skills: ["Workflow Planning", "Subagent Delegation", "Git Integration", "Task Breakdown"],
    persona: "You are Archer, the lead coordinator. Decompose large engineering goals into parallelizable subtasks, hire specialist subagents when needed, and maintain clean Kanban status.",
    permissions: "Full Access • Subagent Spawner • Bash Gated",
    liveAction: "Analyzing dependency graph & delegating subtasks",
    quote: "Decomposing task #142 into modular AST patches and assigning to specialists.",
    toolCall: "hire_subagent(target='Sub-PythonDev', task='Refactor AST parser')",
    color: "#a78bfa",
  },
  {
    id: "coder",
    name: "Coder",
    role: "Full-Stack Engineer",
    preset: "coder",
    model: "deepseek/deepseek-r1",
    skills: ["Python", "TypeScript", "FastAPI", "React", "Unit Testing", "AST Refactoring"],
    persona: "You are Coder, a rigorous software engineer. Write atomic patches, verify test suites, create rollback backups before editing, and prune dead-end error loops.",
    permissions: "File Read/Write • Local Terminal • Web Search",
    liveAction: "Writing backend/core/agent/context_ast.py (+38 -6)",
    quote: "Pruned 3 dead-end tool loops from message history. Zero token bloat.",
    toolCall: "edit_file(path='backend/core/agent/context_ast.py')",
    color: "#10b981",
  },
  {
    id: "judge",
    name: "Judge AI",
    role: "Security & Policy Gate",
    preset: "judge",
    model: "openai/o3-mini",
    skills: ["Policy Audit", "Risk Scoring", "Command Firewall", "Access Control"],
    persona: "You are Judge AI. Intercept all shell commands, database queries, and file deletions. Evaluate security risks and require human one-click confirmation for destructive actions.",
    permissions: "Security Interceptor • Policy Enforcement Gate",
    liveAction: "Auditing bash shell execution permissions",
    quote: "Command 'git push origin main' intercepted. Policy requires human confirmation.",
    toolCall: "request_human_approval(action='git_push', tier='human')",
    color: "#fbbf24",
  },
  {
    id: "researcher",
    name: "Researcher",
    role: "GraphRAG & Semantic Intelligence",
    preset: "researcher",
    model: "google/gemini-2.5-pro",
    skills: ["pgvector", "LanceDB HNSW", "Ontology Traversal", "DOM Scraping", "Summarization"],
    persona: "You are Researcher. Traverse multi-hop codebase entities, query dense vector embeddings in LanceDB/pgvector, and synthesize complex technical documentation.",
    permissions: "Vector DB Read • Network Traversal • Web Fetch",
    liveAction: "Querying pgvector + LanceDB HNSW embeddings",
    quote: "Found 4 multi-hop entity relations in ontology graph in 11ms.",
    toolCall: "vector_search(query='atomic redis session lock', top_k=5)",
    color: "#38bdf8",
  },
  {
    id: "qa",
    name: "QA Runner",
    role: "Playwright Automation",
    preset: "qa",
    model: "anthropic/claude-3-7-sonnet",
    skills: ["Playwright", "Headless Browser", "DOM Inspection", "Pytest Suite", "Visual Diff"],
    persona: "You are QA Runner. Drive headless browser sessions, inspect live DOM mutations, capture screenshot artifacts, and verify end-to-end user workflows.",
    permissions: "Browser Automation • DOM Inspection • Artifact Capture",
    liveAction: "Executing headless browser integration suite",
    quote: "Playwright test suite passed: 14 test cases validated in 2.1s.",
    toolCall: "browser_navigate(url='http://localhost:3000/auth')",
    color: "#f43f5e",
  },
  {
    id: "subagent",
    name: "Sub-PythonDev",
    role: "Specialist Subagent (Depth 1)",
    preset: "subagent",
    model: "deepseek/deepseek-r1",
    skills: ["AST Parsing", "Targeted Bugfix", "Regex Validation", "Sandbox Run"],
    persona: "You are a temporary specialist subagent spawned by Archer for a specific subtask. Execute with depth-1 safety guards and report results back to the team coordinator.",
    permissions: "Restricted File I/O • Subagents Blocked (Depth 1 Guard)",
    liveAction: "Parsing abstract syntax tree for regex safety",
    quote: "Specialist task finished with zero recursion. Reporting back to Archer.",
    toolCall: "report_task_complete(metrics={'lines_parsed': 1420})",
    color: "#f59e0b",
  },
];

export default function SwarmTeamShowcase() {
  const [selectedAgent, setSelectedAgent] = useState<TeamMember>(TEAM_MEMBERS[0]);
  const [isSimulating, setIsSimulating] = useState(true);
  const [tickerIndex, setTickerIndex] = useState(0);

  // Rotate highlight every few seconds if not paused
  useEffect(() => {
    if (!isSimulating) return;
    const timer = setInterval(() => {
      setTickerIndex((prev) => (prev + 1) % TEAM_MEMBERS.length);
    }, 4500);
    return () => clearInterval(timer);
  }, [isSimulating]);

  const activeAgent = TEAM_MEMBERS[tickerIndex] || selectedAgent;

  return (
    <div
      style={{
        width: "100%",
        maxWidth: 1200,
        margin: "0 auto 40px",
        padding: "0 16px",
      }}
    >
      {/* Container Card */}
      <div
        style={{
          background: "var(--bg-glass-panel, rgba(13, 13, 30, 0.75))",
          backdropFilter: "blur(24px)",
          WebkitBackdropFilter: "blur(24px)",
          border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.08))",
          borderRadius: 20,
          padding: "20px 24px",
          boxShadow: "0 16px 48px rgba(0, 0, 0, 0.1), 0 0 0 1px rgba(167, 139, 250, 0.08) inset",
          position: "relative",
          overflow: "hidden",
        }}
      >
        {/* Section Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 12,
            marginBottom: 16,
            position: "relative",
            zIndex: 1,
          }}
        >
          <div>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 5,
                fontSize: 10.5,
                fontWeight: 800,
                color: "var(--color-primary, #7c3aed)",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                marginBottom: 3,
              }}
            >
              <Sparkles size={12} />
              <span>Multi-Agent Architecture</span>
            </div>
            <h3
              style={{
                fontSize: "clamp(18px, 2.4vw, 24px)",
                fontWeight: 800,
                color: "var(--color-ink-strong, #0f172a)",
                margin: 0,
                letterSpacing: "-0.02em",
              }}
            >
              Create & Customize Your Autonomous Engineering Team
            </h3>
            <p
              style={{
                fontSize: 12.5,
                color: "var(--color-body, #475569)",
                margin: "3px 0 0",
                maxWidth: 820,
                lineHeight: 1.4,
              }}
            >
              Configure custom personas, system instructions, modular skills, and LLM backends (Claude 3.7, DeepSeek R1, GPT-4o, Gemini 2.5) with granular tool permissions.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 5,
                padding: "4px 11px",
                borderRadius: 9999,
                background: "var(--color-canvas-raised, #f1f5f9)",
                border: "1px solid var(--color-hairline, #e2e8f0)",
                fontSize: 11,
                color: "var(--color-primary, #7c3aed)",
                fontWeight: 700,
              }}
            >
              <Layers size={12} />
              <span>Multi-Agent System</span>
            </div>
          </div>
        </div>

        {/* Team Avatar Grid (Scroll & Hover Interactive) */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
            gap: 10,
            marginBottom: 16,
            position: "relative",
            zIndex: 1,
          }}
        >
          {TEAM_MEMBERS.map((member, index) => {
            const isActive = activeAgent.id === member.id;
            return (
              <div
                key={member.id}
                onClick={() => {
                  setTickerIndex(index);
                  setSelectedAgent(member);
                  setIsSimulating(false);
                }}
                style={{
                  background: isActive
                    ? "var(--bg-glass-card, #ffffff)"
                    : "var(--color-canvas-raised, #f8fafc)",
                  border: isActive
                    ? `2px solid ${member.color}`
                    : "1px solid var(--color-hairline, #e2e8f0)",
                  borderRadius: 14,
                  padding: "10px 8px",
                  cursor: "pointer",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  textAlign: "center",
                  transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
                  transform: isActive ? "translateY(-3px)" : "none",
                  boxShadow: isActive
                    ? `0 8px 20px ${member.color}25`
                    : "0 2px 6px rgba(0, 0, 0, 0.03)",
                }}
              >
                <div style={{ marginBottom: 6, position: "relative" }}>
                  <PrettyAvatar preset={member.preset} name={member.name} size={36} isWorking={isActive} />
                </div>
                <div style={{ fontSize: 12.5, fontWeight: 800, color: "var(--color-ink-strong, #0f172a)", marginBottom: 1 }}>
                  {member.name}
                </div>
                <div style={{ fontSize: 10, color: "var(--color-body, #475569)", fontWeight: 500, lineHeight: 1.2, marginBottom: 5 }}>
                  {member.role}
                </div>
                <div
                  style={{
                    fontSize: 8.5,
                    fontFamily: "var(--font-mono, monospace)",
                    padding: "1px 5px",
                    borderRadius: 4,
                    background: `${member.color}15`,
                    color: member.color,
                    fontWeight: 700,
                    maxWidth: "100%",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {member.model.split("/")[1] || member.model}
                </div>
              </div>
            );
          })}
        </div>

        {/* Selected Member Detail View (Compact 2-Column Grid) */}
        <div
          style={{
            background: "var(--bg-glass-card, #ffffff)",
            border: "1px solid var(--color-hairline, #e2e8f0)",
            borderRadius: 14,
            padding: "14px 18px",
            boxShadow: "0 6px 18px rgba(0, 0, 0, 0.04)",
            position: "relative",
            zIndex: 1,
          }}
        >
          {/* Header row */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: 10,
              paddingBottom: 10,
              marginBottom: 10,
              borderBottom: "1px solid var(--color-hairline, #e2e8f0)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <PrettyAvatar preset={activeAgent.preset} name={activeAgent.name} size={32} />
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 14.5, fontWeight: 800, color: "var(--color-ink-strong, #0f172a)" }}>
                    {activeAgent.name}
                  </span>
                  <span
                    style={{
                      fontSize: 9.5,
                      fontWeight: 700,
                      padding: "1px 6px",
                      borderRadius: 4,
                      background: `${activeAgent.color}18`,
                      color: activeAgent.color,
                      border: `1px solid ${activeAgent.color}35`,
                      textTransform: "uppercase",
                    }}
                  >
                    {activeAgent.role}
                  </span>
                  <span style={{ fontSize: 10.5, fontFamily: "var(--font-mono, monospace)", color: "var(--color-primary, #7c3aed)", fontWeight: 600 }}>
                    {activeAgent.model}
                  </span>
                </div>
              </div>
            </div>

            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 5,
                padding: "3px 9px",
                borderRadius: 9999,
                background: `${activeAgent.color}15`,
                border: `1px solid ${activeAgent.color}35`,
                fontSize: 9.5,
                fontWeight: 700,
                fontFamily: "var(--font-mono, monospace)",
                color: activeAgent.color,
              }}
            >
              <Zap size={11} />
              <span>CUSTOM PERSONA & EXECUTION</span>
            </div>
          </div>

          {/* 2-Column Content Layout */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: 12,
              alignItems: "start",
            }}
          >
            {/* Left: Persona Prompt */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-mute, #64748b)", marginBottom: 4 }}>
                CONFIGURED PERSONA & INSTRUCTIONS
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: "var(--color-ink, #1e293b)",
                  lineHeight: 1.45,
                  padding: "8px 12px",
                  background: "var(--color-canvas-raised, #f8fafc)",
                  borderRadius: 8,
                  border: "1px solid var(--color-hairline, #e2e8f0)",
                  borderLeft: `3px solid ${activeAgent.color}`,
                }}
              >
                &ldquo;{activeAgent.persona}&rdquo;
              </div>
            </div>

            {/* Right: Assigned Skills + Tool Pipeline */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-mute, #64748b)", marginBottom: 4 }}>
                ASSIGNED SKILLS
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 8 }}>
                {activeAgent.skills.map((s) => (
                  <span
                    key={s}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                      fontSize: 10.5,
                      fontFamily: "var(--font-mono, monospace)",
                      fontWeight: 600,
                      padding: "2px 7px",
                      borderRadius: 5,
                      background: "var(--color-canvas-raised, #f1f5f9)",
                      border: "1px solid var(--color-hairline, #e2e8f0)",
                      color: "var(--color-ink-strong, #0f172a)",
                    }}
                  >
                    <Zap size={10} style={{ color: activeAgent.color, flexShrink: 0 }} />
                    <span>{s}</span>
                  </span>
                ))}
              </div>

              {/* Active Tool Pipeline Terminal */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "6px 10px",
                  background: "#080914",
                  borderRadius: 8,
                  border: "1px solid rgba(167, 139, 250, 0.3)",
                  fontSize: 11,
                  fontFamily: "var(--font-mono, monospace)",
                  boxShadow: "0 2px 8px rgba(0, 0, 0, 0.2)",
                  overflowX: "auto",
                }}
              >
                <Terminal size={12} style={{ color: "#38bdf8", flexShrink: 0 }} />
                <span style={{ color: "#38bdf8", fontWeight: 700 }}>&gt;_ tool:</span>
                <span style={{ color: "#f1f5f9" }}>{activeAgent.toolCall}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
