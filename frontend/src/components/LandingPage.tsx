import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleStop,
  Copy,
  FileCode2,
  Folder,
  GitBranch,
  Globe,
  LockKeyhole,
  Moon,
  Network,
  Play,
  ShieldCheck,
  Sparkles,
  Sun,
  Terminal,
  Users,
  Wrench,
} from "lucide-react";
import styles from "./LandingPage.module.css";
import IntegrationsAnimation from "./IntegrationsAnimation";
import { useTheme } from "@/hooks/useTheme";

function GitHubMark({ size = 17 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 .7a11.5 11.5 0 0 0-3.64 22.4c.58.1.79-.25.79-.56v-2.24c-3.23.7-3.91-1.37-3.91-1.37-.53-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.7.08-.7 1.17.08 1.78 1.2 1.78 1.2 1.04 1.77 2.72 1.26 3.38.96.1-.75.4-1.26.74-1.55-2.58-.29-5.29-1.29-5.29-5.69 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.47.11-3.05 0 0 .97-.31 3.16 1.18a10.9 10.9 0 0 1 5.76 0c2.2-1.49 3.16-1.18 3.16-1.18.63 1.58.23 2.76.11 3.05.74.81 1.19 1.83 1.19 3.09 0 4.41-2.72 5.39-5.3 5.68.42.36.79 1.07.79 2.16v3.2c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .7Z" />
    </svg>
  );
}

type LandingPageProps = {
  onLaunchApp?: () => void;
  onSignIn?: () => void;
  onSignUp?: () => void;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
  hosted?: boolean;
};

type DemoTab = "activity" | "approval" | "changes" | "terminal" | "browser";

const demoTabs: { id: DemoTab; label: string; icon: typeof Terminal; count?: string }[] = [
  { id: "activity", label: "Work", icon: Wrench, count: "4" },
  { id: "approval", label: "Approval", icon: ShieldCheck, count: "1" },
  { id: "changes", label: "Files", icon: Folder, count: "6" },
  { id: "terminal", label: "Terminal", icon: Terminal },
  { id: "browser", label: "Browser", icon: Globe },
];

const agents = [
  { initials: "AR", name: "Architect", task: "Mapping the dependency graph", color: "violet" },
  { initials: "BE", name: "Backend", task: "Implementing the API route", color: "blue" },
  { initials: "FE", name: "Frontend", task: "Updating the workspace view", color: "amber" },
  { initials: "QA", name: "Reviewer", task: "Waiting for implementation", color: "green" },
];

const infrastructure = [
  { name: "Python", logo: "/logos/python.svg", group: "Runtime" },
  { name: "Next.js", logo: "/logos/nextjs.svg", group: "Interface", invert: true },
  { name: "TypeScript", logo: "/logos/typescript.svg", group: "Interface" },
  { name: "FastAPI", logo: "/logos/fastapi.svg", group: "Runtime" },
  { name: "PostgreSQL", logo: "/logos/postgres.svg", group: "Data" },
  { name: "LanceDB", logo: "/logos/lancedb.png", group: "Memory" },
  { name: "Tree-sitter", logo: "/logos/treesitter.png", group: "Code intelligence" },
  { name: "Docker", logo: "/logos/docker.svg", group: "Infrastructure" },
  { name: "OpenLLMetry", logo: "/logos/openllmetry.png", group: "Observability" },
  { name: "Sentry", logo: "/logos/sentry.svg", group: "Observability" },
  { name: "MCP", logo: "/logos/mcp.png", group: "Protocol" },
  { name: "WebSockets", logo: "/logos/websocket.svg", group: "Realtime" },
];

const modelProviders = [
  { name: "Anthropic", logo: "/logos/anthropic.svg" },
  { name: "OpenAI", logo: "/logos/openai.svg" },
  { name: "Google Gemini", logo: "/logos/googlegemini.svg" },
  { name: "Local Ollama", logo: "/logos/ollama.svg", invert: true },
  { name: "OpenRouter", logo: "/logos/openrouter.svg" },
  { name: "NVIDIA NIM", logo: "/logos/nvidia.svg" },
];

const workflow = [
  {
    number: "01",
    title: "Describe the outcome",
    body: "Give Carole the goal, constraints, and the repository. It turns the request into a shared plan before work begins.",
  },
  {
    number: "02",
    title: "Watch the team work",
    body: "Specialist agents coordinate in parallel while every thought, tool call, handoff, and background task stays visible.",
  },
  {
    number: "03",
    title: "Review every decision",
    body: "Approve sensitive actions, inspect exact file changes, and step in wherever judgment matters.",
  },
];

const faqs = [
  {
    q: "What makes Carole different from a single coding agent?",
    a: "Carole coordinates a team of role-based agents around one shared objective. You can follow each agent, inspect their work, and review the combined result from one workspace.",
  },
  {
    q: "Can I keep models and code local?",
    a: "Yes. Carole is designed for local-first workflows and supports local model providers alongside cloud models, so you can choose where your code and inference run.",
  },
  {
    q: "How are risky actions handled?",
    a: "Actions that need your judgment appear as clear approval requests with the command, reason, and affected scope before the agent proceeds.",
  },
  {
    q: "Can I inspect the source?",
    a: "The source is public on GitHub, so you can inspect the project and run it locally. Check the repository for its current reuse terms.",
  },
];

function ProductPreview() {
  const [activeTab, setActiveTab] = useState<DemoTab>("activity");
  const [isPaused, setIsPaused] = useState(false);

  useEffect(() => {
    if (isPaused) return;
    const timer = window.setInterval(() => {
      setActiveTab((current) => demoTabs[(demoTabs.findIndex((tab) => tab.id === current) + 1) % demoTabs.length].id);
    }, 3400);
    return () => window.clearInterval(timer);
  }, [isPaused]);

  const selectDemo = (tab: DemoTab) => {
    setActiveTab(tab);
    setIsPaused(true);
    window.setTimeout(() => setIsPaused(false), 9000);
  };

  return (
    <div className={styles.productPreview}>
      <div className={styles.windowBar}>
        <div className={styles.windowDots}><span /><span /><span /></div>
        <div className={styles.windowTitle}>carole / checkout-redesign</div>
        <div className={styles.liveBadge}><span /> Team active</div>
      </div>

      <div className={styles.workspaceShell}>
        <aside className={styles.agentRail} aria-label="Workspace navigation">
          <img className={styles.previewBrand} src="/branding/logo-mark-animated.webp" alt="" />
          <button className={activeTab === "activity" ? styles.activeRailTool : ""} onClick={() => selectDemo("activity")} aria-label="Team activity"><Users size={15} /></button>
          <button className={activeTab === "changes" ? styles.activeRailTool : ""} onClick={() => selectDemo("changes")} aria-label="Files and editor"><Folder size={15} /></button>
          <button className={activeTab === "terminal" ? styles.activeRailTool : ""} onClick={() => selectDemo("terminal")} aria-label="Terminal"><Terminal size={15} /></button>
          <button className={activeTab === "browser" ? styles.activeRailTool : ""} onClick={() => selectDemo("browser")} aria-label="Browser"><Globe size={15} /></button>
          <button className={activeTab === "approval" ? styles.activeRailTool : ""} onClick={() => selectDemo("approval")} aria-label="Approvals and permissions"><ShieldCheck size={15} /></button>
          <button onClick={() => selectDemo("activity")} aria-label="MCP tools and skills"><Sparkles size={15} /></button>
          <div className={styles.railSpacer} />
          <span className={styles.railProject}>CR</span>
        </aside>

        <div className={styles.conversation}>
          <div className={styles.conversationHead}>
            <div>
              <span className={styles.eyebrow}>Team conversation</span>
              <strong>Ship the checkout redesign</strong>
            </div>
            <div className={styles.previewTeam} aria-label="Four agents in this team">
              {agents.map((agent, index) => (
                <div className={`${styles.agentAvatar} ${styles[agent.color]}`} style={{ zIndex: agents.length - index }} key={agent.name}>
                  {agent.initials}{index < 3 && <i />}
                  <div className={styles.agentTooltip}><strong>{agent.name}</strong><span>{agent.task}</span></div>
                </div>
              ))}
            </div>
            <div className={styles.runControls}>
              <div className={styles.contextDial} aria-label="Context usage: 64 percent"><div><span>64</span><small>%</small></div></div>
              <span>3 working</span>
              <button aria-label="Stop team"><CircleStop size={15} /></button>
            </div>
          </div>

          <div className={styles.chatBody}>
            <div className={styles.userMessage}>
              <span>Redesign checkout, keep the existing API, and make failures easy to recover from.</span>
              <i />
            </div>

            <div className={styles.agentMessage}>
              <div className={`${styles.messageAvatar} ${styles.violet}`}>AR</div>
              <div>
                <div className={styles.messageMeta}><strong>Architect</strong><span>now</span></div>
                <p>I split this into the payment state machine, UI implementation, and a focused review pass.</p>
                <div className={styles.planGrid}>
                  <span><CheckCircle2 size={14} /> Trace checkout flow</span>
                  <span><Play size={14} /> Build recovery states</span>
                  <span><span className={styles.waitingDot} /> Review file changes</span>
                </div>
              </div>
            </div>

            <div className={styles.previewTabs} role="tablist" aria-label="Workspace detail">
              {demoTabs.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === tab.id}
                    className={activeTab === tab.id ? styles.activeTab : ""}
                    onClick={() => selectDemo(tab.id)}
                  >
                    <Icon size={14} />{tab.label}
                    {tab.count && <span className={styles.tabCount}>{tab.count}</span>}
                  </button>
                )
              })}
            </div>

            <div className={styles.detailPanel}>
              {activeTab === "activity" && (
                <motion.div key="activity" initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }}>
                  <div className={styles.sceneCaption}><span>Agent workflow</span><i /><em>Delegating and using connected tools</em></div>
                  <div className={styles.activityRow}>
                    <span className={`${styles.miniAvatar} ${styles.blue}`}>BE</span>
                    <div><strong>Backend used PostgreSQL through MCP</strong><code>inspect_schema · checkout_sessions</code></div>
                    <span className={styles.successState}>done</span>
                  </div>
                  <div className={styles.activityRow}>
                    <span className={`${styles.miniAvatar} ${styles.amber}`}>FE</span>
                    <div><strong>Frontend loaded the UI review skill</strong><span>Editing recovery states and payment summary</span></div>
                    <span className={styles.runningState}>working</span>
                  </div>
                </motion.div>
              )}
              {activeTab === "approval" && (
                <motion.div className={styles.approvalCard} key="approval" initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }}>
                  <div className={styles.approvalIcon}><LockKeyhole size={17} /></div>
                  <div className={styles.approvalCopy}>
                    <strong>Permission requested</strong>
                    <span>Backend wants to run a database migration.</span>
                    <code>pnpm prisma migrate dev</code>
                  </div>
                  <div className={styles.approvalActions}><button>Reject</button><button>Allow once</button></div>
                </motion.div>
              )}
              {activeTab === "changes" && (
                <motion.div className={styles.diffCard} key="changes" initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }}>
                  <div className={styles.fileTree}>
                    <strong><GitBranch size={14} /> 6 changed files</strong>
                    <span className={styles.selectedFile}>CheckoutFlow.tsx <b>+84</b></span>
                    <span>payment-machine.ts <b>+42</b></span>
                    <span>checkout.css <b>+31</b></span>
                  </div>
                  <pre><span className={styles.diffMinus}>- setError(message)</span>{"\n"}<span className={styles.diffPlus}>+ transition({`{ type: 'RETRY' }`})</span>{"\n"}<span className={styles.diffPlus}>+ focusErrorSummary()</span></pre>
                </motion.div>
              )}
              {activeTab === "terminal" && (
                <motion.div className={styles.demoTerminal} key="terminal" initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }}>
                  <div><span /><span /><span /><b>Backend · checkout tests</b></div>
                  <code><i>$</i> pnpm test checkout --run</code>
                  <code className={styles.terminalLine}>✓ payment-state.test.ts <em>12 passed</em></code>
                  <code className={styles.terminalLine}>✓ recovery-flow.test.ts <em>8 passed</em></code>
                  <span className={styles.terminalCursor}>▋</span>
                </motion.div>
              )}
              {activeTab === "browser" && (
                <motion.div className={styles.demoBrowser} key="browser" initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }}>
                  <div className={styles.browserBar}><span>‹</span><span>›</span><span>↻</span><code>localhost:3000/checkout</code></div>
                  <div className={styles.browserPage}>
                    <div><small>Checkout</small><strong>Complete your order</strong><span className={styles.browserField} /><span className={styles.browserField} /><button>Pay securely</button></div>
                    <span className={styles.browserPointer}><i />Agent testing recovery state</span>
                  </div>
                </motion.div>
              )}
            </div>
          </div>

          <div className={styles.composer}>
            <span>Ask the team or give new direction…</span>
            <div><button aria-label="Attach context">+</button><button className={styles.sendButton} aria-label="Send message"><ArrowRight size={16} /></button></div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function LandingPage({ onLaunchApp, onSignIn, onSignUp, theme: themeOverride, onToggleTheme, hosted = false }: LandingPageProps) {
  const themeContext = useTheme();
  const theme = themeOverride ?? themeContext.theme;
  const toggleTheme = onToggleTheme ?? themeContext.toggleTheme;
  const [openFaq, setOpenFaq] = useState<number | null>(0);
  const [copied, setCopied] = useState(false);

  const copyInstall = async () => {
    await navigator.clipboard?.writeText("pip install carole.ai\ncaroleai");
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return (
    <main className={styles.page}>
      <nav className={styles.nav} aria-label="Main navigation">
        <a className={styles.logo} href="#top" aria-label="Carole.ai home">
          <img className={styles.brandMark} src="/branding/logo-mark-animated.webp" alt="" />
          <img className={styles.brandWordmark} src={theme === "dark" ? "/branding/logo-wordmark-dark.png" : "/branding/logo-wordmark.png"} alt="Carole.ai" />
        </a>
        <div className={styles.navLinks}>
          {hosted && <a href="#install">Install</a>}
          <a href="#workflow">Workflow</a>
          <a href="#integrations">MCP tools</a>
          <a href="#control">Control</a>
          <a href="#infrastructure">Infrastructure</a>
        </div>
        <div className={styles.navActions}>
          <button className={styles.iconButton} onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <button className={styles.signIn} onClick={onSignIn}>Sign in</button>
          <button className={styles.navCta} onClick={onLaunchApp}>Open workspace <ArrowRight size={15} /></button>
        </div>
      </nav>

      <section className={styles.hero} id="top">
        <div className={styles.heroGlow} />
        <motion.div className={styles.heroCopy} initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.55 }}>
          <img className={styles.heroBrandMark} src="/branding/logo-mark-animated.webp" alt="" />
          <div className={styles.heroKicker}> The local-first workspace for agent teams</div>
          <h1>A software team<br />you can <em>talk to.</em></h1>
          <p>Plan, delegate, review, and ship with a coordinated team of AI agents—without losing sight of what they are doing.</p>
          <div className={styles.heroActions}>
            {hosted ? (
              <a className={styles.primaryCta} href="#install">Install &amp; get started <ArrowRight size={17} /></a>
            ) : (
              <button className={styles.primaryCta} onClick={onSignUp}>Start building <ArrowRight size={17} /></button>
            )}
            <a className={styles.secondaryCta} href="https://github.com/sshivasai/Carole.ai" target="_blank" rel="noreferrer"><GitHubMark /> View on GitHub</a>
          </div>
          {hosted && (
            <div className={styles.quickStart} id="install">
              <div className={styles.quickStartHeader}>
                <div>
                  <span className={styles.quickStartEyebrow}>GET STARTED</span>
                  <h2>Install Carole.ai on your computer</h2>
                </div>
                <button className={styles.quickStartCopy} type="button" onClick={copyInstall} aria-live="polite">
                  {copied ? <Check size={15} /> : <Copy size={15} />}
                  {copied ? "Copied" : "Copy commands"}
                </button>
              </div>
              <div className={styles.quickStartCommands} aria-label="Installation commands">
                <div><span>1</span><code>pip install carole.ai</code></div>
                <div><span>2</span><code>caroleai</code></div>
              </div>
              <p>Keep the terminal running, then <a href="#install" onClick={(event) => { event.preventDefault(); onLaunchApp?.(); }}>open your local workspace</a> to sign in or start building. Your workspace runs on your computer.</p>
            </div>
          )}
          <div className={styles.heroProof}>
            <span><Check size={14} /> Public source</span>
            <span><Check size={14} /> Local-first</span>
            <span><Check size={14} /> Model-flexible</span>
          </div>
        </motion.div>
        <motion.div className={styles.heroProduct} initial={{ opacity: 0, y: 28, scale: 0.985 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.7, delay: 0.12 }}>
          <ProductPreview />
        </motion.div>
      </section>

      <section className={styles.integrationsSection} id="integrations">
        <div className={styles.integrationsCopy}>
          <span className={styles.eyebrow}>Model Context Protocol</span>
          <h2>Give every agent<br />the right tools.</h2>
          <p>Connect the systems your team already works in. Carole routes each task to the relevant MCP tools while keeping access and approvals visible.</p>
          <div className={styles.integrationNames}>
            {["GitHub", "PostgreSQL", "Linear", "Slack", "Supabase", "Figma"].map((name) => <span key={name}>{name}</span>)}
          </div>
        </div>
        <div className={styles.integrationStage}>
          <div className={styles.integrationGrid} />
          <div className={styles.integrationAnimation}><IntegrationsAnimation /></div>
          <div className={styles.stageLabel}><Network size={14} /><span>Live MCP routing</span><i /></div>
        </div>
      </section>

      <section className={styles.statement}>
        <p>One request enters.</p>
        <h2>A coordinated team moves it forward.</h2>
        <div className={styles.signalLine}><span /><i /><i /><i /><span /></div>
      </section>

      <section className={styles.workflowSection} id="workflow">
        <div className={styles.sectionIntro}>
          <span className={styles.eyebrow}>How work moves</span>
          <h2>From intent to reviewed code,<br />in one continuous workspace.</h2>
        </div>
        <div className={styles.workflowGrid}>
          {workflow.map((item) => (
            <article className={styles.workflowCard} key={item.number}>
              <span className={styles.cardNumber}>{item.number}</span>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.visibilitySection}>
        <div className={styles.visibilityCopy}>
          <span className={styles.eyebrow}>Work stays legible</span>
          <h2>See the work.<br />Shape it while it happens.</h2>
          <p>Carole turns agent activity into a readable timeline. Background jobs, tool calls, handoffs, and code edits stay connected to the conversation that caused them.</p>
          <ul>
            <li><Terminal size={18} /><div><strong>Tool activity</strong><span>Commands, results, and failures with useful context.</span></div></li>
            <li><Users size={18} /><div><strong>Agent presence</strong><span>Who is working, what they own, and what comes next.</span></div></li>
            <li><FileCode2 size={18} /><div><strong>Reviewable changes</strong><span>Files and diffs grouped by the task that changed them.</span></div></li>
          </ul>
        </div>
        <div className={styles.timelineCard}>
          <div className={styles.timelineTop}><span>Live activity</span><span><i /> 4 events</span></div>
          <div className={styles.timelineItem}>
            <div className={`${styles.timelineIcon} ${styles.violet}`}><Network size={15} /></div>
            <div><strong>Architect delegated 3 tasks</strong><span>Frontend, Backend, and Reviewer</span></div><time>09:42</time>
          </div>
          <div className={styles.timelineItem}>
            <div className={`${styles.timelineIcon} ${styles.blue}`}><Terminal size={15} /></div>
            <div><strong>Backend completed a tool call</strong><code>pnpm test checkout</code></div><time>09:44</time>
          </div>
          <div className={`${styles.timelineItem} ${styles.timelineFocus}`}>
            <div className={`${styles.timelineIcon} ${styles.amber}`}><ShieldCheck size={15} /></div>
            <div><strong>Your approval is needed</strong><span>Run the checkout database migration</span></div><button>Review</button>
          </div>
          <div className={styles.timelineItem}>
            <div className={`${styles.timelineIcon} ${styles.green}`}><GitBranch size={15} /></div>
            <div><strong>Reviewer started a diff review</strong><span>6 files · 157 additions · 24 deletions</span></div><time>09:47</time>
          </div>
        </div>
      </section>

      <section className={styles.controlSection} id="control">
        <div className={styles.controlVisual}>
          <div className={styles.permissionWindow}>
            <div className={styles.permissionHead}><div><ShieldCheck size={18} /></div><span>Approval request</span><small>From Backend</small></div>
            <h3>Allow this database migration?</h3>
            <p>The agent needs to update the local development schema to continue.</p>
            <code>$ pnpm prisma migrate dev --name checkout-state</code>
            <dl><div><dt>Scope</dt><dd>Local database</dd></div><div><dt>Requested by</dt><dd>Checkout task</dd></div></dl>
            <div className={styles.permissionActions}><button>Reject</button><button>Allow once</button></div>
          </div>
        </div>
        <div className={styles.controlCopy}>
          <span className={styles.eyebrow}>Human control, built in</span>
          <h2>Nothing important hides behind a spinner.</h2>
          <p>When an agent needs more access, you see the exact action, its reason, and its scope. Approve once, reject, or redirect the team from the same conversation.</p>
          <div className={styles.controlPoints}>
            <span><LockKeyhole size={16} /> Explicit permission boundaries</span>
            <span><GitBranch size={16} /> Inspect changes before shipping</span>
            <span><CircleStop size={16} /> Stop or redirect work at any time</span>
          </div>
        </div>
      </section>

      <section className={styles.openSourceSection} id="open-source">
        <div className={styles.openSourceCopy}>
          <span className={styles.eyebrow}>Public source on GitHub</span>
          <h2>Your team. Your models.<br />Your machine.</h2>
          <p>Inspect the system, adapt the workflow, connect the tools you trust, and choose the models that fit each role.</p>
          <a href="https://github.com/sshivasai/Carole.ai" target="_blank" rel="noreferrer">Explore the repository <ArrowRight size={16} /></a>
        </div>
        <div className={styles.terminalCard}>
          <div className={styles.terminalHead}><span><i /><i /><i /></span><small>terminal</small></div>
          <div className={styles.terminalBody}>
            <span className={styles.comment}># Install and start your workspace</span>
            <div><span className={styles.prompt}>$</span> pip install carole.ai</div>
            <div><span className={styles.prompt}>$</span> caroleai</div>
            <span className={styles.ready}>✓ Workspace ready at 127.0.0.1:8000</span>
          </div>
          <button className={styles.copyButton} onClick={copyInstall}>{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "Copied" : "Copy"}</button>
        </div>
      </section>

      <section className={styles.infrastructureSection} id="infrastructure">
        <div className={styles.infrastructureHead}>
          <div>
            <span className={styles.eyebrow}>Tools and infrastructure</span>
            <h2>Built on the stack<br />you already trust.</h2>
          </div>
          <p>Open foundations across runtime, code intelligence, storage, observability, and agent connectivity.</p>
        </div>
        <div className={styles.techGrid}>
          {infrastructure.map((tech) => (
            <div className={styles.techItem} key={tech.name}>
              <div className={styles.techLogo}><img className={tech.invert ? styles.invertLogo : ""} src={tech.logo} alt="" loading="lazy" /></div>
              <div><strong>{tech.name}</strong><span>{tech.group}</span></div>
            </div>
          ))}
        </div>
        <div className={styles.modelStrip}>
          <span>Works across model providers</span>
          {modelProviders.map((provider) => (
            <img
              key={provider.name}
              className={provider.invert ? styles.invertLogo : ""}
              src={provider.logo}
              alt={provider.name}
              title={provider.name}
              loading="lazy"
            />
          ))}
        </div>
      </section>

      <section className={styles.faqSection}>
        <div className={styles.sectionIntro}>
          <span className={styles.eyebrow}>Questions, answered</span>
          <h2>Built for teams that want<br />clarity and control.</h2>
        </div>
        <div className={styles.faqList}>
          {faqs.map((faq, index) => (
            <div className={`${styles.faqItem} ${openFaq === index ? styles.faqOpen : ""}`} key={faq.q}>
              <button onClick={() => setOpenFaq(openFaq === index ? null : index)} aria-expanded={openFaq === index}>
                <span>{faq.q}</span><ChevronDown size={18} />
              </button>
              <div className={styles.faqAnswer}><p>{faq.a}</p></div>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.finalCta}>
        <div className={styles.finalGlow} />
        <span className={styles.eyebrow}>Ready when you are</span>
        <h2>Bring your next build.<br /><em>Carole brings the team.</em></h2>
        <button className={styles.primaryCta} onClick={onSignUp}>Create your workspace <ArrowRight size={17} /></button>
      </section>

      <footer className={styles.footer}>
        <a className={styles.logo} href="#top"><img className={styles.brandMark} src="/branding/logo-mark-animated.webp" alt="" /><img className={styles.brandWordmark} src={theme === "dark" ? "/branding/logo-wordmark-dark.png" : "/branding/logo-wordmark.png"} alt="Carole.ai" /></a>
        <p>Local-first multi-agent workspace for building software.</p>
        <div><a href="https://github.com/sshivasai/Carole.ai" target="_blank" rel="noreferrer">GitHub</a><a href="#integrations">MCP tools</a><a href="https://caroleai.com/privacy/">Privacy</a><a href="https://caroleai.com/terms/">Terms</a></div>
      </footer>
    </main>
  );
}
