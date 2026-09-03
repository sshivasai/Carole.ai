"use client";

import React, { useState, useRef } from "react";
import {
  Sun,
  Moon,
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
  ChevronDown,
  BookOpen,
  MessageSquare,
  Sparkles,
} from "lucide-react";

import styles from "./LandingPage.module.css";
import { useTheme } from "@/hooks/useTheme";
import { motion, AnimatePresence, useScroll, useTransform, useSpring, Variants } from "framer-motion";
import SwarmTeamShowcase from "./SwarmTeamShowcase";
import IntegrationsAnimation from "./IntegrationsAnimation";
import TeamChatAnimation from "./TeamChatAnimation";
import SupportedModelsShowcase from "./SupportedModelsShowcase";
import ConvergingLines from "./ConvergingLines";

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
    stiffness: 90,
    damping: 20,
    restDelta: 0.001,
  });

  const scale = useTransform(smoothProgress, [0, 1], [0.94, 1]);
  const y = useTransform(smoothProgress, [0, 1], [40, 0]);

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

const FAQS = [
  {
    q: "Is Carole.ai really 100% free and open source?",
    a: "Yes. Carole.ai is licensed under Apache 2.0. You can run it locally, inspect all source code, self-host it in air-gapped environments, and modify it without vendor lock-in or subscription fees.",
  },
  {
    q: "How does Carole differ from single-agent IDE extensions?",
    a: "Traditional assistants operate as a single LLM in a single thread. Carole uses an autonomous swarm architecture: Archer plans and coordinates, specialist subagents write atomic patches, QA validates in a headless browser, and Judge AI enforces security gates.",
  },
  {
    q: "Can I run Carole completely offline with local models?",
    a: "Yes. Carole has native integration with Ollama, vLLM, and LM Studio. You can run models like Qwen 2.5 Coder, Llama 3.3, or DeepSeek R1 locally with zero telemetry and zero external data transfer.",
  },
  {
    q: "How does Judge AI protect my codebase?",
    a: "Judge AI acts as a real-time security firewall. Every shell command, git operation, database query, and file deletion is scored for security risk. Any destructive action halts execution until you provide one-click human approval.",
  },
  {
    q: "How do Model Context Protocol (MCP) integrations work?",
    a: "Carole supports the Model Context Protocol (MCP) standard. You can connect 30+ preconfigured tools (GitHub, PostgreSQL, Slack, Linear, Notion, Supabase, Stripe) or attach your own custom stdio/SSE servers with 1-click token authorization.",
  },
];

const TECH_STACK_ITEMS = [
  // Core Runtimes & Frameworks
  { name: "Python", logo: "/logos/python.svg" },
  { name: "Next.js", logo: "/logos/nextjs.svg", invertInDark: true },
  { name: "TypeScript", logo: "/logos/typescript.svg" },
  { name: "React", logo: "/logos/react.svg" },
  { name: "FastAPI", logo: "/logos/fastapi.svg" },

  // Autonomous Browser Agents & Web Automation
  { name: "Browserbase", logo: "/logos/browserbase.svg" },
  { name: "Browser-Use", logo: "/logos/browseruse.svg" },
  { name: "Playwright", logo: "/logos/playwright.svg" },
  { name: "Puppeteer", logo: "/logos/puppeteer.svg" },

  // AI Frontier Models & Inference
  { name: "Anthropic", logo: "/logos/anthropic.svg" },
  { name: "OpenAI", logo: "/logos/openai.svg" },
  { name: "Google Gemini", logo: "/logos/googlegemini.svg" },
  { name: "DeepSeek", logo: "/logos/deepseek.svg" },
  { name: "Groq", logo: "/logos/groq.svg" },
  { name: "Mistral AI", logo: "/logos/mistral.svg" },
  { name: "Ollama", logo: "/logos/ollama.svg" },

  // Storage & Vector Databases
  { name: "LanceDB", logo: "/logos/lancedb.png" },
  { name: "SQLite", logo: "/logos/sqlite.svg" },
  { name: "PostgreSQL", logo: "/logos/postgres.svg" },
  { name: "Redis", logo: "/logos/redis.svg" },
  { name: "Supabase", logo: "/logos/supabase.svg" },
  { name: "MongoDB", logo: "/logos/mongodb.svg" },

  // Code Intelligence & Compilers
  { name: "Tree-sitter", logo: "/logos/treesitter.png" },
  { name: "FlashRank", logo: "/logos/flashrank.png" },
  { name: "Model2Vec", logo: "/logos/model2vec.svg" },

  // Observability & Security
  { name: "OpenLLMetry", logo: "/logos/openllmetry.png" },
  { name: "Sentry", logo: "/logos/sentry.svg" },
  { name: "JWT", logo: "/logos/jwt.svg" },

  // Protocols & Infrastructure
  { name: "MCP Protocol", logo: "/logos/mcp.png" },
  { name: "WebSockets", logo: "/logos/websocket.svg" },
  { name: "Docker", logo: "/logos/docker.svg" },
  { name: "AWS S3", logo: "/logos/aws.svg" },

  // Preconfigured Integrations
  { name: "GitHub", logo: "/logos/github.svg", invertInDark: true },
  { name: "GitLab", logo: "/logos/gitlab.svg" },
  { name: "Linear", logo: "/logos/linear.svg" },
  { name: "Notion", logo: "/logos/notion.svg", invertInDark: true },
  { name: "Slack", logo: "/logos/slack.svg" },
  { name: "Discord", logo: "/logos/discord.svg" },
  { name: "Jira", logo: "/logos/jira.svg" },
  { name: "Figma", logo: "/logos/figma.svg" },
  { name: "Stripe", logo: "/logos/stripe.svg" },
  { name: "HubSpot", logo: "/logos/hubspot.svg" },
  { name: "Airtable", logo: "/logos/airtable.svg" },
  { name: "Brave Search", logo: "/logos/brave-search.svg" },
  { name: "Perplexity AI", logo: "/logos/perplexity.svg", invertInDark: true },
];



export default function LandingPage({
  onLaunchApp,
  onSignIn,
  onSignUp,
}: LandingPageProps) {
  const { theme, toggleTheme } = useTheme();
  const [copiedCli, setCopiedCli] = useState(false);
  const [copiedTerminal, setCopiedTerminal] = useState(false);
  const [selectedGraphQuery, setSelectedGraphQuery] = useState(0);
  const [quickstartTab, setQuickstartTab] = useState<QuickstartTab>("cli");
  const [openFaqIndex, setOpenFaqIndex] = useState<number | null>(null);

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
      query: 'find_symbol_definition("parse_file_ast") — AST definition & call hierarchy',
      astKind: "function",
      astSymbol: "parse_file_ast(content, rel_path)",
      astFile: "backend/core/knowledge/ast_parser.py",
      astLines: "Lines 237–247",
      astSnippet: `def parse_file_ast(content: str, rel_path: str) -> tuple[List[ASTChunk], List[str]]:
    norm_path = rel_path.replace("\\\\", "/").lower()
    ext = posixpath.splitext(norm_path)[1]
    if ext == ".py":
        return parse_python_file(content, rel_path)
    elif ext in (".ts", ".tsx", ".js", ".jsx"):
        return parse_ts_js_file(content, rel_path)
    return parse_polyglot_regex(content, rel_path)`,
      denseVector: "LanceDB HNSW: Vectorized code semantics + Auto-Dream cross-task memory",
      denseScore: "0.984 (Semantic Exact Match)",
      graphPathway:
        "[code_graph.parse_file] ──(invokes)──> [parse_file_ast] ──(dispatches)──> [PythonASTVisitor | parse_ts_js_file] ──(indexes)──> [ASTChunk & CallHierarchy]",
      graphMetrics: [
        { label: "Token Savings", val: "98.4% (Direct AST Slice)" },
        { label: "Lookup Latency", val: "1.2ms (O(1) Symbol Index)" },
        { label: "Call Sites", val: "6 Cross-File Invocations" },
      ],
    },
    {
      query: 'get_file_outline("code_graph.py") — Symbol graph & active editor locks',
      astKind: "class",
      astSymbol: "CodeGraph (Symbol Index & Collision Lock)",
      astFile: "backend/core/knowledge/code_graph.py",
      astLines: "Lines 40–280",
      astSnippet: `class CodeGraph:
    def __init__(self, workspace_root: str = None):
        self.symbol_index: Dict[str, Dict[str, List[ASTChunk]]] = {}
        self.call_hierarchy: Dict[str, Dict[str, List[Dict]]] = {}
        self.active_editors: Dict[str, Dict[str, Set[str]]] = {}
    async def mark_file_active(self, path: str, agent_name: str): ...
    async def get_symbol_definitions(self, symbol_name: str): ...`,
      denseVector: "LanceDB: Multi-agent coordination patterns & AST dependency graphs",
      denseScore: "0.961 (Dependency Graph Match)",
      graphPathway:
        "[ActiveEditorWatcher] ──(monitors)──> [write_file / edit_file] ──(collision_check)──> [JudgeAIFirewall] ──(alerts)──> [TeamChat SSE]",
      graphMetrics: [
        { label: "Indexed Symbols", val: "1,250+ AST Chunks" },
        { label: "Editor Conflict Gate", val: "Zero-Latency Collision Lock" },
        { label: "Graph Engine", val: "NetworkX DAG + In-Memory Index" },
      ],
    },
    {
      query: 'get_symbol_callers("ast_snip_dead_ends") — Context compaction & pruning',
      astKind: "function",
      astSymbol: "ast_snip_dead_ends(messages)",
      astFile: "backend/core/agent/context_ast.py",
      astLines: "Lines 112–158",
      astSnippet: `def ast_snip_dead_ends(messages: List[Dict]) -> tuple[List[Dict], int]:
    ast = parse_to_context_ast(messages)
    snipped = 0
    for node in ast:
        if node.is_failed_tool_dead_end():
            node.prune()
            snipped += 1
    return reconstruct_messages(ast), snipped`,
      denseVector: "LanceDB: Token compaction checkpoints & working state memory flush",
      denseScore: "0.976 (Context Optimization Match)",
      graphPathway:
        "[ReACTAgent.run_loop] ──(evaluates)──> [_micro_compact] ──(prunes)──> [ast_snip_dead_ends] ──(flushes)──> [LanceDB & SQLite CompactionEvent]",
      graphMetrics: [
        { label: "Context Window Guard", val: "Sliding Window (80% Trigger)" },
        { label: "Dead-End Pruning", val: "AST Observation Snipping" },
        { label: "Checkpoint Durability", val: "Survives Server Restarts" },
      ],
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
    setCopiedTerminal(true);
    setTimeout(() => setCopiedTerminal(false), 2000);
  };

  const fadeInUp: Variants = {
    hidden: { opacity: 0, y: 24 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.16, 1, 0.3, 1] as const } },
  };

  const staggerContainer: Variants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: { staggerChildren: 0.1, delayChildren: 0.05 },
    },
  };

  return (
    <div className={styles.landingRoot}>
      {/* Travelling Diagonal Lines Converging Towards Pointer & Ambient Background */}
      <div className={styles.bgContainer}>
        <ConvergingLines lineCount={44} />
        <div className={styles.bgHeroGlow} />
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
              alt="Carole.ai"
              className={styles.navBrandWordmark}
            />
          </div>

          <nav className={styles.navLinks}>
            <span
              onClick={() => scrollToSection("integrations")}
              className={styles.navLink}
            >
              MCP Tools
            </span>
            <span
              onClick={() => scrollToSection("architecture")}
              className={styles.navLink}
            >
              Architecture
            </span>
            <span
              onClick={() => scrollToSection("models")}
              className={styles.navLink}
            >
              Models
            </span>
            <span
              onClick={() => scrollToSection("opensource")}
              className={styles.navLink}
            >
              Open Source
            </span>
            <span
              onClick={() => scrollToSection("faq")}
              className={styles.navLink}
            >
              FAQ
            </span>
          </nav>

          <div className={styles.navActions}>
            {/* Theme Toggle Button */}
            <button
              onClick={toggleTheme}
              className={styles.themeBtn}
              title={theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode"}
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
              <span>GitHub</span>
            </a>

            {/* Sign In */}
            <button
              onClick={onSignIn || onLaunchApp}
              className={styles.signInBtn}
            >
              Sign In
            </button>

            {/* Launch Console */}
            <button
              onClick={onLaunchApp || onSignIn}
              className={styles.navLaunchBtn}
            >
              <span>Launch Console</span>
              <ArrowRight size={13} />
            </button>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <motion.section
        className={styles.heroSection}
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
      >
        <div className={styles.containerNarrow}>
          <motion.div variants={fadeInUp} className={styles.heroMark}>
            <img
              src="/branding/logo-mark-animated.webp"
              alt="Carole.ai"
              className={styles.heroMarkImg}
            />
          </motion.div>

          <motion.div variants={fadeInUp} className={styles.heroEyebrow}>
            AUTONOMOUS AI ENGINEERING SWARM
          </motion.div>

          <motion.h1 variants={fadeInUp} className={styles.heroHeadline}>
            The Open Source<br />
            <span className={styles.heroAccent}>AI Engineering Swarm.</span>
          </motion.h1>

          <motion.p variants={fadeInUp} className={styles.heroSubtitle}>
            Deploy autonomous AI engineering teams that plan, code, test in the browser, and ship software directly in your workspace.
          </motion.p>

          <motion.div variants={fadeInUp} className={styles.heroCtas}>
            <button
              onClick={onLaunchApp || onSignIn}
              className={styles.btnPrimary}
            >
              <span>Launch Web Console</span>
              <ArrowRight size={14} />
            </button>

            <a
              href="https://github.com/sshivasai/Carole.ai"
              target="_blank"
              rel="noreferrer"
              className={styles.btnSecondary}
            >
              <GithubIcon size={15} />
              <span>Contribute on GitHub</span>
            </a>
          </motion.div>

          {/* Quickstart CLI Box */}
          <motion.div
            variants={fadeInUp}
            onClick={copyCliSnippet}
            className={styles.cliBar}
            title="Click to copy"
          >
            <span className={styles.cliPrompt}>$</span>
            <span>pip install carole-ai &amp;&amp; carole run</span>
            <span
              className={`${styles.cliCopyBtn} ${copiedCli ? styles.cliCopyBtnCopied : ""
                }`}
            >
              {copiedCli ? (
                <>
                  <Check size={11} />
                  <span>Copied</span>
                </>
              ) : (
                <>
                  <Copy size={11} />
                  <span>Copy</span>
                </>
              )}
            </span>
          </motion.div>

          <motion.div variants={fadeInUp} className={styles.heroTrustText}>
            Apache 2.0 Licensed · Multi-Agent Swarm · 100% Local &amp; Private
          </motion.div>
        </div>
      </motion.section>

      {/* Section 1: Interactive Swarm Team Showcase */}
      <section id="team" className={styles.section} style={{ paddingTop: 40, paddingBottom: 40 }}>
        <ScrollExpandWrapper>
          <SwarmTeamShowcase />
        </ScrollExpandWrapper>
      </section>

      {/* Section 2: Live Synced Team Execution Simulator (Split Layout) */}
      <section id="simulator" className={`${styles.section} ${styles.sectionAlt}`}>
        <ScrollExpandWrapper>
          <div className={styles.container}>
            <div className={styles.simulatorSplitSection}>
              <div className={styles.simulatorLeftCol}>
                <h2 className={styles.sectionTitle} style={{ textAlign: "left" }}>
                  Tag an @agent...<br />
                  <span className={styles.heroAccent}>Watch the swarm execute.</span>
                </h2>
                <p className={styles.sectionDesc} style={{ textAlign: "left", marginBottom: 24, maxWidth: "100%" }}>
                  Send an engineering goal in the team chat. Watch the lead orchestrator decompose tasks, dispatch specialist subagents, and push verified code in real-time.
                </p>


              </div>

              <div className={styles.simulatorRightCol}>
                <TeamChatAnimation />
              </div>
            </div>
          </div>
        </ScrollExpandWrapper>
      </section>

      {/* Section 3: 30+ 1-Click MCP Integrations Spotlight */}
      <section id="integrations" className={styles.section}>
        <ScrollExpandWrapper>
          <div className={styles.container}>
            <div className={styles.integrationsSection}>
              <div>
                <div className={styles.eyebrow}>Model Context Protocol</div>
                <h2 className={styles.sectionTitle}>
                  30+ 1-Click<br />
                  <span className={styles.heroAccent}>MCP Integrations.</span>
                </h2>
                <p className={styles.sectionDesc}>
                  Connect directly to PostgreSQL, GitHub, Linear, Slack, Supabase, Redis, Notion, Stripe, and Docker. Dynamic stdio/SSE registration gives agents real-time tool access with token-level security firewalls.
                </p>

                <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                  <a
                    href="https://github.com/sshivasai/Carole.ai#mcp-servers"
                    target="_blank"
                    rel="noreferrer"
                    className={styles.btnSecondary}
                  >
                    <span>Browse MCP Marketplace</span>
                    <ExternalLink size={13} />
                  </a>
                </div>
              </div>

              <div className={styles.integrationsVisualBox}>
                <div style={{ width: "100%", transform: "scale(0.88)" }}>
                  <IntegrationsAnimation />
                </div>
              </div>
            </div>
          </div>
        </ScrollExpandWrapper>
      </section>

      {/* Section 4: Universal Supported Models Ecosystem */}
      <section id="models" className={`${styles.section} ${styles.sectionAlt}`}>
        <ScrollExpandWrapper>
          <SupportedModelsShowcase />
        </ScrollExpandWrapper>
      </section>

      {/* Section 5: GraphRAG Interactive Code Search Explorer */}
      <section id="graphrag" className={styles.section}>
        <ScrollExpandWrapper>
          <div className={styles.container}>
            <div style={{ maxWidth: 680, marginBottom: 32 }}>
              <div className={styles.eyebrow}>GraphRAG Intelligence</div>
              <h2 className={styles.sectionTitle}>
                GraphRAG Code Search.<br />
                <span className={styles.heroAccent}>Dense Vectors + Code Ontologies.</span>
              </h2>
              <p className={styles.sectionDesc} style={{ margin: 0 }}>
                LanceDB vector search combined with code relationship graphs to trace function calls, imports, and AST paths across multi-repo codebases.
              </p>
            </div>

            <div className={styles.graphragContainer}>
              <div className={styles.graphQueryBar}>
                <Search size={15} style={{ color: "var(--color-primary-soft, #818cf8)" }} />
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
                      className={`${styles.graphQueryBtn} ${selectedGraphQuery === idx ? styles.graphQueryBtnActive : ""
                        }`}
                    >
                      Query #{idx + 1}
                    </button>
                  ))}
                </div>
              </div>

              <div className={styles.graphDualGrid}>
                {/* Left Pane: AST Symbol Definition & Slicing */}
                <div className={styles.graphPane}>
                  <div className={styles.graphPaneHeader}>
                    <div className={styles.graphPaneTitle}>
                      <Code2 size={15} style={{ color: "var(--color-primary-soft, #818cf8)" }} />
                      <span>AST Semantic Chunk</span>
                    </div>
                    <span className={styles.graphTag}>
                      {graphQueries[selectedGraphQuery].astKind} • {graphQueries[selectedGraphQuery].astLines}
                    </span>
                  </div>
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={selectedGraphQuery}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -4 }}
                      transition={{ duration: 0.16 }}
                      className={styles.graphResultItem}
                    >
                      <div className={styles.graphSymbolName}>
                        {graphQueries[selectedGraphQuery].astSymbol}
                      </div>
                      <div className={styles.graphFilePath}>
                        📁 {graphQueries[selectedGraphQuery].astFile}
                      </div>
                      <pre className={styles.graphCodeSnippet}>
                        <code>{graphQueries[selectedGraphQuery].astSnippet}</code>
                      </pre>
                    </motion.div>
                  </AnimatePresence>
                </div>

                {/* Right Pane: GraphRAG Multi-Hop & Semantic Vector */}
                <div className={styles.graphPane}>
                  <div className={styles.graphPaneHeader}>
                    <div className={styles.graphPaneTitle}>
                      <Network size={15} style={{ color: "var(--color-primary-soft, #818cf8)" }} />
                      <span>Dense Vector + Code Ontology</span>
                    </div>
                    <span className={styles.graphTag}>LanceDB + NetworkX</span>
                  </div>
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={selectedGraphQuery}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -4 }}
                      transition={{ duration: 0.16 }}
                      className={styles.graphResultItem}
                    >
                      <div className={styles.graphSectionSubhead}>
                        Semantic Vector Memory
                      </div>
                      <div className={styles.graphDenseScore}>
                        {graphQueries[selectedGraphQuery].denseScore}
                      </div>
                      <div className={styles.graphDenseVector}>
                        {graphQueries[selectedGraphQuery].denseVector}
                      </div>

                      <div className={styles.graphSectionSubhead} style={{ marginTop: 10 }}>
                        Multi-Hop Call &amp; Dependency Pathway
                      </div>
                      <div className={styles.graphPathwayBox}>
                        {graphQueries[selectedGraphQuery].graphPathway}
                      </div>

                      <div className={styles.graphMetricsRow}>
                        {graphQueries[selectedGraphQuery].graphMetrics.map((m, mIdx) => (
                          <div key={mIdx} className={styles.graphMetricChip}>
                            <span className={styles.graphMetricLabel}>{m.label}</span>
                            <span className={styles.graphMetricVal}>{m.val}</span>
                          </div>
                        ))}
                      </div>
                    </motion.div>
                  </AnimatePresence>
                </div>
              </div>
            </div>
          </div>
        </ScrollExpandWrapper>
      </section>

      {/* Section 6: System Architecture Bento Grid */}
      <section id="architecture" className={`${styles.section} ${styles.sectionAlt}`}>
        <ScrollExpandWrapper>
          <div className={styles.container}>
            <div style={{ maxWidth: 680, marginBottom: 36 }}>
              <div className={styles.eyebrow}>System Architecture</div>
              <h2 className={styles.sectionTitle}>
                Deterministic execution.<br />
                <span className={styles.heroAccent}>Zero context bloat.</span>
              </h2>
              <p className={styles.sectionDesc} style={{ margin: 0 }}>
                Engineered for robust multi-agent orchestration, rollback safety, and low latency.
              </p>
            </div>

            <div className={styles.bentoGrid}>
              {/* Bento 1: AST Context Pruning */}
              <div className={`${styles.bentoCellSpan7} ${styles.bentoCard}`}>
                <div>
                  <div className={styles.bentoCardHeader}>
                    <div className={styles.bentoIconWrapper}>
                      <Code2 size={18} />
                    </div>
                    <div>
                      <h3 className={styles.bentoTitle}>Smart Context AST Management</h3>
                      <span className={styles.bentoBadge}>AST Dead-End Pruning</span>
                    </div>
                  </div>
                  <p className={styles.bentoText}>
                    Agents decompose reasoning into structured AST nodes. Dead-end tool attempts are safely pruned from history, preventing context bloat and token waste.
                  </p>
                </div>
                <div className={styles.bentoVisual}>
                  <div style={{ color: "var(--color-primary-soft, #818cf8)", marginBottom: 4 }}>// AST History Optimizer</div>
                  <div>- pruned_nodes: 3 dead-end tool loops (saved 1,840 tokens)</div>
                  <div style={{ color: "var(--color-ink-strong, #ffffff)" }}>+ active_context: 4,120 / 128,000 tokens (optimal reasoning window)</div>
                </div>
              </div>

              {/* Bento 2: Guarded Subagents */}
              <div className={`${styles.bentoCellSpan5} ${styles.bentoCard}`}>
                <div>
                  <div className={styles.bentoCardHeader}>
                    <div className={styles.bentoIconWrapper}>
                      <Layers size={18} />
                    </div>
                    <div>
                      <h3 className={styles.bentoTitle}>Guarded Subagents</h3>
                      <span className={styles.bentoBadge}>Depth-1 Guard</span>
                    </div>
                  </div>
                  <p className={styles.bentoText}>
                    Lead orchestrators spawn temporary specialists for isolated tasks with strict concurrency boundaries to prevent recursion loops.
                  </p>
                </div>
                <div className={styles.bentoVisual}>
                  <div style={{ color: "var(--color-primary-soft, #818cf8)" }}>{"[Archer Lead] -> [Sub-PythonDev (Depth 1)]"}</div>
                  <div style={{ color: "var(--color-mute)", marginTop: 4 }}>Status: Isolated sandbox • Subagent recursion blocked</div>
                </div>
              </div>

              {/* Bento 3: Judge AI Security */}
              <div className={`${styles.bentoCellSpan5} ${styles.bentoCard}`}>
                <div>
                  <div className={styles.bentoCardHeader}>
                    <div className={styles.bentoIconWrapper}>
                      <ShieldCheck size={18} />
                    </div>
                    <div>
                      <h3 className={styles.bentoTitle}>Judge AI Security Gate</h3>
                      <span className={styles.bentoBadge}>Human Approval Gate</span>
                    </div>
                  </div>
                  <p className={styles.bentoText}>
                    Real-time security evaluator intercepts shell commands, database queries, and file deletions, requiring one-click confirmation for critical actions.
                  </p>
                </div>
                <div className={styles.bentoVisual}>
                  <div style={{ color: "var(--color-primary-soft, #818cf8)" }}>&gt;_ Intercepted: git push origin main</div>
                  <div style={{ color: "#e2e8f0" }}>Policy Rule: Production branch modification requires human sign-off</div>
                </div>
              </div>

              {/* Bento 4: Visual Browser QA */}
              <div className={`${styles.bentoCellSpan7} ${styles.bentoCard}`}>
                <div>
                  <div className={styles.bentoCardHeader}>
                    <div className={styles.bentoIconWrapper}>
                      <Laptop size={18} />
                    </div>
                    <div>
                      <h3 className={styles.bentoTitle}>Visual Browser Automation</h3>
                      <span className={styles.bentoBadge}>Playwright + Chromium Engine</span>
                    </div>
                  </div>
                  <p className={styles.bentoText}>
                    Browser subagents autonomously navigate live web apps, inspect DOM trees, verify frontend regressions, and request interactive Human-in-the-Loop takeovers for CAPTCHA solving.
                  </p>
                </div>
                <div className={styles.bentoVisual}>
                  <div style={{ color: "var(--color-primary-soft, #818cf8)" }}>&gt; browser_navigate(url=&apos;http://localhost:3000/dashboard&apos;)</div>
                  <div style={{ color: "var(--color-mute)" }}>DOM element #submit-btn clicked • 14 E2E assertion checks passed • Verified screenshot attached</div>
                </div>
              </div>

              {/* Bento 5: AutoDream Memory */}
              <div className={`${styles.bentoCellSpan12} ${styles.bentoCard}`}>
                <div>
                  <div className={styles.bentoCardHeader}>
                    <div className={styles.bentoIconWrapper}>
                      <Brain size={18} />
                    </div>
                    <div>
                      <h3 className={styles.bentoTitle}>AutoDream Codebase Memory</h3>
                      <span className={styles.bentoBadge}>LanceDB + pgvector</span>
                    </div>
                  </div>
                  <p className={styles.bentoText}>
                    Agents consolidate architectural learnings in the background, remembering design patterns, conventions, and bug fixes across engineering sessions.
                  </p>
                </div>
                <div className={styles.bentoVisual} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
                  <div>
                    <div style={{ color: "var(--color-primary-soft, #818cf8)" }}>Memory Consolidation Status: 48 codebase insights indexed</div>
                    <div style={{ color: "var(--color-mute)" }}>Patterns remembered: Fastify auth routing, AST parser optimizations, Redis session locks</div>
                  </div>
                  <span className={styles.bentoBadge} style={{ color: "var(--color-primary-soft, #818cf8)", background: "rgba(99, 102, 241, 0.1)", padding: "2px 8px", borderRadius: 4 }}>
                    Synchronized
                  </span>
                </div>
              </div>
            </div>
          </div>
        </ScrollExpandWrapper>
      </section>

      {/* Section 7: 100% Free & Open Source Hub */}
      <section id="opensource" className={styles.section}>
        <ScrollExpandWrapper>
          <div className={styles.container}>
            <div style={{ maxWidth: 680, marginBottom: 36 }}>
              <div className={styles.eyebrow}>100% Free &amp; Open Source</div>
              <h2 className={styles.sectionTitle}>
                Apache 2.0 Licensed.<br />
                <span className={styles.heroAccent}>No vendor lock-in.</span>
              </h2>
              <p className={styles.sectionDesc} style={{ margin: 0 }}>
                Run with local models or bring your own API keys. All source code is open, auditable, and self-hostable.
              </p>
            </div>

            {/* Quickstart & Contributor Terminal */}
            <div className={styles.terminalCard}>
              <div className={styles.terminalTop}>
                <div className={styles.terminalTabs}>
                  <button
                    onClick={() => setQuickstartTab("cli")}
                    className={`${styles.terminalTabBtn} ${quickstartTab === "cli" ? styles.terminalTabBtnActive : ""
                      }`}
                  >
                    Quickstart CLI (pip)
                  </button>
                  <button
                    onClick={() => setQuickstartTab("source")}
                    className={`${styles.terminalTabBtn} ${quickstartTab === "source" ? styles.terminalTabBtnActive : ""
                      }`}
                  >
                    Developer &amp; Contributor Setup
                  </button>
                </div>

                <button
                  onClick={handleCopyQuickstart}
                  className={styles.cliCopyBtn}
                  title="Copy setup commands"
                >
                  {copiedTerminal ? (
                    <>
                      <Check size={12} style={{ color: "#10b981" }} />
                      <span style={{ color: "#10b981" }}>Copied!</span>
                    </>
                  ) : (
                    <>
                      <Copy size={12} />
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
                  transition={{ duration: 0.16 }}
                  className={styles.terminalBody}
                >
                  <code>{quickstartSnippets[quickstartTab]}</code>
                </motion.pre>
              </AnimatePresence>
            </div>
          </div>
        </ScrollExpandWrapper>
      </section>

      {/* Section 8: FAQ & Community */}
      <section id="faq" className={`${styles.section} ${styles.sectionAlt}`}>
        <ScrollExpandWrapper>
          <div className={styles.container}>
            <div className={styles.communityGrid}>
              {/* FAQ Accordion */}
              <div>
                <div className={styles.eyebrow}>FAQ</div>
                <h2 className={styles.sectionTitle}>Common questions</h2>
                <div style={{ marginBottom: 24 }} />

                <div className={styles.faqList}>
                  {FAQS.map((faq, idx) => {
                    const isOpen = openFaqIndex === idx;
                    return (
                      <div key={idx} className={styles.faqItem}>
                        <button
                          onClick={() => setOpenFaqIndex(isOpen ? null : idx)}
                          className={styles.faqQuestion}
                        >
                          <span>{faq.q}</span>
                          <ChevronDown
                            size={18}
                            className={`${styles.faqChevron} ${isOpen ? styles.faqChevronOpen : ""
                              }`}
                          />
                        </button>
                        {isOpen && (
                          <div className={styles.faqAnswer}>{faq.a}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Community Cards */}
              <div>
                <div className={styles.eyebrow}>Community</div>
                <h2 className={styles.sectionTitle}>Come build with us.</h2>
                <p className={styles.sectionDesc} style={{ marginBottom: 24 }}>
                  Every PR matters. Every issue filed improves the platform.
                </p>

                <a
                  href="https://github.com/sshivasai/Carole.ai"
                  target="_blank"
                  rel="noreferrer"
                  className={styles.communityCard}
                >
                  <div className={styles.communityCardIcon}>
                    <GithubIcon size={20} />
                  </div>
                  <div>
                    <h4 className={styles.communityCardTitle}>GitHub Repository</h4>
                    <p className={styles.communityCardDesc}>
                      Source code, issues, pull requests, and roadmap.
                    </p>
                  </div>
                  <ExternalLink size={15} className={styles.communityArrow} />
                </a>

                <a
                  href="https://github.com/sshivasai/Carole.ai/discussions"
                  target="_blank"
                  rel="noreferrer"
                  className={styles.communityCard}
                >
                  <div className={styles.communityCardIcon}>
                    <MessageSquare size={20} />
                  </div>
                  <div>
                    <h4 className={styles.communityCardTitle}>Discussions &amp; Ideas</h4>
                    <p className={styles.communityCardDesc}>
                      Share agent workflows, custom tools, and ideas.
                    </p>
                  </div>
                  <ExternalLink size={15} className={styles.communityArrow} />
                </a>

                <a
                  href="https://github.com/sshivasai/Carole.ai#readme"
                  target="_blank"
                  rel="noreferrer"
                  className={styles.communityCard}
                >
                  <div className={styles.communityCardIcon}>
                    <BookOpen size={20} />
                  </div>
                  <div>
                    <h4 className={styles.communityCardTitle}>Documentation</h4>
                    <p className={styles.communityCardDesc}>
                      Architecture docs, setup guides, and MCP API references.
                    </p>
                  </div>
                  <ExternalLink size={15} className={styles.communityArrow} />
                </a>
              </div>
            </div>
          </div>
        </ScrollExpandWrapper>
      </section>

      {/* Closing CTA Banner */}
      <section className={styles.ctaBanner}>
        <ScrollExpandWrapper>
          <div className={styles.containerNarrow}>
            <h2 className={styles.ctaTitle}>
              Start your engineering team in minutes.
            </h2>
            <p className={styles.ctaDesc}>
              100% free and open source under Apache 2.0. Run with local models or bring your own API keys.
            </p>

            <div style={{ display: "flex", justifyContent: "center", gap: 12, flexWrap: "wrap", marginBottom: 24 }}>
              <button
                onClick={onLaunchApp || onSignIn}
                className={styles.btnPrimary}
              >
                <span>Launch Web Console</span>
                <ArrowRight size={14} />
              </button>

              <a
                href="https://github.com/sshivasai/Carole.ai"
                target="_blank"
                rel="noreferrer"
                className={styles.btnSecondary}
              >
                <GithubIcon size={15} />
                <span>Star on GitHub</span>
              </a>
            </div>

            <div
              onClick={copyCliSnippet}
              className={styles.cliBar}
              style={{ margin: "0 auto" }}
              title="Click to copy"
            >
              <span className={styles.cliPrompt}>$</span>
              <span>pip install carole-ai &amp;&amp; carole run</span>
              <span
                className={`${styles.cliCopyBtn} ${copiedCli ? styles.cliCopyBtnCopied : ""
                  }`}
              >
                {copiedCli ? "Copied" : "Copy"}
              </span>
            </div>
          </div>
        </ScrollExpandWrapper>
      </section>

      {/* Built With Tech Stack Marquee */}
      <section className={styles.builtWithSection}>
        <div className={styles.builtWithHeader}>
          <div className={styles.builtWithBadge}>
            Built with Modern Open Source &amp; AI Infrastructure
          </div>
        </div>

        <div className={styles.marqueeContainer}>
          <div className={styles.marqueeTrack}>
            {[...TECH_STACK_ITEMS, ...TECH_STACK_ITEMS].map((tech, idx) => (
              <div key={`${tech.name}-${idx}`} className={styles.techPill}>
                <div className={styles.techLogoWrapper}>
                  <img
                    src={tech.logo}
                    alt={tech.name}
                    className={`${styles.techLogo} ${tech.invertInDark ? styles.invertInDark : ""
                      }`}
                    loading="lazy"
                  />
                </div>
                <span className={styles.techName}>{tech.name}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Minimalist High-Craft Footer */}
      <footer className={styles.footer}>
        <div className={styles.container}>
          <div className={styles.footerInner}>
            <div className={styles.footerTop}>
              <div className={styles.footerBrand}>
                <div className={styles.footerLogoRow}>
                  <img
                    src="/branding/logo-mark-animated.webp"
                    alt="Carole.ai"
                    width={22}
                    height={22}
                    style={{ objectFit: "contain" }}
                  />
                  <span style={{ fontWeight: 700, fontSize: 15 }}>Carole.ai</span>
                </div>
                <p className={styles.footerDesc}>
                  Autonomous AI engineering swarms. 100% free and open source under Apache 2.0.
                </p>
              </div>

              <ul className={styles.footerNav}>
                <li>
                  <span
                    onClick={() => scrollToSection("team")}
                    className={styles.footerNavLink}
                    style={{ cursor: "pointer" }}
                  >
                    Swarm Team
                  </span>
                </li>
                <li>
                  <span
                    onClick={() => scrollToSection("simulator")}
                    className={styles.footerNavLink}
                    style={{ cursor: "pointer" }}
                  >
                    Simulator
                  </span>
                </li>
                <li>
                  <span
                    onClick={() => scrollToSection("integrations")}
                    className={styles.footerNavLink}
                    style={{ cursor: "pointer" }}
                  >
                    MCP Tools
                  </span>
                </li>
                <li>
                  <span
                    onClick={() => scrollToSection("models")}
                    className={styles.footerNavLink}
                    style={{ cursor: "pointer" }}
                  >
                    Models
                  </span>
                </li>
                <li>
                  <span
                    onClick={() => scrollToSection("graphrag")}
                    className={styles.footerNavLink}
                    style={{ cursor: "pointer" }}
                  >
                    GraphRAG
                  </span>
                </li>
                <li>
                  <span
                    onClick={() => scrollToSection("faq")}
                    className={styles.footerNavLink}
                    style={{ cursor: "pointer" }}
                  >
                    FAQ
                  </span>
                </li>
                <li>
                  <a
                    href="https://github.com/sshivasai/Carole.ai"
                    target="_blank"
                    rel="noreferrer"
                    className={styles.footerNavLink}
                  >
                    GitHub
                  </a>
                </li>
              </ul>
            </div>

            <div className={styles.footerBottom}>
              <span className={styles.footerCopyright}>
                Apache 2.0 Licensed · © {new Date().getFullYear()} Carole.ai
              </span>

              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <button
                  onClick={toggleTheme}
                  className={styles.themeBtn}
                  title="Toggle Theme"
                  aria-label="Toggle Theme"
                >
                  {theme === "dark" ? (
                    <Sun size={13} style={{ color: "#fbbf24" }} />
                  ) : (
                    <Moon size={13} style={{ color: "#6366f1" }} />
                  )}
                </button>
                <span style={{ fontSize: 12, color: "var(--color-mute, #71717a)" }}>
                  v1.0.0
                </span>
              </div>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
