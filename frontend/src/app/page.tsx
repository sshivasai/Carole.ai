"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import styles from "./page.module.css";
import { useWebSocket } from "@/hooks/useWebSocket";
import { api } from "@/hooks/useApi";
import type {
  ChatMessage, AgentConfig, TaskItem, WSEvent,
  FileChangeEvent, ApprovalRequestEvent, BrowserScreenshotEvent, LearningItem,
} from "@/lib/types";

// ---- Color map for agent avatars ----
const AVATAR_COLORS = ["#5b6cff", "#9b6dff", "#34d399", "#fb923c", "#f87171", "#fbbf24"];
function avatarColor(name: string) {
  let hash = 0;
  for (const ch of name) hash = ch.charCodeAt(0) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

export default function Home() {
  // ---- State ----
  const [userId, setUserId] = useState<string | null>(null);
  const [users, setUsers] = useState<any[]>([]);

  // ---- 2D Collaborative Board Canvas States ----
  const [viewMode, setViewMode] = useState<"playground" | "split">("playground");
  const [visualLevel, setVisualLevel] = useState<"organizations" | "projects" | "table">("organizations");
  const [hoveredAgentId, setHoveredAgentId] = useState<string | null>(null);
  const [isChatDrawerOpen, setIsChatDrawerOpen] = useState(false);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projects, setProjects] = useState<any[]>([]);
  const [teamId, setTeamId] = useState<string | null>(null);
  const [teams, setTeams] = useState<any[]>([]);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [learnings, setLearnings] = useState<LearningItem[]>([]);
  const [inputText, setInputText] = useState("");
  const [loading, setLoading] = useState(true);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, string>>({});
  const [typingAgents, setTypingAgents] = useState<Set<string>>(new Set());
  const [rightTab, setRightTab] = useState<"tasks" | "diffs" | "browser" | "knowledge">("tasks");
  const [diffs, setDiffs] = useState<FileChangeEvent[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<ApprovalRequestEvent[]>([]);
  const [browserScreenshots, setBrowserScreenshots] = useState<BrowserScreenshotEvent[]>([]);
  const [showAddAgent, setShowAddAgent] = useState(false);
  const [showAddTenant, setShowAddTenant] = useState(false);
  const [showAddProject, setShowAddProject] = useState(false);
  const [showAddTeam, setShowAddTeam] = useState(false);
  const [showAddKnowledge, setShowAddKnowledge] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ---- WebSocket ----
  const { connected, events, sendMessage } = useWebSocket(teamId);

  // ---- Init: Seed & Load ----
  useEffect(() => {
    async function init() {
      try {
        await api.seedDemo();
        
        const usrs = await api.listUsers();
        setUsers(usrs);
        if (usrs.length > 0) {
          setUserId(usrs[0].id);
        }

        const projs = await api.listProjects();
        setProjects(projs);
        if (projs.length > 0) {
          setProjectId(projs[0].id);
        }
      } catch (e) {
        console.error("Init load error:", e);
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  // ---- Load Teams & Learnings when Project changes ----
  useEffect(() => {
    if (!projectId) return;
    const activeProj = projectId;
    async function loadProjectData() {
      try {
        const tms = await api.listTeams(activeProj);
        setTeams(tms);
        if (tms.length > 0) {
          setTeamId(tms[0].id);
        } else {
          setTeamId(null);
          setAgents([]);
          setMessages([]);
          setTasks([]);
        }

        const lrns = await api.listLearnings(activeProj);
        setLearnings(lrns);
      } catch (e) {
        console.error("Load project data error:", e);
      }
    }
    loadProjectData();
  }, [projectId]);

  // ---- Load Agents, Messages, Tasks when Team changes ----
  useEffect(() => {
    if (!teamId) return;
    const activeTeam = teamId;
    async function loadTeamData() {
      try {
        const agts = await api.listAgents(activeTeam);
        setAgents(agts);

        const msgs = await api.listMessages(activeTeam);
        setMessages(msgs.map((m: any) => ({
          ...m, type: "message",
          sender_name: agts.find((a: AgentConfig) => a.id === m.sender_id)?.name,
          role: agts.find((a: AgentConfig) => a.id === m.sender_id)?.role,
        })));

        const tks = await api.listTasks(activeTeam);
        setTasks(tks);
      } catch (e) {
        console.error("Load team data error:", e);
      }
    }
    loadTeamData();
  }, [teamId]);

  // ---- Process WS events ----
  useEffect(() => {
    if (events.length === 0) return;
    const latest = events[events.length - 1];
    processEvent(latest);
  }, [events]);

  const processEvent = useCallback((evt: WSEvent) => {
    const senderId = evt.sender_id || "unknown";
    const senderName = evt.sender_name || (senderId === "human" ? "You" : "Agent");
    const text = evt.text || "";

    switch (evt.type) {
      case "message":
        setMessages((prev) => [...prev, {
          id: Date.now().toString(),
          sender_id: senderId,
          sender_name: senderName,
          text: text,
          role: evt.role || undefined,
          type: "message",
        }]);
        setTypingAgents((prev) => { const n = new Set(prev); n.delete(senderId); return n; });
        break;

      case "typing":
        setTypingAgents((prev) => new Set(prev).add(senderId));
        break;

      case "thought_delta":
        // Accumulate thought into the last message from this agent
        setMessages((prev) => {
          const last = [...prev];
          const existingIdx = last.findLastIndex(
            (m) => m.sender_id === senderId && m.type === "thought"
          );
          if (existingIdx >= 0) {
            last[existingIdx] = { ...last[existingIdx], text: (last[existingIdx].text || "") + (evt.delta || "") };
          } else {
            last.push({
              id: Date.now().toString(),
              sender_id: senderId,
              sender_name: senderName,
              text: evt.delta || "",
              role: evt.role || undefined,
              type: "thought",
            });
          }
          return last;
        });
        break;

      case "agent_status":
        setAgentStatuses((prev) => ({ ...prev, [senderId]: evt.status || "idle" }));
        if (evt.status === "idle") {
          setTypingAgents((prev) => { const n = new Set(prev); n.delete(senderId); return n; });
        }
        break;

      case "tool_start":
        setMessages((prev) => [...prev, {
          id: Date.now().toString(),
          sender_id: senderId,
          sender_name: senderName,
          text: `Running \`${evt.tool_name || "tool"}\`...`,
          type: "tool_start",
          tool_name: evt.tool_name || "tool",
          arguments: evt.arguments || {},
        }]);
        break;

      case "tool_end":
        setMessages((prev) => [...prev, {
          id: Date.now().toString(),
          sender_id: senderId,
          sender_name: senderName,
          text: evt.observation || "",
          type: "tool_end",
          tool_name: evt.tool_name || "tool",
          observation: evt.observation || "",
        }]);
        break;

      case "file_change":
        const fc = evt as FileChangeEvent;
        setDiffs((prev) => [fc, ...prev]);
        setMessages((prev) => [...prev, {
          id: Date.now().toString(),
          sender_id: fc.sender_id || "unknown",
          sender_name: fc.sender_name || "Agent",
          text: fc.diff || "",
          type: "file_change",
          path: fc.path || "",
          action: fc.action || "edit",
          diff: fc.diff || "",
        }]);
        break;

      case "approval_request":
        const ar = evt as ApprovalRequestEvent;
        setPendingApprovals((prev) => [...prev, ar]);
        setMessages((prev) => [...prev, {
          id: Date.now().toString(),
          sender_id: ar.agent_id || "agent",
          sender_name: ar.agent_name || "Agent",
          text: ar.text || "",
          type: "approval_request",
          tx_id: ar.tx_id || "",
          tool_name: ar.tool_name || "tool",
          arguments: ar.arguments || {},
        }]);
        break;

      case "browser_screenshot":
        const bs = evt as BrowserScreenshotEvent;
        setBrowserScreenshots((prev) => [bs, ...prev.slice(0, 9)]);
        setMessages((prev) => [...prev, {
          id: Date.now().toString(),
          sender_id: bs.sender_id || "unknown",
          sender_name: bs.sender_name || "Agent",
          text: `Browsing: ${bs.url || ""}`,
          type: "browser_screenshot",
          image_base64: bs.image_base64 || "",
        }]);
        break;

      case "shell_output":
        setMessages((prev) => [...prev, {
          id: Date.now().toString(),
          sender_id: "system",
          text: text,
          type: "shell_output",
          stream: evt.stream === "stderr" ? "stderr" : "stdout",
        }]);
        break;

      case "task_update":
        if (evt.task) {
          const activeTask = evt.task;
          if (evt.action === "created") {
            setTasks((prev) => [activeTask, ...prev]);
          } else if (evt.action === "updated") {
            setTasks((prev) => prev.map((t) => t.id === activeTask.id ? { ...t, ...activeTask } : t));
          }
        }
        break;

      case "agent_question":
        setMessages((prev) => [...prev, {
          id: Date.now().toString(),
          sender_id: evt.agent_id || senderId,
          sender_name: evt.agent_name || senderName,
          text: text,
          type: "agent_question",
          tx_id: evt.question_id || "",
        }]);
        break;
    }
  }, []);

  // ---- Auto-scroll ----
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ---- Send ----
  const handleSend = () => {
    if (!inputText.trim()) return;
    sendMessage(inputText.trim());
    setMessages((prev) => [...prev, {
      id: Date.now().toString(),
      sender_id: "human",
      sender_name: "You",
      text: inputText.trim(),
      type: "message",
    }]);
    setInputText("");
  };

  const handleApproval = async (txId: string, approved: boolean) => {
    try {
      await api.approveToolExecution(txId, approved);
      setPendingApprovals((prev) => prev.filter((a) => a.tx_id !== txId));
    } catch (e) {
      console.error("Approval error:", e);
    }
  };

  const handleAnswer = async (questionId: string, answer: string) => {
    try {
      await api.answerAgentQuestion(questionId, answer);
    } catch (e) {
      console.error("Answer error:", e);
    }
  };

  // ---- Loading ----
  if (loading) {
    return (
      <div className={styles.setupBanner}>
        <h1>Carole.ai</h1>
        <p>Initializing multi-agent platform...</p>
      </div>
    );
  }

  if (!teamId && viewMode === "split") {
    return (
      <div className={styles.setupBanner}>
        <h1>Carole.ai</h1>
        <p>No team found. Make sure the backend is running and the database is seeded.</p>
        <button className="btn btn-primary" onClick={() => window.location.reload()}>Retry</button>
      </div>
    );
  }

  // ---- Render ----
  return (
    <div className={styles.page}>
      
      {/* 1. Toggle Deck (View Switcher) - Floating over the page */}
      <div className={styles.toggleDeck} style={{ position: "absolute", top: "20px", right: "20px", zIndex: 100 }}>
        <button 
          className={`${styles.toggleBtn} ${viewMode === "playground" ? styles.toggleBtnActive : ""}`} 
          onClick={() => setViewMode("playground")}
        >
          Playground ⚡
        </button>
        <button 
          className={`${styles.toggleBtn} ${viewMode === "split" ? styles.toggleBtnActive : ""}`} 
          onClick={() => {
            setViewMode("split");
            setIsChatDrawerOpen(false);
          }}
        >
          Split View 📊
        </button>
      </div>

      {viewMode === "playground" ? (
        /* ==================== PLAYGROUND VIEW ==================== */
        <div className={styles.playgroundContainer}>
          <div className={styles.playgroundGrid} />

          {/* Floating Breadcrumbs */}
          <div className={styles.visualBreadcrumbs}>
            <span 
              className={`${styles.breadcrumbSegment} ${visualLevel === "organizations" ? styles.breadcrumbActive : ""}`}
              onClick={() => {
                setVisualLevel("organizations");
                setShowAddTenant(false);
                setShowAddProject(false);
                setShowAddTeam(false);
              }}
            >
              Organizations 🌐
            </span>
            {userId && (
              <>
                <span className={styles.breadcrumbSeparator}>&gt;</span>
                <span 
                  className={`${styles.breadcrumbSegment} ${visualLevel === "projects" ? styles.breadcrumbActive : ""}`}
                  onClick={() => {
                    setVisualLevel("projects");
                    setShowAddTenant(false);
                    setShowAddProject(false);
                    setShowAddTeam(false);
                  }}
                >
                  {users.find(u => u.id === userId)?.email.split("@")[0].toUpperCase() || "Active Org"} 🏢
                </span>
              </>
            )}
            {projectId && (
              <>
                <span className={styles.breadcrumbSeparator}>&gt;</span>
                <span 
                  className={`${styles.breadcrumbSegment} ${visualLevel === "table" ? styles.breadcrumbActive : ""}`}
                  onClick={() => {
                    setVisualLevel("table");
                    setShowAddTenant(false);
                    setShowAddProject(false);
                    setShowAddTeam(false);
                  }}
                >
                  {projects.find(p => p.id === projectId)?.name || "Active Project"} 📁
                </span>
              </>
            )}
          </div>

          {/* LEVEL 1: Organizations Bubbles */}
          {visualLevel === "organizations" && (
            <div className={styles.bubbleCluster}>
              {users.map((usr) => (
                <div 
                  key={usr.id} 
                  className={styles.glowBubble}
                  onClick={() => {
                    setUserId(usr.id);
                    setVisualLevel("projects");
                  }}
                >
                  <span className={styles.glowBubbleIcon}>🏢</span>
                  <div className={styles.glowBubbleText}>{usr.email.split("@")[0].toUpperCase()}</div>
                  <div className={styles.glowBubbleDomain}>{usr.email.split("@")[1] || "domain.ai"}</div>
                </div>
              ))}

              {/* Quick Tenant creation bubble */}
              <div 
                className={styles.glowBubble}
                style={{ borderStyle: "dashed", borderColor: "var(--accent-blue)", background: "rgba(91, 108, 255, 0.05)" }}
                onClick={() => setShowAddTenant(true)}
              >
                <span className={styles.glowBubbleIcon} style={{ filter: "none", animation: "none" }}>➕</span>
                <div className={styles.glowBubbleText} style={{ color: "var(--accent-blue)" }}>New Org</div>
              </div>

              {/* Overlay form to create new tenant domain */}
              {showAddTenant && (
                <div className={styles.playgroundOverlayForm} style={{ position: "absolute", zIndex: 110, width: "300px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                    <div style={{ fontSize: "13px", fontWeight: "700" }}>Launch New Organization</div>
                    <button onClick={() => setShowAddTenant(false)} style={{ background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer" }}>✕</button>
                  </div>
                  <input id="pg-tenant-email" className="input" placeholder="e.g. sales@tesla.com" style={{ fontSize: "12px", marginBottom: "8px" }} />
                  <button 
                    className="btn btn-primary"
                    style={{ width: "100%", fontSize: "12px" }}
                    onClick={async () => {
                      const email = (document.getElementById("pg-tenant-email") as HTMLInputElement).value.trim();
                      if (!email) return;
                      try {
                        const res = await api.createUser(email, email.split("@")[0]);
                        setUsers(prev => [res, ...prev]);
                        setUserId(res.id);
                        setShowAddTenant(false);
                        setVisualLevel("projects");
                      } catch (e) { console.error(e); }
                    }}
                  >
                    ✓ Launch Domain
                  </button>
                </div>
              )}
            </div>
          )}

          {/* LEVEL 2: Satellite Project Orbits */}
          {visualLevel === "projects" && (
            <div className={styles.orbitContainer}>
              {/* Central Org node */}
              <div className={styles.centralOrgNode} onClick={() => setVisualLevel("organizations")}>
                <span style={{ fontSize: "28px" }}>🏢</span>
                <div style={{ fontSize: "11px", fontWeight: "700", marginTop: "4px" }}>
                  {users.find(u => u.id === userId)?.email.split("@")[0].toUpperCase() || "ORG"}
                </div>
                <span style={{ fontSize: "9px", opacity: 0.6, marginTop: "2px" }}>Back to Orgs</span>
              </div>

              {/* Satellite Project Orbits */}
              {(() => {
                const visibleProjects = projects;
                return (
                  <>
                    {/* SVG connections */}
                    <svg className={styles.orbitCanvas}>
                      {visibleProjects.map((p, idx) => {
                        const totalNodes = visibleProjects.length + 1; // +1 for the "add new project" node
                        const angle = (idx * 2 * Math.PI) / totalNodes;
                        const radius = 180;
                        const targetX = 290 + Math.cos(angle) * radius;
                        const targetY = 190 + Math.sin(angle) * radius;
                        return (
                          <line 
                            key={p.id} 
                            x1={290} y1={190} 
                            x2={targetX} y2={targetY} 
                            stroke="rgba(155, 109, 255, 0.25)" 
                            strokeWidth="2" 
                            strokeDasharray="4 4" 
                          />
                        );
                      })}
                      {/* Connection to the Add node */}
                      {(() => {
                        const totalNodes = visibleProjects.length + 1;
                        const angle = (visibleProjects.length * 2 * Math.PI) / totalNodes;
                        const radius = 180;
                        const targetX = 290 + Math.cos(angle) * radius;
                        const targetY = 190 + Math.sin(angle) * radius;
                        return (
                          <line 
                            x1={290} y1={190} 
                            x2={targetX} y2={targetY} 
                            stroke="rgba(91, 108, 255, 0.25)" 
                            strokeWidth="2" 
                            strokeDasharray="4 4" 
                          />
                        );
                      })()}
                    </svg>

                    {/* Project Orbit Nodes */}
                    {visibleProjects.map((p, idx) => {
                      const totalNodes = visibleProjects.length + 1;
                      const angle = (idx * 2 * Math.PI) / totalNodes;
                      const radius = 180;
                      const topPos = 190 + Math.sin(angle) * radius - 50; // centering correction
                      const leftPos = 290 + Math.cos(angle) * radius - 75;
                      const isActive = p.id === projectId;

                      return (
                        <div 
                          key={p.id}
                          className={`${styles.projectOrbitNode} ${isActive ? styles.projectOrbitNodeActive : ""}`}
                          style={{ top: `${topPos}px`, left: `${leftPos}px` }}
                          onClick={() => {
                            setProjectId(p.id);
                            setVisualLevel("table");
                          }}
                        >
                          <span style={{ fontSize: "20px" }}>📁</span>
                          <div className={styles.projectCardName} style={{ margin: 0, width: "100%" }}>{p.name}</div>
                          <div style={{ fontSize: "10px", color: "var(--text-tertiary)" }}>Open Table View →</div>
                        </div>
                      );
                    })}

                    {/* Add Project Orbit Node */}
                    {(() => {
                      const totalNodes = visibleProjects.length + 1;
                      const angle = (visibleProjects.length * 2 * Math.PI) / totalNodes;
                      const radius = 180;
                      const topPos = 190 + Math.sin(angle) * radius - 50;
                      const leftPos = 290 + Math.cos(angle) * radius - 75;

                      return (
                        <div 
                          className={styles.projectOrbitNode}
                          style={{ 
                            top: `${topPos}px`, 
                            left: `${leftPos}px`, 
                            borderStyle: "dashed", 
                            borderColor: "var(--accent-blue)",
                            background: "rgba(91,108,255,0.02)"
                          }}
                          onClick={() => setShowAddProject(true)}
                        >
                          <span style={{ fontSize: "20px", color: "var(--accent-blue)" }}>➕</span>
                          <div className={styles.projectCardName} style={{ margin: 0, color: "var(--accent-blue)" }}>New Project</div>
                          <div style={{ fontSize: "10px", color: "var(--text-tertiary)" }}>Launch Workspace Node</div>
                        </div>
                      );
                    })()}

                    {/* Overlay form to create new project */}
                    {showAddProject && (
                      <div className={styles.playgroundOverlayForm} style={{ position: "absolute", zIndex: 110, width: "300px" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                          <div style={{ fontSize: "13px", fontWeight: "700" }}>Start Workspace Project</div>
                          <button onClick={() => setShowAddProject(false)} style={{ background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer" }}>✕</button>
                        </div>
                        <input id="pg-project-name" className="input" placeholder="e.g. LLM Reasoning Agent" style={{ fontSize: "12px", marginBottom: "8px" }} />
                        <button 
                          className="btn btn-primary"
                          style={{ width: "100%", fontSize: "12px" }}
                          onClick={async () => {
                            const name = (document.getElementById("pg-project-name") as HTMLInputElement).value.trim();
                            if (!name) return;
                            try {
                              const res = await api.createProject(name, userId || undefined);
                              setProjects(prev => [res, ...prev]);
                              setProjectId(res.id);
                              setShowAddProject(false);
                              setVisualLevel("table");
                            } catch (e) { console.error(e); }
                          }}
                        >
                          ✓ Initialize Node
                        </button>
                      </div>
                    )}
                  </>
                );
              })()}
            </div>
          )}

          {/* LEVEL 3: Virtual Conference Table */}
          {visualLevel === "table" && (
            <div className={styles.tableContainer}>
              <div className={styles.roomTagLine}>
                🛰️ Active Project Space: {projects.find(p => p.id === projectId)?.name || "WORKSPACE"}
              </div>

              <div className={styles.conferenceTableWrapper}>
                {/* Conference Oval desk */}
                <div 
                  className={styles.conferenceTable}
                  onClick={() => setIsChatDrawerOpen(true)}
                >
                  <div className={styles.holoPulseNode} />
                  <div className={styles.holoCore}>
                    <span>📡 CORE</span>
                  </div>
                  <div className={styles.tableInstructions}>
                    Group Chat Room
                  </div>
                  <div style={{ fontSize: "10px", color: "var(--text-tertiary)", marginTop: "4px" }}>
                    Click Desk to open logs & terminal ✕
                  </div>
                </div>

                {/* Seated Bot Avatars placement */}
                {agents.map((agent, idx) => {
                  const angle = (idx * 2 * Math.PI) / (agents.length || 1);
                  const rx = 240; // horizontal radius
                  const ry = 140; // vertical radius
                  const topPos = 190 + Math.sin(angle) * ry - 30;
                  const leftPos = 290 + Math.cos(angle) * rx - 30;
                  const status = agentStatuses[agent.id] || "idle";

                  return (
                    <div 
                      key={agent.id}
                      className={styles.botAvatarSeat}
                      style={{ top: `${topPos}px`, left: `${leftPos}px` }}
                      onMouseEnter={() => setHoveredAgentId(agent.id)}
                      onMouseLeave={() => setHoveredAgentId(null)}
                      onClick={(e) => {
                        e.stopPropagation();
                        setIsChatDrawerOpen(true);
                      }}
                    >
                      {/* Glow ring based on status */}
                      <div className={`${styles.seatGlowRing} ${status === "thinking" ? styles.thinking : styles.idle}`} />

                      {/* Avatar sphere */}
                      <div className={styles.seatAvatarCircle} style={{ background: avatarColor(agent.name) }}>
                        {agent.name[0]}
                      </div>

                      {/* Active green/yellow dot */}
                      <div className={`${styles.seatActiveLight} ${status === "thinking" ? styles.thinking : ""}`} />

                      {/* Typing indicator inside seat */}
                      {typingAgents.has(agent.id) && (
                        <div className={styles.seatTypingIndicator}>
                          <span /><span /><span />
                        </div>
                      )}

                      {/* Frosted Hover card details */}
                      {hoveredAgentId === agent.id && (
                        <div className={styles.agentHoverCard} onClick={(e) => e.stopPropagation()}>
                          <div className={styles.hoverCardHeader}>
                            <div className={styles.hoverCardAvatar} style={{ background: avatarColor(agent.name) }}>
                              {agent.name[0]}
                            </div>
                            <div className={styles.hoverCardTitle}>
                              <h4>{agent.name}</h4>
                              <p>{agent.role}</p>
                            </div>
                          </div>

                          <div className={styles.hoverCardSection}>
                            <label>Model System</label>
                            <span className={styles.hoverCardModelBadge}>{agent.model}</span>
                          </div>

                          {agent.skills && agent.skills.length > 0 && (
                            <div className={styles.hoverCardSection}>
                              <label>Engine Skills</label>
                              <div className={styles.hoverCardSkillsList}>
                                {agent.skills.map((s, i) => (
                                  <span key={i} className={styles.hoverCardSkillBadge}>{s}</span>
                                ))}
                              </div>
                            </div>
                          )}

                          {agent.custom_instructions && (
                            <div className={styles.hoverCardSection} style={{ marginBottom: 0 }}>
                              <label>Directives</label>
                              <div className={styles.hoverCardInstructions}>
                                {agent.custom_instructions}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Fast Team Creation Room and invite bots pill floating */}
              <div style={{ display: "flex", gap: "10px", marginTop: "30px", zIndex: 10 }}>
                <button 
                  className="btn btn-primary"
                  style={{ fontSize: "12px", background: "linear-gradient(135deg, var(--accent-blue), var(--accent-purple))" }}
                  onClick={() => {
                    setIsChatDrawerOpen(true);
                    setShowAddAgent(true);
                  }}
                >
                  ➕ Commission AI Agent to Table
                </button>
                <button 
                  className="btn btn-ghost"
                  style={{ fontSize: "12px", background: "rgba(255,255,255,0.05)" }}
                  onClick={() => {
                    setShowAddTeam(true);
                  }}
                >
                  📡 Switch/Launch Active Room
                </button>
              </div>

              {/* Overlay form to create new team room */}
              {showAddTeam && (
                <div className={styles.playgroundOverlayForm} style={{ position: "absolute", zIndex: 110, width: "320px", bottom: "80px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                    <div style={{ fontSize: "13px", fontWeight: "700" }}>Launch Active Team Room</div>
                    <button onClick={() => setShowAddTeam(false)} style={{ background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer" }}>✕</button>
                  </div>
                  <input id="pg-team-name" className="input" placeholder="e.g. backend-dev" style={{ fontSize: "12px", marginBottom: "8px" }} />
                  <button 
                    className="btn btn-primary"
                    style={{ width: "100%", fontSize: "12px" }}
                    onClick={async () => {
                      const name = (document.getElementById("pg-team-name") as HTMLInputElement).value.trim();
                      if (!name || !projectId) return;
                      try {
                        const res = await api.createTeam(name, projectId);
                        setTeams(prev => [res, ...prev]);
                        setTeamId(res.id);
                        setShowAddTeam(false);
                      } catch (e) { console.error(e); }
                    }}
                  >
                    ✓ Open Room Channel
                  </button>
                  <div style={{ fontSize: "11px", color: "var(--text-tertiary)", marginTop: "8px", borderTop: "1px solid var(--border-subtle)", paddingTop: "8px" }}>
                    Existing Rooms:
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "6px", maxHeight: "100px", overflowY: "auto" }}>
                    {teams.map(t => (
                      <span 
                        key={t.id} 
                        style={{ cursor: "pointer", fontSize: "11px", padding: "4px 8px", background: t.id === teamId ? "rgba(52,211,153,0.15)" : "rgba(255,255,255,0.05)", border: `1px solid ${t.id === teamId ? "var(--accent-green)" : "var(--border-subtle)"}`, borderRadius: "4px" }}
                        onClick={() => {
                          setTeamId(t.id);
                          setShowAddTeam(false);
                        }}
                      >
                        📡 {t.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* SLIDEOUT GROUP CHAT DRAWER */}
          {isChatDrawerOpen && (
            <div className={styles.chatDrawerOverlay} onClick={() => setIsChatDrawerOpen(false)}>
              <div className={styles.chatDrawer} onClick={(e) => e.stopPropagation()}>
                {/* Header */}
                <div className={styles.chatDrawerHeader}>
                  <div className={styles.chatDrawerHeaderTitle}>
                    <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                      <span style={{ fontSize: "16px" }}>📡</span>
                      <h2>#{teams.find(t => t.id === teamId)?.name || "general"}</h2>
                    </div>
                    <div className={styles.connectionBadge}>
                      <div className={`${styles.dot} ${connected ? styles.connected : styles.disconnected}`} />
                      {connected ? "Live" : "Reconnecting"}
                    </div>
                  </div>

                  <button className={styles.chatDrawerCloseBtn} onClick={() => setIsChatDrawerOpen(false)}>
                    ✕ Close
                  </button>
                </div>

                <div className={styles.chatDrawerSplitBody}>
                  {/* Reuse Main Chat panel layout */}
                  <div className={styles.chatDrawerChatSection}>
                    <div className={styles.messagesContainer}>
                      {messages.map((msg) => (
                        <div key={msg.id} className={`${styles.messageBubble} ${msg.sender_id === "human" ? styles.human : styles.agent}`}>
                          {msg.sender_id !== "human" && (
                            <div className={styles.messageHeader}>
                              <span className={styles.senderName}>{msg.sender_name || "Agent"}</span>
                              {msg.role && <span className={styles.roleBadge}>{msg.role}</span>}
                              {msg.type === "thought" && <span className={styles.roleBadge} style={{ background: "rgba(251,191,36,0.15)", color: "#fbbf24" }}>thinking</span>}
                            </div>
                          )}

                          {/* Tool execution card */}
                          {msg.type === "tool_start" && (
                            <div className={styles.toolCard}>
                              <div className={styles.toolHeader}>🛠️ {msg.tool_name}</div>
                              <div className={styles.toolOutput}>{JSON.stringify(msg.arguments, null, 2)}</div>
                            </div>
                          )}

                          {msg.type === "tool_end" && (
                            <div className={styles.toolCard}>
                              <div className={styles.toolHeader}>✓ {msg.tool_name} — Result</div>
                              <div className={styles.toolOutput}>{msg.observation}</div>
                            </div>
                          )}

                          {/* Diff viewer */}
                          {msg.type === "file_change" && msg.diff && (
                            <div className={styles.diffBlock}>
                              <div className={styles.diffHeader}>
                                📄 {msg.action === "create" ? "Created" : "Modified"}: {msg.path}
                              </div>
                              <div className={styles.diffContent}>
                                {msg.diff.split("\n").map((line, i) => {
                                  let cls = styles.diffLine;
                                  if (line.startsWith("+") && !line.startsWith("+++")) cls += ` ${styles.diffLineAdd || "diff-line-add"}`;
                                  else if (line.startsWith("-") && !line.startsWith("---")) cls += ` ${styles.diffLineRemove || "diff-line-remove"}`;
                                  else if (line.startsWith("@@")) cls += ` diff-line-header`;
                                  return <div key={i} className={cls}>{line}</div>;
                                })}
                              </div>
                            </div>
                          )}

                          {/* Approval request */}
                          {msg.type === "approval_request" && msg.tx_id && (
                            <div className={styles.approvalCard}>
                              <h4>🛑 Approval Required</h4>
                              <p>{msg.text}</p>
                              <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "4px" }}>
                                Tool: <code>{msg.tool_name}</code> | Args: <code>{JSON.stringify(msg.arguments)}</code>
                              </p>
                              <div className={styles.approvalActions}>
                                <button className="btn btn-success" onClick={() => handleApproval(msg.tx_id!, true)}>✓ Approve</button>
                                <button className="btn btn-danger" onClick={() => handleApproval(msg.tx_id!, false)}>✗ Deny</button>
                              </div>
                            </div>
                          )}

                          {/* Agent question */}
                          {msg.type === "agent_question" && msg.tx_id && (
                            <div className={styles.approvalCard}>
                              <h4>❓ Agent Question</h4>
                              <p>{msg.text}</p>
                              <div className={styles.approvalActions}>
                                <input
                                  type="text"
                                  placeholder="Type your answer..."
                                  className="input"
                                  style={{ flex: 1, marginRight: "8px" }}
                                  id={`pg-answer-${msg.tx_id}`}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter") {
                                      const input = e.target as HTMLInputElement;
                                      if (input.value.trim()) {
                                        handleAnswer(msg.tx_id!, input.value.trim());
                                        input.disabled = true;
                                        input.value = "Answered ✓";
                                      }
                                    }
                                  }}
                                />
                                <button className="btn btn-primary" onClick={() => {
                                  const input = document.getElementById(`pg-answer-${msg.tx_id}`) as HTMLInputElement;
                                  if (input && input.value.trim()) {
                                    handleAnswer(msg.tx_id!, input.value.trim());
                                    input.disabled = true;
                                    input.value = "Answered ✓";
                                  }
                                }}>Send</button>
                              </div>
                            </div>
                          )}

                          {/* Browser screenshot */}
                          {msg.type === "browser_screenshot" && msg.image_base64 && (
                            <div className={styles.browserView}>
                              <div className={styles.browserUrl}>🌐 {msg.text}</div>
                              <img src={msg.image_base64} alt="Browser viewport" />
                            </div>
                          )}

                          {/* Shell output */}
                          {msg.type === "shell_output" && (
                            <div className={styles.terminalBlock}>
                              <span className={msg.stream === "stderr" ? styles.stderr : ""}>{msg.text}</span>
                            </div>
                          )}

                          {/* Regular text messages */}
                          {(msg.type === "message" || msg.type === "thought") && (
                            <span>{msg.text}</span>
                          )}
                        </div>
                      ))}

                      {/* Typing indicators */}
                      {Array.from(typingAgents).map((agentId) => {
                        const agent = agents.find((a) => a.id === agentId);
                        if (!agent) return null;
                        return (
                          <div key={agentId} className={styles.typingIndicator}>
                            <span>{agent.name} is thinking</span>
                            <div className={styles.typingDots}>
                              <span /><span /><span />
                            </div>
                          </div>
                        );
                      })}

                      <div ref={messagesEndRef} />
                    </div>

                    {/* Input */}
                    <div className={styles.inputBar}>
                      <div className={styles.inputWrapper}>
                        <input
                          value={inputText}
                          onChange={(e) => setInputText(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                          placeholder="Message the team... (use @name to mention an agent)"
                        />
                        <button className={styles.sendBtn} onClick={handleSend} disabled={!inputText.trim()}>
                          ↑
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Right tab console inside drawer */}
                  <div className={styles.chatDrawerInfoSection}>
                    <div className={styles.rightPanelHeader}>
                      <div className={styles.tabBar}>
                        <button className={`${styles.tab} ${rightTab === "tasks" ? styles.active : ""}`} onClick={() => setRightTab("tasks")}>Tasks</button>
                        <button className={`${styles.tab} ${rightTab === "diffs" ? styles.active : ""}`} onClick={() => setRightTab("diffs")}>Diffs</button>
                        <button className={`${styles.tab} ${rightTab === "browser" ? styles.active : ""}`} onClick={() => setRightTab("browser")}>Browser</button>
                        <button className={`${styles.tab} ${rightTab === "knowledge" ? styles.active : ""}`} onClick={() => setRightTab("knowledge")}>Knowledge</button>
                      </div>
                    </div>

                    <div className={styles.rightPanelContent}>
                      {/* Tasks tab */}
                      {rightTab === "tasks" && (
                        <>
                          {tasks.length === 0 ? (
                            <p style={{ color: "var(--text-tertiary)", fontSize: "13px", textAlign: "center", padding: "24px 0" }}>
                              No tasks yet.
                            </p>
                          ) : (
                            tasks.map((task) => (
                              <div key={task.id} className={styles.taskItem}>
                                <div className={styles.taskTitle}>{task.title}</div>
                                <div className={styles.taskMeta}>
                                  <span className={`badge badge-${task.status === "done" ? "green" : task.status === "in_progress" ? "blue" : task.priority === "critical" ? "red" : "yellow"}`}>
                                    {task.status}
                                  </span>
                                  <span>{task.priority}</span>
                                  {task.assigned_to && <span>→ {task.assigned_to}</span>}
                                </div>
                              </div>
                            ))
                          )}
                        </>
                      )}

                      {/* Diffs tab */}
                      {rightTab === "diffs" && (
                        <>
                          {diffs.length === 0 ? (
                            <p style={{ color: "var(--text-tertiary)", fontSize: "13px", textAlign: "center", padding: "24px 0" }}>
                              No file changes yet.
                            </p>
                          ) : (
                            diffs.map((d, i) => (
                              <div key={i} className={styles.diffBlock} style={{ marginBottom: "12px" }}>
                                <div className={styles.diffHeader}>
                                  📄 {d.sender_name}: {d.action} {d.path}
                                </div>
                                <div className={styles.diffContent}>
                                  {d.diff.split("\n").slice(0, 30).map((line, j) => {
                                    let cls = "diff-line-context";
                                    if (line.startsWith("+") && !line.startsWith("+++")) cls = "diff-line-add";
                                    else if (line.startsWith("-") && !line.startsWith("---")) cls = "diff-line-remove";
                                    else if (line.startsWith("@@")) cls = "diff-line-header";
                                    return <div key={j} className={`${styles.diffLine} ${cls}`}>{line}</div>;
                                  })}
                                </div>
                              </div>
                            ))
                          )}
                        </>
                      )}

                      {/* Browser tab */}
                      {rightTab === "browser" && (
                        <>
                          {browserScreenshots.length === 0 ? (
                            <p style={{ color: "var(--text-tertiary)", fontSize: "13px", textAlign: "center", padding: "24px 0" }}>
                              No browser activity yet.
                            </p>
                          ) : (
                            browserScreenshots.map((bs, i) => (
                              <div key={i} className={styles.browserView} style={{ marginBottom: "12px" }}>
                                <div className={styles.browserUrl}>🌐 {bs.sender_name}: {bs.url}</div>
                                <img src={bs.image_base64} alt={`Browser: ${bs.url}`} />
                              </div>
                            ))
                          )}
                        </>
                      )}

                      {/* Knowledge tab */}
                      {rightTab === "knowledge" && (
                        <>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                            <h4 style={{ fontSize: "11px", fontWeight: "600", color: "var(--text-tertiary)", textTransform: "uppercase" }}>Long-term Memory</h4>
                            <button 
                              className="btn btn-ghost" 
                              style={{ fontSize: "10px", padding: "2px 6px" }}
                              onClick={() => setShowAddKnowledge(!showAddKnowledge)}
                            >
                              {showAddKnowledge ? "Cancel" : "+ Add"}
                            </button>
                          </div>

                          {showAddKnowledge && (
                            <div style={{
                              padding: "12px", background: "var(--bg-surface)", borderRadius: "var(--radius-md)",
                              border: "1px solid var(--border-subtle)", marginBottom: "16px"
                            }}>
                              <input id="pg-knowledge-summary" className="input" placeholder="Task Summary..." style={{ fontSize: "12px", marginBottom: "8px" }} />
                              <textarea id="pg-knowledge-rule" className="input" placeholder="Concrete Lesson..." style={{ fontSize: "12px", minHeight: "50px", marginBottom: "8px" }} />
                              <button
                                className="btn btn-primary"
                                style={{ width: "100%", fontSize: "12px" }}
                                onClick={async () => {
                                  const summary = (document.getElementById("pg-knowledge-summary") as HTMLInputElement).value.trim();
                                  const rule = (document.getElementById("pg-knowledge-rule") as HTMLTextAreaElement).value.trim();
                                  if (!summary || !rule || !projectId) return;
                                  try {
                                    const res = await api.createLearning({ project_id: projectId, task_summary: summary, lesson_rule: rule });
                                    setLearnings(prev => [res, ...prev]);
                                    setShowAddKnowledge(false);
                                  } catch (e) { console.error(e); }
                                }}
                              >
                                Save to pgvector
                              </button>
                            </div>
                          )}

                          {learnings.length === 0 ? (
                            <p style={{ color: "var(--text-tertiary)", fontSize: "13px", textAlign: "center", padding: "24px 0" }}>
                              No knowledge items.
                            </p>
                          ) : (
                            learnings.map((l) => (
                              <div key={l.id} className={styles.taskItem} style={{ borderLeft: "3px solid var(--accent-purple)", padding: "10px", marginBottom: "8px" }}>
                                <div style={{ fontSize: "11px", fontWeight: "600", color: "var(--text-primary)" }}>
                                  💡 Context: {l.task_summary}
                                </div>
                                <div style={{ fontSize: "11px", color: "var(--text-secondary)", fontStyle: "italic", marginTop: "4px" }}>
                                  Rule: "{l.lesson_rule}"
                                </div>
                              </div>
                            ))
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        /* ==================== SPLIT VIEW (ORIGINAL BACKWARD COMPATIBLE) ==================== */
        <>
          {/* ---- SIDEBAR ---- */}
          <aside className={styles.sidebar}>
            <div className={styles.sidebarHeader}>
              <h1>⚡ Carole.ai</h1>
              <p>Multi-Agent Engineering Platform</p>
            </div>

            {/* ---- TENANT / PROJECT / TEAM PLAYGROUND DECK ---- */}
            <div className={styles.sidebarSection} style={{ borderBottom: "1px solid var(--border-subtle)", paddingBottom: "20px" }}>
              <div className={styles.playgroundDeck}>
                
                {/* Tenant (User) Selector */}
                <div style={{ marginBottom: "4px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                    <label style={{ fontSize: "10px", fontWeight: "700", textTransform: "uppercase", color: "var(--text-tertiary)", letterSpacing: "0.5px" }}>Tenant Domain</label>
                    <button 
                      onClick={() => setShowAddTenant(!showAddTenant)}
                      style={{ background: "none", border: "none", color: "var(--accent-blue)", fontSize: "11px", cursor: "pointer", fontWeight: "600" }}
                    >
                      {showAddTenant ? "Back" : "+ Add"}
                    </button>
                  </div>

                  {showAddTenant ? (
                    <div className={styles.playgroundOverlayForm}>
                      <div style={{ fontSize: "12px", fontWeight: "600", color: "var(--text-primary)", marginBottom: "8px" }}>Launch New Tenant</div>
                      <input id="new-tenant-email" className="input" placeholder="e.g. enterprise@google.com" style={{ fontSize: "12px", marginBottom: "8px" }} />
                      <button 
                        className="btn btn-primary" 
                        style={{ width: "100%", fontSize: "12px" }}
                        onClick={async () => {
                          const email = (document.getElementById("new-tenant-email") as HTMLInputElement).value.trim();
                          if (!email) return;
                          try {
                            const res = await api.createUser(email, email.split("@")[0]);
                            setUsers(prev => [res, ...prev]);
                            setUserId(res.id);
                            setShowAddTenant(false);
                          } catch (e) { console.error(e); }
                        }}
                      >
                        ✓ Create Organization
                      </button>
                    </div>
                  ) : (
                    <>
                      {(() => {
                        const currentTenant = users.find(u => u.id === userId) || users[0];
                        return currentTenant ? (
                          <div 
                            className={`${styles.tenantCapsule} ${styles.tenantCapsuleActive}`}
                            onClick={() => setShowAddTenant(true)}
                          >
                            <div className={styles.tenantAvatarNode}>
                              {currentTenant.email[0].toUpperCase()}
                            </div>
                            <div className={styles.tenantInfoNode}>
                              <div className={styles.title}>Active Org</div>
                              <div className={styles.value}>{currentTenant.email}</div>
                            </div>
                            <span style={{ fontSize: "12px", color: "var(--text-tertiary)" }}>⚙️</span>
                          </div>
                        ) : (
                          <div style={{ color: "var(--text-tertiary)", fontSize: "12px" }}>No Tenant Set</div>
                        );
                      })()}
                    </>
                  )}
                </div>

                {/* Dotted Connection Flow line */}
                <div className={styles.connectorLine}>
                  <div className={styles.connectorLineDotted} />
                </div>

                {/* Project Selector */}
                <div style={{ marginBottom: "4px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                    <label style={{ fontSize: "10px", fontWeight: "700", textTransform: "uppercase", color: "var(--text-tertiary)", letterSpacing: "0.5px" }}>Projects</label>
                    <button 
                      onClick={() => setShowAddProject(!showAddProject)}
                      style={{ background: "none", border: "none", color: "var(--accent-blue)", fontSize: "11px", cursor: "pointer", fontWeight: "600" }}
                    >
                      {showAddProject ? "Back" : "+ Add"}
                    </button>
                  </div>

                  {showAddProject ? (
                    <div className={styles.playgroundOverlayForm}>
                      <div style={{ fontSize: "12px", fontWeight: "600", color: "var(--text-primary)", marginBottom: "8px" }}>Start Workspace Project</div>
                      <input id="new-project-name" className="input" placeholder="e.g. Neural Crawler API" style={{ fontSize: "12px", marginBottom: "8px" }} />
                      <button 
                        className="btn btn-primary" 
                        style={{ width: "100%", fontSize: "12px" }}
                        onClick={async () => {
                          const name = (document.getElementById("new-project-name") as HTMLInputElement).value.trim();
                          if (!name) return;
                          try {
                            const res = await api.createProject(name, userId || undefined);
                            setProjects(prev => [res, ...prev]);
                            setProjectId(res.id);
                            setShowAddProject(false);
                          } catch (e) { console.error(e); }
                        }}
                      >
                        ✓ Init Project
                      </button>
                    </div>
                  ) : (
                    <div className={styles.projectListCarousel}>
                      {projects.map(p => {
                        const isActive = p.id === projectId;
                        return (
                          <div 
                            key={p.id} 
                            className={`${styles.projectVisualCard} ${isActive ? styles.projectVisualCardActive : ""}`}
                            onClick={() => setProjectId(p.id)}
                          >
                            <div className={styles.projectCardFolderIcon}>📁</div>
                            <div className={styles.projectCardName}>{p.name}</div>
                          </div>
                        );
                      })}
                      <div 
                        className={styles.projectVisualCard}
                        style={{ borderStyle: "dashed", opacity: 0.6, justifyContent: "center", alignItems: "center" }}
                        onClick={() => setShowAddProject(true)}
                      >
                        <div style={{ fontSize: "20px", color: "var(--accent-blue)", fontWeight: "bold" }}>+</div>
                        <div style={{ fontSize: "11px", color: "var(--text-secondary)", marginTop: "4px" }}>New Proj</div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Dotted Connection Flow line */}
                <div className={styles.connectorLine}>
                  <div className={styles.connectorLineDotted} />
                </div>

                {/* Team Selector */}
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                    <label style={{ fontSize: "10px", fontWeight: "700", textTransform: "uppercase", color: "var(--text-tertiary)", letterSpacing: "0.5px" }}>Active Rooms</label>
                    <button 
                      onClick={() => setShowAddTeam(!showAddTeam)}
                      style={{ background: "none", border: "none", color: "var(--accent-blue)", fontSize: "11px", cursor: "pointer", fontWeight: "600" }}
                      disabled={!projectId}
                    >
                      {showAddTeam ? "Back" : "+ Add"}
                    </button>
                  </div>

                  {showAddTeam ? (
                    <div className={styles.playgroundOverlayForm}>
                      <div style={{ fontSize: "12px", fontWeight: "600", color: "var(--text-primary)", marginBottom: "8px" }}>Setup Team Room</div>
                      <input id="new-team-name" className="input" placeholder="e.g. frontend-core" style={{ fontSize: "12px", marginBottom: "8px" }} />
                      <button 
                        className="btn btn-primary" 
                        style={{ width: "100%", fontSize: "12px" }}
                        onClick={async () => {
                          const name = (document.getElementById("new-team-name") as HTMLInputElement).value.trim();
                          if (!name || !projectId) return;
                          try {
                            const res = await api.createTeam(name, projectId);
                            setTeams(prev => [res, ...prev]);
                            setTeamId(res.id);
                            setShowAddTeam(false);
                          } catch (e) { console.error(e); }
                        }}
                      >
                        ✓ Open Room
                      </button>
                    </div>
                  ) : (
                    <div className={styles.teamGridStack}>
                      {teams.length === 0 ? (
                        <div style={{ color: "var(--text-tertiary)", fontSize: "11px", fontStyle: "italic", padding: "4px 0" }}>No active team rooms. Create one!</div>
                      ) : (
                        teams.map(t => {
                          const isActive = t.id === teamId;
                          return (
                            <div 
                              key={t.id} 
                              className={`${styles.teamVisualPill} ${isActive ? styles.teamVisualPillActive : ""}`}
                              onClick={() => setTeamId(t.id)}
                            >
                              <div className={styles.teamBroadcastLight} />
                              <span>📡 {t.name}</span>
                            </div>
                          );
                        })
                      )}
                    </div>
                  )}
                </div>

              </div>
            </div>

            <div className={styles.sidebarSection}>
              <h3>Team Members</h3>
              {agents.map((agent) => {
                const status = agentStatuses[agent.id] || "idle";
                return (
                  <div key={agent.id} className={styles.agentCard}>
                    <div className={styles.agentAvatar} style={{ background: avatarColor(agent.name) }}>
                      {agent.name[0]}
                    </div>
                    <div className={styles.agentInfo}>
                      <div className={styles.name}>{agent.name}</div>
                      <div className={styles.role}>{agent.role} · {agent.model}</div>
                    </div>
                    <div className={`${styles.statusDot} ${styles[status] || styles.idle}`} title={status} />
                  </div>
                );
              })}

              {/* Add Agent Button / Form */}
              {!showAddAgent ? (
                <button
                  className="btn btn-ghost"
                  style={{ width: "100%", marginTop: "8px", fontSize: "12px" }}
                  onClick={() => setShowAddAgent(true)}
                  id="add-agent-btn"
                >+ Add Agent</button>
              ) : (
                <div style={{
                  marginTop: "8px", padding: "12px",
                  background: "var(--bg-surface)", borderRadius: "var(--radius-md)",
                  border: "1px solid var(--border-subtle)",
                }}>
                  <div style={{ fontSize: "11px", fontWeight: "600", textTransform: "uppercase", color: "var(--text-tertiary)", marginBottom: "4px" }}>Role Template</div>
                  <select 
                    className="input" 
                    style={{ marginBottom: "8px", background: "rgba(255,255,255,0.06)", border: "1px solid rgba(91, 108, 255, 0.4)", cursor: "pointer", fontSize: "12px" }}
                    onChange={(e) => {
                      const val = e.target.value;
                      const nameEl = document.getElementById("new-agent-name") as HTMLInputElement;
                      const roleEl = document.getElementById("new-agent-role") as HTMLInputElement;
                      const skillsEl = document.getElementById("new-agent-skills") as HTMLInputElement;
                      const instEl = document.getElementById("new-agent-instructions") as HTMLTextAreaElement;
                      const sysEl = document.getElementById("new-agent-system-prompt") as HTMLTextAreaElement;
                      
                      if (val === "coder") {
                        roleEl.value = "Fullstack Developer";
                        skillsEl.value = "react, typescript, node, css";
                        instEl.value = "Write clean, modular code. Prefer functional components and async/await syntax.";
                        sysEl.value = "You are a master Fullstack Developer dedicated to writing pristine TypeScript and CSS.";
                        if (!nameEl.value) nameEl.value = "Nova";
                      } else if (val === "db") {
                        roleEl.value = "Database Architect";
                        skillsEl.value = "postgresql, pgvector, prisma, query_tuning";
                        instEl.value = "Enforce index optimization, suggest schema safety rules, and always write EXPLAIN ANALYZE.";
                        sysEl.value = "You are Helix, the database architect and ultimate optimizer.";
                        if (!nameEl.value) nameEl.value = "Helix";
                      } else if (val === "reviewer") {
                        roleEl.value = "Senior Reviewer";
                        skillsEl.value = "git, code_review, quality_assurance";
                        instEl.value = "Evaluate all changes against strict maintainability principles and check for hidden edge cases.";
                        sysEl.value = "You are Sage, a thoughtful senior code reviewer who maintains high codebase standards.";
                        if (!nameEl.value) nameEl.value = "Sage";
                      } else if (val === "secops") {
                        roleEl.value = "SecOps Specialist";
                        skillsEl.value = "security, pentest, audit, patch";
                        instEl.value = "Search for injections, security leaks, outdated dependencies, and verify token safety.";
                        sysEl.value = "You are Sentinel, the security guardian who audits all code changes.";
                        if (!nameEl.value) nameEl.value = "Sentinel";
                      }
                    }}
                  >
                    <option value="">-- Choose Ready-Made Template --</option>
                    <option value="coder">📁 Coder (Fullstack Developer)</option>
                    <option value="db">💾 Database Architect (Postgres Optimizer)</option>
                    <option value="reviewer">🔍 Senior Reviewer (Sage QA Auditor)</option>
                    <option value="secops">🛡️ SecOps Specialist (Security Guard)</option>
                  </select>

                  <input className="input" placeholder="Name" id="new-agent-name" style={{ marginBottom: "6px" }} />
                  <input className="input" placeholder="Custom Role (e.g. Coder, Rust Specialist)" id="new-agent-role" style={{ marginBottom: "6px" }} />
                  <select className="input" id="new-agent-model" style={{ marginBottom: "6px" }}>
                    <option value="gpt-4o-mini">gpt-4o-mini</option>
                    <option value="gpt-4o">gpt-4o</option>
                    <option value="claude-3-5-sonnet">claude-3-5-sonnet</option>
                    <option value="claude-3-7-sonnet">claude-3-7-sonnet</option>
                    <option value="claude-4-5-sonnet">claude-4-5-sonnet</option>
                    <option value="claude-4-8-sonnet">claude-4-8-sonnet</option>
                    <option value="claude-4-8-opus">claude-4-8-opus</option>
                    <option value="gemini-1.5-pro">gemini-1.5-pro</option>
                    <option value="gemini-2.0-flash">gemini-2.0-flash</option>
                    <option value="qwen-plus">qwen-plus</option>
                  </select>
                  <input className="input" placeholder="Skills (e.g. git, web_research)" id="new-agent-skills" style={{ marginBottom: "6px" }} />
                  <textarea className="input" placeholder="Custom Instructions (e.g. prioritize safety)" id="new-agent-instructions" style={{ marginBottom: "6px", minHeight: "48px", fontSize: "12px", resize: "vertical" }} />
                  <textarea className="input" placeholder="System Prompt Override (Optional)" id="new-agent-system-prompt" style={{ marginBottom: "6px", minHeight: "48px", fontSize: "12px", resize: "vertical" }} />
                  
                  <div style={{ display: "flex", gap: "6px" }}>
                    <button className="btn btn-primary" style={{ flex: 1, fontSize: "12px" }} onClick={async () => {
                      const name = (document.getElementById("new-agent-name") as HTMLInputElement).value.trim();
                      const role = (document.getElementById("new-agent-role") as HTMLInputElement).value.trim() || "Coder";
                      const model = (document.getElementById("new-agent-model") as HTMLSelectElement).value;
                      const skillsRaw = (document.getElementById("new-agent-skills") as HTMLInputElement).value.trim();
                      const skills = skillsRaw ? skillsRaw.split(",").map(s => s.trim()).filter(Boolean) : [];
                      const customInstructions = (document.getElementById("new-agent-instructions") as HTMLTextAreaElement).value.trim() || undefined;
                      const systemPrompt = (document.getElementById("new-agent-system-prompt") as HTMLTextAreaElement).value.trim() || undefined;
                      
                      if (!name || !teamId) return;
                      try {
                        const agent = await api.createAgent({ 
                          team_id: teamId, 
                          name, 
                          role, 
                          model,
                          skills,
                          custom_instructions: customInstructions,
                          system_prompt: systemPrompt
                        });
                        setAgents((prev) => [...prev, agent]);
                        setShowAddAgent(false);
                      } catch (e) { console.error("Create agent error:", e); }
                    }}>Create</button>
                    <button className="btn btn-ghost" style={{ fontSize: "12px" }} onClick={() => setShowAddAgent(false)}>Cancel</button>
                  </div>
                </div>
              )}
            </div>
          </aside>

          {/* ---- MAIN CHAT ---- */}
          <main className={styles.mainArea}>
            <div className={styles.chatHeader}>
              <h2># general</h2>
              <div className={styles.connectionBadge}>
                <div className={`${styles.dot} ${connected ? styles.connected : styles.disconnected}`} />
                {connected ? "Connected" : "Reconnecting..."}
              </div>
            </div>

            <div className={styles.messagesContainer}>
              {messages.map((msg) => (
                <div key={msg.id} className={`${styles.messageBubble} ${msg.sender_id === "human" ? styles.human : styles.agent}`}>
                  {msg.sender_id !== "human" && (
                    <div className={styles.messageHeader}>
                      <span className={styles.senderName}>{msg.sender_name || "Agent"}</span>
                      {msg.role && <span className={styles.roleBadge}>{msg.role}</span>}
                      {msg.type === "thought" && <span className={styles.roleBadge} style={{ background: "rgba(251,191,36,0.15)", color: "#fbbf24" }}>thinking</span>}
                    </div>
                  )}

                  {/* Tool execution card */}
                  {msg.type === "tool_start" && (
                    <div className={styles.toolCard}>
                      <div className={styles.toolHeader}>🛠️ {msg.tool_name}</div>
                      <div className={styles.toolOutput}>{JSON.stringify(msg.arguments, null, 2)}</div>
                    </div>
                  )}

                  {msg.type === "tool_end" && (
                    <div className={styles.toolCard}>
                      <div className={styles.toolHeader}>✓ {msg.tool_name} — Result</div>
                      <div className={styles.toolOutput}>{msg.observation}</div>
                    </div>
                  )}

                  {/* Diff viewer */}
                  {msg.type === "file_change" && msg.diff && (
                    <div className={styles.diffBlock}>
                      <div className={styles.diffHeader}>
                        📄 {msg.action === "create" ? "Created" : "Modified"}: {msg.path}
                      </div>
                      <div className={styles.diffContent}>
                        {msg.diff.split("\n").map((line, i) => {
                          let cls = styles.diffLine;
                          if (line.startsWith("+") && !line.startsWith("+++")) cls += ` ${styles.diffLineAdd || "diff-line-add"}`;
                          else if (line.startsWith("-") && !line.startsWith("---")) cls += ` ${styles.diffLineRemove || "diff-line-remove"}`;
                          else if (line.startsWith("@@")) cls += ` diff-line-header`;
                          return <div key={i} className={cls}>{line}</div>;
                        })}
                      </div>
                    </div>
                  )}

                  {/* Approval request */}
                  {msg.type === "approval_request" && msg.tx_id && (
                    <div className={styles.approvalCard}>
                      <h4>🛑 Approval Required</h4>
                      <p>{msg.text}</p>
                      <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "4px" }}>
                        Tool: <code>{msg.tool_name}</code> | Args: <code>{JSON.stringify(msg.arguments)}</code>
                      </p>
                      <div className={styles.approvalActions}>
                        <button className="btn btn-success" onClick={() => handleApproval(msg.tx_id!, true)}>✓ Approve</button>
                        <button className="btn btn-danger" onClick={() => handleApproval(msg.tx_id!, false)}>✗ Deny</button>
                      </div>
                    </div>
                  )}

                  {/* Agent question */}
                  {msg.type === "agent_question" && msg.tx_id && (
                    <div className={styles.approvalCard}>
                      <h4>❓ Agent Question</h4>
                      <p>{msg.text}</p>
                      <div className={styles.approvalActions}>
                        <input
                          type="text"
                          placeholder="Type your answer..."
                          className="input"
                          style={{ flex: 1, marginRight: "8px" }}
                          id={`answer-${msg.tx_id}`}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              const input = e.target as HTMLInputElement;
                              if (input.value.trim()) {
                                handleAnswer(msg.tx_id!, input.value.trim());
                                input.disabled = true;
                                input.value = "Answered ✓";
                              }
                            }
                          }}
                        />
                        <button className="btn btn-primary" onClick={() => {
                          const input = document.getElementById(`answer-${msg.tx_id}`) as HTMLInputElement;
                          if (input && input.value.trim()) {
                            handleAnswer(msg.tx_id!, input.value.trim());
                            input.disabled = true;
                            input.value = "Answered ✓";
                          }
                        }}>Send</button>
                      </div>
                    </div>
                  )}

                  {/* Browser screenshot */}
                  {msg.type === "browser_screenshot" && msg.image_base64 && (
                    <div className={styles.browserView}>
                      <div className={styles.browserUrl}>🌐 {msg.text}</div>
                      <img src={msg.image_base64} alt="Browser viewport" />
                    </div>
                  )}

                  {/* Shell output */}
                  {msg.type === "shell_output" && (
                    <div className={styles.terminalBlock}>
                      <span className={msg.stream === "stderr" ? styles.stderr : ""}>{msg.text}</span>
                    </div>
                  )}

                  {/* Regular text messages */}
                  {(msg.type === "message" || msg.type === "thought") && (
                    <span>{msg.text}</span>
                  )}
                </div>
              ))}

              {/* Typing indicators */}
              {Array.from(typingAgents).map((agentId) => {
                const agent = agents.find((a) => a.id === agentId);
                if (!agent) return null;
                return (
                  <div key={agentId} className={styles.typingIndicator}>
                    <span>{agent.name} is thinking</span>
                    <div className={styles.typingDots}>
                      <span /><span /><span />
                    </div>
                  </div>
                );
              })}

              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className={styles.inputBar}>
              <div className={styles.inputWrapper}>
                <input
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                  placeholder="Message the team... (use @name to mention an agent)"
                  id="chat-input"
                />
                <button className={styles.sendBtn} onClick={handleSend} disabled={!inputText.trim()} id="send-btn">
                  ↑
                </button>
              </div>
            </div>
          </main>

          {/* ---- RIGHT PANEL ---- */}
          <aside className={styles.rightPanel}>
            <div className={styles.rightPanelHeader}>
              <div className={styles.tabBar}>
                <button className={`${styles.tab} ${rightTab === "tasks" ? styles.active : ""}`} onClick={() => setRightTab("tasks")}>Tasks</button>
                <button className={`${styles.tab} ${rightTab === "diffs" ? styles.active : ""}`} onClick={() => setRightTab("diffs")}>Diffs</button>
                <button className={`${styles.tab} ${rightTab === "browser" ? styles.active : ""}`} onClick={() => setRightTab("browser")}>Browser</button>
                <button className={`${styles.tab} ${rightTab === "knowledge" ? styles.active : ""}`} onClick={() => setRightTab("knowledge")}>Knowledge</button>
              </div>
            </div>

            <div className={styles.rightPanelContent}>
              {/* Tasks tab */}
              {rightTab === "tasks" && (
                <>
                  {tasks.length === 0 ? (
                    <p style={{ color: "var(--text-tertiary)", fontSize: "13px", textAlign: "center", padding: "24px 0" }}>
                      No tasks yet. Agents will create tasks as they work.
                    </p>
                  ) : (
                    tasks.map((task) => (
                      <div key={task.id} className={styles.taskItem}>
                        <div className={styles.taskTitle}>{task.title}</div>
                        <div className={styles.taskMeta}>
                          <span className={`badge badge-${task.status === "done" ? "green" : task.status === "in_progress" ? "blue" : task.priority === "critical" ? "red" : "yellow"}`}>
                            {task.status}
                          </span>
                          <span>{task.priority}</span>
                          {task.assigned_to && <span>→ {task.assigned_to}</span>}
                        </div>
                      </div>
                    ))
                  )}
                </>
              )}

              {/* Diffs tab */}
              {rightTab === "diffs" && (
                <>
                  {diffs.length === 0 ? (
                    <p style={{ color: "var(--text-tertiary)", fontSize: "13px", textAlign: "center", padding: "24px 0" }}>
                      No file changes yet. Diffs will appear here as agents edit files.
                    </p>
                  ) : (
                    diffs.map((d, i) => (
                      <div key={i} className={styles.diffBlock} style={{ marginBottom: "12px" }}>
                        <div className={styles.diffHeader}>
                          📄 {d.sender_name}: {d.action} {d.path}
                        </div>
                        <div className={styles.diffContent}>
                          {d.diff.split("\n").slice(0, 30).map((line, j) => {
                            let cls = "diff-line-context";
                            if (line.startsWith("+") && !line.startsWith("+++")) cls = "diff-line-add";
                            else if (line.startsWith("-") && !line.startsWith("---")) cls = "diff-line-remove";
                            else if (line.startsWith("@@")) cls = "diff-line-header";
                            return <div key={j} className={`${styles.diffLine} ${cls}`}>{line}</div>;
                          })}
                        </div>
                      </div>
                    ))
                  )}
                </>
              )}

              {/* Browser tab */}
              {rightTab === "browser" && (
                <>
                  {browserScreenshots.length === 0 ? (
                    <p style={{ color: "var(--text-tertiary)", fontSize: "13px", textAlign: "center", padding: "24px 0" }}>
                      No browser activity yet. Screenshots will stream here when agents browse.
                    </p>
                  ) : (
                    browserScreenshots.map((bs, i) => (
                      <div key={i} className={styles.browserView} style={{ marginBottom: "12px" }}>
                        <div className={styles.browserUrl}>🌐 {bs.sender_name}: {bs.url}</div>
                        <img src={bs.image_base64} alt={`Browser: ${bs.url}`} />
                      </div>
                    ))
                  )}
                </>
              )}

              {/* Knowledge tab */}
              {rightTab === "knowledge" && (
                <>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                    <h4 style={{ fontSize: "12px", fontWeight: "600", color: "var(--text-tertiary)", textTransform: "uppercase" }}>Long-term Memory (pgvector)</h4>
                    <button 
                      className="btn btn-ghost" 
                      style={{ fontSize: "11px", padding: "2px 6px" }}
                      onClick={() => setShowAddKnowledge(!showAddKnowledge)}
                    >
                      {showAddKnowledge ? "Cancel" : "+ Add"}
                    </button>
                  </div>

                  {showAddKnowledge && (
                    <div style={{
                      padding: "12px", background: "var(--bg-surface)", borderRadius: "var(--radius-md)",
                      border: "1px solid var(--border-subtle)", marginBottom: "16px"
                    }}>
                      <div style={{ marginBottom: "8px" }}>
                        <label style={{ fontSize: "11px", fontWeight: "600", color: "var(--text-secondary)" }}>Task Summary / Context</label>
                        <input id="new-knowledge-summary" className="input" placeholder="e.g. Setting up pgvector connections..." style={{ fontSize: "12px", marginTop: "4px" }} />
                      </div>
                      <div style={{ marginBottom: "8px" }}>
                        <label style={{ fontSize: "11px", fontWeight: "600", color: "var(--text-secondary)" }}>Concrete Lesson / Rule</label>
                        <textarea id="new-knowledge-rule" className="input" placeholder="e.g. Always use .is_(None) instead of == None in SQLAlchemy pgvector columns." style={{ fontSize: "12px", marginTop: "4px", minHeight: "60px", resize: "vertical" }} />
                      </div>
                      <button
                        className="btn btn-primary"
                        style={{ width: "100%", fontSize: "12px" }}
                        onClick={async () => {
                          const summary = (document.getElementById("new-knowledge-summary") as HTMLInputElement).value.trim();
                          const rule = (document.getElementById("new-knowledge-rule") as HTMLTextAreaElement).value.trim();
                          if (!summary || !rule || !projectId) return;
                          try {
                            const res = await api.createLearning({ project_id: projectId, task_summary: summary, lesson_rule: rule });
                            setLearnings(prev => [res, ...prev]);
                            setShowAddKnowledge(false);
                          } catch (e) {
                            console.error(e);
                          }
                        }}
                      >
                        Save to pgvector Ledger
                      </button>
                    </div>
                  )}

                  {learnings.length === 0 ? (
                    <p style={{ color: "var(--text-tertiary)", fontSize: "13px", textAlign: "center", padding: "24px 0" }}>
                      No knowledge items yet. Add custom lessons or wait for the 'Dream' consolidator worker to summarize chats automatically.
                    </p>
                  ) : (
                    learnings.map((l) => (
                      <div key={l.id} className={styles.taskItem} style={{ borderLeft: "3px solid var(--accent-purple)", padding: "12px", marginBottom: "8px" }}>
                        <div style={{ fontSize: "12px", fontWeight: "600", color: "var(--text-primary)", marginBottom: "4px" }}>
                          💡 Context: {l.task_summary}
                        </div>
                        <div style={{ fontSize: "12px", color: "var(--text-secondary)", lineHeight: "1.4", fontStyle: "italic" }}>
                          Rule: "{l.lesson_rule}"
                        </div>
                      </div>
                    ))
                  )}
                </>
              )}
            </div>
          </aside>
        </>
      )}
    </div>
  );
}
