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
    role: "Swarm Coordinator & Lead Architect",
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
      setTickerIndex(prev => (prev + 1) % TEAM_MEMBERS.length);
    }, 4500);
    return () => clearInterval(timer);
  }, [isSimulating]);

  const activeAgent = TEAM_MEMBERS[tickerIndex] || selectedAgent;

  return (
    <div
      style={{
        width: "100%",
        maxWidth: 1200,
        margin: "0 auto 60px",
        padding: "0 24px",
      }}
    >
      {/* Container Card */}
      <div
        style={{
          background: "var(--bg-glass-panel, rgba(13, 13, 30, 0.75))",
          backdropFilter: "blur(24px)",
          WebkitBackdropFilter: "blur(24px)",
          border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.08))",
          borderRadius: 24,
          padding: "36px 32px",
          boxShadow: "0 20px 60px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(167, 139, 250, 0.08) inset",
          position: "relative",
          overflow: "hidden",
        }}
      >
        {/* Ambient Top Glow */}
        <div
          style={{
            position: "absolute",
            top: -100,
            left: "50%",
            transform: "translateX(-50%)",
            width: 600,
            height: 200,
            background: "radial-gradient(ellipse, rgba(167, 139, 250, 0.2) 0%, transparent 70%)",
            filter: "blur(50px)",
            pointerEvents: "none",
          }}
        />

        {/* Section Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 16,
            marginBottom: 32,
            position: "relative",
            zIndex: 1,
          }}
        >
          <div>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontSize: 11,
                fontWeight: 700,
                color: "var(--color-primary, #a78bfa)",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                marginBottom: 6,
              }}
            >
              <Sparkles size={13} />
              <span>Multi-Agent Architecture</span>
            </div>
            <h3
              style={{
                fontSize: "clamp(22px, 3.2vw, 32px)",
                fontWeight: 800,
                color: "var(--color-ink-strong, #ffffff)",
                margin: 0,
                letterSpacing: "-0.02em",
              }}
            >
              Create & Customize Your Autonomous Engineering Team
            </h3>
            <p
              style={{
                fontSize: 14.5,
                color: "var(--color-mute, #94a3b8)",
                margin: "8px 0 0",
                maxWidth: 780,
                lineHeight: 1.55,
              }}
            >
              Configure custom personas, system instructions, modular skills, and LLM backends (Claude 3.5, DeepSeek V3, GPT-4o, Ollama) with granular tool permission matrices.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "6px 14px",
                borderRadius: 9999,
                background: "var(--color-canvas-raised, #18182f)",
                border: "1px solid var(--border-glass, rgba(255,255,255,0.1))",
                fontSize: 12,
                color: "var(--color-primary-soft, #c4b5fd)",
                fontWeight: 600,
              }}
            >
              <Layers size={13} />
              <span>Modular Agent Swarm</span>
            </div>
          </div>
        </div>

        {/* Team Avatar Grid (Scroll & Hover Interactive) */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
            gap: 16,
            marginBottom: 28,
            position: "relative",
            zIndex: 1,
          }}
        >
          {TEAM_MEMBERS.map((member, idx) => {
            const isHighlighted = (activeAgent.id === member.id);

            return (
              <MagneticCard
                key={member.id}
                tiltMaxAngle={11}
                liftAmount={12}
                glowColor={`${member.color}35`}
                style={{ borderRadius: 18, height: "100%" }}
              >
                <div
                  onMouseEnter={() => {
                    setSelectedAgent(member);
                    setTickerIndex(idx);
                  }}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    padding: "18px 12px",
                    borderRadius: 18,
                    height: "100%",
                    background: isHighlighted
                      ? `linear-gradient(135deg, ${member.color}15, var(--color-canvas-raised, #18182f))`
                      : "var(--color-canvas-raised, #18182f)",
                    border: isHighlighted
                      ? `1.5px solid ${member.color}`
                      : "1px solid var(--border-glass, rgba(255,255,255,0.06))",
                    boxShadow: isHighlighted
                      ? `0 12px 28px ${member.color}25`
                      : "0 4px 12px rgba(0,0,0,0.2)",
                    transition: "all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1)",
                    cursor: "pointer",
                    textAlign: "center",
                    position: "relative",
                  }}
                >
                  {/* Pretty Illustrated Character Avatar */}
                  <div style={{ marginBottom: 12 }}>
                    <PrettyAvatar
                      preset={member.preset}
                      name={member.name}
                      size={64}
                      isWorking={isHighlighted}
                    />
                  </div>

                  {/* Agent Name */}
                  <div
                    style={{
                      fontSize: 14,
                      fontWeight: 700,
                      color: isHighlighted ? member.color : "var(--color-ink-strong, #ffffff)",
                      marginBottom: 2,
                    }}
                  >
                    {member.name}
                  </div>

                  {/* Agent Role */}
                  <div
                    style={{
                      fontSize: 11,
                      color: "var(--color-mute, #94a3b8)",
                      lineHeight: 1.3,
                      marginBottom: 10,
                      minHeight: 28,
                    }}
                  >
                    {member.role}
                  </div>

                  {/* Model Pill */}
                  <span
                    style={{
                      fontSize: 9.5,
                      fontFamily: "var(--font-family-mono, monospace)",
                      padding: "2px 8px",
                      borderRadius: 9999,
                      background: "rgba(255,255,255,0.05)",
                      border: "1px solid rgba(255,255,255,0.08)",
                      color: isHighlighted ? member.color : "var(--color-mute, #94a3b8)",
                    }}
                  >
                    {member.model}
                  </span>
                </div>
              </MagneticCard>
            );
          })}
        </div>

        {/* Dynamic Live Working Workbench Preview */}
        <div
          style={{
            background: "var(--color-canvas-soft, #0d0d1e)",
            borderRadius: 18,
            border: `1px solid ${activeAgent.color}40`,
            padding: "24px",
            position: "relative",
            zIndex: 1,
            boxShadow: `0 12px 36px ${activeAgent.color}18`,
            transition: "all 0.3s ease",
          }}
        >
          {/* Top Bar: Identity, Model, Permissions */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: 12,
              marginBottom: 16,
              paddingBottom: 14,
              borderBottom: "1px solid var(--border-glass, rgba(255, 255, 255, 0.08))",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <PrettyAvatar preset={activeAgent.preset} name={activeAgent.name} size={42} />
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 15, fontWeight: 800, color: "var(--color-ink-strong, #ffffff)" }}>
                    {activeAgent.name}
                  </span>
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: 6,
                      background: `${activeAgent.color}20`,
                      color: activeAgent.color,
                      border: `1px solid ${activeAgent.color}40`,
                      textTransform: "uppercase",
                    }}
                  >
                    {activeAgent.role}
                  </span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
                  <span style={{ fontSize: 11, fontFamily: "var(--font-family-mono, monospace)", color: "var(--color-primary-soft, #c4b5fd)" }}>
                    {activeAgent.model}
                  </span>
                  <span style={{ fontSize: 11, color: "var(--color-mute, #94a3b8)" }}>•</span>
                  <span style={{ fontSize: 11, color: "var(--color-mute, #94a3b8)" }}>
                    {activeAgent.permissions}
                  </span>
                </div>
              </div>
            </div>

            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "4px 12px",
                borderRadius: 9999,
                background: `${activeAgent.color}15`,
                border: `1px solid ${activeAgent.color}40`,
                fontSize: 11,
                fontWeight: 700,
                fontFamily: "var(--font-family-mono, monospace)",
                color: activeAgent.color,
              }}
            >
              <Zap size={12} />
              <span>CUSTOM PERSONA & EXECUTION</span>
            </div>
          </div>

          {/* Persona System Prompt */}
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-mute, #94a3b8)", marginBottom: 6 }}>
              Configured Persona & Instructions
            </div>
            <div
              style={{
                fontSize: 13,
                color: "var(--color-body, #e2e8f0)",
                lineHeight: 1.6,
                padding: "10px 14px",
                background: "rgba(255, 255, 255, 0.025)",
                borderRadius: 10,
                border: "1px solid rgba(255, 255, 255, 0.06)",
                borderLeft: `3px solid ${activeAgent.color}`,
              }}
            >
              "{activeAgent.persona}"
            </div>
          </div>

          {/* Assigned Skills */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-mute, #94a3b8)", marginBottom: 6 }}>
              Assigned Skills
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {activeAgent.skills.map(s => (
                <span
                  key={s}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 5,
                    fontSize: 11,
                    fontFamily: "var(--font-family-mono, monospace)",
                    padding: "3px 8px",
                    borderRadius: 6,
                    background: "rgba(255, 255, 255, 0.05)",
                    border: "1px solid rgba(255, 255, 255, 0.1)",
                    color: "var(--color-ink, #f8fafc)",
                  }}
                >
                  <Zap size={11} style={{ color: activeAgent.color, flexShrink: 0 }} />
                  <span>{s}</span>
                </span>
              ))}
            </div>
          </div>

          {/* Live Coordinated Tool Call */}
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-mute, #94a3b8)", marginBottom: 6 }}>
              Active Tool Pipeline
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "10px 14px",
                background: "rgba(0, 0, 0, 0.5)",
                borderRadius: 10,
                border: "1px solid rgba(255, 255, 255, 0.08)",
                fontSize: 12,
                fontFamily: "var(--font-family-mono, monospace)",
                color: "var(--color-primary-soft, #c4b5fd)",
                overflowX: "auto",
              }}
            >
              <Terminal size={14} style={{ color: activeAgent.color, flexShrink: 0 }} />
              <span style={{ color: "var(--color-mute, #94a3b8)" }}>tool_call:</span>
              <span style={{ color: activeAgent.color }}>{activeAgent.toolCall}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
