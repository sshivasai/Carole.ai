"use client";

import React, { useState } from "react";
import {
  Sun,
  Moon,
  ArrowRight,
  Sparkles,
  Bot,
  Brain,
  Video,
  Globe,
  Layers,
  Terminal,
  ShieldCheck,
  CheckCircle2,
  Zap,
  Kanban,
  Code2,
  Search,
  Check,
  Copy,
  Download,
  Lock,
  Cpu,
  Boxes,
  Database,
  Network,
  Activity,
  Server,
  Play,
  FileCode,
} from "lucide-react";
import styles from "./LandingPage.module.css";
import { useTheme } from "@/hooks/useTheme";
import SwarmTeamShowcase from "./SwarmTeamShowcase";
import GravityText from "./GravityText";
import GravityParticles from "./GravityParticles";
import MagneticCard from "./MagneticCard";

function GithubIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
      />
    </svg>
  );
}

interface LandingPageProps {
  onLaunchApp?: () => void;
  onSignIn?: () => void;
  onSignUp?: () => void;
}

type SandboxTab = "fullstack" | "graphrag" | "meeting" | "mcp";
type QuickstartTab = "git" | "docker" | "python" | "k8s";

export default function LandingPage({
  onLaunchApp,
  onSignIn,
  onSignUp,
}: LandingPageProps) {
  const { theme, toggleTheme } = useTheme();
  const [activeTab, setActiveTab] = useState<SandboxTab>("fullstack");
  const [quickstartTab, setQuickstartTab] = useState<QuickstartTab>("git");
  const [copied, setCopied] = useState(false);
  const [selectedGraphQuery, setSelectedGraphQuery] = useState(0);

  const scrollToSection = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth" });
    }
  };

  const graphQueries = [
    {
      query: "How are agent context dead-ends and tool observations pruned?",
      denseFile: "backend/core/agent/context_ast.py",
      score: "0.968 (AST Context Match)",
      denseSummary:
        "Lightweight AST parser decomposes message history into ActionNodes and ObsNodes, safely pruning failed dead-end loops without stripping valid reasoning.",
      graphNodes:
        "[ReActAgent] ──(generates)──> [ActionNode] ──(intercepts)──> [JudgeAIFirewall] ──(evaluates)──> [ToolExecutor]",
    },
    {
      query: "Trace guarded subagent delegation & concurrency limits",
      denseFile: "backend/core/tools/agent_tools.py",
      score: "0.954 (Coordination Match)",
      denseSummary:
        "Primary coordinators spawn temporary specialist subagents (max depth 1, max 3 concurrent) with restricted toolsets to prevent infinite recursion.",
      graphNodes:
        "[Archer (Coordinator)] ──(hires)──> [Sub-PythonDeveloper] ──(executes_task)──> [TaskNotification] ──(reports)──> [TeamChat]",
    },
    {
      query: "Inspect MCP sandbox tool authorization firewall",
      denseFile: "backend/core/tools/mcp_client.py",
      score: "0.962 (JSON-RPC 2.0 Match)",
      denseSummary:
        "JSON-RPC 2.0 tool execution interceptor with permission prompt firewall and per-agent token access control.",
      graphNodes:
        "[AgentTask] ──(tool_call)──> [MCPFirewall] ──(validates_token)──> [PostgresMCPServer] ──(returns_payload)──> [AgentContext]",
    },
  ];

  const quickstartSnippets: Record<QuickstartTab, string> = {
    git: `# 1. Clone the open-source repository
git clone https://github.com/sshivasai/Carole.ai.git
cd Carole.ai

# 2. Setup & start the FastAPI backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: .\\venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001

# 3. In a separate terminal, launch Next.js frontend
cd ../frontend
npm install
npm run dev

# Open console at http://localhost:3000`,
    docker: `# Run the full Carole.ai multi-agent cluster with Docker Compose
git clone https://github.com/sshivasai/Carole.ai.git
cd Carole.ai

docker compose up -d --build

# Open Web Console at http://localhost:3000
# Backend API available at http://localhost:8001`,
    python: `# Run agent cluster with ReAct reasoning loop directly
cd backend
source venv/bin/activate

# Execute agent team workflow
python -m core.agent.react_agent

# Features pgvector semantic memory, AST dead-end pruning,
# and real-time WebSocket live reasoning stream.`,
    k8s: `# Deploy Carole.ai swarm cluster on Kubernetes
git clone https://github.com/sshivasai/Carole.ai.git
cd Carole.ai/deploy

kubectl apply -f k8s-namespace.yaml
kubectl apply -f k8s-postgres-pgvector.yaml
kubectl apply -f k8s-backend-deployment.yaml
kubectl apply -f k8s-frontend-deployment.yaml`,
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(quickstartSnippets[quickstartTab]);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={styles.landingRoot}>
      {/* Background Atmospheric Mesh */}
      <div className={styles.bgMeshContainer}>
        <div className={styles.bgGlowOrbPrimary} />
        <div className={styles.bgGlowOrbSecondary} />
        <div className={styles.bgBlueprintGrid} />
        <div className={styles.bgCrosshairs} />
      </div>

      {/* Navigation Header */}
      <header className={styles.navbar}>
        <div className={styles.navContainer}>
          <div
            className={styles.brandLink}
            onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          >
            <img
              src="/branding/logo-mark-animated.webp"
              alt="Carole.ai Logo"
              className={styles.navBrandMark}
            />
            <img
              src={
                theme === "dark"
                  ? "/branding/logo-wordmark-dark.png"
                  : "/branding/logo-wordmark.png"
              }
              alt="Carole.ai — AI Agents. Real Work."
              className={styles.navBrandWordmark}
            />
          </div>

          <nav className={styles.navLinks}>
            <span
              onClick={() => scrollToSection("team")}
              className={styles.navLink}
            >
              Swarm Team
            </span>
            <span
              onClick={() => scrollToSection("sandbox")}
              className={styles.navLink}
            >
              Swarm Sandbox
            </span>
            <span
              onClick={() => scrollToSection("graphrag")}
              className={styles.navLink}
            >
              GraphRAG Engine
            </span>
            <span
              onClick={() => scrollToSection("features")}
              className={styles.navLink}
            >
              Architecture
            </span>
            <span
              onClick={() => scrollToSection("opensource")}
              className={styles.navLink}
            >
              Open Source
            </span>
            <span
              onClick={() => scrollToSection("quickstart")}
              className={styles.navLink}
            >
              Quickstart
            </span>
          </nav>

          <div className={styles.navActions}>
            {/* Theme Toggle Button */}
            <button
              onClick={toggleTheme}
              className={styles.themeBtn}
              title={
                theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode"
              }
              aria-label="Toggle theme"
            >
              {theme === "dark" ? (
                <Sun size={16} style={{ color: "#fbbf24" }} />
              ) : (
                <Moon size={16} style={{ color: "#6366f1" }} />
              )}
            </button>

            {/* GitHub Star Button */}
            <a
              href="https://github.com/sshivasai/Carole.ai"
              target="_blank"
              rel="noreferrer"
              className={styles.githubBtn}
              title="Star on GitHub"
            >
              <GithubIcon size={15} />
              <span>Star</span>
            </a>

            <button onClick={onSignIn || onLaunchApp} className={styles.signInBtn}>
              Sign In
            </button>

            <button
              onClick={onLaunchApp || onSignIn}
              className={styles.launchBtn}
            >
              Launch Console
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className={styles.heroSection}>
        {/* Interactive Anti-Gravity Physics Canvas Background */}
        <GravityParticles particleCount={55} connectionDistance={120} mouseRadius={160} />

        {/* HUD Status Pill */}
        <div className={styles.hudBadge}>
          <span className={styles.hudDot} />
          <Zap size={13} style={{ color: "var(--color-primary, #a78bfa)", flexShrink: 0 }} />
          <span>90+ BUILT-IN TOOLS • GUARDED REACT SWARMS • 100% LOCAL & OPEN SOURCE</span>
        </div>

        <h1 className={styles.heroTitle}>
          <GravityText text="Autonomous Agent Swarms." gravityStrength={32} radius={170} />{" "}
          <span className={styles.heroGradientText}>
            <GravityText text="Built for Hard Engineering." isGradient gravityStrength={38} radius={190} />
          </span>
        </h1>

        <p className={styles.heroSubtitle}>
          Deploy self-coordinating teams of specialized AI agents with Actor-model FIFO message queues,
          typed AST dead-end pruning, depth-1 guarded subagent delegation, Judge AI security firewalls,
          and background AutoDream semantic memory consolidation.
        </p>

        <div className={styles.heroCtaGroup}>
          <button
            onClick={onLaunchApp || onSignIn}
            className={styles.heroPrimaryBtn}
          >
            <Sparkles size={17} />
            Launch Web Console
          </button>
          <button
            onClick={() => scrollToSection("quickstart")}
            className={styles.heroSecondaryBtn}
          >
            <Download size={16} />
            Self-Host / Quickstart
          </button>
        </div>

        {/* Interactive Swarm Team Showcase with Pretty Avatars */}
        <div id="team" style={{ width: "100%" }}>
          <SwarmTeamShowcase />
        </div>

        {/* Interactive Swarm Sandbox Stage */}
        <div id="sandbox" className={styles.sandboxStage}>
          <div className={styles.stageHeader}>
            <div className={styles.stageDots}>
              <span className={`${styles.dot} ${styles.dotRed}`} />
              <span className={`${styles.dot} ${styles.dotYellow}`} />
              <span className={`${styles.dot} ${styles.dotGreen}`} />
            </div>

            <div className={styles.stageTabs}>
              <button
                className={`${styles.stageTabBtn} ${
                  activeTab === "fullstack" ? styles.stageTabActive : ""
                }`}
                onClick={() => setActiveTab("fullstack")}
              >
                <Bot size={13} />
                Full-Stack ReAct Swarm
              </button>
              <button
                className={`${styles.stageTabBtn} ${
                  activeTab === "graphrag" ? styles.stageTabActive : ""
                }`}
                onClick={() => setActiveTab("graphrag")}
              >
                <Brain size={13} />
                AutoDream & LanceDB
              </button>
              <button
                className={`${styles.stageTabBtn} ${
                  activeTab === "meeting" ? styles.stageTabActive : ""
                }`}
                onClick={() => setActiveTab("meeting")}
              >
                <ShieldCheck size={13} />
                Judge AI Security Gate
              </button>
              <button
                className={`${styles.stageTabBtn} ${
                  activeTab === "mcp" ? styles.stageTabActive : ""
                }`}
                onClick={() => setActiveTab("mcp")}
              >
                <Terminal size={13} />
                Universal MCP & Tools
              </button>
            </div>

            <div className={styles.stageStatusBadge}>
              <Activity size={12} />
              <span>LIVE TELEMETRY STREAM</span>
            </div>
          </div>

          <div className={styles.stageContent}>
            {activeTab === "fullstack" && (
              <div className={styles.chatSimulation}>
                <div className={styles.simMessage}>
                  <div
                    className={styles.simAvatar}
                    style={{
                      background: "rgba(167, 139, 250, 0.15)",
                      color: "#a78bfa",
                    }}
                  >
                    <Bot size={18} />
                  </div>
                  <div className={styles.simBubble}>
                    <div className={styles.simHeader}>
                      <span className={styles.simName}>Archer (Lead Coordinator)</span>
                      <span className={styles.simRole}>Planner</span>
                    </div>
                    <div>
                      Task received:{" "}
                      <em>"Refactor authentication to distributed Redis locks and verify Playwright integration tests."</em>{" "}
                      Delegating backend logic to <strong>Coder Specialist</strong> and
                      headless browser verification to <strong>QA Runner</strong>.
                    </div>
                    <div className={styles.simToolBox}>
                      <Terminal size={14} />
                      <span>
                        {'tool_call: hire_subagent(target="Sub-PythonDev", task="Implement atomic token refresh", permissions={"subagents": "block"})'}
                      </span>
                    </div>
                  </div>
                </div>

                <div className={styles.simMessage} style={{ marginLeft: 32 }}>
                  <div
                    className={styles.simAvatar}
                    style={{
                      background: "rgba(16, 185, 129, 0.15)",
                      color: "#10b981",
                    }}
                  >
                    <Code2 size={18} />
                  </div>
                  <div className={styles.simBubble}>
                    <div className={styles.simHeader}>
                      <span className={styles.simName}>Coder Specialist</span>
                      <span className={styles.simRole}>Backend Worker</span>
                    </div>
                    <div>
                      Created automatic snapshot backup in <code>file_backups</code> and patched <code>backend/core/api/auth.py</code>.
                      AST dead-end pruner verified 0 cyclic errors.
                    </div>
                    <div
                      className={styles.simToolBox}
                      style={{ color: "#10b981", borderColor: "rgba(16, 185, 129, 0.3)" }}
                    >
                      <CheckCircle2 size={14} />
                      <span>pytest tests/test_auth.py: 18 passed in 0.94s (100% coverage)</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === "graphrag" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "10px 16px",
                    background: "var(--color-canvas-raised)",
                    borderRadius: 10,
                    border: "1px solid var(--color-hairline)",
                  }}
                >
                  <Search size={15} style={{ color: "var(--color-primary)" }} />
                  <span
                    style={{
                      fontSize: 13,
                      fontFamily: "var(--font-family-mono, monospace)",
                    }}
                  >
                    query: "Find token refresh lifecycle & dead-end pruning patterns"
                  </span>
                </div>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 14,
                  }}
                >
                  <div
                    style={{
                      padding: 16,
                      background: "var(--color-canvas-raised)",
                      borderRadius: 12,
                      border: "1px solid var(--color-hairline)",
                    }}
                  >
                    <div
                      style={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: "var(--color-primary)",
                        marginBottom: 8,
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                      }}
                    >
                      <Database size={13} />
                      Dense Vector Retrieval (LanceDB)
                    </div>
                    <div
                      style={{
                        fontSize: 12.5,
                        color: "var(--color-body)",
                        lineHeight: 1.55,
                      }}
                    >
                      Top similarity match (score: <strong>0.968</strong>) against{" "}
                      <code>core/agent/context_ast.py</code>. 1536-dim vector cosine L2
                      retrieval complete in <strong>11ms</strong>.
                    </div>
                  </div>

                  <div
                    style={{
                      padding: 16,
                      background: "var(--color-canvas-raised)",
                      borderRadius: 12,
                      border: "1px solid var(--color-hairline)",
                    }}
                  >
                    <div
                      style={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: "#38bdf8",
                        marginBottom: 8,
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                      }}
                    >
                      <Zap size={13} />
                      AutoDream Background Consolidation
                    </div>
                    <div
                      style={{
                        fontSize: 12.5,
                        color: "var(--color-body)",
                        lineHeight: 1.55,
                      }}
                    >
                      Background dream worker consolidated <strong>24 unprocessed messages</strong>,
                      decayed low-confidence memories, and updated <code>learnings</code> table.
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === "meeting" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "10px 16px",
                    background: "rgba(251, 191, 36, 0.08)",
                    borderRadius: 10,
                    border: "1px solid rgba(251, 191, 36, 0.3)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      fontSize: 13,
                      fontWeight: 700,
                      color: "#fbbf24",
                    }}
                  >
                    <ShieldCheck size={16} />
                    <span>Judge AI Security Gate — Multi-Tier Authorization</span>
                  </div>
                  <span
                    style={{
                      fontSize: 11,
                      fontFamily: "var(--font-family-mono, monospace)",
                      color: "#fbbf24",
                    }}
                  >
                    STATUS: INTERCEPTED & GATED
                  </span>
                </div>

                <div
                  style={{
                    padding: 16,
                    background: "var(--color-canvas-raised)",
                    borderRadius: 12,
                    border: "1px solid var(--color-hairline)",
                    fontSize: 13,
                    lineHeight: 1.6,
                  }}
                >
                  <p style={{ margin: "0 0 10px", fontFamily: "var(--font-family-mono, monospace)", color: "var(--color-ink-strong)" }}>
                    <strong>Tool Intercepted:</strong> execute_command(command="git push origin main --force")
                  </p>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "10px 14px",
                      background: "rgba(239, 68, 68, 0.1)",
                      borderRadius: 8,
                      color: "#f87171",
                      border: "1px solid rgba(239, 68, 68, 0.3)",
                    }}
                  >
                    <Zap size={14} />
                    <span>
                      <strong>Judge AI Verdict:</strong> Destructive git force push detected. Escalated to <strong>Human Approval Card</strong> over WebSocket.
                    </span>
                  </div>
                </div>
              </div>
            )}

            {activeTab === "mcp" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "10px 16px",
                    background: "var(--color-canvas-raised)",
                    borderRadius: 10,
                    border: "1px solid var(--color-hairline)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      fontSize: 13,
                      fontWeight: 700,
                      color: "var(--color-primary)",
                    }}
                  >
                    <Terminal size={16} />
                    <span>90+ Unified Engineering Tools & MCP Client</span>
                  </div>
                  <span
                    style={{
                      fontSize: 11,
                      fontFamily: "var(--font-family-mono, monospace)",
                      color: "#10b981",
                    }}
                  >
                    STATUS: JSON-RPC 2.0 ACTIVE
                  </span>
                </div>

                <div
                  style={{
                    padding: 16,
                    background: "var(--color-canvas-raised)",
                    borderRadius: 12,
                    border: "1px solid var(--color-hairline)",
                    fontFamily: "var(--font-family-mono, monospace)",
                    fontSize: 12.5,
                    lineHeight: 1.6,
                  }}
                >
                  <div style={{ color: "var(--color-mute)", marginBottom: 6 }}>
                    // Invoking external MCP server tool [mcp_postgres]
                  </div>
                  <div style={{ color: "var(--color-ink-strong)" }}>
                    POST /mcp/postgres/execute_query →{" "}
                    <span style={{ color: "#38bdf8" }}>
                      "SELECT * FROM users WHERE status = 'active'"
                    </span>
                  </div>
                  <div
                    style={{
                      marginTop: 10,
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      color: "#10b981",
                    }}
                  >
                    <CheckCircle2 size={14} />
                    <span>Authorized by Policy Matrix: Read-Only Query Approved ✓</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Stats Bar */}
      <section className={styles.statsSection}>
        <div className={styles.statsGrid}>
          <div className={styles.statItem}>
            <span className={styles.statNumber}>&lt; 15ms</span>
            <span className={styles.statLabel}>LanceDB HNSW Latency</span>
          </div>
          <div className={styles.statItem}>
            <span className={styles.statNumber}>90+</span>
            <span className={styles.statLabel}>Built-in Tools & MCP</span>
          </div>
          <div className={styles.statItem}>
            <span className={styles.statNumber}>Depth-1</span>
            <span className={styles.statLabel}>Guarded Subagent Delegation</span>
          </div>
          <div className={styles.statItem}>
            <span className={styles.statNumber}>100%</span>
            <span className={styles.statLabel}>Local, Private & Open Source</span>
          </div>
        </div>
      </section>

      {/* GraphRAG Interactive Engine Deep Dive */}
      <section id="graphrag" className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={styles.sectionEyebrow}>Semantic Intelligence</div>
          <h2 className={styles.sectionTitle}>
            <GravityText text="Hybrid GraphRAG. Dense Vectors Meet Sparse Knowledge Graphs." gravityStrength={22} radius={140} />
          </h2>
          <p className={styles.sectionDesc}>
            Standard vector databases lose contextual relationships across multi-hop
            codebases. Carole.ai pairs LanceDB dense embeddings with NetworkX ontology
            graphs for complete structural recall.
          </p>
        </div>

        <div className={styles.graphragContainer}>
          <div className={styles.graphQueryBar}>
            <Search size={16} style={{ color: "var(--color-primary)" }} />
            <input
              className={styles.graphQueryInput}
              value={graphQueries[selectedGraphQuery].query}
              readOnly
            />
            <div style={{ display: "flex", gap: 6 }}>
              {graphQueries.map((q, idx) => (
                <button
                  key={idx}
                  onClick={() => setSelectedGraphQuery(idx)}
                  style={{
                    padding: "4px 10px",
                    borderRadius: 6,
                    fontSize: 11,
                    fontWeight: 700,
                    fontFamily: "var(--font-family-mono, monospace)",
                    border:
                      selectedGraphQuery === idx
                        ? "1px solid var(--color-primary)"
                        : "1px solid var(--color-hairline)",
                    background:
                      selectedGraphQuery === idx
                        ? "var(--color-primary-glow)"
                        : "var(--color-canvas-soft)",
                    color:
                      selectedGraphQuery === idx
                        ? "var(--color-primary)"
                        : "var(--color-mute)",
                    cursor: "pointer",
                  }}
                >
                  Query #{idx + 1}
                </button>
              ))}
            </div>
          </div>

          <div className={styles.graphDualGrid}>
            <div className={styles.graphPane}>
              <div className={styles.graphPaneHeader}>
                <div className={styles.graphPaneTitle}>
                  <Database size={15} style={{ color: "var(--color-primary)" }} />
                  <span>Dense Vector Engine</span>
                </div>
                <span className={styles.graphTag}>LanceDB (L2)</span>
              </div>
              <div className={styles.graphResultItem}>
                <div style={{ fontWeight: 600, color: "var(--color-ink-strong)", marginBottom: 4 }}>
                  Match File: {graphQueries[selectedGraphQuery].denseFile}
                </div>
                <div style={{ fontSize: 12, color: "var(--color-primary)", marginBottom: 6 }}>
                  {graphQueries[selectedGraphQuery].score}
                </div>
                <div>{graphQueries[selectedGraphQuery].denseSummary}</div>
              </div>
            </div>

            <div className={styles.graphPane}>
              <div className={styles.graphPaneHeader}>
                <div className={styles.graphPaneTitle}>
                  <Network size={15} style={{ color: "#38bdf8" }} />
                  <span>Sparse Knowledge Ontology</span>
                </div>
                <span className={styles.graphTag} style={{ color: "#38bdf8" }}>
                  NetworkX Multi-Hop
                </span>
              </div>
              <div className={styles.graphResultItem}>
                <div style={{ fontWeight: 600, color: "var(--color-ink-strong)", marginBottom: 6 }}>
                  Discovered Entity Pathway
                </div>
                <div
                  style={{
                    fontFamily: "var(--font-family-mono, monospace)",
                    fontSize: 11.5,
                    color: "#38bdf8",
                    lineHeight: 1.6,
                  }}
                >
                  {graphQueries[selectedGraphQuery].graphNodes}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Core Features Architecture */}
      <section id="features" className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={styles.sectionEyebrow}>Swarm Architecture</div>
          <h2 className={styles.sectionTitle}>
            <GravityText text="Everything your agent team needs to execute real-world engineering." gravityStrength={22} radius={140} />
          </h2>
          <p className={styles.sectionDesc}>
            Built from first principles for developers and engineering teams who demand
            genuine autonomy, safety guardrails, low latency, and zero vendor lock-in.
          </p>
        </div>

        <div className={styles.featuresGrid}>
          <MagneticCard tiltMaxAngle={8} liftAmount={10} glowColor="rgba(167, 139, 250, 0.25)" style={{ borderRadius: 16 }}>
            <div className={styles.featureCard} style={{ height: "100%" }}>
              <div className={styles.featureIconWrap}>
                <Brain size={24} />
              </div>
              <h3 className={styles.featureTitle}>ReAct Loop & AST Pruning</h3>
              <p className={styles.featureText}>
                Autonomous ReAct reasoning loops with typed AST-level dead-end pruning.
                Failed tool actions are safely removed from context without corrupting
                valid thought chains or blowing token budgets.
              </p>
              <span className={styles.featureBadge}>
                <Sparkles size={13} /> AST Context Pruning
              </span>
            </div>
          </MagneticCard>

          <MagneticCard tiltMaxAngle={8} liftAmount={10} glowColor="rgba(16, 185, 129, 0.25)" style={{ borderRadius: 16 }}>
            <div className={styles.featureCard} style={{ height: "100%" }}>
              <div className={styles.featureIconWrap}>
                <Bot size={24} />
              </div>
              <h3 className={styles.featureTitle}>Guarded Subagent Delegation</h3>
              <p className={styles.featureText}>
                Primary coordinators hire specialist temporary subagents on-the-fly.
                Strict depth-1 delegation guards and team concurrency limits prevent
                infinite recursive loops and runaway token usage.
              </p>
              <span className={styles.featureBadge}>
                <Sparkles size={13} /> Depth-1 Guarded Swarms
              </span>
            </div>
          </MagneticCard>

          <MagneticCard tiltMaxAngle={8} liftAmount={10} glowColor="rgba(251, 191, 36, 0.25)" style={{ borderRadius: 16 }}>
            <div className={styles.featureCard} style={{ height: "100%" }}>
              <div className={styles.featureIconWrap}>
                <ShieldCheck size={24} />
              </div>
              <h3 className={styles.featureTitle}>Judge AI Security Firewall</h3>
              <p className={styles.featureText}>
                Multi-tiered tool authorization (Safe, Judge, Human, Block).
                A dedicated Judge LLM evaluates shell and database mutations in real time,
                requiring one-click human approvals for critical actions.
              </p>
              <span className={styles.featureBadge}>
                <Sparkles size={13} /> Multi-Tier Permission Gate
              </span>
            </div>
          </MagneticCard>

          <MagneticCard tiltMaxAngle={8} liftAmount={10} glowColor="rgba(56, 189, 248, 0.25)" style={{ borderRadius: 16 }}>
            <div className={styles.featureCard} style={{ height: "100%" }}>
              <div className={styles.featureIconWrap}>
                <Kanban size={24} />
              </div>
              <h3 className={styles.featureTitle}>Native Autonomous Kanban</h3>
              <p className={styles.featureText}>
                Agents autonomously create, assign, prioritize, and complete engineering
                tasks on real-time Kanban boards with bidirectional WebSocket sync,
                keeping human leads and agents aligned.
              </p>
              <span className={styles.featureBadge}>
                <Sparkles size={13} /> Live Board Sync
              </span>
            </div>
          </MagneticCard>

          <MagneticCard tiltMaxAngle={8} liftAmount={10} glowColor="rgba(244, 114, 182, 0.25)" style={{ borderRadius: 16 }}>
            <div className={styles.featureCard} style={{ height: "100%" }}>
              <div className={styles.featureIconWrap}>
                <Terminal size={24} />
              </div>
              <h3 className={styles.featureTitle}>90+ Engineering Tools</h3>
              <p className={styles.featureText}>
                Integrated bash execution, safe file I/O with rollback backups, Playwright
                headless browser automation, git branch management, and universal Model
                Context Protocol (MCP) server support.
              </p>
              <span className={styles.featureBadge}>
                <Sparkles size={13} /> Unified Tool Registry
              </span>
            </div>
          </MagneticCard>

          <MagneticCard tiltMaxAngle={8} liftAmount={10} glowColor="rgba(129, 140, 248, 0.25)" style={{ borderRadius: 16 }}>
            <div className={styles.featureCard} style={{ height: "100%" }}>
              <div className={styles.featureIconWrap}>
                <Database size={24} />
              </div>
              <h3 className={styles.featureTitle}>AutoDream & Semantic Memory</h3>
              <p className={styles.featureText}>
                Autonomous background memory consolidation (<code>auto_dream.py</code>).
                Distills raw conversations into dense 1536-dim vector embeddings with
                LanceDB HNSW search, confidence decay scoring, and persistent team scratchpads.
              </p>
              <span className={styles.featureBadge}>
                <Sparkles size={13} /> AutoDream Memory Worker
              </span>
            </div>
          </MagneticCard>
        </div>
      </section>

      {/* 100% Free & Open Source Hub */}
      <section id="opensource" className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={styles.sectionEyebrow}>Free & Open Source</div>
          <h2 className={styles.sectionTitle}>
            <GravityText text="100% Open Source. Self-Host, Download, and Own Your Swarm." gravityStrength={22} radius={140} />
          </h2>
          <p className={styles.sectionDesc}>
            No subscriptions, no hidden limits, and no vendor lock-in. Run with
            local LLMs (Ollama, vLLM, DeepSeek) or bring your own API keys.
          </p>
        </div>

        <div className={styles.openSourceContainer}>
          {/* 4 Pillars Grid */}
          <div className={styles.osGrid}>
            <MagneticCard tiltMaxAngle={10} liftAmount={12} glowColor="rgba(56, 189, 248, 0.25)" style={{ borderRadius: 16 }}>
              <div className={styles.osPillarCard} style={{ height: "100%" }}>
                <img
                  src="/icons/pillar-opensource.svg"
                  alt="Apache 2.0 Licensed"
                  className={styles.osIconImg}
                />
                <div className={styles.osPillarTitle}>Apache 2.0 Licensed</div>
                <div className={styles.osPillarDesc}>
                  Completely free to use, modify, self-host, and embed in commercial
                  or research platforms.
                </div>
              </div>
            </MagneticCard>

            <MagneticCard tiltMaxAngle={10} liftAmount={12} glowColor="rgba(16, 185, 129, 0.25)" style={{ borderRadius: 16 }}>
              <div className={styles.osPillarCard} style={{ height: "100%" }}>
                <img
                  src="/icons/pillar-privacy.svg"
                  alt="Local-First & Private"
                  className={styles.osIconImg}
                />
                <div className={styles.osPillarTitle}>Local-First & Private</div>
                <div className={styles.osPillarDesc}>
                  PostgreSQL, pgvector, and agent workspaces run directly in your
                  environment. Full privacy with zero telemetry.
                </div>
              </div>
            </MagneticCard>

            <MagneticCard tiltMaxAngle={10} liftAmount={12} glowColor="rgba(245, 158, 11, 0.25)" style={{ borderRadius: 16 }}>
              <div className={styles.osPillarCard} style={{ height: "100%" }}>
                <img
                  src="/icons/pillar-multimodal.svg"
                  alt="Multi-Modal Chat & Files"
                  className={styles.osIconImg}
                />
                <div className={styles.osPillarTitle}>Multi-Modal Chat & Files</div>
                <div className={styles.osPillarDesc}>
                  Attach PDFs, Word docs, CSVs, and images directly in chat with
                  automatic extraction and sandboxed file references.
                </div>
              </div>
            </MagneticCard>

            <MagneticCard tiltMaxAngle={10} liftAmount={12} glowColor="rgba(167, 139, 250, 0.25)" style={{ borderRadius: 16 }}>
              <div className={styles.osPillarCard} style={{ height: "100%" }}>
                <img
                  src="/icons/pillar-mcp.svg"
                  alt="Universal MCP Support"
                  className={styles.osIconImg}
                />
                <div className={styles.osPillarTitle}>Universal MCP Support</div>
                <div className={styles.osPillarDesc}>
                  Plug in any open-source Model Context Protocol server for
                  PostgreSQL, GitHub, Docker, and beyond.
                </div>
              </div>
            </MagneticCard>
          </div>

          {/* Quickstart Terminal Card */}
          <div id="quickstart" className={styles.terminalCard}>
            <div className={styles.terminalTop}>
              <div className={styles.terminalTabs}>
                <button
                  className={`${styles.terminalTab} ${
                    quickstartTab === "git" ? styles.terminalTabActive : ""
                  }`}
                  onClick={() => setQuickstartTab("git")}
                >
                  Git / Manual
                </button>
                <button
                  className={`${styles.terminalTab} ${
                    quickstartTab === "docker" ? styles.terminalTabActive : ""
                  }`}
                  onClick={() => setQuickstartTab("docker")}
                >
                  Docker Compose
                </button>
                <button
                  className={`${styles.terminalTab} ${
                    quickstartTab === "python" ? styles.terminalTabActive : ""
                  }`}
                  onClick={() => setQuickstartTab("python")}
                >
                  Python Agent Loop
                </button>
                <button
                  className={`${styles.terminalTab} ${
                    quickstartTab === "k8s" ? styles.terminalTabActive : ""
                  }`}
                  onClick={() => setQuickstartTab("k8s")}
                >
                  Kubernetes
                </button>
              </div>

              <button onClick={handleCopy} className={styles.copyBtn}>
                {copied ? (
                  <>
                    <Check size={13} style={{ color: "#10b981" }} />
                    <span style={{ color: "#10b981" }}>Copied to Clipboard!</span>
                  </>
                ) : (
                  <>
                    <Copy size={13} />
                    <span>Copy Command</span>
                  </>
                )}
              </button>
            </div>

            <pre className={styles.terminalBody}>
              <code>{quickstartSnippets[quickstartTab]}</code>
            </pre>
          </div>
        </div>
      </section>

      {/* CTA Banner */}
      <section className={styles.ctaBanner}>
        <h2 className={styles.ctaTitle}>
          Ready to orchestrate your first autonomous AI team?
        </h2>
        <p
          style={{
            fontSize: 16.5,
            color: "var(--color-body)",
            maxWidth: 620,
            margin: "0 auto 32px",
            lineHeight: 1.6,
          }}
        >
          Carole.ai is 100% free and open-source. Download, run locally, or launch
          the web console now.
        </p>
        <div
          style={{
            display: "flex",
            gap: 16,
            justifyContent: "center",
            flexWrap: "wrap",
          }}
        >
          <button
            onClick={onLaunchApp || onSignIn}
            className={styles.heroPrimaryBtn}
          >
            <Sparkles size={17} />
            Launch Carole.ai Console
          </button>
          <a
            href="https://github.com/sshivasai/Carole.ai"
            target="_blank"
            rel="noreferrer"
            className={styles.heroSecondaryBtn}
          >
            <GithubIcon size={17} />
            Star on GitHub
          </a>
        </div>
      </section>

      {/* Footer */}
      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <div className={styles.footerBrand}>
            <img
              src="/branding/logo-mark-animated.webp"
              alt="Carole.ai"
              width={26}
              height={26}
              style={{ objectFit: "contain" }}
            />
            <img
              src={
                theme === "dark"
                  ? "/branding/logo-wordmark-dark.png"
                  : "/branding/logo-wordmark.png"
              }
              alt="Carole.ai"
              height={20}
              style={{ objectFit: "contain" }}
            />
          </div>

          <div className={styles.footerStatusBadge}>
            <span className={styles.footerDot} />
            <span>All Systems Operational • v2.4.0-edge</span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
            <button
              onClick={toggleTheme}
              className={styles.themeBtn}
              title="Toggle Theme"
            >
              {theme === "dark" ? (
                <Sun size={15} style={{ color: "#fbbf24" }} />
              ) : (
                <Moon size={15} style={{ color: "#6366f1" }} />
              )}
            </button>
            <span className={styles.footerCopyright}>
              100% Free & Open-Source (Apache 2.0) • © {new Date().getFullYear()}{" "}
              Carole.ai
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
