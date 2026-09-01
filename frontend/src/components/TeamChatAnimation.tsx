"use client";

import React, { useState, useEffect, useRef } from "react";
import PrettyAvatar from "./PrettyAvatar";
import {
  Play,
  Pause,
  Sparkles,
  Bot,
  ShieldCheck,
  Terminal,
  Send,
  ChevronRight,
  ChevronDown,
  ChevronLeft,
  Folder,
  LayoutGrid,
  FileCode,
  Sun,
  Bell,
  Image as ImageIcon,
  Clock,
  PlayCircle,
  CheckCircle,
  Plus,
} from "lucide-react";
import MagneticCard from "./MagneticCard";
import GravityText from "./GravityText";

type ActiveScene = "chat" | "kanban" | "explorer" | "terminal" | "security";
type ScenePhase = "title" | "ui";

interface SceneMeta {
  id: ActiveScene;
  badge: string;
  title: string;
  subtitle: string;
  description: string;
  icon: any;
  color: string;
}

const SCENES: SceneMeta[] = [
  {
    id: "chat",
    badge: "01 / MULTI-AGENT COLLABORATION",
    title: "Chat with the Team as Real Devs",
    subtitle: "Natural language intent → Actor-model decomposition in seconds.",
    description:
      "Admin dispatches a high-level engineering prompt. Watch real-time typing, message dispatch, and Archer's ReAct loop orchestrating specialist subagents.",
    icon: Bot,
    color: "#a78bfa",
  },
  {
    id: "kanban",
    badge: "02 / DYNAMIC TASK ORCHESTRATION",
    title: "Inbuilt Autonomous Kanban Board",
    subtitle: "Watch complex software features break down into live, assigned task cards.",
    description:
      "Agents automatically decompose complex workstreams into prioritized task cards with assigned PrettyAvatars and bidirectional WebSocket status synchronization.",
    icon: LayoutGrid,
    color: "#38bdf8",
  },
  {
    id: "explorer",
    badge: "03 / CODE EDITING & ROLLBACK SAFETY",
    title: "Inbuilt File Explorer & AST Diff Viewer",
    subtitle: "Inspect syntax-highlighted code diffs with point-in-time rollback protection.",
    description:
      "Browse the complete codebase tree, inspect syntax-highlighted side-by-side code diffs, and restore point-in-time rollback backup snapshots.",
    icon: Folder,
    color: "#10b981",
  },
  {
    id: "terminal",
    badge: "04 / SHELL EXECUTION & VERSION CONTROL",
    title: "Integrated PTY Terminal & Git Control",
    subtitle: "Live shell execution, test suites, and atomic git commit tracking.",
    description:
      "Interactive shell streams pytest suite execution (24 passed in 0.94s), visualizes git branch commits, and runs headless Playwright browser tests.",
    icon: Terminal,
    color: "#f472b6",
  },
  {
    id: "security",
    badge: "05 / ZERO-TRUST POLICY ENFORCEMENT",
    title: "Judge AI Real-Time Security Gate",
    subtitle: "Zero unauthorized mutations. Multi-tier policy firewall evaluating every command.",
    description:
      "A dedicated security evaluator LLM intercepts shell commands, git pushes, and database mutations with automated risk scoring and human approval escalation.",
    icon: ShieldCheck,
    color: "#fbbf24",
  },
];

const PROMPT_TO_TYPE =
  "@Archer Upgrade the auth pipeline: migrate to RS256 JWT tokens with sliding expiration and Redis rate-limiting (100 req/min).";

export default function TeamChatAnimation() {
  const [activeScene, setActiveScene] = useState<ActiveScene>("chat");
  const [scenePhase, setScenePhase] = useState<ScenePhase>("title");
  const [isPlaying, setIsPlaying] = useState(true);

  // Animated Typing for Title Card
  const [titleTypedText, setTitleTypedText] = useState("");
  const [isTitleTyping, setIsTitleTyping] = useState(true);

  // Chat typing & streaming simulation states
  const [typedText, setTypedText] = useState("");
  const [isTyping, setIsTyping] = useState(true);
  const [messageSent, setMessageSent] = useState(false);
  const [isSendBtnActive, setIsSendBtnActive] = useState(false);
  const [archerThinking, setArcherThinking] = useState(false);
  const [archerResponded, setArcherResponded] = useState(false);
  const [subagentCompleted, setSubagentCompleted] = useState(false);
  const [qaResponded, setQaResponded] = useState(false);

  // Explorer & Terminal tab states
  const [explorerTab, setExplorerTab] = useState<"diff" | "history">("diff");
  const [terminalTab, setTerminalTab] = useState<"pytest" | "git" | "playwright">("pytest");

  const chatContainerRef = useRef<HTMLDivElement>(null);

  const currentSceneMeta = SCENES.find((s) => s.id === activeScene) || SCENES[0];
  const SceneIcon = currentSceneMeta.icon;

  // 1. Snappy Title Card Typing Animation
  useEffect(() => {
    if (scenePhase === "title") {
      const fullTitle = currentSceneMeta.title;
      setTitleTypedText("");
      setIsTitleTyping(true);
      let charIdx = 0;

      const titleInterval = setInterval(() => {
        if (charIdx < fullTitle.length) {
          setTitleTypedText(fullTitle.slice(0, charIdx + 1));
          charIdx++;
        } else {
          clearInterval(titleInterval);
          setIsTitleTyping(false);
        }
      }, 22); // Fast 22ms per char for snappy typing

      return () => clearInterval(titleInterval);
    }
  }, [scenePhase, activeScene, currentSceneMeta.title]);

  // 2. Fast-Paced Continuous Video Reel Cycle Manager
  useEffect(() => {
    if (!isPlaying) return;

    let timer: NodeJS.Timeout;

    if (scenePhase === "title") {
      // Snappy 1.5s Title Card duration
      timer = setTimeout(() => {
        setScenePhase("ui");
      }, 1500);
    } else if (scenePhase === "ui") {
      // Snappy UI durations: 4.8s for chat, 2.8s for other scenes
      const uiDuration = activeScene === "chat" ? 4800 : 2800;
      timer = setTimeout(() => {
        const sceneOrder: ActiveScene[] = ["chat", "kanban", "explorer", "terminal", "security"];
        const currentIdx = sceneOrder.indexOf(activeScene);
        const nextScene = sceneOrder[(currentIdx + 1) % sceneOrder.length];

        // Reset chat animation states when looping back to chat
        if (nextScene === "chat") {
          setMessageSent(false);
          setArcherThinking(false);
          setArcherResponded(false);
          setSubagentCompleted(false);
          setQaResponded(false);
          setTypedText("");
        }

        setActiveScene(nextScene);
        setScenePhase("title"); // Start next scene on title card
      }, uiDuration);
    }

    return () => clearTimeout(timer);
  }, [activeScene, scenePhase, isPlaying]);

  // 3. Ultra-Fast Chat Typing & Message Dispatch Simulation during UI phase
  useEffect(() => {
    if (!isPlaying) return;

    if (activeScene === "chat" && scenePhase === "ui" && !messageSent) {
      setIsTyping(true);
      let charIdx = 0;
      setTypedText("");

      const interval = setInterval(() => {
        if (charIdx < PROMPT_TO_TYPE.length) {
          setTypedText(PROMPT_TO_TYPE.slice(0, charIdx + 1));
          charIdx++;
        } else {
          clearInterval(interval);
          setIsTyping(false);
          // Rapid click and message dispatch
          setTimeout(() => {
            setIsSendBtnActive(true);
            setTimeout(() => {
              setIsSendBtnActive(false);
              setMessageSent(true);
              setTypedText("");

              // Snappy Archer thinking
              setArcherThinking(true);
              setTimeout(() => {
                setArcherThinking(false);
                setArcherResponded(true);

                // Snappy subagent completion after 700ms
                setTimeout(() => {
                  setSubagentCompleted(true);
                  // Snappy QA response after 600ms
                  setTimeout(() => {
                    setQaResponded(true);
                  }, 600);
                }, 700);
              }, 600);
            }, 150);
          }, 200);
        }
      }, 10); // Ultra-fast 10ms per char

      return () => clearInterval(interval);
    }
  }, [activeScene, scenePhase, messageSent, isPlaying]);

  // Auto scroll chat container when new messages arrive
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTo({
        top: chatContainerRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messageSent, archerResponded, subagentCompleted, qaResponded, activeScene, scenePhase]);

  return (
    <MagneticCard
      tiltMaxAngle={2}
      liftAmount={4}
      glowColor="rgba(167, 139, 250, 0.16)"
      style={{ width: "100%", borderRadius: 20 }}
    >
      <div
        style={{
          background: "#030315",
          border: "1px solid var(--color-hairline, #2a2a3f)",
          borderRadius: 20,
          overflow: "hidden",
          boxShadow: "0 32px 80px rgba(0, 0, 0, 0.8), 0 0 0 1px rgba(167, 139, 250, 0.15)",
          display: "flex",
          flexDirection: "column",
          minHeight: 560,
          maxHeight: 560,
          position: "relative",
          fontFamily: "var(--font-sans, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif)",
        }}
      >
        {/* Top Window Chrome Header with Single Minimal Play/Pause Button */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "10px 18px",
            background: "#0a0a1a",
            borderBottom: "1px solid var(--color-hairline, #2a2a3f)",
            zIndex: 10,
          }}
        >
          {/* Mac Traffic Lights & Workspace Title */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 11, height: 11, borderRadius: "50%", background: "#ef4444", display: "inline-block" }} />
            <span style={{ width: 11, height: 11, borderRadius: "50%", background: "#f59e0b", display: "inline-block" }} />
            <span style={{ width: 11, height: 11, borderRadius: "50%", background: "#10b981", display: "inline-block" }} />
            <span
              style={{
                marginLeft: 10,
                fontSize: 12,
                fontFamily: "var(--font-mono, monospace)",
                color: "var(--color-body, #94a3b8)",
                fontWeight: 600,
              }}
            >
              Carole.ai Console: {currentSceneMeta.badge}
            </span>
          </div>

          {/* Minimal Play / Pause Toggle Button */}
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 5,
              padding: "4px 10px",
              borderRadius: 6,
              fontSize: 11.5,
              fontWeight: 600,
              background: isPlaying ? "rgba(239, 68, 68, 0.12)" : "rgba(16, 185, 129, 0.15)",
              color: isPlaying ? "#f87171" : "#34d399",
              border: isPlaying ? "1px solid rgba(239, 68, 68, 0.3)" : "1px solid rgba(16, 185, 129, 0.3)",
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
          >
            {isPlaying ? <Pause size={12} /> : <Play size={12} />}
            <span>{isPlaying ? "Pause" : "Play"}</span>
          </button>
        </div>

        {/* ======================================================================
            PHASE A: FULL-FRAME CINEMATIC TITLE CARD WITH TYPING ANIMATION
            ====================================================================== */}
        {scenePhase === "title" && (
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              textAlign: "center",
              padding: "40px 32px",
              background: "radial-gradient(circle at center, rgba(167, 139, 250, 0.14) 0%, #030315 75%)",
              position: "relative",
              overflow: "hidden",
              animation: "fadeIn 0.2s ease-out",
            }}
          >
            {/* Ambient Purple Glow */}
            <div
              style={{
                position: "absolute",
                width: 320,
                height: 320,
                borderRadius: "50%",
                background: currentSceneMeta.color,
                filter: "blur(110px)",
                opacity: 0.15,
                pointerEvents: "none",
              }}
            />

            {/* Glowing Icon Badge */}
            <div
              style={{
                width: 52,
                height: 52,
                borderRadius: 14,
                background: `${currentSceneMeta.color}20`,
                border: `1px solid ${currentSceneMeta.color}50`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: currentSceneMeta.color,
                boxShadow: `0 0 24px ${currentSceneMeta.color}35`,
                marginBottom: 16,
              }}
            >
              <SceneIcon size={26} />
            </div>

            {/* Scene Badge */}
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "3px 12px",
                borderRadius: 9999,
                background: `${currentSceneMeta.color}15`,
                border: `1px solid ${currentSceneMeta.color}35`,
                fontSize: 11,
                fontWeight: 800,
                color: currentSceneMeta.color,
                letterSpacing: 0.8,
                marginBottom: 12,
                textTransform: "uppercase",
              }}
            >
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: currentSceneMeta.color }} />
              <span>{currentSceneMeta.badge}</span>
            </div>

            {/* Main Headline with Live Typing Animation & Glowing Cursor */}
            <h2
              style={{
                fontSize: "clamp(26px, 3.8vw, 38px)",
                fontWeight: 900,
                color: "#ffffff",
                letterSpacing: "-0.03em",
                marginBottom: 10,
                maxWidth: 740,
                lineHeight: 1.15,
                minHeight: 46,
              }}
            >
              <span>{titleTypedText}</span>
              {isTitleTyping && (
                <span
                  style={{
                    display: "inline-block",
                    width: 3,
                    height: "0.85em",
                    background: currentSceneMeta.color,
                    marginLeft: 4,
                    verticalAlign: "middle",
                    boxShadow: `0 0 10px ${currentSceneMeta.color}`,
                    animation: "blink 0.8s infinite",
                  }}
                />
              )}
            </h2>

            {/* Sub-headline */}
            <div
              style={{
                fontSize: 15,
                fontWeight: 600,
                color: currentSceneMeta.color,
                marginBottom: 12,
                maxWidth: 680,
                animation: "fadeIn 0.3s ease-out",
              }}
            >
              {currentSceneMeta.subtitle}
            </div>

            {/* Description Paragraph */}
            <p
              style={{
                fontSize: 13.5,
                color: "var(--color-body, #94a3b8)",
                maxWidth: 600,
                lineHeight: 1.55,
                margin: 0,
                animation: "fadeIn 0.4s ease-out",
              }}
            >
              {currentSceneMeta.description}
            </p>

            {/* Fast-Paced Progress Timer Bar (1.5s) */}
            <div
              style={{
                position: "absolute",
                bottom: 0,
                left: 0,
                height: 3,
                background: currentSceneMeta.color,
                width: "100%",
                animation: "progressTimer 1.5s linear forwards",
                transformOrigin: "left",
              }}
            />
          </div>
        )}

        {/* ======================================================================
            PHASE B: EXACT CAROLE.AI LIVE WORKSPACE CONSOLE UI
            ====================================================================== */}
        {scenePhase === "ui" && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "220px 1fr",
              flex: 1,
              minHeight: 0,
              background: "#030315",
              animation: "fadeIn 0.25s ease-out",
            }}
          >
            {/* Left Console Sidebar (Exact Real App Colors & Layout) */}
            <div
              style={{
                background: "#0a0a1a",
                borderRight: "1px solid var(--color-hairline, #2a2a3f)",
                display: "flex",
                flexDirection: "column",
                padding: "16px 12px",
                justifyContent: "space-between",
                userSelect: "none",
              }}
            >
              <div>
                {/* Brand Logo */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18, padding: "0 4px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ width: 26, height: 26, borderRadius: 8, background: "linear-gradient(135deg, #a855f7, #6366f1)", display: "flex", alignItems: "center", justifyContent: "center", color: "#ffffff" }}>
                      <Sparkles size={14} />
                    </div>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 800, color: "#ffffff", letterSpacing: -0.2 }}>carole ai</div>
                      <div style={{ fontSize: 7, fontWeight: 700, color: "#64748b", letterSpacing: 0.8, textTransform: "uppercase" }}><del style={{ opacity: 0.6 }}>AI AGENTS.</del> <span style={{ color: "#a78bfa" }}>AI TEAMMATES.</span> REAL WORK.</div>
                    </div>
                  </div>
                  <ChevronLeft size={14} color="#64748b" />
                </div>

                {/* Project Section */}
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 9.5, fontWeight: 800, color: "var(--color-mute, #64748b)", letterSpacing: 0.6, marginBottom: 5, textTransform: "uppercase" }}>PROJECT</div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 10px", background: "rgba(255, 255, 255, 0.04)", borderRadius: 6, border: "1px solid var(--color-hairline, #2a2a3f)", fontSize: 12, fontWeight: 600, color: "#f1f5f9" }}>
                    <span>Project1</span>
                    <ChevronDown size={12} color="#64748b" />
                  </div>
                  <div style={{ fontSize: 10.5, color: "#64748b", paddingLeft: 4, marginTop: 2 }}>+ New project</div>
                </div>

                {/* Team Room Section */}
                <div style={{ marginBottom: 14 }}>
                  <div style={{ fontSize: 9.5, fontWeight: 800, color: "var(--color-mute, #64748b)", letterSpacing: 0.6, marginBottom: 5, textTransform: "uppercase" }}>TEAM ROOM</div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 10px", background: "rgba(255, 255, 255, 0.04)", borderRadius: 6, border: "1px solid var(--color-hairline, #2a2a3f)", fontSize: 12, fontWeight: 600, color: "#f1f5f9" }}>
                    <span>Team1</span>
                    <ChevronDown size={12} color="#64748b" />
                  </div>
                  <div style={{ fontSize: 10.5, color: "#64748b", paddingLeft: 4, marginTop: 2 }}>+ New team</div>
                </div>

                {/* Workspace Nav Items (Highlighting the active scene tab) */}
                <div>
                  <div style={{ fontSize: 9.5, fontWeight: 800, color: "var(--color-mute, #64748b)", letterSpacing: 0.6, marginBottom: 6, textTransform: "uppercase" }}>WORKSPACE</div>

                  {/* Chat Room */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "7px 10px",
                      borderRadius: 8,
                      background: activeScene === "chat" ? "rgba(167, 139, 250, 0.18)" : "transparent",
                      border: activeScene === "chat" ? "1px solid rgba(167, 139, 250, 0.35)" : "1px solid transparent",
                      color: activeScene === "chat" ? "#ffffff" : "var(--color-body, #94a3b8)",
                      fontSize: 12,
                      fontWeight: 600,
                      marginBottom: 2,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <Bot size={14} color={activeScene === "chat" ? "#a78bfa" : "#64748b"} />
                      <span>Chat Room</span>
                    </div>
                    {activeScene === "chat" && <ChevronRight size={13} color="#a78bfa" />}
                  </div>

                  {/* Task Board */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "7px 10px",
                      borderRadius: 8,
                      background: activeScene === "kanban" ? "rgba(56, 189, 248, 0.18)" : "transparent",
                      border: activeScene === "kanban" ? "1px solid rgba(56, 189, 248, 0.35)" : "1px solid transparent",
                      color: activeScene === "kanban" ? "#ffffff" : "var(--color-body, #94a3b8)",
                      fontSize: 12,
                      fontWeight: 600,
                      marginBottom: 2,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <LayoutGrid size={14} color={activeScene === "kanban" ? "#38bdf8" : "#64748b"} />
                      <span>Task Board</span>
                    </div>
                    {activeScene === "kanban" && <ChevronRight size={13} color="#38bdf8" />}
                  </div>

                  {/* File Explorer */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "7px 10px",
                      borderRadius: 8,
                      background: activeScene === "explorer" ? "rgba(16, 185, 129, 0.18)" : "transparent",
                      border: activeScene === "explorer" ? "1px solid rgba(16, 185, 129, 0.35)" : "1px solid transparent",
                      color: activeScene === "explorer" ? "#ffffff" : "var(--color-body, #94a3b8)",
                      fontSize: 12,
                      fontWeight: 600,
                      marginBottom: 2,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <Folder size={14} color={activeScene === "explorer" ? "#10b981" : "#64748b"} />
                      <span>File Explorer</span>
                    </div>
                    {activeScene === "explorer" && <ChevronRight size={13} color="#10b981" />}
                  </div>

                  {/* Terminal & Git */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "7px 10px",
                      borderRadius: 8,
                      background: activeScene === "terminal" ? "rgba(244, 114, 182, 0.18)" : "transparent",
                      border: activeScene === "terminal" ? "1px solid rgba(244, 114, 182, 0.35)" : "1px solid transparent",
                      color: activeScene === "terminal" ? "#ffffff" : "var(--color-body, #94a3b8)",
                      fontSize: 12,
                      fontWeight: 600,
                      marginBottom: 2,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <Terminal size={14} color={activeScene === "terminal" ? "#f472b6" : "#64748b"} />
                      <span>Terminal & Git</span>
                    </div>
                    {activeScene === "terminal" && <ChevronRight size={13} color="#f472b6" />}
                  </div>

                  {/* Security Gate */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "7px 10px",
                      borderRadius: 8,
                      background: activeScene === "security" ? "rgba(251, 191, 36, 0.18)" : "transparent",
                      border: activeScene === "security" ? "1px solid rgba(251, 191, 36, 0.35)" : "1px solid transparent",
                      color: activeScene === "security" ? "#ffffff" : "var(--color-body, #94a3b8)",
                      fontSize: 12,
                      fontWeight: 600,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <ShieldCheck size={14} color={activeScene === "security" ? "#fbbf24" : "#64748b"} />
                      <span>Security Gate</span>
                    </div>
                    {activeScene === "security" && <ChevronRight size={13} color="#fbbf24" />}
                  </div>
                </div>
              </div>

              {/* Sidebar Bottom Profile Card: Admin */}
              <div style={{ borderTop: "1px solid var(--color-hairline, #2a2a3f)", paddingTop: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6, paddingLeft: 2 }}>
                  <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#10b981" }} />
                  <span style={{ fontSize: 11, color: "#10b981", fontWeight: 600 }}>Connected</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "4px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ width: 24, height: 24, borderRadius: "50%", background: "linear-gradient(135deg, #a855f7, #6366f1)", display: "flex", alignItems: "center", justifyContent: "center", color: "#ffffff", fontSize: 11, fontWeight: 700 }}>
                      A
                    </div>
                    <div>
                      <div style={{ fontSize: 11, fontWeight: 700, color: "#f1f5f9" }}>Admin</div>
                      <div style={{ fontSize: 9, color: "#64748b" }}>admin@carole.ai</div>
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 4, color: "#64748b" }}>
                    <Sun size={11} />
                    <Bell size={11} />
                  </div>
                </div>
              </div>
            </div>

            {/* Dynamic Console Subsystem Area */}
            <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0, background: "#030315" }}>
              
              {/* VIEW 1: LIVE TEAM CHAT */}
              {activeScene === "chat" && (
                <>
                  <div style={{ padding: "12px 20px", borderBottom: "1px solid var(--color-hairline, #2a2a3f)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <span style={{ fontSize: 14, fontWeight: 800, color: "#ffffff" }}>Team Chat</span>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "1px 6px", borderRadius: 9999, background: "rgba(168, 85, 247, 0.2)", border: "1px solid rgba(168, 85, 247, 0.4)", fontSize: 9.5, fontWeight: 800, color: "#c084fc" }}>
                        <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#c084fc" }} /> LIVE
                      </span>
                      <span style={{ fontSize: 11, color: "var(--color-body, #94a3b8)" }}>Collaborate with your <del style={{ opacity: 0.6 }}>AI agents</del> <span style={{ color: "#a78bfa", fontWeight: 500 }}>AI teammates</span> · Shift+Enter for newline</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <div style={{ padding: "4px 8px", borderRadius: 6, background: "rgba(255,255,255,0.04)", fontSize: 11, color: "#cbd5e1" }}>🌐 4 Agents Active</div>
                    </div>
                  </div>

                  <div ref={chatContainerRef} style={{ flex: 1, overflowY: "auto", minHeight: 0, padding: "16px 20px", display: "flex", flexDirection: "column", gap: 12 }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, padding: "4px 0", fontSize: 11, color: "var(--color-mute, #64748b)" }}>
                      <span>🚀 Team workspace initialized (#Project1 / #Team1)</span>
                    </div>

                    {/* Admin Message Sent */}
                    {messageSent && (
                      <div style={{ display: "flex", flexDirection: "row-reverse", gap: 10, animation: "fadeIn 0.2s ease-out" }}>
                        <div style={{ width: 30, height: 30, borderRadius: "50%", background: "linear-gradient(135deg, #a855f7, #6366f1)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 12, fontWeight: 700 }}>
                          A
                        </div>
                        <div style={{ maxWidth: "78%", display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
                          <div style={{ fontSize: 10, color: "#64748b", marginBottom: 2 }}>12:45 AM</div>
                          <div style={{ padding: "10px 14px", borderRadius: "14px 2px 14px 14px", background: "#121225", border: "1px solid var(--color-hairline, #2a2a3f)", fontSize: 12.5, color: "#f1f5f9", lineHeight: 1.5, boxShadow: "0 4px 14px rgba(0,0,0,0.3)" }}>
                            {PROMPT_TO_TYPE}
                            <div style={{ display: "inline-flex", alignItems: "center", gap: 5, marginTop: 6, padding: "2px 8px", borderRadius: 6, background: "rgba(167, 139, 250, 0.15)", border: "1px solid rgba(167, 139, 250, 0.3)", fontSize: 10.5, color: "#c4b5fd", fontWeight: 600 }}>
                              <ImageIcon size={11} />
                              <span>auth_architecture.png</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Archer Thinking */}
                    {archerThinking && (
                      <div style={{ display: "flex", gap: 10, alignItems: "center", padding: "8px 12px", background: "rgba(167, 139, 250, 0.06)", borderRadius: 10, border: "1px solid rgba(167, 139, 250, 0.2)", width: "fit-content" }}>
                        <PrettyAvatar preset="archer" name="Archer" size={24} isWorking={true} />
                        <span style={{ fontSize: 11.5, color: "#c4b5fd" }}>Archer is analyzing task dependencies in ReAct loop...</span>
                      </div>
                    )}

                    {/* Archer Response */}
                    {archerResponded && (
                      <div style={{ display: "flex", gap: 10, animation: "fadeIn 0.2s ease-out" }}>
                        <PrettyAvatar preset="archer" name="Archer" size={30} />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                            <span style={{ fontSize: 12.5, fontWeight: 700, color: "#ffffff" }}>Archer</span>
                            <span style={{ fontSize: 10, color: "var(--color-body, #94a3b8)" }}>Lead Coordinator</span>
                            <span style={{ fontSize: 10, color: "#64748b", marginLeft: "auto" }}>12:46 AM</span>
                          </div>
                          <div style={{ padding: "7px 10px", borderRadius: 8, background: "rgba(167, 139, 250, 0.08)", borderLeft: "2px solid #a78bfa", fontSize: 11.5, color: "#cbd5e1", marginBottom: 6 }}>
                            <span style={{ fontWeight: 700, color: "#a78bfa" }}>Thought: </span>
                            Decomposing auth migration into 3 parallel workstreams: 1) RS256 JWT & Redis bucket, 2) GraphRAG AST route mapping, 3) Playwright E2E verification. Spawning Coder subagent with depth-1 safety permissions.
                          </div>
                          <div style={{ padding: "9px 12px", borderRadius: "2px 14px 14px 14px", background: "rgba(255, 255, 255, 0.03)", border: "1px solid var(--color-hairline, #2a2a3f)", fontSize: 12.5, color: "#e2e8f0", lineHeight: 1.5 }}>
                            Task received. Initializing Actor-model FIFO queues and hiring specialist subagents with depth-1 safety guards.
                            <div style={{ marginTop: 6, padding: "5px 8px", borderRadius: 6, background: "#0a0a1a", border: "1px solid rgba(167, 139, 250, 0.25)", fontFamily: "var(--font-mono, monospace)", fontSize: 10.5, color: "#c4b5fd", display: "flex", alignItems: "center", gap: 6 }}>
                              <Terminal size={11} />
                              <span>{"hire_subagent(target='Sub-PythonDeveloper_8777', task='Implement RS256 JWT & Redis rate limiter', permissions={'subagents': 'block'})"}</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Subagent Completed Card */}
                    {subagentCompleted && (
                      <div style={{ padding: "10px 14px", borderRadius: 8, background: "rgba(16, 185, 129, 0.06)", border: "1px solid rgba(16, 185, 129, 0.35)", display: "flex", flexDirection: "column", gap: 6, animation: "fadeIn 0.2s ease-out" }}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <span style={{ color: "#34d399", fontSize: 13 }}>✓</span>
                            <span style={{ fontSize: 12, fontWeight: 700, color: "#34d399" }}>Subagent Task Completed</span>
                            <span style={{ padding: "1px 6px", borderRadius: 9999, background: "rgba(251, 191, 36, 0.15)", border: "1px solid rgba(251, 191, 36, 0.3)", fontSize: 9.5, fontWeight: 700, color: "#fbbf24" }}>
                              👾 Sub-PythonDeveloper_8777
                            </span>
                          </div>
                          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 9.5, color: "#94a3b8" }}>ID: 8779b01c</span>
                        </div>
                        <div style={{ fontSize: 11.5, color: "#e2e8f0", lineHeight: 1.45, fontFamily: "var(--font-mono, monospace)", background: "#0a0a1a", padding: "6px 10px", borderRadius: 6 }}>
                          File &apos;backend/core/auth/jwt_handler.py&apos; successfully updated in project root with RS256 asymmetric signing, sliding expiration refresh, and Redis token bucket rate limiting (100 req/min). AST syntax validation passed (0 cyclic errors).
                        </div>
                      </div>
                    )}

                    {/* QA Runner Response */}
                    {qaResponded && (
                      <div style={{ display: "flex", gap: 10, animation: "fadeIn 0.2s ease-out" }}>
                        <PrettyAvatar preset="qa" name="QA Runner" size={30} />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                            <span style={{ fontSize: 12.5, fontWeight: 700, color: "#ffffff" }}>QA Runner</span>
                            <span style={{ fontSize: 10, color: "var(--color-body, #94a3b8)" }}>Playwright Automation</span>
                            <span style={{ fontSize: 10, color: "#64748b", marginLeft: "auto" }}>12:48 AM</span>
                          </div>
                          <div style={{ padding: "9px 12px", borderRadius: "2px 14px 14px 14px", background: "rgba(255, 255, 255, 0.03)", border: "1px solid var(--color-hairline, #2a2a3f)", fontSize: 12.5, color: "#e2e8f0", lineHeight: 1.5 }}>
                            Playwright headless browser verification passed: Verified /login, /refresh token exchange, and HTTP 429 rate limit response (3 assertions, 0 errors).
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Bottom Live Typing Input Field */}
                  <div style={{ padding: "10px 16px", borderTop: "1px solid var(--color-hairline, #2a2a3f)", background: "#0a0a1a", display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{ width: 30, height: 30, borderRadius: 8, background: "rgba(255, 255, 255, 0.04)", border: "1px solid var(--color-hairline, #2a2a3f)", display: "flex", alignItems: "center", justifyContent: "center", color: "#94a3b8" }}>
                      <Folder size={13} />
                    </div>

                    <div
                      style={{
                        flex: 1,
                        padding: "7px 12px",
                        borderRadius: 8,
                        background: "#030315",
                        border: "1px solid var(--color-hairline, #2a2a3f)",
                        fontSize: 11.5,
                        color: typedText ? "#f1f5f9" : "var(--color-mute, #64748b)",
                        display: "flex",
                        alignItems: "center",
                        minHeight: 32,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {typedText ? (
                        <span>
                          {typedText}
                          {isTyping && <span style={{ borderLeft: "2px solid #a78bfa", marginLeft: 2, animation: "blink 1s infinite" }} />}
                        </span>
                      ) : (
                        <span>Message your team... (@ to mention an agent or a file · Enter to send)</span>
                      )}
                    </div>

                    <div
                      style={{
                        width: 32,
                        height: 32,
                        borderRadius: 8,
                        background: isSendBtnActive ? "linear-gradient(135deg, #38bdf8, #a855f7)" : "linear-gradient(135deg, #a855f7, #6366f1)",
                        transform: isSendBtnActive ? "scale(0.9)" : "scale(1)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color: "#fff",
                        transition: "all 0.15s ease",
                        boxShadow: isSendBtnActive ? "0 0 16px rgba(168, 85, 247, 0.8)" : "0 4px 14px rgba(168, 85, 247, 0.35)",
                      }}
                    >
                      <Send size={13} />
                    </div>
                  </div>
                </>
              )}

              {/* VIEW 2: INBUILT AUTONOMOUS KANBAN BOARD */}
              {activeScene === "kanban" && (
                <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "16px 18px", overflow: "hidden" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 800, color: "#ffffff", display: "flex", alignItems: "center", gap: 8 }}>
                        <span>Autonomous Engineering Task Board</span>
                        <span style={{ fontSize: 9.5, padding: "2px 6px", borderRadius: 9999, background: "rgba(56, 189, 248, 0.2)", border: "1px solid rgba(56, 189, 248, 0.4)", color: "#38bdf8", fontWeight: 700 }}>
                          REAL-TIME WS SYNC
                        </span>
                      </div>
                      <div style={{ fontSize: 11, color: "var(--color-body, #94a3b8)" }}>Agents autonomously create, claim, execute, and verify tasks across workstreams.</div>
                    </div>
                    <div style={{ display: "flex", gap: 6 }}>
                      <button style={{ padding: "4px 10px", borderRadius: 6, background: "rgba(255, 255, 255, 0.05)", border: "1px solid var(--color-hairline, #2a2a3f)", fontSize: 11, color: "#cbd5e1", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
                        <Plus size={11} /> Add Task
                      </button>
                    </div>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, flex: 1, minHeight: 0, overflowX: "auto" }}>
                    {/* Backlog */}
                    <div style={{ background: "#0a0a1a", borderRadius: 10, border: "1px solid var(--color-hairline, #2a2a3f)", padding: "10px", display: "flex", flexDirection: "column", gap: 8 }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 11.5, fontWeight: 700, color: "var(--color-body, #94a3b8)", paddingBottom: 6, borderBottom: "1px solid var(--color-hairline, #2a2a3f)" }}>
                        <span style={{ display: "flex", alignItems: "center", gap: 5 }}><Clock size={12} /> Backlog</span>
                        <span style={{ fontSize: 10, background: "rgba(255,255,255,0.06)", padding: "1px 6px", borderRadius: 9999 }}>2</span>
                      </div>
                      <div style={{ padding: "10px", borderRadius: 8, background: "#121225", border: "1px solid var(--color-hairline, #2a2a3f)", fontSize: 11.5 }}>
                        <div style={{ fontWeight: 700, color: "#f1f5f9", marginBottom: 4 }}>Setup Redis Cluster Sharding</div>
                        <div style={{ fontSize: 10, color: "var(--color-mute, #64748b)", marginBottom: 8 }}>Multi-node rate limiter failover state</div>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                          <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 4, background: "rgba(59, 130, 246, 0.15)", color: "#60a5fa", fontWeight: 700 }}>P2 Medium</span>
                          <PrettyAvatar preset="analyst" name="Architect" size={18} />
                        </div>
                      </div>
                    </div>

                    {/* In Progress */}
                    <div style={{ background: "rgba(56, 189, 248, 0.03)", borderRadius: 10, border: "1px solid rgba(56, 189, 248, 0.25)", padding: "10px", display: "flex", flexDirection: "column", gap: 8 }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 11.5, fontWeight: 700, color: "#38bdf8", paddingBottom: 6, borderBottom: "1px solid rgba(56, 189, 248, 0.15)" }}>
                        <span style={{ display: "flex", alignItems: "center", gap: 5 }}><PlayCircle size={12} /> In Progress</span>
                        <span style={{ fontSize: 10, background: "rgba(56, 189, 248, 0.2)", padding: "1px 6px", borderRadius: 9999, color: "#38bdf8" }}>2</span>
                      </div>
                      <div style={{ padding: "10px", borderRadius: 8, background: "#151829", border: "1px solid rgba(56, 189, 248, 0.35)", fontSize: 11.5, boxShadow: "0 4px 14px rgba(56, 189, 248, 0.1)" }}>
                        <div style={{ fontWeight: 700, color: "#f1f5f9", marginBottom: 4 }}>RS256 JWT Token Migration</div>
                        <div style={{ fontSize: 10, color: "var(--color-body, #94a3b8)", marginBottom: 8 }}>Asymmetric crypto signing in jwt_handler.py</div>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                          <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 4, background: "rgba(239, 68, 68, 0.15)", color: "#f87171", fontWeight: 700 }}>P0 Critical</span>
                          <PrettyAvatar preset="coder" name="Coder" size={18} />
                        </div>
                      </div>
                      <div style={{ padding: "10px", borderRadius: 8, background: "#121225", border: "1px solid var(--color-hairline, #2a2a3f)", fontSize: 11.5 }}>
                        <div style={{ fontWeight: 700, color: "#f1f5f9", marginBottom: 4 }}>Redis Token Bucket Limiter</div>
                        <div style={{ fontSize: 10, color: "var(--color-body, #94a3b8)", marginBottom: 8 }}>100 req/min sliding expiration window</div>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                          <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 4, background: "rgba(245, 158, 11, 0.15)", color: "#fbbf24", fontWeight: 700 }}>P1 High</span>
                          <PrettyAvatar preset="subagent" name="Sub-PythonDev" size={18} />
                        </div>
                      </div>
                    </div>

                    {/* Security Review */}
                    <div style={{ background: "rgba(251, 191, 36, 0.03)", borderRadius: 10, border: "1px solid rgba(251, 191, 36, 0.25)", padding: "10px", display: "flex", flexDirection: "column", gap: 8 }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 11.5, fontWeight: 700, color: "#fbbf24", paddingBottom: 6, borderBottom: "1px solid rgba(251, 191, 36, 0.15)" }}>
                        <span style={{ display: "flex", alignItems: "center", gap: 5 }}><ShieldCheck size={12} /> Security Review</span>
                        <span style={{ fontSize: 10, background: "rgba(251, 191, 36, 0.2)", padding: "1px 6px", borderRadius: 9999, color: "#fbbf24" }}>1</span>
                      </div>
                      <div style={{ padding: "10px", borderRadius: 8, background: "#181822", border: "1px solid rgba(251, 191, 36, 0.3)", fontSize: 11.5 }}>
                        <div style={{ fontWeight: 700, color: "#f1f5f9", marginBottom: 4 }}>Policy Matrix Shell Intercept</div>
                        <div style={{ fontSize: 10, color: "var(--color-body, #94a3b8)", marginBottom: 8 }}>Evaluating pytest test execution safety</div>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                          <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 4, background: "rgba(251, 191, 36, 0.15)", color: "#fbbf24", fontWeight: 700 }}>Evaluating</span>
                          <PrettyAvatar preset="judge" name="Judge AI" size={18} />
                        </div>
                      </div>
                    </div>

                    {/* Done */}
                    <div style={{ background: "rgba(16, 185, 129, 0.03)", borderRadius: 10, border: "1px solid rgba(16, 185, 129, 0.25)", padding: "10px", display: "flex", flexDirection: "column", gap: 8 }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 11.5, fontWeight: 700, color: "#34d399", paddingBottom: 6, borderBottom: "1px solid rgba(16, 185, 129, 0.15)" }}>
                        <span style={{ display: "flex", alignItems: "center", gap: 5 }}><CheckCircle size={12} /> Done</span>
                        <span style={{ fontSize: 10, background: "rgba(16, 185, 129, 0.2)", padding: "1px 6px", borderRadius: 9999, color: "#34d399" }}>3</span>
                      </div>
                      <div style={{ padding: "10px", borderRadius: 8, background: "#12191c", border: "1px solid rgba(16, 185, 129, 0.3)", fontSize: 11.5 }}>
                        <div style={{ fontWeight: 700, color: "#f1f5f9", marginBottom: 4 }}>Playwright E2E Auth Suite</div>
                        <div style={{ fontSize: 10, color: "#34d399", marginBottom: 8 }}>3 assertions passed in 1.84s</div>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                          <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 4, background: "rgba(16, 185, 129, 0.15)", color: "#34d399", fontWeight: 700 }}>Verified ✓</span>
                          <PrettyAvatar preset="qa" name="QA Runner" size={18} />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* VIEW 3: INBUILT FILE EXPLORER & AST DIFF VIEWER */}
              {activeScene === "explorer" && (
                <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", height: "100%", overflow: "hidden" }}>
                  <div style={{ background: "#0a0a1a", borderRight: "1px solid var(--color-hairline, #2a2a3f)", padding: "12px 10px", display: "flex", flexDirection: "column", gap: 6, fontSize: 11.5 }}>
                    <div style={{ fontSize: 10, fontWeight: 800, color: "var(--color-mute, #64748b)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>PROJECT FILES</div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, color: "#cbd5e1", fontWeight: 600, padding: "3px 6px" }}>
                      <span>📁</span> <span>backend/core</span>
                    </div>
                    <div style={{ marginLeft: 12, display: "flex", flexDirection: "column", gap: 4 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--color-body, #94a3b8)", padding: "2px 6px" }}>
                        <span>📁</span> <span>agent/</span>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, color: "#38bdf8", padding: "2px 6px" }}>
                        <span>🐍</span> <span>context_ast.py</span>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--color-body, #94a3b8)", padding: "2px 6px" }}>
                        <span>📁</span> <span>auth/</span>
                      </div>
                      <div style={{ marginLeft: 12, display: "flex", alignItems: "center", gap: 6, color: "#10b981", background: "rgba(16, 185, 129, 0.15)", padding: "3px 6px", borderRadius: 4, fontWeight: 700 }}>
                        <span>🐍</span> <span>jwt_handler.py</span>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, color: "#fbbf24", padding: "2px 6px" }}>
                        <span>📁</span> <span>file_backups/</span>
                      </div>
                      <div style={{ marginLeft: 12, display: "flex", alignItems: "center", gap: 6, color: "var(--color-body, #94a3b8)", padding: "2px 6px", fontSize: 10.5 }}>
                        <span>🛡️</span> <span>jwt.bak.178720</span>
                      </div>
                    </div>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
                    <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--color-hairline, #2a2a3f)", background: "#0a0a1a", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <div style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 10px", borderRadius: 6, background: "rgba(16, 185, 129, 0.15)", border: "1px solid rgba(16, 185, 129, 0.3)", fontSize: 11.5, color: "#34d399", fontWeight: 700 }}>
                          <FileCode size={13} />
                          <span>backend/core/auth/jwt_handler.py</span>
                        </div>
                        <span style={{ fontSize: 10, color: "var(--color-mute, #64748b)" }}>AST Validated • Rollback Snapshot Created</span>
                      </div>

                      <div style={{ display: "flex", gap: 4 }}>
                        <button onClick={() => setExplorerTab("diff")} style={{ padding: "3px 8px", borderRadius: 4, background: explorerTab === "diff" ? "rgba(255,255,255,0.1)" : "transparent", color: explorerTab === "diff" ? "#fff" : "var(--color-body, #94a3b8)", fontSize: 10.5, border: "none", cursor: "pointer" }}>
                          Diff Viewer (+34 -6)
                        </button>
                        <button onClick={() => setExplorerTab("history")} style={{ padding: "3px 8px", borderRadius: 4, background: explorerTab === "history" ? "rgba(255,255,255,0.1)" : "transparent", color: explorerTab === "history" ? "#fff" : "var(--color-body, #94a3b8)", fontSize: 10.5, border: "none", cursor: "pointer" }}>
                          Rollback History
                        </button>
                      </div>
                    </div>

                    <div style={{ flex: 1, padding: "12px 16px", background: "#030315", overflowY: "auto", fontFamily: "var(--font-mono, monospace)", fontSize: 11.5, lineHeight: 1.6 }}>
                      <div style={{ color: "#64748b", marginBottom: 6 }}>{"// Diff: RS256 Asymmetric Token Signing & Sliding Expiration"}</div>
                      <div style={{ background: "rgba(239, 68, 68, 0.12)", color: "#f87171", padding: "1px 6px" }}>{"- def encode_token(payload: dict) -> str:"}</div>
                      <div style={{ background: "rgba(239, 68, 68, 0.12)", color: "#f87171", padding: "1px 6px" }}>{"-     return jwt.encode(payload, SECRET_KEY, algorithm='HS256')"}</div>
                      <div style={{ background: "rgba(16, 185, 129, 0.15)", color: "#34d399", padding: "1px 6px" }}>{"+ def encode_token(payload: dict, private_key: str) -> str:"}</div>
                      <div style={{ background: "rgba(16, 185, 129, 0.15)", color: "#34d399", padding: "1px 6px" }}>{"+     headers = { 'alg': 'RS256', 'typ': 'JWT' }"}</div>
                      <div style={{ background: "rgba(16, 185, 129, 0.15)", color: "#34d399", padding: "1px 6px" }}>{"+     return jwt.encode(payload, private_key, algorithm='RS256', headers=headers)"}</div>
                      <div style={{ color: "#94a3b8", padding: "1px 6px" }}>{" "}</div>
                      <div style={{ background: "rgba(16, 185, 129, 0.15)", color: "#34d399", padding: "1px 6px" }}>{"+ async def check_rate_limit(redis_client, user_id: str, limit: int = 100) -> bool:"}</div>
                      <div style={{ background: "rgba(16, 185, 129, 0.15)", color: "#34d399", padding: "1px 6px" }}>{"+     key = f'rate_limit:{user_id}'"}</div>
                      <div style={{ background: "rgba(16, 185, 129, 0.15)", color: "#34d399", padding: "1px 6px" }}>{"+     current = await redis_client.incr(key)"}</div>
                      <div style={{ background: "rgba(16, 185, 129, 0.15)", color: "#34d399", padding: "1px 6px" }}>{"+     if current == 1: await redis_client.expire(key, 60)"}</div>
                      <div style={{ background: "rgba(16, 185, 129, 0.15)", color: "#34d399", padding: "1px 6px" }}>{"+     return current <= limit"}</div>
                    </div>
                  </div>
                </div>
              )}

              {/* VIEW 4: INTEGRATED TERMINAL & GIT BRANCH CONTROL */}
              {activeScene === "terminal" && (
                <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "14px 18px", background: "#030315" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div style={{ fontSize: 13, fontWeight: 800, color: "#ffffff", display: "flex", alignItems: "center", gap: 6 }}>
                        <Terminal size={14} color="#f472b6" />
                        <span>Interactive Engineering PTY Shell & Git Control</span>
                      </div>
                      <span style={{ fontSize: 10, color: "#34d399", display: "flex", alignItems: "center", gap: 4 }}>
                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#34d399" }} /> PTY Online
                      </span>
                    </div>

                    <div style={{ display: "flex", gap: 4 }}>
                      <button onClick={() => setTerminalTab("pytest")} style={{ padding: "3px 9px", borderRadius: 4, background: terminalTab === "pytest" ? "rgba(244, 114, 182, 0.2)" : "transparent", color: terminalTab === "pytest" ? "#f472b6" : "var(--color-body, #94a3b8)", fontSize: 11, border: "1px solid rgba(244, 114, 182, 0.3)", cursor: "pointer" }}>
                        pytest (test runner)
                      </button>
                      <button onClick={() => setTerminalTab("git")} style={{ padding: "3px 9px", borderRadius: 4, background: terminalTab === "git" ? "rgba(244, 114, 182, 0.2)" : "transparent", color: terminalTab === "git" ? "#f472b6" : "var(--color-body, #94a3b8)", fontSize: 11, border: "1px solid var(--color-hairline, #2a2a3f)", cursor: "pointer" }}>
                        git (branch graph)
                      </button>
                      <button onClick={() => setTerminalTab("playwright")} style={{ padding: "3px 9px", borderRadius: 4, background: terminalTab === "playwright" ? "rgba(244, 114, 182, 0.2)" : "transparent", color: terminalTab === "playwright" ? "#f472b6" : "var(--color-body, #94a3b8)", fontSize: 11, border: "1px solid var(--color-hairline, #2a2a3f)", cursor: "pointer" }}>
                        Playwright (headless)
                      </button>
                    </div>
                  </div>

                  <div style={{ flex: 1, padding: "12px 14px", borderRadius: 8, background: "#0a0a1a", border: "1px solid var(--color-hairline, #2a2a3f)", fontFamily: "var(--font-mono, monospace)", fontSize: 11, lineHeight: 1.5, overflowY: "auto" }}>
                    {terminalTab === "pytest" && (
                      <>
                        <div style={{ color: "var(--color-body, #94a3b8)" }}>$ pytest tests/test_jwt_auth.py --cov=backend/core/auth -v</div>
                        <div style={{ color: "#64748b", margin: "4px 0" }}>============================= test session starts ==============================</div>
                        <div style={{ color: "#38bdf8" }}>rootdir: c:/Users/sanko/OneDrive/Desktop/Carole.ai</div>
                        <div style={{ color: "#38bdf8" }}>collected 24 items</div>
                        <div style={{ color: "#34d399", margin: "4px 0" }}>tests/test_jwt_auth.py::test_rs256_keypair_generation PASSED           [  4%]</div>
                        <div style={{ color: "#34d399" }}>tests/test_jwt_auth.py::test_sliding_expiration_refresh PASSED         [  8%]</div>
                        <div style={{ color: "#34d399" }}>tests/test_jwt_auth.py::test_redis_rate_limit_throttle PASSED         [ 12%]</div>
                        <div style={{ color: "#34d399" }}>tests/test_jwt_auth.py::test_dead_end_ast_pruner PASSED                [ 16%]</div>
                        <div style={{ color: "#34d399" }}>tests/test_jwt_auth.py::test_judge_ai_permission_matrix PASSED        [100%]</div>
                        <div style={{ color: "#34d399", fontWeight: 700, marginTop: 8 }}>======================== 24 passed in 0.94s (100% cov) ========================</div>
                      </>
                    )}

                    {terminalTab === "git" && (
                      <>
                        <div style={{ color: "var(--color-body, #94a3b8)" }}>$ git log --graph --oneline --decorate -n 5</div>
                        <div style={{ color: "#38bdf8" }}>* 78f9a2b (HEAD -&gt; feature/rs256-jwt-redis-auth) feat: implement RS256 token signing and Redis bucket</div>
                        <div style={{ color: "#a855f7" }}>* 52c1e09 (origin/main, main) chore: prune dead-end ast nodes in ReAct context</div>
                        <div style={{ color: "#64748b" }}>* 31b87a1 docs: update GraphRAG LanceDB schema definitions</div>
                        <div style={{ color: "#34d399", marginTop: 8 }}>Branch clean. 0 uncommitted changes. Ready for automated merge.</div>
                      </>
                    )}

                    {terminalTab === "playwright" && (
                      <>
                        <div style={{ color: "var(--color-body, #94a3b8)" }}>$ npx playwright test tests/e2e/auth.spec.ts --project=chromium</div>
                        <div style={{ color: "#38bdf8" }}>Running 3 tests using 1 worker</div>
                        <div style={{ color: "#34d399" }}>[chromium] › auth.spec.ts:12:5 › User login flow with RS256 token (840ms)</div>
                        <div style={{ color: "#34d399" }}>[chromium] › auth.spec.ts:28:5 › Silent background token refresh cycle (520ms)</div>
                        <div style={{ color: "#34d399" }}>[chromium] › auth.spec.ts:46:5 › Exceeding 100 req/min triggers HTTP 429 (480ms)</div>
                        <div style={{ color: "#34d399", fontWeight: 700, marginTop: 8 }}>3 passed (1.84s) ✓ Verified zero regressions.</div>
                      </>
                    )}
                  </div>
                </div>
              )}

              {/* VIEW 5: JUDGE AI SECURITY GATE */}
              {activeScene === "security" && (
                <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "16px 18px", background: "#030315" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
                    <div>
                      <div style={{ fontSize: 14.5, fontWeight: 800, color: "#ffffff", display: "flex", alignItems: "center", gap: 8 }}>
                        <ShieldCheck size={16} color="#fbbf24" />
                        <span>Judge AI Real-Time Security Interceptor</span>
                        <span style={{ fontSize: 9.5, padding: "2px 6px", borderRadius: 9999, background: "rgba(251, 191, 36, 0.2)", border: "1px solid rgba(251, 191, 36, 0.4)", color: "#fbbf24", fontWeight: 700 }}>
                          MULTI-TIER POLICY MATRIX
                        </span>
                      </div>
                      <div style={{ fontSize: 11, color: "var(--color-body, #94a3b8)" }}>Automated risk scoring intercepts destructive shell commands, git operations, and DB mutations.</div>
                    </div>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    <div style={{ padding: "12px", borderRadius: 8, background: "rgba(16, 185, 129, 0.05)", border: "1px solid rgba(16, 185, 129, 0.25)" }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                        <span style={{ fontSize: 12, fontWeight: 700, color: "#34d399" }}>Tier 1: Safe (Auto-Execute)</span>
                        <span style={{ fontSize: 9, padding: "1px 5px", background: "rgba(16,185,129,0.2)", color: "#34d399", borderRadius: 4 }}>Score &lt; 0.2</span>
                      </div>
                      <div style={{ fontSize: 11, color: "#cbd5e1", lineHeight: 1.4 }}>
                        Read-only file I/O, unit test executions (<code>pytest</code>), code search queries, and memory vector recall.
                      </div>
                    </div>

                    <div style={{ padding: "12px", borderRadius: 8, background: "rgba(239, 68, 68, 0.05)", border: "1px solid rgba(239, 68, 68, 0.25)" }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                        <span style={{ fontSize: 12, fontWeight: 700, color: "#f87171" }}>Tier 2: Gated (Human Card)</span>
                        <span style={{ fontSize: 9, padding: "1px 5px", background: "rgba(239,68,68,0.2)", color: "#f87171", borderRadius: 4 }}>Score &ge; 0.7</span>
                      </div>
                      <div style={{ fontSize: 11, color: "#cbd5e1", lineHeight: 1.4 }}>
                        Destructive git push force, file deletions (<code>rm -rf</code>), production DB migrations, and external API webhook triggers.
                      </div>
                    </div>
                  </div>

                  <div style={{ marginTop: 12, padding: "12px 14px", borderRadius: 8, background: "#0a0a1a", border: "1px solid rgba(251, 191, 36, 0.3)" }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#fbbf24", marginBottom: 4 }}>LIVE AUDIT STREAM:</div>
                    <div style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11, color: "#f1f5f9" }}>
                      Tool Call: <code>execute_command(command=&quot;pytest tests/test_jwt_auth.py&quot;)</code>
                    </div>
                    <div style={{ fontSize: 10.5, color: "#34d399", marginTop: 4 }}>
                      ✓ Evaluated: Risk score 0.04 (SAFE). Auto-approved with zero human intervention required.
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </MagneticCard>
  );
}
