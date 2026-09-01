"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Sun,
  Moon,
  Sparkles,
  Zap,
  ArrowRight,
  Check,
  Copy,
  Terminal,
  ShieldCheck,
  Database,
  Network,
  Boxes,
  Code2,
  GitBranch,
  Search,
  ExternalLink,
  Laptop,
  Cpu,
  Brain,
  Layers,
} from "lucide-react";

import styles from "./LandingPage.module.css";
import { useTheme } from "@/hooks/useTheme";
import { motion, AnimatePresence, useScroll, useTransform, useSpring } from "framer-motion";
import SwarmTeamShowcase from "./SwarmTeamShowcase";
import IntegrationsAnimation from "./IntegrationsAnimation";
import MagneticCard from "./MagneticCard";
import TeamChatAnimation from "./TeamChatAnimation";
import SupportedModelsShowcase from "./SupportedModelsShowcase";
import GravityParticles from "./GravityParticles";

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

type QuickstartTab = "cli" | "source";

function ScrollExpandWrapper({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end center"],
  });

  const smoothProgress = useSpring(scrollYProgress, {
    stiffness: 100,
    damping: 20,
    restDelta: 0.001
  });

  const scale = useTransform(smoothProgress, [0, 1], [0.93, 1]);
  const y = useTransform(smoothProgress, [0, 1], [100, 0]);

  return (
    <motion.div
      ref={ref}
      style={{
        scale,
        y,
        willChange: "transform",
      }}
    >
      {children}
    </motion.div>
  );
}

export default function LandingPage({
  onLaunchApp,
  onSignIn,
  onSignUp,
}: LandingPageProps) {
  const { theme, toggleTheme } = useTheme();
  const [copied, setCopied] = useState(false);
  const [copiedCli, setCopiedCli] = useState(false);
  const [selectedGraphQuery, setSelectedGraphQuery] = useState(0);
  const [quickstartTab, setQuickstartTab] = useState<QuickstartTab>("cli");
  const [typedTitle1, setTypedTitle1] = useState("");
  const [typedTitle2, setTypedTitle2] = useState("");

  useEffect(() => {
    const text1 = "Autonomous AI engineering teams.";
    const text2 = "Built for hard engineering.";
    let i = 0;
    let j = 0;

    const interval1 = setInterval(() => {
      setTypedTitle1(text1.substring(0, i + 1));
      i++;
      if (i >= text1.length) {
        clearInterval(interval1);
        setTimeout(() => {
          const interval2 = setInterval(() => {
            setTypedTitle2(text2.substring(0, j + 1));
            j++;
            if (j >= text2.length) clearInterval(interval2);
          }, 35);
        }, 200);
      }
    }, 30);

    return () => {
      clearInterval(interval1);
    };
  }, []);

  const staggerContainer = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: { staggerChildren: 0.1, delayChildren: 0.1 }
    }
  };

  const fadeUp = {
    hidden: { opacity: 0, y: 24 },
    show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.16, 1, 0.3, 1] as const } }
  };

  const bentoItem = {
    hidden: { opacity: 0, y: 20 },
    show: { 
      opacity: 1, 
      y: 0,
      transition: { type: "spring" as const, stiffness: 100, damping: 18 }
    }
  };

  const copyCliSnippet = () => {
    navigator.clipboard.writeText("pip install carole-ai && carole run");
    setCopiedCli(true);
    setTimeout(() => setCopiedCli(false), 2000);
  };

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
        "[ReActAgent] -> (generates) -> [ActionNode] -> (intercepts) -> [JudgeAIFirewall] -> (evaluates) -> [ToolExecutor]",
    },
    {
      query: "Trace guarded subagent delegation & concurrency limits",
      denseFile: "backend/core/tools/agent_tools.py",
      score: "0.954 (Coordination Match)",
      denseSummary:
        "Primary coordinators spawn temporary specialist subagents (max depth 1, max 3 concurrent) with restricted toolsets to prevent infinite recursion.",
      graphNodes:
        "[Archer Coordinator] -> (hires) -> [Sub-PythonDeveloper] -> (executes_task) -> [TaskNotification] -> (reports) -> [TeamChat]",
    },
    {
      query: "Inspect MCP sandbox tool authorization firewall",
      denseFile: "backend/core/tools/mcp_client.py",
      score: "0.962 (JSON-RPC 2.0 Match)",
      denseSummary:
        "JSON-RPC 2.0 tool execution interceptor with permission prompt firewall and per-agent token access control.",
      graphNodes:
        "[AgentTask] -> (tool_call) -> [MCPFirewall] -> (validates_token) -> [PostgresMCPServer] -> (returns_payload) -> [AgentContext]",
    },
  ];

  const quickstartSnippets: Record<QuickstartTab, string> = {
    cli: `# 1. Install Carole via pip
pip install carole-ai

# 2. Launch the autonomous AI engineering server
carole run

# Open web console at http://localhost:3000`,
    source: `# 1. Clone the open-source repository
git clone https://github.com/sshivasai/Carole.ai.git
cd Carole.ai

# 2. Setup & start the FastAPI backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: .\\venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001

# 3. In a separate terminal, launch the Next.js frontend
cd ../frontend
npm install
npm run dev

# 4. Open http://localhost:3000 to contribute & test`,
  };

  const handleCopyQuickstart = () => {
    navigator.clipboard.writeText(quickstartSnippets[quickstartTab]);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={styles.landingRoot}>
      {/*
        THESIS: An autonomous engineering mission control landing page that replaces generic pastel SaaS templates with a high-density, cybernetic flightdeck.
        OWN-WORLD: Obsidian Void (#030315) bedrock, 1px Starlight Hairlines (#2a2a3f), Cybernetic Lavender (#a78bfa) / Telemetry Cyan (#38bdf8) glows, 56px blueprint gridlines, and JetBrains Mono telemetry.
        STORY: Developers discover true multi-agent swarm orchestration, verify AST context pruning and GraphRAG telemetry, and convert via 1-click web console launch or CLI install.
        FIRST VIEWPORT: Sticky 24px backdrop-blur glass navbar with live telemetry pill, high-impact Bricolage Grotesque hero, dual conversion CLI copy bar + Launch Console CTA, over dynamic physics particles.
        FORM: Persuade / Orbital Flightdeck.
        FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
      */}

      {/* Background Atmospheric Mesh */}
      <div className={styles.bgMeshContainer}>
        <div className={styles.bgGlowOrbPrimary} />
        <div className={styles.bgGlowOrbSecondary} />
        <div className={styles.bgBlueprintGrid} />
        <div className={styles.bgCrosshairs} />
        <GravityParticles particleCount={70} connectionDistance={125} repelStrength={4.5} />
      </div>

      {/* Navigation Header */}
      <motion.header 
        className={styles.navbar}
        initial={{ y: -80, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      >
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
              alt="Carole.ai: AI Agents. Real Work."
              className={styles.navBrandWordmark}
            />
          </div>

          <nav className={styles.navLinks}>
            <span
              onClick={() => scrollToSection("team")}
              className={styles.navLink}
            >
              Agent Swarm
            </span>
            <span
              onClick={() => scrollToSection("models")}
              className={styles.navLink}
            >
              Models
            </span>
            <span
              onClick={() => scrollToSection("graphrag")}
              className={styles.navLink}
            >
              GraphRAG
            </span>
            <span
              onClick={() => scrollToSection("architecture")}
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
                <Sun size={15} style={{ color: "#fbbf24" }} />
              ) : (
                <Moon size={15} style={{ color: "#6366f1" }} />
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
              <GithubIcon size={14} />
              <span>Star</span>
            </a>

            {/* Sign In */}
            <button onClick={onSignIn || onLaunchApp} className={styles.signInBtn}>
              Sign In
            </button>

            {/* Launch Console */}
            <button
              onClick={onLaunchApp || onSignIn}
              className={styles.navLaunchBtn}
              title="Launch AI Engineering Console"
            >
              <span>Launch Console</span>
              <ArrowRight size={13} />
            </button>
          </div>
        </div>
      </motion.header>

      {/* Hero Section */}
      <motion.section 
        className={styles.heroSection}
        variants={staggerContainer}
        initial="hidden"
        animate="show"
      >
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(480px, 1fr))", gap: "40px", alignItems: "center", maxWidth: "1280px", margin: "0 auto", width: "100%", padding: "0 24px", transform: "translateY(-5vh)" }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", textAlign: "left", maxWidth: "600px" }}>
            {/* Release Status Badge */}
            <motion.div variants={fadeUp} className={styles.releaseBadge} style={{ margin: "0 0 16px 0", alignSelf: "flex-start" }}>
              <span className={styles.releaseDot} />
              <span className={styles.releaseText}>Guarded Swarms • Playwright Automation • 30+ MCPs</span>
              <span className={styles.releaseDivider}>|</span>
              <span className={styles.releaseHighlight}>Apache 2.0</span>
            </motion.div>

            <motion.h1 variants={fadeUp} className={styles.heroTitle} style={{ minHeight: "180px", textAlign: "left", display: "flex", flexDirection: "column" }}>
              <span style={{ minHeight: "60px" }}>
                {typedTitle1}
                {typedTitle1.length < "Autonomous AI engineering teams.".length && (
                  <span className={styles.typingCursor}>|</span>
                )}
              </span>
              <span className={styles.heroAccentText} style={{ minHeight: "60px" }}>
                {typedTitle1.length >= "Autonomous AI engineering teams.".length && (
                  <>
                    {typedTitle2}
                    {typedTitle2.length < "Built for hard engineering.".length && (
                      <span className={styles.typingCursor}>|</span>
                    )}
                  </>
                )}
              </span>
            </motion.h1>

            <motion.p variants={fadeUp} className={styles.heroSubtitle} style={{ textAlign: "left", margin: "0 0 24px 0", maxWidth: "560px" }}>
              Autonomous AI engineering swarms with visual browser automation, 30+ 1-click MCP integrations, and hybrid GraphRAG.
            </motion.p>

            {/* Primary CLI Command Bar */}
            <motion.div variants={fadeUp} className={styles.heroCliBar} style={{ margin: "0 0 24px 0", alignSelf: "flex-start" }}>
              <div className={styles.heroCliCode}>
                <span className={styles.heroCliPrompt}>$</span>
                <span>pip install carole-ai &amp;&amp; carole run</span>
              </div>
              <button
                onClick={copyCliSnippet}
                className={`${styles.heroCliCopyBtn} ${copiedCli ? styles.heroCliCopyBtnCopied : ""}`}
                title="Copy quickstart command"
              >
                {copiedCli ? (
                  <>
                    <Check size={12} />
                    <span>Copied</span>
                  </>
                ) : (
                  <>
                    <Copy size={12} />
                    <span>Copy</span>
                  </>
                )}
              </button>
            </motion.div>

            {/* Hero Actions */}
            <motion.div variants={fadeUp} className={styles.heroCtaGroup} style={{ justifyContent: "flex-start", width: "100%" }}>
              <button
                onClick={onLaunchApp || onSignIn}
                className={styles.heroPrimaryBtn}
              >
                <span>Launch Web Console</span>
                <ArrowRight size={14} />
              </button>

              <a
                href="https://github.com/sshivasai/Carole.ai"
                target="_blank"
                rel="noreferrer"
                className={styles.heroSecondaryBtn}
              >
                <GithubIcon size={15} />
                <span>Contribute on GitHub</span>
                <ExternalLink size={12} style={{ opacity: 0.6 }} />
              </a>
            </motion.div>
          </div>

          <div style={{ display: "flex", justifyContent: "center", alignItems: "center" }}>
            <div style={{ transform: "scale(0.9)", width: "100%" }}>
              <IntegrationsAnimation />
            </div>
          </div>
        </div>
      </motion.section>

      {/* Interactive Swarm Team Showcase */}
      <section id="team" className={styles.section} style={{ paddingTop: 48, paddingBottom: 24 }}>
        <ScrollExpandWrapper>
          <SwarmTeamShowcase />
        </ScrollExpandWrapper>
      </section>

      {/* Live Interactive Team Execution Simulator */}
      <section id="sandbox" className={styles.section} style={{ paddingTop: 24, paddingBottom: 48 }}>
        <ScrollExpandWrapper>
          <div style={{ textAlign: "center", marginBottom: 24 }}>
          <h2
            style={{
              fontSize: "clamp(24px, 3.4vw, 36px)",
              fontWeight: 800,
              letterSpacing: "-0.03em",
              color: "var(--color-ink-strong, #ffffff)",
              marginBottom: 8,
            }}
          >
            Tag an agent. Watch the swarm execute.
          </h2>
          <p
            style={{
              fontSize: 14.5,
              color: "var(--color-mute, #94a3b8)",
              maxWidth: 680,
              margin: "0 auto",
              lineHeight: 1.5,
            }}
          >
            Send a coding request in the team chat. Watch the lead coordinator break it down, dispatch specialized subagents, and push verified code in real-time.
          </p>
        </div>

        <TeamChatAnimation />
        </ScrollExpandWrapper>
      </section>

      {/* Stats Bar */}
      <motion.section 
        className={styles.statsSection}
        variants={staggerContainer}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-50px" }}
      >
        <div className={styles.statsGrid}>
          <motion.div variants={fadeUp} className={styles.statItem}>
            <span className={styles.statNumber}>&lt; 15ms</span>
            <span className={styles.statLabel}>Vector Search Latency</span>
          </motion.div>
          <motion.div variants={fadeUp} className={styles.statItem}>
            <span className={styles.statNumber}>90+</span>
            <span className={styles.statLabel}>Built-in Tools & MCP</span>
          </motion.div>
          <motion.div variants={fadeUp} className={styles.statItem}>
            <span className={styles.statNumber}>Depth-1</span>
            <span className={styles.statLabel}>Guarded Subagent Recursion</span>
          </motion.div>
          <motion.div variants={fadeUp} className={styles.statItem}>
            <span className={styles.statNumber}>100%</span>
            <span className={styles.statLabel}>Local-First & Open Source</span>
          </motion.div>
        </div>
      </motion.section>

      {/* Universal Supported Models Ecosystem */}
      <section id="models" className={styles.section}>
        <ScrollExpandWrapper>
          <SupportedModelsShowcase />
        </ScrollExpandWrapper>
      </section>

      {/* GraphRAG Interactive Engine Explorer */}
      <section id="graphrag" className={styles.section}>
        <ScrollExpandWrapper>
          <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>
            GraphRAG Code Search.
          </h2>
          <p className={styles.sectionDesc}>
            Vector search combined with code relationship graphs to trace function calls, imports, and AST paths.
          </p>
        </div>

        <div className={styles.graphragContainer}>
          <div className={styles.graphQueryBar}>
            <Search size={15} style={{ color: "var(--color-primary)" }} />
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
                <span className={styles.graphTag}>LanceDB HNSW</span>
              </div>
              <AnimatePresence mode="wait">
                <motion.div
                  key={selectedGraphQuery}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                  className={styles.graphResultItem}
                >
                  <div style={{ fontWeight: 600, color: "var(--color-ink-strong)", marginBottom: 4 }}>
                    Match File: {graphQueries[selectedGraphQuery].denseFile}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--color-primary)", marginBottom: 6 }}>
                    {graphQueries[selectedGraphQuery].score}
                  </div>
                  <div>{graphQueries[selectedGraphQuery].denseSummary}</div>
                </motion.div>
              </AnimatePresence>
            </div>

            <div className={styles.graphPane}>
              <div className={styles.graphPaneHeader}>
                <div className={styles.graphPaneTitle}>
                  <Network size={15} style={{ color: "var(--color-primary)" }} />
                  <span>Sparse Knowledge Graph</span>
                </div>
                <span className={styles.graphTag}>
                  NetworkX Multi-Hop
                </span>
              </div>
              <AnimatePresence mode="wait">
                <motion.div
                  key={selectedGraphQuery}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                  className={styles.graphResultItem}
                >
                  <div style={{ fontWeight: 700, color: "var(--color-ink-strong)", marginBottom: 6 }}>
                    Discovered Entity Pathway
                  </div>
                  <div
                    style={{
                      fontFamily: "var(--font-family-mono, monospace)",
                      fontSize: 12,
                      fontWeight: 600,
                      color: "var(--color-primary-soft, #4f46e5)",
                      lineHeight: 1.6,
                    }}
                  >
                    {graphQueries[selectedGraphQuery].graphNodes}
                  </div>
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </div>
        </ScrollExpandWrapper>
      </section>

      {/* Asymmetric Architecture Bento Grid */}
      <section id="architecture" className={styles.section}>
        <ScrollExpandWrapper>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>
              System Architecture.
            </h2>
            <p className={styles.sectionDesc}>
              Designed for deterministic execution, safety boundaries, and low latency.
            </p>
          </div>

          <motion.div 
            className={styles.bentoGrid}
            variants={{
              hidden: {},
              show: {
                transition: {
                  staggerChildren: 0.1
                }
              }
            }}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.1 }}
          >
          {/* Cell 1: Smart Context AST Management (Span 7) */}
          <motion.div variants={bentoItem} className={styles.bentoCellSpan7}>
            <MagneticCard tiltMaxAngle={6} liftAmount={8} glowColor="rgba(167, 139, 250, 0.2)" style={{ height: "100%", borderRadius: 16 }}>
              <div className={styles.bentoCard}>
                <div>
                  <div className={styles.bentoCardHeader}>
                    <div className={styles.bentoIconWrapper}>
                      <Code2 size={20} />
                    </div>
                    <div>
                      <h3 className={styles.bentoTitle}>Smart Context Management</h3>
                      <span className={styles.bentoBadge}>AST Dead-End Pruning</span>
                    </div>
                  </div>
                  <p className={styles.bentoText}>
                    Agents decompose reasoning into structured AST nodes. Dead-end tool attempts are safely pruned from history, preventing context bloat and token waste.
                  </p>
                </div>
                <div className={styles.bentoVisual}>
                  <div style={{ color: "#34d399", marginBottom: 4 }}>// AST History Optimizer</div>
                  <div>- pruned_nodes: 3 dead-end tool loops (saved 1,840 tokens)</div>
                  <div style={{ color: "var(--color-primary)" }}>+ active_context: 4,120 / 128,000 tokens (optimal reasoning window)</div>
                </div>
              </div>
            </MagneticCard>
          </motion.div>

          {/* Cell 2: Guarded Subagents (Span 5) */}
          <motion.div variants={bentoItem} className={styles.bentoCellSpan5}>
            <MagneticCard tiltMaxAngle={6} liftAmount={8} glowColor="rgba(16, 185, 129, 0.2)" style={{ height: "100%", borderRadius: 16 }}>
              <div className={styles.bentoCard}>
                <div>
                  <div className={styles.bentoCardHeader}>
                    <div className={styles.bentoIconWrapper} style={{ color: "#10b981", background: "rgba(16, 185, 129, 0.1)", borderColor: "rgba(16, 185, 129, 0.25)" }}>
                      <Layers size={20} />
                    </div>
                    <div>
                      <h3 className={styles.bentoTitle}>Guarded Subagent Delegation</h3>
                      <span className={styles.bentoBadge} style={{ color: "#10b981" }}>Depth-1 Guard</span>
                    </div>
                  </div>
                  <p className={styles.bentoText}>
                    Lead coordinators spawn temporary specialists for isolated tasks with strict concurrency boundaries to prevent recursion loops.
                  </p>
                </div>
                <div className={styles.bentoVisual}>
                  <div style={{ color: "#10b981" }}>{"[Archer Lead] -> [Sub-PythonDev (Depth 1)]"}</div>
                  <div style={{ color: "var(--color-mute)", marginTop: 4 }}>Status: Isolated sandbox • Subagent recursion blocked</div>
                </div>
              </div>
            </MagneticCard>
          </motion.div>

          {/* Cell 3: Judge AI Security Firewall (Span 5) */}
          <motion.div variants={bentoItem} className={styles.bentoCellSpan5}>
            <MagneticCard tiltMaxAngle={6} liftAmount={8} glowColor="rgba(251, 191, 36, 0.2)" style={{ height: "100%", borderRadius: 16 }}>
              <div className={styles.bentoCard}>
                <div>
                  <div className={styles.bentoCardHeader}>
                    <div className={styles.bentoIconWrapper} style={{ color: "#fbbf24", background: "rgba(251, 191, 36, 0.1)", borderColor: "rgba(251, 191, 36, 0.25)" }}>
                      <ShieldCheck size={20} />
                    </div>
                    <div>
                      <h3 className={styles.bentoTitle}>Judge AI Security Gate</h3>
                      <span className={styles.bentoBadge} style={{ color: "#fbbf24" }}>Human Approval Gate</span>
                    </div>
                  </div>
                  <p className={styles.bentoText}>
                    Real-time security evaluator intercepts shell commands, database queries, and file deletions, requiring one-click confirmation for critical actions.
                  </p>
                </div>
                <div className={styles.bentoVisual}>
                  <div style={{ color: "#fbbf24" }}>&gt;_ Intercepted: git push origin main</div>
                  <div style={{ color: "#e2e8f0" }}>Policy Rule: Production branch modification requires human sign-off</div>
                </div>
              </div>
            </MagneticCard>
          </motion.div>

          {/* Cell 4: Playwright Headless & Visual Browser QA (Span 7) */}
          <motion.div variants={bentoItem} className={styles.bentoCellSpan7}>
            <MagneticCard tiltMaxAngle={6} liftAmount={8} glowColor="rgba(244, 63, 94, 0.2)" style={{ height: "100%", borderRadius: 16 }}>
              <div className={styles.bentoCard}>
                <div>
                  <div className={styles.bentoCardHeader}>
                    <div className={styles.bentoIconWrapper} style={{ color: "#f43f5e", background: "rgba(244, 63, 94, 0.1)", borderColor: "rgba(244, 63, 94, 0.25)" }}>
                      <Laptop size={20} />
                    </div>
                    <div>
                      <h3 className={styles.bentoTitle}>Visual Browser Automation &amp; Human Takeover</h3>
                      <span className={styles.bentoBadge} style={{ color: "#f43f5e" }}>Playwright + Chromium Engine</span>
                    </div>
                  </div>
                  <p className={styles.bentoText}>
                    Browser subagents autonomously navigate live web apps, inspect DOM trees, fill forms, verify frontend regressions, and request interactive Human-in-the-Loop takeovers with live screen streaming for CAPTCHA solving.
                  </p>
                </div>
                <div className={styles.bentoVisual}>
                  <div style={{ color: "#f43f5e" }}>&gt; browser_navigate(url=&apos;http://localhost:3000/dashboard&apos;)</div>
                  <div style={{ color: "#34d399" }}>DOM element #submit-btn clicked • 14 E2E assertion checks passed • Verified screenshot attached</div>
                </div>
              </div>
            </MagneticCard>
          </motion.div>

          {/* Cell 5: AutoDream Codebase Memory (Span 12) */}
          <motion.div variants={bentoItem} className={styles.bentoCellSpan8} style={{ gridColumn: "span 12" }}>
            <MagneticCard tiltMaxAngle={4} liftAmount={6} glowColor="rgba(129, 140, 248, 0.2)" style={{ height: "100%", borderRadius: 16 }}>
              <div className={styles.bentoCard}>
                <div>
                  <div className={styles.bentoCardHeader}>
                    <div className={styles.bentoIconWrapper} style={{ color: "#818cf8", background: "rgba(129, 140, 248, 0.1)", borderColor: "rgba(129, 140, 248, 0.25)" }}>
                      <Brain size={20} />
                    </div>
                    <div>
                      <h3 className={styles.bentoTitle}>AutoDream Persistent Codebase Memory</h3>
                      <span className={styles.bentoBadge} style={{ color: "#818cf8" }}>LanceDB + pgvector</span>
                    </div>
                  </div>
                  <p className={styles.bentoText}>
                    Agents consolidate architectural learnings in the background, remembering design patterns, conventions, and bug fixes across engineering sessions.
                  </p>
                </div>
                <div className={styles.bentoVisual} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
                  <div>
                    <div style={{ color: "#818cf8" }}>Memory Consolidation Status: 48 codebase insights indexed</div>
                    <div style={{ color: "var(--color-mute)" }}>Patterns remembered: Fastify auth routing, AST parser optimizations, Redis session locks</div>
                  </div>
                  <span className={styles.bentoBadge} style={{ color: "#34d399", background: "rgba(52, 211, 153, 0.1)", borderColor: "rgba(52, 211, 153, 0.3)" }}>
                    Synchronized
                  </span>
                </div>
              </div>
            </MagneticCard>
          </motion.div>
          </motion.div>
        </ScrollExpandWrapper>
      </section>

      {/* 100% Free & Open Source Hub */}
      <section id="opensource" className={styles.section}>
        <ScrollExpandWrapper>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>
              100% Open Source.
            </h2>
            <p className={styles.sectionDesc}>
              Apache 2.0 licensed. Run with local models or bring your own API keys. No vendor lock-in.
            </p>
          </div>

          <div className={styles.openSourceContainer}>
          {/* 4 Pillars Grid */}
          <motion.div 
            className={styles.osPillarsGrid}
            variants={{
              hidden: {},
              show: {
                transition: {
                  staggerChildren: 0.08
                }
              }
            }}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.15 }}
          >
            <motion.div variants={bentoItem} className={styles.osPillarCard}>
              <div className={styles.osPillarIcon} style={{ background: "rgba(56, 189, 248, 0.1)", color: "#38bdf8" }}>
                <GitBranch size={18} />
              </div>
              <div className={styles.osPillarTitle}>Apache 2.0 Licensed</div>
              <div className={styles.osPillarDesc}>
                Completely free to use, modify, self-host, and embed in commercial or research platforms.
              </div>
            </motion.div>

            <motion.div variants={bentoItem} className={styles.osPillarCard}>
              <div className={styles.osPillarIcon} style={{ background: "rgba(16, 185, 129, 0.1)", color: "#10b981" }}>
                <ShieldCheck size={18} />
              </div>
              <div className={styles.osPillarTitle}>Local-First & Private</div>
              <div className={styles.osPillarDesc}>
                PostgreSQL, pgvector, and agent workspaces run directly in your environment with zero telemetry.
              </div>
            </motion.div>

            <motion.div variants={bentoItem} className={styles.osPillarCard}>
              <div className={styles.osPillarIcon} style={{ background: "rgba(245, 158, 11, 0.1)", color: "#f59e0b" }}>
                <Boxes size={18} />
              </div>
              <div className={styles.osPillarTitle}>Multi-Modal Context</div>
              <div className={styles.osPillarDesc}>
                Attach PDFs, Word docs, CSVs, and code repositories directly with sandboxed file extractions.
              </div>
            </motion.div>

            <motion.div variants={bentoItem} className={styles.osPillarCard}>
              <div className={styles.osPillarIcon} style={{ background: "rgba(167, 139, 250, 0.1)", color: "#a78bfa" }}>
                <Cpu size={18} />
              </div>
              <div className={styles.osPillarTitle}>1-Click MCP Marketplace</div>
              <div className={styles.osPillarDesc}>
                Connect 30+ pre-configured MCP servers (GitHub, PostgreSQL, Slack, Linear, Notion, Supabase, Stripe) with 1-click token authorization, live brand logos, and dynamic stdio/SSE registration.
              </div>
            </motion.div>
          </motion.div>

          {/* Quickstart & Contributor Terminal */}
          <motion.div 
            id="quickstart" 
            variants={bentoItem} 
            className={styles.terminalCard}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.15 }}
          >
            <div className={styles.terminalTop}>
              <div className={styles.terminalTabs}>
                <button
                  onClick={() => setQuickstartTab("cli")}
                  className={`${styles.terminalTabBtn} ${quickstartTab === "cli" ? styles.terminalTabBtnActive : ""}`}
                >
                  Quickstart CLI (pip)
                </button>
                <button
                  onClick={() => setQuickstartTab("source")}
                  className={`${styles.terminalTabBtn} ${quickstartTab === "source" ? styles.terminalTabBtnActive : ""}`}
                >
                  Developer & Contributor Setup
                </button>
              </div>

              <button onClick={handleCopyQuickstart} className={styles.copyBtn} title="Copy setup commands">
                {copied ? (
                  <>
                    <Check size={13} style={{ color: "#10b981" }} />
                    <span style={{ color: "#10b981" }}>Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy size={13} />
                    <span>Copy Snippet</span>
                  </>
                )}
              </button>
            </div>

            <AnimatePresence mode="wait">
              <motion.pre
                key={quickstartTab}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                className={styles.terminalBody}
              >
                <code>{quickstartSnippets[quickstartTab]}</code>
              </motion.pre>
            </AnimatePresence>
          </motion.div>
        </div>
        </ScrollExpandWrapper>
      </section>

      {/* Closing CTA Banner */}
      <section className={styles.ctaBanner}>
        <ScrollExpandWrapper>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: "100%" }}>
            <h2 className={styles.ctaTitle}>
              Start Your Team in Minutes.
            </h2>
            <p className={styles.ctaDesc}>
              100% open-source under Apache 2.0.
            </p>
        <div className={styles.ctaButtons}>
          <div
            onClick={copyCliSnippet}
            className={styles.heroCliBar}
            style={{ margin: 0, cursor: "pointer", maxWidth: 440 }}
            title="Click to copy"
          >
            <div className={styles.heroCliCode} style={{ fontSize: 13 }}>
              <Terminal size={15} style={{ color: "var(--color-primary)" }} />
              <span>$ pip install carole-ai</span>
            </div>
            <span className={styles.heroCliCopyBtn}>
              {copiedCli ? "Copied!" : "Copy"}
            </span>
          </div>

          <button
            onClick={onLaunchApp || onSignIn}
            className={styles.heroSecondaryBtn}
          >
            <Sparkles size={16} style={{ color: "var(--color-primary)" }} />
            <span>Launch Web Console</span>
          </button>

          <a
            href="https://github.com/sshivasai/Carole.ai"
            target="_blank"
            rel="noreferrer"
            className={styles.heroSecondaryBtn}
          >
            <GithubIcon size={16} />
            <span>Star on GitHub</span>
          </a>
        </div>
        </div>
        </ScrollExpandWrapper>
      </section>

      {/* High-Precision Footer */}
      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <div className={styles.footerBrand}>
            <img
              src="/branding/logo-mark-animated.webp"
              alt="Carole.ai"
              width={24}
              height={24}
              style={{ objectFit: "contain" }}
            />
            <img
              src={
                theme === "dark"
                  ? "/branding/logo-wordmark-dark.png"
                  : "/branding/logo-wordmark.png"
              }
              alt="Carole.ai"
              height={18}
              style={{ objectFit: "contain" }}
            />
          </div>

          <div className={styles.footerStatusBadge}>
            <span className={styles.footerDot} />
            <span>All Systems Operational • v1.0.0</span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <button
              onClick={toggleTheme}
              className={styles.themeBtn}
              title="Toggle Theme"
              aria-label="Toggle Theme"
            >
              {theme === "dark" ? (
                <Sun size={14} style={{ color: "#fbbf24" }} />
              ) : (
                <Moon size={14} style={{ color: "#6366f1" }} />
              )}
            </button>
            <span className={styles.footerCopyright}>
              100% Free & Open-Source (Apache 2.0) • © {new Date().getFullYear()} Carole.ai
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
