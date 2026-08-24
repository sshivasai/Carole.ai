"use client";

import React, { useState, useEffect } from "react";
import {
  Sun,
  Moon,
  Sparkles,
  Bot,
  Terminal,
  Shield,
  ShieldCheck,
  Layers,
  ArrowRight,
  GitBranch,
  Cpu,
  Database,
  Lock,
  Zap,
  Globe,
  Code2,
  CheckCircle2,
  Copy,
  ExternalLink,
  Workflow,
  Network,
  Download,
  Flame,
  ChevronRight,
  Activity,
  Server,
  Play,
  FileCode,
  ChevronDown,
  Monitor,
  Laptop,
  Search,
  Check,
  Brain,
  Video,
  Kanban,
  Boxes,
} from "lucide-react";

import styles from "./LandingPage.module.css";
import { useTheme } from "@/hooks/useTheme";
import SwarmTeamShowcase from "./SwarmTeamShowcase";
import GravityText from "./GravityText";
import GravityParticles from "./GravityParticles";
import MagneticCard from "./MagneticCard";
import TeamChatAnimation from "./TeamChatAnimation";
import SupportedModelsShowcase from "./SupportedModelsShowcase";

function WindowsIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <path d="M0 3.449L9.75 2.1v9.451H0m10.949-9.602L24 0v11.551H10.949M0 12.6h9.75v9.451L0 20.699M10.949 12.6H24V24l-12.951-1.801" />
    </svg>
  );
}

function AppleIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M15.97 6.37c.61-.75 1.04-1.8 0.92-2.85-.9.04-2.02.6-2.66 1.34-.56.65-1.06 1.7-0.93 2.72 1.01.08 2.05-.46 2.67-1.21z" />
    </svg>
  );
}



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

export default function LandingPage({
  onLaunchApp,
  onSignIn,
  onSignUp,
}: LandingPageProps) {
  const { theme, toggleTheme } = useTheme();
  const [activeTab, setActiveTab] = useState<SandboxTab>("fullstack");
  const [copied, setCopied] = useState(false);
  const [copiedCli, setCopiedCli] = useState(false);
  const [selectedGraphQuery, setSelectedGraphQuery] = useState(0);

  // Strategic Platform & Context Detection
  const [userOS, setUserOS] = useState<"windows" | "mac" | "linux">("windows");
  const [isLocalHost, setIsLocalHost] = useState(false);
  const [navDropdownOpen, setNavDropdownOpen] = useState(false);
  const [heroDropdownOpen, setHeroDropdownOpen] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      setIsLocalHost(
        window.location.hostname === "localhost" ||
        window.location.hostname === "127.0.0.1" ||
        window.location.hostname.endsWith(".local")
      );
      const ua = navigator.userAgent.toLowerCase();
      if (ua.includes("mac")) {
        setUserOS("mac");
      } else if (ua.includes("linux")) {
        setUserOS("linux");
      } else {
        setUserOS("windows");
      }
    }
  }, []);

  // Close dropdowns on outside click
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest(`.${styles.downloadSplitGroup}`)) {
        setNavDropdownOpen(false);
        setHeroDropdownOpen(false);
      }
    };
    window.addEventListener("click", handleOutsideClick);
    return () => window.removeEventListener("click", handleOutsideClick);
  }, []);

  const copyCliSnippet = () => {
    navigator.clipboard.writeText("pip install carole-ai && carole run");
    setCopiedCli(true);
    setTimeout(() => setCopiedCli(false), 2000);
  };

  const getPrimaryDownloadInfo = () => {
    if (userOS === "mac") {
      return {
        label: "Download for macOS",
        sub: "Apple Silicon & Intel (.dmg)",
        icon: <AppleIcon size={16} />,
        href: "https://github.com/sshivasai/Carole.ai/releases",
      };
    }
    return {
      label: "Download for Windows",
      sub: "Windows 10 / 11 (.exe)",
      icon: <WindowsIcon size={16} />,
      href: "https://github.com/sshivasai/Carole.ai/releases",
    };
  };

  const primaryDownload = getPrimaryDownloadInfo();

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

  const quickstartManualSnippet = `# 1. Clone the open-source repository
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

# Open console at http://localhost:3000`;

  const handleCopy = () => {
    navigator.clipboard.writeText(quickstartManualSnippet);
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
              onClick={() => scrollToSection("models")}
              className={styles.navLink}
            >
              Supported Models
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

            {/* Single Streamlined Sign In */}
            <button onClick={onSignIn || onLaunchApp} className={styles.signInBtn}>
              Sign In
            </button>

            {/* Strategic Action: If running on localhost, show Launch Console. If on website, show Download with Dropdown */}
            {isLocalHost ? (
              <button
                onClick={onLaunchApp || onSignIn}
                className={styles.launchBtn}
                title="Launch Local AI Engineering Console"
              >
                Launch Console
                <ArrowRight size={14} />
              </button>
            ) : (
              <div className={styles.downloadSplitGroup}>
                <a
                  href={primaryDownload.href}
                  target="_blank"
                  rel="noreferrer"
                  className={styles.downloadSplitMain}
                  title={`${primaryDownload.label} (${primaryDownload.sub})`}
                >
                  {primaryDownload.icon}
                  <span>Download</span>
                </a>
                <button
                  type="button"
                  className={styles.downloadSplitChevron}
                  onClick={(e) => {
                    e.stopPropagation();
                    setNavDropdownOpen(!navDropdownOpen);
                  }}
                  title="Choose operating system"
                  aria-label="Toggle download options"
                >
                  <ChevronDown size={14} />
                </button>

                {navDropdownOpen && (
                  <div className={styles.downloadDropdownMenu}>
                    <div className={styles.downloadDropdownHeader}>
                      <span>DESKTOP APP</span>
                      <span>v1.0.0</span>
                    </div>
                    <a
                      href="https://github.com/sshivasai/Carole.ai/releases"
                      target="_blank"
                      rel="noreferrer"
                      className={styles.downloadDropdownItem}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <div style={{ color: "#38bdf8", display: "flex" }}>
                          <WindowsIcon size={18} />
                        </div>
                        <div>
                          <div className={styles.downloadItemTitle}>Windows (64-bit)</div>
                          <div className={styles.downloadItemSub}>Setup .exe • Windows 10 / 11</div>
                        </div>
                      </div>
                      <span className={styles.downloadItemBadge}>.exe</span>
                    </a>
                    <a
                      href="https://github.com/sshivasai/Carole.ai/releases"
                      target="_blank"
                      rel="noreferrer"
                      className={styles.downloadDropdownItem}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <div style={{ color: "#f8fafc", display: "flex" }}>
                          <AppleIcon size={18} />
                        </div>
                        <div>
                          <div className={styles.downloadItemTitle}>macOS</div>
                          <div className={styles.downloadItemSub}>Apple Silicon & Intel (.dmg)</div>
                        </div>
                      </div>
                      <span className={styles.downloadItemBadge}>.dmg</span>
                    </a>
                    <div className={styles.downloadDropdownDivider} />
                    <button
                      type="button"
                      onClick={() => {
                        setNavDropdownOpen(false);
                        if (onLaunchApp || onSignIn) (onLaunchApp || onSignIn)!();
                      }}
                      className={styles.downloadDropdownItem}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <Sparkles size={17} style={{ color: "var(--color-primary)" }} />
                        <div>
                          <div className={styles.downloadItemTitle}>Launch Web Console</div>
                          <div className={styles.downloadItemSub}>Instant browser access • Zero install</div>
                        </div>
                      </div>
                      <ArrowRight size={14} style={{ opacity: 0.7 }} />
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className={styles.heroSection}>
        {/* Interactive Anti-Gravity Physics Canvas Background */}
        <GravityParticles particleCount={88} connectionDistance={125} mouseRadius={170} />

        {/* HUD Status Pill */}
        <div className={styles.hudBadge}>
          <span className={styles.hudDot} />
          <Zap size={13} style={{ color: "var(--color-primary, #a78bfa)", flexShrink: 0 }} />
          <span>90+ BUILT-IN TOOLS • GUARDED MULTI-AGENT TEAMS • 100% LOCAL & OPEN SOURCE</span>
        </div>

        <h1 className={styles.heroTitle}>
          <GravityText text="Autonomous AI Engineering Teams." gravityStrength={32} radius={170} />{" "}
          <span className={styles.heroGradientText}>
            <GravityText text="Built for Hard Engineering." isGradient gravityStrength={38} radius={190} />
          </span>
        </h1>

        <p className={styles.heroSubtitle}>
          Deploy autonomous teams of AI engineers that collaborate to build features, fix bugs, run tests, and manage workflows — with real-time reasoning loops, safety guardrails, and long-term memory.
        </p>

        {/* Strategic Hero CTA Group */}
        <div className={styles.heroCtaGroup}>
          {/* Primary Download for OS with Dropdown */}
          <div className={styles.downloadSplitGroup}>
            <a
              href={primaryDownload.href}
              target="_blank"
              rel="noreferrer"
              className={styles.heroDownloadBtn}
            >
              {primaryDownload.icon}
              <div style={{ textAlign: "left" }}>
                <div>{primaryDownload.label}</div>
                <div style={{ fontSize: 11, opacity: 0.85, fontWeight: 500 }}>
                  {primaryDownload.sub} • Free v1.0.0
                </div>
              </div>
            </a>
            <button
              type="button"
              className={styles.heroDownloadChevron}
              onClick={(e) => {
                e.stopPropagation();
                setHeroDropdownOpen(!heroDropdownOpen);
              }}
              title="Select Platform"
              aria-label="Toggle download options"
            >
              <ChevronDown size={18} />
            </button>

            {heroDropdownOpen && (
              <div className={styles.downloadDropdownMenu}>
                <div className={styles.downloadDropdownHeader}>
                  <span>OFFICIAL DESKTOP BUILDS</span>
                  <span>v1.0.0</span>
                </div>
                <a
                  href="https://github.com/sshivasai/Carole.ai/releases"
                  target="_blank"
                  rel="noreferrer"
                  className={styles.downloadDropdownItem}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{ color: "#38bdf8", display: "flex" }}>
                      <WindowsIcon size={20} />
                    </div>
                    <div>
                      <div className={styles.downloadItemTitle}>Windows 10 / 11</div>
                      <div className={styles.downloadItemSub}>Setup Installer (.exe) • 64-bit</div>
                    </div>
                  </div>
                  <span className={styles.downloadItemBadge}>.exe</span>
                </a>
                <a
                  href="https://github.com/sshivasai/Carole.ai/releases"
                  target="_blank"
                  rel="noreferrer"
                  className={styles.downloadDropdownItem}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{ color: "#f8fafc", display: "flex" }}>
                      <AppleIcon size={20} />
                    </div>
                    <div>
                      <div className={styles.downloadItemTitle}>macOS</div>
                      <div className={styles.downloadItemSub}>Apple Silicon (M1-M4) & Intel (.dmg)</div>
                    </div>
                  </div>
                  <span className={styles.downloadItemBadge}>.dmg</span>
                </a>
                <div className={styles.downloadDropdownDivider} />
                <div
                  onClick={() => {
                    setHeroDropdownOpen(false);
                    copyCliSnippet();
                  }}
                  className={styles.downloadDropdownItem}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{ color: "var(--color-primary)", display: "flex" }}>
                      <Terminal size={18} />
                    </div>
                    <div>
                      <div className={styles.downloadItemTitle}>Python Package (CLI)</div>
                      <div className={styles.downloadItemSub}>pip install carole-ai && carole run</div>
                    </div>
                  </div>
                  <span className={styles.downloadItemBadge}>pip</span>
                </div>
              </div>
            )}
          </div>

          {/* Secondary Web Console Launch */}
          <button
            onClick={onLaunchApp || onSignIn}
            className={styles.heroSecondaryBtn}
          >
            <Sparkles size={17} style={{ color: "var(--color-primary)" }} />
            <span>Launch Web Console</span>
            <ArrowRight size={15} style={{ opacity: 0.7 }} />
          </button>
        </div>

        {/* Quick CLI Copyable Snippet */}
        <div
          className={styles.cliSnippetChip}
          onClick={copyCliSnippet}
          title="Click to copy quickstart command"
        >
          <Terminal size={14} style={{ color: "var(--color-primary)", flexShrink: 0 }} />
          <span>$ pip install carole-ai && carole run</span>
          {copiedCli ? (
            <CheckCircle2 size={14} style={{ color: "#10b981", flexShrink: 0 }} />
          ) : (
            <Copy size={13} style={{ opacity: 0.6, flexShrink: 0 }} />
          )}
        </div>

        {/* Interactive Swarm Team Showcase with Pretty Avatars */}
        <div id="team" style={{ width: "100%" }}>
          <SwarmTeamShowcase />
        </div>

        {/* Live Interactive Team Chat Workflow Animation */}
        <div id="sandbox" style={{ width: "100%", maxWidth: 1200, margin: "48px auto 64px" }}>
          <div style={{ textAlign: "center", marginBottom: 28 }}>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                padding: "4px 14px",
                borderRadius: 9999,
                background: "rgba(16, 185, 129, 0.1)",
                border: "1px solid rgba(16, 185, 129, 0.25)",
                fontSize: 11,
                fontWeight: 700,
                color: "#10b981",
                marginBottom: 12,
                textTransform: "uppercase",
                letterSpacing: 0.5,
              }}
            >
              <Activity size={13} />
              <span>Real-Time Autonomous Execution Simulator</span>
            </div>
            <h2
              style={{
                fontSize: "clamp(26px, 3.8vw, 38px)",
                fontWeight: 800,
                letterSpacing: "-0.03em",
                color: "var(--color-ink-strong, #ffffff)",
                marginBottom: 10,
              }}
            >
              <GravityText text="Watch Your AI Team Execute Live Engineering." gravityStrength={20} radius={140} />
            </h2>
            <p
              style={{
                fontSize: 15,
                color: "var(--color-mute, #94a3b8)",
                maxWidth: 720,
                margin: "0 auto",
                lineHeight: 1.5,
              }}
            >
              You give the team a goal. Watch Archer coordinate coder, research, and QA agents live across Team Chat, Kanban task boards, code diffs, terminal test runs, and security approval gates.
            </p>
          </div>

          <TeamChatAnimation />
        </div>
      </section>

      {/* Stats Bar */}
      <section className={styles.statsSection}>
        <div className={styles.statsGrid}>
          <div className={styles.statItem}>
            <span className={styles.statNumber}>&lt; 15ms</span>
            <span className={styles.statLabel}>Vector Search Latency</span>
          </div>
          <div className={styles.statItem}>
            <span className={styles.statNumber}>90+</span>
            <span className={styles.statLabel}>Built-in Tools & MCP</span>
          </div>
          <div className={styles.statItem}>
            <span className={styles.statNumber}>Guarded</span>
            <span className={styles.statLabel}>Safe Subagent Delegation</span>
          </div>
          <div className={styles.statItem}>
            <span className={styles.statNumber}>100%</span>
            <span className={styles.statLabel}>Local, Private & Open Source</span>
          </div>
        </div>
      </section>

      {/* Universal Supported Models Ecosystem */}
      <section id="models" className={styles.section}>
        <SupportedModelsShowcase />
      </section>

      {/* GraphRAG Interactive Engine Deep Dive */}
      <section id="graphrag" className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={styles.sectionEyebrow}>Semantic Intelligence</div>
          <h2 className={styles.sectionTitle}>
            <GravityText text="Hybrid Code Search. Understand Every Corner of Your Project." gravityStrength={22} radius={140} />
          </h2>
          <p className={styles.sectionDesc}>
            Traditional search misses how files connect. Carole.ai combines fast vector search with code relationship graphs to understand function calls, dependencies, and imports across your entire project.
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
          <div className={styles.sectionEyebrow}>Multi-Agent Architecture</div>
          <h2 className={styles.sectionTitle}>
            <GravityText text="Everything your AI team needs to build real software." gravityStrength={22} radius={140} />
          </h2>
          <p className={styles.sectionDesc}>
            Built from first principles for developers who demand genuine autonomy, safety guardrails, low latency, and zero vendor lock-in.
          </p>
        </div>

        <div className={styles.featuresGrid}>
          {/* 1. Smart Context Management */}
          <MagneticCard tiltMaxAngle={8} liftAmount={10} glowColor="rgba(167, 139, 250, 0.25)" style={{ borderRadius: 16 }}>
            <div className={styles.featureCard} style={{ height: "100%" }}>
              <img
                src="/icons/feature-context.svg"
                alt="Smart Context Management"
                className={styles.featureIconImg}
              />
              <h3 className={styles.featureTitle}>Smart Context Management</h3>
              <p className={styles.featureText}>
                Agents reason through tasks step-by-step. Failed attempts and dead ends are automatically pruned from context, keeping reasoning sharp and preventing token waste.
              </p>
              <span className={styles.featureBadge}>
                <Sparkles size={13} /> Smart Context Pruning
              </span>
            </div>
          </MagneticCard>

          {/* 2. Guarded Subagents */}
          <MagneticCard tiltMaxAngle={8} liftAmount={10} glowColor="rgba(16, 185, 129, 0.25)" style={{ borderRadius: 16 }}>
            <div className={styles.featureCard} style={{ height: "100%" }}>
              <img
                src="/icons/feature-subagents.svg"
                alt="Guarded Subagent Delegation"
                className={styles.featureIconImg}
              />
              <h3 className={styles.featureTitle}>Guarded Subagent Delegation</h3>
              <p className={styles.featureText}>
                Lead agents spawn temporary specialists for focused subtasks. Strict delegation boundaries prevent runaway loops and keep execution fast and predictable.
              </p>
              <span className={styles.featureBadge}>
                <Sparkles size={13} /> Guarded Subagents
              </span>
            </div>
          </MagneticCard>

          {/* 3. Judge AI Security Firewall */}
          <MagneticCard tiltMaxAngle={8} liftAmount={10} glowColor="rgba(251, 191, 36, 0.25)" style={{ borderRadius: 16 }}>
            <div className={styles.featureCard} style={{ height: "100%" }}>
              <img
                src="/icons/feature-security.svg"
                alt="Judge AI Security Firewall"
                className={styles.featureIconImg}
              />
              <h3 className={styles.featureTitle}>Judge AI Security Firewall</h3>
              <p className={styles.featureText}>
                A built-in security evaluator inspects terminal commands, database operations, and file changes before execution, prompting for your approval on critical actions.
              </p>
              <span className={styles.featureBadge}>
                <Sparkles size={13} /> Security Guardrails
              </span>
            </div>
          </MagneticCard>

          {/* 4. Google Account & Workspace Sync */}
          <MagneticCard tiltMaxAngle={8} liftAmount={10} glowColor="rgba(66, 133, 244, 0.25)" style={{ borderRadius: 16 }}>
            <div className={styles.featureCard} style={{ height: "100%" }}>
              <img
                src="/icons/feature-google.svg"
                alt="Google Account & Workspace Connection"
                className={styles.featureIconImg}
              />
              <h3 className={styles.featureTitle}>Google Account & Workspace Sync</h3>
              <p className={styles.featureText}>
                Connect Google OAuth with one click. Agents schedule Calendar events, read/write Google Drive files, extract meeting tasks from Google Meet, and draft emails.
              </p>
              <span className={styles.featureBadge}>
                <Sparkles size={13} /> OAuth2 & Workspace API
              </span>
            </div>
          </MagneticCard>

          {/* 5. Safe File History & Rollback Snapshots */}
          <MagneticCard tiltMaxAngle={8} liftAmount={10} glowColor="rgba(6, 182, 212, 0.25)" style={{ borderRadius: 16 }}>
            <div className={styles.featureCard} style={{ height: "100%" }}>
              <img
                src="/icons/feature-history.svg"
                alt="File History & 1-Click Rollback"
                className={styles.featureIconImg}
              />
              <h3 className={styles.featureTitle}>File History & 1-Click Rollback</h3>
              <p className={styles.featureText}>
                Every edit creates an atomic snapshot backup in <code>.carole_history</code>. Compare unified visual diffs and instantly rollback any accidental changes in one click.
              </p>
              <span className={styles.featureBadge}>
                <Sparkles size={13} /> Version Snapshots & Diffs
              </span>
            </div>
          </MagneticCard>

          {/* 6. Playwright Headless Browser Automation */}
          <MagneticCard tiltMaxAngle={8} liftAmount={10} glowColor="rgba(225, 29, 72, 0.25)" style={{ borderRadius: 16 }}>
            <div className={styles.featureCard} style={{ height: "100%" }}>
              <img
                src="/icons/feature-browser.svg"
                alt="Playwright Headless Browser Automation"
                className={styles.featureIconImg}
              />
              <h3 className={styles.featureTitle}>Playwright Browser Automation</h3>
              <p className={styles.featureText}>
                Dedicated browser worker subagents navigate live web apps, inspect DOM elements, click, fill forms, execute tests, and capture verified screenshot artifacts.
              </p>
              <span className={styles.featureBadge}>
                <Sparkles size={13} /> Headless DOM & Visual QA
              </span>
            </div>
          </MagneticCard>

          {/* 7. Autonomous Kanban Boards */}
          <MagneticCard tiltMaxAngle={8} liftAmount={10} glowColor="rgba(56, 189, 248, 0.25)" style={{ borderRadius: 16 }}>
            <div className={styles.featureCard} style={{ height: "100%" }}>
              <img
                src="/icons/feature-kanban.svg"
                alt="Autonomous Kanban Boards"
                className={styles.featureIconImg}
              />
              <h3 className={styles.featureTitle}>Autonomous Kanban Boards</h3>
              <p className={styles.featureText}>
                Agents autonomously create, estimate, assign, and track engineering tasks on visual Kanban boards with live updates, keeping you in full control of progress.
              </p>
              <span className={styles.featureBadge}>
                <Sparkles size={13} /> Live Task Boards
              </span>
            </div>
          </MagneticCard>

          {/* 8. Universal MCP Support & 90+ Built-in Tools */}
          <MagneticCard tiltMaxAngle={8} liftAmount={10} glowColor="rgba(244, 114, 182, 0.25)" style={{ borderRadius: 16 }}>
            <div className={styles.featureCard} style={{ height: "100%" }}>
              <img
                src="/icons/feature-tools.svg"
                alt="Universal MCP & 90+ Developer Tools"
                className={styles.featureIconImg}
              />
              <h3 className={styles.featureTitle}>Universal MCP & 90+ Developer Tools</h3>
              <p className={styles.featureText}>
                Native support for Model Context Protocol (MCP) over stdio and SSE. Connect PostgreSQL, GitHub, Docker, Slack, and cloud tools directly to your agent workflows.
              </p>
              <span className={styles.featureBadge}>
                <Sparkles size={13} /> Universal MCP Protocol
              </span>
            </div>
          </MagneticCard>

          {/* 9. Plugin & Skills Studio */}
          <MagneticCard tiltMaxAngle={8} liftAmount={10} glowColor="rgba(139, 92, 246, 0.25)" style={{ borderRadius: 16 }}>
            <div className={styles.featureCard} style={{ height: "100%" }}>
              <img
                src="/icons/feature-plugin.svg"
                alt="Plugin Studio & Custom Tools"
                className={styles.featureIconImg}
              />
              <h3 className={styles.featureTitle}>Plugin Studio & Custom Extensibility</h3>
              <p className={styles.featureText}>
                Extend agent capabilities in seconds with Python <code>@carole_tool</code> decorators and hot-reloadable agent skill scripts with automated YAML frontmatter schemas.
              </p>
              <span className={styles.featureBadge}>
                <Sparkles size={13} /> Python Plugins & Custom Skills
              </span>
            </div>
          </MagneticCard>

          {/* 10. Long-Term Memory & Learnings */}
          <MagneticCard tiltMaxAngle={8} liftAmount={10} glowColor="rgba(129, 140, 248, 0.25)" style={{ borderRadius: 16 }}>
            <div className={styles.featureCard} style={{ height: "100%" }}>
              <img
                src="/icons/feature-memory.svg"
                alt="Long-Term Memory & Learnings"
                className={styles.featureIconImg}
              />
              <h3 className={styles.featureTitle}>AutoDream Memory & Learnings</h3>
              <p className={styles.featureText}>
                Agents consolidate memory in the background, learning codebase design patterns, coding conventions, and bug fixes across sessions for personalized engineering.
              </p>
              <span className={styles.featureBadge}>
                <Sparkles size={13} /> Persistent Vector Memory
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
            <GravityText text="100% Open Source. Self-Host, Download, and Own Your Platform." gravityStrength={22} radius={140} />
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
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#ef4444", display: "inline-block" }} />
                  <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#f59e0b", display: "inline-block" }} />
                  <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#10b981", display: "inline-block" }} />
                </div>
                <span style={{ fontSize: 13, fontWeight: 700, fontFamily: "var(--font-family-mono, monospace)", color: "var(--color-ink-strong)" }}>
                  Manual Setup & Installation (FastAPI + Next.js)
                </span>
              </div>

              <button onClick={handleCopy} className={styles.copyBtn} title="Copy setup commands">
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
              <code>{quickstartManualSnippet}</code>
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
          Carole.ai is 100% free and open-source. Download the desktop app for
          Windows & macOS, run locally via CLI, or launch the web console.
        </p>
        <div
          style={{
            display: "flex",
            gap: 16,
            justifyContent: "center",
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <a
            href={primaryDownload.href}
            target="_blank"
            rel="noreferrer"
            className={styles.heroPrimaryBtn}
            title={primaryDownload.label}
          >
            {primaryDownload.icon}
            <span>{primaryDownload.label}</span>
          </a>
          <button
            onClick={onLaunchApp || onSignIn}
            className={styles.heroSecondaryBtn}
          >
            <Sparkles size={17} style={{ color: "var(--color-primary)" }} />
            <span>Launch Web Console</span>
          </button>
          <a
            href="https://github.com/sshivasai/Carole.ai"
            target="_blank"
            rel="noreferrer"
            className={styles.heroSecondaryBtn}
          >
            <GithubIcon size={17} />
            <span>Star on GitHub</span>
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
            <span>All Systems Operational • v1.0.0</span>
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
