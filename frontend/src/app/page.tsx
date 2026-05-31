"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import styles from "./page.module.css";
import { useWebSocket } from "@/hooks/useWebSocket";
import { api } from "@/hooks/useApi";
import type {
  ChatMessage, AgentConfig, TaskItem, WSEvent,
  FileChangeEvent, ApprovalRequestEvent, BrowserScreenshotEvent,
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
  const [teamId, setTeamId] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [inputText, setInputText] = useState("");
  const [loading, setLoading] = useState(true);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, string>>({});
  const [typingAgents, setTypingAgents] = useState<Set<string>>(new Set());
  const [rightTab, setRightTab] = useState<"tasks" | "diffs" | "browser">("tasks");
  const [diffs, setDiffs] = useState<FileChangeEvent[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<ApprovalRequestEvent[]>([]);
  const [browserScreenshots, setBrowserScreenshots] = useState<BrowserScreenshotEvent[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ---- WebSocket ----
  const { connected, events, sendMessage } = useWebSocket(teamId);

  // ---- Init: Seed & Load ----
  useEffect(() => {
    async function init() {
      try {
        await api.seedDemo();
        const projects = await api.listProjects();
        if (projects.length > 0) {
          setProjectId(projects[0].id);
          const teams = await api.listTeams(projects[0].id);
          if (teams.length > 0) {
            setTeamId(teams[0].id);
            const agts = await api.listAgents(teams[0].id);
            setAgents(agts);
            const msgs = await api.listMessages(teams[0].id);
            setMessages(msgs.map((m: any) => ({
              ...m, type: "message",
              sender_name: agts.find((a: AgentConfig) => a.id === m.sender_id)?.name,
              role: agts.find((a: AgentConfig) => a.id === m.sender_id)?.role,
            })));
            const tks = await api.listTasks(teams[0].id);
            setTasks(tks);
          }
        }
      } catch (e) {
        console.error("Init error:", e);
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  // ---- Process WS events ----
  useEffect(() => {
    if (events.length === 0) return;
    const latest = events[events.length - 1];
    processEvent(latest);
  }, [events]);

  const processEvent = useCallback((evt: WSEvent) => {
    switch (evt.type) {
      case "message":
        setMessages((prev) => [...prev, {
          id: Date.now().toString(),
          sender_id: evt.sender_id,
          sender_name: evt.sender_name || (evt.sender_id === "human" ? "You" : "Agent"),
          text: evt.text,
          role: evt.role,
          type: "message",
        }]);
        setTypingAgents((prev) => { const n = new Set(prev); n.delete(evt.sender_id); return n; });
        break;

      case "typing":
        setTypingAgents((prev) => new Set(prev).add(evt.sender_id));
        break;

      case "thought_delta":
        // Accumulate thought into the last message from this agent
        setMessages((prev) => {
          const last = [...prev];
          const existingIdx = last.findLastIndex(
            (m) => m.sender_id === evt.sender_id && m.type === "thought"
          );
          if (existingIdx >= 0) {
            last[existingIdx] = { ...last[existingIdx], text: last[existingIdx].text + evt.delta };
          } else {
            last.push({
              id: Date.now().toString(),
              sender_id: evt.sender_id,
              sender_name: evt.sender_name,
              text: evt.delta,
              role: evt.role,
              type: "thought",
            });
          }
          return last;
        });
        break;

      case "agent_status":
        setAgentStatuses((prev) => ({ ...prev, [evt.sender_id]: evt.status }));
        if (evt.status === "idle") {
          setTypingAgents((prev) => { const n = new Set(prev); n.delete(evt.sender_id); return n; });
        }
        break;

      case "tool_start":
        setMessages((prev) => [...prev, {
          id: Date.now().toString(),
          sender_id: evt.sender_id,
          sender_name: evt.sender_name,
          text: `Running \`${evt.tool_name}\`...`,
          type: "tool_start",
          tool_name: evt.tool_name,
          arguments: evt.arguments,
        }]);
        break;

      case "tool_end":
        setMessages((prev) => [...prev, {
          id: Date.now().toString(),
          sender_id: evt.sender_id,
          sender_name: evt.sender_name,
          text: evt.observation,
          type: "tool_end",
          tool_name: evt.tool_name,
          observation: evt.observation,
        }]);
        break;

      case "file_change":
        const fc = evt as FileChangeEvent;
        setDiffs((prev) => [fc, ...prev]);
        setMessages((prev) => [...prev, {
          id: Date.now().toString(),
          sender_id: fc.sender_id,
          sender_name: fc.sender_name,
          text: fc.diff,
          type: "file_change",
          path: fc.path,
          action: fc.action,
          diff: fc.diff,
        }]);
        break;

      case "approval_request":
        const ar = evt as ApprovalRequestEvent;
        setPendingApprovals((prev) => [...prev, ar]);
        setMessages((prev) => [...prev, {
          id: Date.now().toString(),
          sender_id: ar.agent_id,
          sender_name: ar.agent_name,
          text: ar.text,
          type: "approval_request",
          tx_id: ar.tx_id,
          tool_name: ar.tool_name,
          arguments: ar.arguments,
        }]);
        break;

      case "browser_screenshot":
        const bs = evt as BrowserScreenshotEvent;
        setBrowserScreenshots((prev) => [bs, ...prev.slice(0, 9)]);
        setMessages((prev) => [...prev, {
          id: Date.now().toString(),
          sender_id: bs.sender_id,
          sender_name: bs.sender_name,
          text: `Browsing: ${bs.url}`,
          type: "browser_screenshot",
          image_base64: bs.image_base64,
        }]);
        break;

      case "shell_output":
        setMessages((prev) => [...prev, {
          id: Date.now().toString(),
          sender_id: "system",
          text: evt.text,
          type: "shell_output",
          stream: evt.stream,
        }]);
        break;

      case "task_update":
        if (evt.action === "created") {
          setTasks((prev) => [evt.task, ...prev]);
        } else if (evt.action === "updated") {
          setTasks((prev) => prev.map((t) => t.id === evt.task.id ? { ...t, ...evt.task } : t));
        }
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

  // ---- Loading ----
  if (loading) {
    return (
      <div className={styles.setupBanner}>
        <h1>Carole.ai</h1>
        <p>Initializing multi-agent platform...</p>
      </div>
    );
  }

  if (!teamId) {
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
      {/* ---- SIDEBAR ---- */}
      <aside className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <h1>⚡ Carole.ai</h1>
          <p>Multi-Agent Engineering Platform</p>
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
        </div>
      </aside>
    </div>
  );
}
