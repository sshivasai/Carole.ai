"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import PrettyAvatar, { PrettyAvatarPreset } from "./PrettyAvatar";
import MagneticCard from "./MagneticCard";
import IntegrationsAnimation from "./IntegrationsAnimation";
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
  const [hoveredCardId, setHoveredCardId] = useState<string | null>(null);
  const [isDetailHovered, setIsDetailHovered] = useState(false);
  const [typedToolCall, setTypedToolCall] = useState("");

  // Rotate highlight every few seconds if not paused
  useEffect(() => {
    if (!isSimulating) return;
    const timer = setInterval(() => {
      setTickerIndex((prev) => (prev + 1) % TEAM_MEMBERS.length);
    }, 4500);
    return () => clearInterval(timer);
  }, [isSimulating]);

  const activeAgent = TEAM_MEMBERS[tickerIndex] || selectedAgent;

  // Typewriter effect for terminal tool calls
  useEffect(() => {
    setTypedToolCall("");
    let i = 0;
    const fullText = activeAgent.toolCall;
    const interval = setInterval(() => {
      setTypedToolCall(fullText.substring(0, i + 1));
      i++;
      if (i >= fullText.length) clearInterval(interval);
    }, 15);
    return () => clearInterval(interval);
  }, [activeAgent.toolCall]);

  // Motion variants
  const containerVariants = {
    hidden: {},
    visible: {
      transition: {
        staggerChildren: 0.08,
      },
    },
  };

  const fadeInUp = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        type: "spring" as const,
        stiffness: 100,
        damping: 18,
      },
    },
  };

  return (
    <motion.div
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, amount: 0.15 }}
      variants={containerVariants}
      style={{
        width: "100%",
        maxWidth: 1200,
        margin: "0 auto 72px",
        padding: "0 24px",
      }}
    >
      {/* Container Card */}
      <motion.div
        variants={fadeInUp}
        style={{
          background: "var(--bg-glass-panel, rgba(10, 10, 26, 0.85))",
          backdropFilter: "blur(16px)",
          WebkitBackdropFilter: "blur(16px)",
          border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.08))",
          borderRadius: 36,
          padding: "48px 36px",
          boxShadow: "none",
          position: "relative",
          overflow: "hidden",
          transition: "outline 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
        }}
      >
        {/* Section Header */}
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 24,
            marginBottom: 36,
            position: "relative",
            zIndex: 1,
          }}
        >
          <div style={{ flex: "1 1 600px" }}>
            <motion.div
              variants={fadeInUp}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontSize: 13,
                fontWeight: 500,
                fontFamily: "'Google Sans Flex', -apple-system, sans-serif",
                color: activeAgent.color,
                textTransform: "uppercase",
                letterSpacing: "0.18px",
                marginBottom: 8,
              }}
            >
              <Sparkles size={13} />
              <span>Multi-Agent Architecture</span>
            </motion.div>
            <motion.h3
              variants={fadeInUp}
              style={{
                fontSize: "clamp(24px, 3.8vw, 42px)",
                fontWeight: 450,
                fontFamily: "'Google Sans Flex', -apple-system, sans-serif",
                color: "var(--color-ink-strong, #ffffff)",
                margin: 0,
                lineHeight: "1.1",
                letterSpacing: "-0.73px",
                textTransform: "uppercase",
              }}
            >
              BUILD YOUR TEAM AND YOUR TEAM BUILDS WHATEVER YOU NEED
            </motion.h3>
            <motion.p
              variants={fadeInUp}
              style={{
                fontSize: 16,
                fontWeight: 400,
                fontFamily: "'Google Sans Flex', -apple-system, sans-serif",
                color: "var(--color-body, #94a3b8)",
                margin: "12px 0 0",
                maxWidth: 820,
                lineHeight: "24px",
              }}
            >
              Deploy autonomous AI teammates with custom personas, system instructions, modular skills, and powerful LLM integrations to automate complex engineering workflows.
            </motion.p>
          </div>

          <motion.div
            variants={fadeInUp}
            style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "8px 16px",
                borderRadius: 9999,
                background: "var(--color-canvas-soft, rgba(255, 255, 255, 0.03))",
                border: "1px solid var(--color-hairline, rgba(255, 255, 255, 0.08))",
                fontSize: 12.5,
                color: "var(--color-ink-strong, #0f172a)",
                fontWeight: 600,
                fontFamily: "'Google Sans Flex', -apple-system, sans-serif",
              }}
            >
              <Layers size={13} />
              <span>Multi-Agent System</span>
            </div>
          </motion.div>
        </div>

        {/* Team Avatar Grid */}
        <motion.div
          variants={containerVariants}
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
            gap: 16,
            marginBottom: 24,
            position: "relative",
            zIndex: 1,
          }}
        >
          {TEAM_MEMBERS.map((member, index) => {
            const isActive = activeAgent.id === member.id;
            const isHovered = hoveredCardId === member.id;
            return (
              <motion.div
                key={member.id}
                variants={fadeInUp}
                onClick={() => {
                  setTickerIndex(index);
                  setSelectedAgent(member);
                  setIsSimulating(false);
                }}
                onMouseEnter={() => setHoveredCardId(member.id)}
                onMouseLeave={() => setHoveredCardId(null)}
                style={{
                  background: isActive
                    ? "rgba(255, 255, 255, 0.03)"
                    : isHovered
                    ? "rgba(255, 255, 255, 0.01)"
                    : "transparent",
                  border: "1px solid transparent",
                  outline: isActive
                    ? `3px solid ${member.color}`
                    : isHovered
                    ? `3px solid rgba(255, 255, 255, 0.15)`
                    : `1px solid var(--color-hairline, rgba(255, 255, 255, 0.08))`,
                  outlineOffset: "0px",
                  borderRadius: 16,
                  padding: "16px 12px",
                  cursor: "pointer",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  textAlign: "center",
                  transition: "all 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
                  transform: isActive
                    ? "translateY(-4px)"
                    : isHovered
                    ? "translateY(-2px)"
                    : "translateY(0)",
                }}
              >
                <div style={{ marginBottom: 8, position: "relative" }}>
                  <PrettyAvatar preset={member.preset} name={member.name} size={40} isWorking={isActive} />
                </div>
                <div
                  style={{
                    fontSize: 14.5,
                    fontWeight: 600,
                    fontFamily: "'Google Sans Flex', -apple-system, sans-serif",
                    color: "var(--color-ink-strong, #ffffff)",
                    marginBottom: 2,
                  }}
                >
                  {member.name}
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: "var(--color-body, #94a3b8)",
                    fontWeight: 400,
                    lineHeight: 1.2,
                    marginBottom: 8,
                    minHeight: 28,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  {member.role}
                </div>
                <div
                  style={{
                    fontSize: 9,
                    fontFamily: "var(--font-mono, monospace)",
                    padding: "2px 8px",
                    borderRadius: 9999,
                    background: `${member.color}15`,
                    color: member.color,
                    fontWeight: 600,
                    maxWidth: "100%",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    border: `1px solid ${member.color}25`,
                  }}
                >
                  {member.model.split("/")[1] || member.model}
                </div>
              </motion.div>
            );
          })}
        </motion.div>

        {/* Selected Member Detail View */}
        <motion.div
          variants={fadeInUp}
          onMouseEnter={() => setIsDetailHovered(true)}
          onMouseLeave={() => setIsDetailHovered(false)}
          style={{
            background: "var(--color-canvas-raised, rgba(255, 255, 255, 0.02))",
            border: "1px solid transparent",
            outline: isDetailHovered
              ? `3.5px solid ${activeAgent.color}40`
              : `1px solid var(--color-hairline, rgba(255, 255, 255, 0.08))`,
            outlineOffset: "0px",
            borderRadius: 16,
            padding: "24px 32px",
            position: "relative",
            zIndex: 1,
            transition: "all 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
          }}
        >
          <AnimatePresence mode="wait">
            <motion.div
              key={activeAgent.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] as const }}
            >
              {/* Header row */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: 12,
                  paddingBottom: 16,
                  marginBottom: 16,
                  borderBottom: "1px solid var(--color-hairline, rgba(255, 255, 255, 0.08))",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <PrettyAvatar preset={activeAgent.preset} name={activeAgent.name} size={36} />
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span
                        style={{
                          fontSize: 17.5,
                          fontWeight: 700,
                          fontFamily: "'Google Sans Flex', -apple-system, sans-serif",
                          color: "var(--color-ink-strong, #0f172a)",
                        }}
                      >
                        {activeAgent.name}
                      </span>
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 700,
                          fontFamily: "'Google Sans Flex', -apple-system, sans-serif",
                          padding: "2px 8px",
                          borderRadius: 9999,
                          background: `${activeAgent.color}18`,
                          color: activeAgent.color,
                          border: `1px solid ${activeAgent.color}35`,
                          textTransform: "uppercase",
                          letterSpacing: "0.5px",
                        }}
                      >
                        {activeAgent.role}
                      </span>
                      <span
                        style={{
                          fontSize: 11,
                          fontFamily: "var(--font-mono, monospace)",
                          color: "var(--color-mute, #64748b)",
                          fontWeight: 600,
                        }}
                      >
                        {activeAgent.model}
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
                    background: "var(--color-canvas-soft, rgba(255, 255, 255, 0.03))",
                    border: "1px solid var(--color-hairline, rgba(255, 255, 255, 0.08))",
                    fontSize: 10,
                    fontWeight: 700,
                    fontFamily: "var(--font-mono, monospace)",
                    color: "var(--color-ink-strong, #0f172a)",
                    letterSpacing: "0.5px",
                  }}
                >
                  <Zap size={10} style={{ color: activeAgent.color }} />
                  <span>CUSTOM PERSONA</span>
                </div>
              </div>

              {/* 2-Column Content Layout */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
                  gap: 24,
                  alignItems: "start",
                }}
              >
                {/* Left: Persona Prompt */}
                <div>
                  <div
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      fontFamily: "'Google Sans Flex', -apple-system, sans-serif",
                      textTransform: "uppercase",
                      letterSpacing: "0.5px",
                      color: "var(--color-mute, #64748b)",
                      marginBottom: 8,
                    }}
                  >
                    CONFIGURED PERSONA & INSTRUCTIONS
                  </div>
                  <div
                    style={{
                      fontSize: 13.5,
                      fontWeight: 500,
                      fontFamily: "'Google Sans Flex', -apple-system, sans-serif",
                      color: "var(--color-ink-strong, #0f172a)",
                      lineHeight: "22px",
                      padding: "16px 20px",
                      background: "var(--color-canvas-soft, #f1f5f9)",
                      borderRadius: 12,
                      border: "1px solid var(--color-hairline, rgba(0, 0, 0, 0.08))",
                      borderLeft: `4px solid ${activeAgent.color}`,
                    }}
                  >
                    &ldquo;{activeAgent.persona}&rdquo;
                  </div>
                </div>

                {/* Right: Assigned Skills + Tool Pipeline */}
                <div>
                  <div
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      fontFamily: "'Google Sans Flex', -apple-system, sans-serif",
                      textTransform: "uppercase",
                      letterSpacing: "0.5px",
                      color: "var(--color-mute, #64748b)",
                      marginBottom: 8,
                    }}
                  >
                    ASSIGNED SKILLS
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 16 }}>
                    {activeAgent.skills.map((s) => (
                      <span
                        key={s}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 6,
                          fontSize: 11.5,
                          fontFamily: "var(--font-mono, monospace)",
                          fontWeight: 600,
                          padding: "4px 10px",
                          borderRadius: 9999,
                          background: "var(--color-canvas-soft, #f1f5f9)",
                          border: "1px solid var(--color-hairline, rgba(0, 0, 0, 0.08))",
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
                      gap: 10,
                      padding: "10px 16px",
                      background: "#0f172a",
                      borderRadius: 12,
                      border: `1px solid ${activeAgent.color}40`,
                      fontSize: 12,
                      fontFamily: "var(--font-mono, monospace)",
                      overflowX: "auto",
                      transition: "all 0.3s ease",
                      boxShadow: "0 4px 12px rgba(0, 0, 0, 0.15)",
                    }}
                  >
                    <Terminal size={13} style={{ color: "#38bdf8", flexShrink: 0 }} />
                    <span style={{ color: "#38bdf8", fontWeight: 700 }}>&gt;_ tool:</span>
                    <span style={{ color: "#f8fafc", fontWeight: 600 }}>{typedToolCall}</span>
                  </div>
                </div>
              </div>
            </motion.div>
          </AnimatePresence>
        </motion.div>
      </motion.div>
    </motion.div>
  );
}
