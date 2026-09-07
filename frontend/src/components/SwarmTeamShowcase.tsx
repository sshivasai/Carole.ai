"use client";

import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence, Variants } from "framer-motion";
import PrettyAvatar, { PrettyAvatarPreset } from "./PrettyAvatar";
import { useTheme } from "@/hooks/useTheme";
import {
  Sparkles,
  Bot,
  Code2,
  ShieldCheck,
  Brain,
  Layers,
  Terminal,
  Laptop,
} from "lucide-react";

interface TeamMember {
  id: string;
  name: string;
  role: string;
  preset: PrettyAvatarPreset;
  model: string;
  skills: string[];
  description: string;
  permissions: string;
  toolCall: string;
  icon: any;
}

const TEAM_MEMBERS: TeamMember[] = [
  {
    id: "archer",
    name: "Archer",
    role: "Lead Orchestrator & Architect",
    preset: "archer",
    model: "anthropic/claude-3-7-sonnet",
    skills: ["Workflow Planning", "Subagent Delegation", "Git Integration", "Task Breakdown"],
    description:
      "Decomposes complex engineering goals into parallelizable subtasks, hires specialist subagents with depth-1 bounds, and maintains real-time Kanban status.",
    permissions: "Full Access • Subagent Spawner • Bash Gated",
    toolCall: "hire_subagent(target='Sub-PythonDev', task='Refactor AST parser')",
    icon: Bot,
  },
  {
    id: "coder",
    name: "Coder",
    role: "Full-Stack Engineer",
    preset: "coder",
    model: "deepseek/deepseek-r1",
    skills: ["Python", "TypeScript", "FastAPI", "React", "Unit Testing", "AST Refactoring"],
    description:
      "Writes atomic multi-file code patches, verifies test suites, generates point-in-time rollback backups, and prunes context dead-ends.",
    permissions: "File Read/Write • Local Terminal • Web Search",
    toolCall: "edit_file(path='backend/core/agent/context_ast.py')",
    icon: Code2,
  },
  {
    id: "judge",
    name: "Judge AI",
    role: "Security & Policy Gate",
    preset: "judge",
    model: "openai/o3-mini",
    skills: ["Policy Audit", "Risk Scoring", "Command Firewall", "Access Control"],
    description:
      "Evaluates risk on every shell command, database query, and git operation. Intercepts dangerous mutations and requires one-click human approval.",
    permissions: "Security Interceptor • Policy Enforcement Gate",
    toolCall: "request_human_approval(action='git_push', tier='human')",
    icon: ShieldCheck,
  },
  {
    id: "researcher",
    name: "Researcher",
    role: "GraphRAG & Code Search",
    preset: "researcher",
    model: "google/gemini-2.5-pro",
    skills: ["pgvector", "LanceDB HNSW", "Ontology Traversal", "DOM Scraping"],
    description:
      "Traverses multi-hop codebase ontologies and queries dense vector embeddings in LanceDB to map function calls, imports, and system dependencies.",
    permissions: "Vector DB Read • Network Traversal • Web Fetch",
    toolCall: "vector_search(query='atomic redis session lock', top_k=5)",
    icon: Brain,
  },
  {
    id: "qa",
    name: "QA Runner",
    role: "Playwright Automation",
    preset: "qa",
    model: "anthropic/claude-3-7-sonnet",
    skills: ["Playwright", "Headless Browser", "DOM Inspection", "Visual Diff"],
    description:
      "Drives headless Chromium sessions, inspects live DOM trees, validates UI flows, captures screenshot proofs, and requests human CAPTCHA takeovers.",
    permissions: "Browser Automation • DOM Inspection • Artifact Capture",
    toolCall: "browser_navigate(url='http://localhost:3000/auth')",
    icon: Laptop,
  },
  {
    id: "subagent",
    name: "Sub-PythonDev",
    role: "Specialist Subagent (Depth 1)",
    preset: "subagent",
    model: "deepseek/deepseek-r1",
    skills: ["AST Parsing", "Targeted Bugfix", "Regex Validation", "Sandbox Run"],
    description:
      "Temporary specialist spawned by Archer for an isolated subtask. Operates with strict depth-1 bounds to eliminate infinite recursion loops.",
    permissions: "Restricted File I/O • Subagents Blocked (Depth 1)",
    toolCall: "report_task_complete(metrics={'lines_parsed': 1420})",
    icon: Layers,
  },
];

const AUTO_ROTATE_DURATION = 2000; // ms (snappy speed as requested)

export default function SwarmTeamShowcase() {
  const { theme } = useTheme();
  const isDark = theme !== "light";
  const [currentIndex, setCurrentIndex] = useState(0);
  const [direction, setDirection] = useState(1);
  const [typedCommand, setTypedCommand] = useState("");
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const selectedAgent = TEAM_MEMBERS[currentIndex];

  // Auto-rotate between agents at increased speed
  useEffect(() => {
    intervalRef.current = setInterval(() => {
      setDirection(1);
      setCurrentIndex((prev) => (prev + 1) % TEAM_MEMBERS.length);
    }, AUTO_ROTATE_DURATION);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [currentIndex]);

  const handleSelectAgent = (index: number) => {
    setDirection(index > currentIndex ? 1 : -1);
    setCurrentIndex(index);
  };

  // Fast typewriter effect for live tool call snippet
  useEffect(() => {
    setTypedCommand("");
    let i = 0;
    const fullText = selectedAgent.toolCall;
    const typingInterval = setInterval(() => {
      setTypedCommand(fullText.substring(0, i + 1));
      i++;
      if (i >= fullText.length) clearInterval(typingInterval);
    }, 8);
    return () => clearInterval(typingInterval);
  }, [selectedAgent.toolCall]);

  const slideVariants: Variants = {
    enter: (dir: number) => ({
      x: dir > 0 ? 18 : -18,
      opacity: 0,
    }),
    center: {
      x: 0,
      opacity: 1,
      transition: {
        x: { type: "spring" as const, stiffness: 380, damping: 28 },
        opacity: { duration: 0.15 },
      },
    },
    exit: (dir: number) => ({
      x: dir > 0 ? -18 : 18,
      opacity: 0,
      transition: {
        x: { type: "spring" as const, stiffness: 380, damping: 28 },
        opacity: { duration: 0.12 },
      },
    }),
  };

  return (
    <div
      style={{
        width: "100%",
        maxWidth: 1140,
        margin: "0 auto",
        padding: "0 24px",
      }}
    >
      {/* Clean Section Header */}
      <div style={{ maxWidth: 720, marginBottom: 32 }}>
        <div
          style={{
            fontSize: 12,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: "var(--color-primary-soft, #818cf8)",
            marginBottom: 12,
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <Sparkles size={13} />
          <span>Multi-Agent Architecture</span>
        </div>
        <h2
          style={{
            fontSize: "clamp(1.85rem, 3.8vw, 2.75rem)",
            fontWeight: 700,
            letterSpacing: "-0.03em",
            lineHeight: 1.2,
            color: "var(--color-ink-strong, #ffffff)",
            margin: "0 0 16px",
          }}
        >
          Build your team.<br />
          <span
            style={{
              background: "linear-gradient(135deg, #a78bfa 0%, #6366f1 50%, #38bdf8 100%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            Your team builds whatever you need.
          </span>
        </h2>
        <p
          style={{
            fontSize: 16,
            color: "var(--color-mute, #a1a1aa)",
            lineHeight: 1.6,
            margin: 0,
          }}
        >
          Deploy specialized AI teammates with distinct personas, tools, and safety boundaries to automate hard engineering workflows.
        </p>
      </div>

      {/* Clean Horizontal Agent Switcher */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))",
          gap: 10,
          marginBottom: 20,
        }}
      >
        {TEAM_MEMBERS.map((member, idx) => {
          const isSelected = currentIndex === idx;
          return (
            <button
              key={member.id}
              onClick={() => handleSelectAgent(idx)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "10px 14px",
                borderRadius: 8,
                position: "relative",
                background: isSelected
                  ? (isDark ? "rgba(99, 102, 241, 0.22)" : "rgba(99, 102, 241, 0.12)")
                  : (isDark ? "rgba(18, 18, 28, 0.72)" : "rgba(255, 255, 255, 0.92)"),
                backdropFilter: "blur(14px)",
                WebkitBackdropFilter: "blur(14px)",
                border: isSelected
                  ? "1.5px solid #6366f1"
                  : (isDark ? "1px solid rgba(255, 255, 255, 0.08)" : "1px solid rgba(0, 0, 0, 0.08)"),
                boxShadow: isSelected
                  ? (isDark ? "0 4px 14px rgba(99, 102, 241, 0.25)" : "0 4px 14px rgba(99, 102, 241, 0.15)")
                  : (isDark ? "none" : "0 2px 6px rgba(0, 0, 0, 0.03)"),
                color: isSelected
                  ? (isDark ? "#ffffff" : "#4338ca")
                  : (isDark ? "#cbd5e1" : "#0f172a"),
                cursor: "pointer",
                textAlign: "left",
                transition: "all 0.15s ease",
                overflow: "hidden",
              }}
            >
              {/* Active Progress Bar */}
              {isSelected && (
                <motion.div
                  key={`progress-${currentIndex}`}
                  initial={{ width: "0%" }}
                  animate={{ width: "100%" }}
                  transition={{ duration: AUTO_ROTATE_DURATION / 1000, ease: "linear" }}
                  style={{
                    position: "absolute",
                    bottom: 0,
                    left: 0,
                    height: 2,
                    background: "var(--color-primary-soft, #818cf8)",
                    opacity: 0.85,
                  }}
                />
              )}

              <div style={{ transform: "scale(0.85)", position: "relative", zIndex: 1 }}>
                <PrettyAvatar preset={member.preset} size={28} />
              </div>
              <div style={{ position: "relative", zIndex: 1 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600, color: isSelected ? (isDark ? "#fff" : "#4338ca") : (isDark ? "#e2e8f0" : "#0f172a") }}>
                  {member.name}
                </div>
                <div style={{ fontSize: 11, color: isDark ? "#94a3b8" : "#64748b" }}>
                  {member.role.split("&")[0].trim()}
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Simple, Pure Agent Details Card */}
      <div
        style={{
          background: isDark ? "rgba(14, 14, 24, 0.78)" : "rgba(255, 255, 255, 0.95)",
          backdropFilter: "blur(24px)",
          WebkitBackdropFilter: "blur(24px)",
          border: isDark ? "1px solid rgba(255, 255, 255, 0.12)" : "1px solid rgba(0, 0, 0, 0.08)",
          borderRadius: 14,
          padding: "28px",
          minHeight: 310,
          position: "relative",
          overflow: "hidden",
          boxShadow: isDark
            ? "0 16px 40px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.08)"
            : "0 12px 36px rgba(0, 0, 0, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.8)",
        }}
      >
        <AnimatePresence mode="wait" custom={direction}>
          <motion.div
            key={selectedAgent.id}
            custom={direction}
            variants={slideVariants}
            initial="enter"
            animate="center"
            exit="exit"
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                flexWrap: "wrap",
                gap: 16,
                marginBottom: 16,
                paddingBottom: 16,
                borderBottom: isDark ? "1px solid rgba(255, 255, 255, 0.06)" : "1px solid rgba(0, 0, 0, 0.06)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                <PrettyAvatar preset={selectedAgent.preset} size={44} />
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <h3
                      style={{
                        fontSize: 18,
                        fontWeight: 700,
                        color: isDark ? "#ffffff" : "#0f172a",
                        margin: 0,
                      }}
                    >
                      {selectedAgent.name}
                    </h3>
                    <span
                      style={{
                        fontSize: 11,
                        fontFamily: "var(--font-family-mono, monospace)",
                        padding: "2px 8px",
                        borderRadius: 4,
                        background: isDark ? "rgba(99, 102, 241, 0.1)" : "#ede9fe",
                        color: isDark ? "var(--color-primary-soft, #818cf8)" : "#4338ca",
                        border: isDark ? "1px solid rgba(99, 102, 241, 0.2)" : "1px solid rgba(99, 102, 241, 0.3)",
                      }}
                    >
                      {selectedAgent.model}
                    </span>
                  </div>
                  <div style={{ fontSize: 13, color: isDark ? "#94a3b8" : "#64748b", marginTop: 2 }}>
                    {selectedAgent.role}
                  </div>
                </div>
              </div>

              <div
                style={{
                  fontSize: 11.5,
                  fontFamily: "var(--font-family-mono, monospace)",
                  color: isDark ? "#94a3b8" : "#475569",
                  background: isDark ? "rgba(255, 255, 255, 0.04)" : "rgba(0, 0, 0, 0.04)",
                  backdropFilter: "blur(8px)",
                  WebkitBackdropFilter: "blur(8px)",
                  border: isDark ? "1px solid rgba(255, 255, 255, 0.08)" : "1px solid rgba(0, 0, 0, 0.08)",
                  padding: "4px 10px",
                  borderRadius: 6,
                }}
              >
                {selectedAgent.permissions}
              </div>
            </div>

            <p
              style={{
                fontSize: 14.5,
                color: isDark ? "#cbd5e1" : "#334155",
                lineHeight: 1.6,
                margin: "0 0 20px",
              }}
            >
              {selectedAgent.description}
            </p>

            {/* Skills Badges */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 20 }}>
              {selectedAgent.skills.map((skill, idx) => (
                <span
                  key={idx}
                  style={{
                    fontSize: 11.5,
                    fontWeight: 500,
                    padding: "3px 9px",
                    borderRadius: 4,
                    background: isDark ? "rgba(255, 255, 255, 0.04)" : "rgba(0, 0, 0, 0.04)",
                    backdropFilter: "blur(8px)",
                    WebkitBackdropFilter: "blur(8px)",
                    border: isDark ? "1px solid rgba(255, 255, 255, 0.08)" : "1px solid rgba(0, 0, 0, 0.08)",
                    color: isDark ? "#e2e8f0" : "#1e293b",
                  }}
                >
                  {skill}
                </span>
              ))}
            </div>

            {/* Live Fast Terminal Tool Call */}
            <div
              style={{
                background: isDark ? "rgba(6, 6, 14, 0.72)" : "#0f172a",
                backdropFilter: "blur(12px)",
                WebkitBackdropFilter: "blur(12px)",
                border: isDark ? "1px solid rgba(255, 255, 255, 0.08)" : "1px solid #1e293b",
                borderRadius: 8,
                padding: "12px 14px",
                fontFamily: "var(--font-family-mono, monospace)",
                fontSize: 12.5,
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <Terminal size={14} style={{ color: "var(--color-primary-soft, #818cf8)", flexShrink: 0 }} />
              <span style={{ color: "var(--color-mute, #71717a)" }}>$</span>
              <span style={{ color: "var(--color-primary-soft, #818cf8)" }}>
                {typedCommand}
                <span
                  style={{
                    display: "inline-block",
                    width: 6,
                    height: 14,
                    background: "var(--color-primary-soft, #818cf8)",
                    marginLeft: 2,
                    verticalAlign: "middle",
                    animation: "blink 1s step-end infinite",
                  }}
                />
              </span>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
