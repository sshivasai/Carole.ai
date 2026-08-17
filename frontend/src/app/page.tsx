"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { PanelGroup, Panel, PanelResizeHandle } from "react-resizable-panels";
import Sidebar from "@/components/Sidebar";
import ChatInterface from "@/components/ChatInterface";
import KanbanBoard from "@/components/KanbanBoard";
import BrowserView from "@/components/BrowserView";
import MemoryView from "@/components/MemoryView";
import AgentPanel from "@/components/AgentPanel";
import SettingsPanel from "@/components/SettingsPanel";
import PluginStudio from "@/components/PluginStudio";
import SkillsStudio from "@/components/SkillsStudio";
import McpIntegration from "@/components/McpIntegration";
import ScratchpadPanel from "@/components/ScratchpadPanel";
import LoadingScreen from "@/components/LoadingScreen";
import AuthPage from "@/components/AuthPage";
import ToastContainer from "@/components/Toast";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { AuthProvider, useAuth } from "@/hooks/useAuth";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useToast } from "@/hooks/useToast";
import { api } from "@/hooks/useApi";
import FileExplorerPanel from "@/components/FileExplorerPanel";
import KeyboardShortcutsModal from "@/components/KeyboardShortcutsModal";
import type { AgentConfig, ChatMessage, TaskItem, BrowserScreenshotEvent, LearningItem, ScratchpadItem } from "@/lib/types";

const makeId = () => `${Date.now()}-${Math.random().toString(36).slice(2)}`;

function applyWSEvent(prev: ChatMessage[], evt: any): ChatMessage[] {
  const ts = Date.now();
  switch (evt.type) {
    case "thought_delta": {
      const sid = `streaming-${evt.sender_id}`;
      const tid = `thinking-${evt.sender_id}`;
      let filtered = prev;
      if (prev.some(m => m.id === tid)) filtered = prev.filter(m => m.id !== tid);

      const ex = filtered.find(m => m.id === sid);
      if (ex) return filtered.map(m => m.id === sid ? { ...m, text: m.text + (evt.delta || "") } : m);
      return [...filtered, { id: sid, sender_id: evt.sender_id || "agent", sender_name: evt.sender_name, role: evt.role, text: evt.delta || "", type: "streaming", timestamp: ts }];
    }
    case "stream_reasoning": {
      // Append reasoning chunk to the streaming bubble for this agent
      const sid = `streaming-${evt.sender_id}`;
      const tid = `thinking-${evt.sender_id}`;
      let filtered = prev;
      if (prev.some(m => m.id === tid)) filtered = prev.filter(m => m.id !== tid);

      const ex = filtered.find(m => m.id === sid);
      const appended = (ex?.reasoning || "") + (evt.chunk || "");
      if (ex) return filtered.map(m => m.id === sid ? { ...m, reasoning: appended } : m);
      // No streaming bubble yet — create one to hold the reasoning
      return [...filtered, { id: sid, sender_id: evt.sender_id || "agent", sender_name: evt.sender_name, role: evt.role, text: "", reasoning: appended, type: "streaming", timestamp: ts }];
    }
    case "tool_start": {
      // Append a tool-call entry to the streaming agent's reasoning trace
      const sid = `streaming-${evt.sender_id}`;
      const tid = `thinking-${evt.sender_id}`;
      let filtered = prev;
      if (prev.some(m => m.id === tid)) filtered = prev.filter(m => m.id !== tid);

      const args = evt.arguments ? JSON.stringify(evt.arguments, null, 2) : "";
      const entry = `\n🛠️ **${evt.tool_name}**\n\`\`\`json\n${args}\n\`\`\`\n`;
      const ex = filtered.find(m => m.id === sid);
      if (ex) return filtered.map(m => m.id === sid ? { ...m, reasoning: (m.reasoning || "") + entry } : m);
      return [...filtered, { id: sid, sender_id: evt.sender_id || "agent", sender_name: evt.sender_name, role: evt.role, text: "", reasoning: entry, type: "streaming", timestamp: ts }];
    }
    case "thought_reset": {
      const sid = `streaming-${evt.sender_id}`;
      return prev.map(m => m.id === sid ? { ...m, text: "" } : m);
    }
    case "tool_end": {
      // Append tool result to the streaming agent's reasoning trace
      const sid = `streaming-${evt.sender_id}`;
      const obs = (evt.observation || "").slice(0, 1000);
      const entry = `📄 **Result:**\n\`\`\`\n${obs}\n\`\`\`\n`;
      return prev.map(m => m.id === sid ? { ...m, reasoning: (m.reasoning || "") + entry } : m);
    }
    case "tool_progress": {
      // Append mid-execution progress text to the active streaming agent's reasoning trace
      const sid = `streaming-${evt.sender_id}`;
      const progress = evt.progress || evt.text || "";
      if (!progress) return prev;
      const entry = `⏳ ${progress}\n`;
      return prev.map(m => m.id === sid ? { ...m, reasoning: (m.reasoning || "") + entry } : m);
    }
    case "message": {
      const sid = `streaming-${evt.sender_id}`;
      const streamingMsg = prev.find(m => m.id === sid);
      const newId = evt.id || makeId();
      // Preserve the accumulated reasoning into the final message, and remove existing duplicate IDs
      return [...prev.filter(m => m.id !== sid && m.id !== `thinking-${evt.sender_id}` && m.id !== newId), {
        id: newId, sender_id: evt.sender_id || "agent", sender_name: evt.sender_name,
        role: evt.role, text: evt.text || "", type: "message", timestamp: evt.timestamp || ts,
        reasoning: evt.reasoning || streamingMsg?.reasoning || undefined,
      }];
    }
    case "agent_status": {
      if (["thinking", "active", "executing_tool"].includes(evt.status)) {
        const tid = `thinking-${evt.sender_id}`;
        if (prev.some(m => m.id === tid || m.id === `streaming-${evt.sender_id}`)) return prev;
        return [...prev, { id: tid, sender_id: evt.sender_id || "agent", sender_name: evt.sender_name, role: evt.role, text: "", type: "thinking", timestamp: ts }];
      }
      if (evt.status === "idle") {
        // Clean up any lingering thinking bubbles for this agent
        return prev.filter(m => m.id !== `thinking-${evt.sender_id}`);
      }
      return prev;
    }
    case "approval_request": {
      const sid = `streaming-${evt.agent_id || evt.sender_id}`;
      const hasStream = prev.some(m => m.id === sid);
      if (hasStream) {
        return prev.map(m => m.id === sid ? { ...m, pending_approval: { tx_id: evt.tx_id, tool_name: evt.tool_name, arguments: evt.arguments, text: evt.text || "" } } : m);
      }
      return [...prev, { id: makeId(), sender_id: evt.agent_id || evt.sender_id || "agent", sender_name: evt.agent_name || evt.sender_name, text: evt.text || "", type: "approval_request", tx_id: evt.tx_id, tool_name: evt.tool_name, arguments: evt.arguments, timestamp: ts }];
    }
    case "approval_update": {
      const sid = `streaming-${evt.agent_id || evt.sender_id}`;
      return prev.map(m => {
        if (m.id === sid && m.pending_approval && m.pending_approval.tx_id === evt.tx_id) {
          return { ...m, pending_approval: { ...m.pending_approval, text: evt.text || "" } };
        }
        if (m.type === "approval_request" && m.tx_id === evt.tx_id) {
          return { ...m, text: evt.text || "" };
        }
        return m;
      });
    }
    case "approval_resolved": {
      const sid = `streaming-${evt.agent_id || evt.sender_id}`;
      return prev.map(m => {
        if (m.id === sid && m.pending_approval && m.pending_approval.tx_id === evt.tx_id) {
          return { ...m, pending_approval: { ...m.pending_approval, status: evt.status } };
        }
        if (m.type === "approval_request" && m.tx_id === evt.tx_id) {
          return { ...m, status: evt.status };
        }
        return m;
      });
    }
    case "file_change":
      return [...prev, { id: makeId(), sender_id: evt.sender_id || "agent", sender_name: evt.sender_name, type: "file_change", path: evt.path, action: evt.action, diff: evt.diff, text: evt.text || "", timestamp: ts }];
    case "agent_question":
      return [...prev, { id: makeId(), sender_id: evt.agent_id || evt.sender_id || "agent", sender_name: evt.agent_name || evt.sender_name, text: evt.text || "", type: "agent_question", question_id: evt.question_id, question: evt.question, timestamp: ts }];
    case "collapse_to_reasoning": {
      const sid = `streaming-${evt.sender_id}`;
      return prev.map(m => {
        if (m.id === sid) {
          const newReasoning = (m.reasoning || "") + "\n\n" + (m.text || "");
          return { ...m, text: "", reasoning: newReasoning };
        }
        return m;
      });
    }
    case "chat_cleared":
      return [];
    case "message_deleted":
      return prev.filter(m => m.id !== evt.message_id);
    case "message_rewind":
      if (evt.from_timestamp) {
        const pivot = new Date(evt.from_timestamp).getTime();
        return prev.filter(m => {
          const mts = typeof m.timestamp === "number" ? m.timestamp : new Date(m.timestamp || 0).getTime();
          return mts < pivot;
        });
      }
      return prev;
    default:
      return prev;
  }
}

function AppShell() {
  const { user } = useAuth();
  const toast = useToast();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [activeView, setActiveView] = useState("chat");
  const [projects, setProjects] = useState<any[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [teams, setTeams] = useState<any[]>([]);
  const [teamId, setTeamId] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [learnings, setLearnings] = useState<LearningItem[]>([]);
  const [entityMemories, setEntityMemories] = useState<any[]>([]);
  const [screenshots, setScreenshots] = useState<BrowserScreenshotEvent[]>([]);
  const [appLoading, setAppLoading] = useState(true);
  const [streamingAgents, setStreamingAgents] = useState<Set<string>>(new Set());
  const [explorerOpen, setExplorerOpen] = useState(false);
  // Latest file_change WS event, fed to the FileExplorerPanel for realtime sync.
  const [lastFileChange, setLastFileChange] = useState<any | null>(null);
  // A file path the explorer should open automatically (set when the user
  // clicks a file-change card in chat).
  const [pendingOpenFile, setPendingOpenFile] = useState<string | null>(null);
  const [agentQueues, setAgentQueues] = useState<Record<string, number>>({});
  const [scratchpads, setScratchpads] = useState<ScratchpadItem[]>([]);

  useEffect(() => {
    const handleGlobalKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        setExplorerOpen(o => !o);
      }
    };
    window.addEventListener("keydown", handleGlobalKey);
    return () => window.removeEventListener("keydown", handleGlobalKey);
  }, []);

  const handleWSEvent = useCallback((evt: any) => {
    if (evt.type === "thought_delta" && evt.sender_id) {
      setStreamingAgents(s => new Set([...s, evt.sender_id!]));
    } else if ((evt.type === "message" || (evt.type === "agent_status" && evt.status === "idle")) && evt.sender_id) {
      setStreamingAgents(s => { const n = new Set(s); n.delete(evt.sender_id!); return n; });
    }

    if (["thought_delta", "thought_reset", "stream_reasoning", "message", "approval_request", "approval_update", "approval_resolved", "agent_question", "tool_start", "tool_end", "tool_progress", "agent_status", "message_deleted", "message_rewind", "chat_cleared", "file_change", "collapse_to_reasoning"].includes(evt.type)) {
      setMessages(prev => {
        const updated = applyWSEvent(prev, evt);
        return updated.length > 150 ? updated.slice(-150) : updated;
      });
    }

    if (evt.type === "file_change") {
      setLastFileChange({ ...evt, _seq: Date.now() });
    }
    if (evt.type === "browser_screenshot") {
      setScreenshots(prev => [...prev, evt as BrowserScreenshotEvent].slice(-50));
    }
    if (evt.type === "task_update" && evt.task) {
      setTasks(prev => {
        const exists = prev.some(t => t.id === evt.task!.id);
        if (exists) {
          return prev.map(t => t.id === evt.task!.id ? { ...t, ...evt.task! } : t);
        }
        return [evt.task!, ...prev];
      });
    }
    if (evt.type === "agent_queue_update" && evt.agent_id != null) {
      setAgentQueues(prev => ({ ...prev, [evt.agent_id]: evt.queue_depth ?? 0 }));
    }
    if (evt.type === "scratchpad_updated") {
      const target = (evt.target === "team" ? "team" : "personal") as "team" | "personal";
      const agentName = evt.agent_name || "";
      const content = evt.content ?? "";
      const updated_at = evt.timestamp;
      setScratchpads(prev => {
        const idx = prev.findIndex(p => p.target === target && (target === "team" || p.agent_name === agentName));
        const entry: ScratchpadItem = {
          target,
          agent_name: target === "team" ? "Team" : agentName,
          agent_id: evt.agent_id,
          label: evt.label || (target === "team" ? "Team Scratchpad" : `${agentName}'s Scratchpad`),
          content,
          updated_at,
          size_bytes: content.length,
        };
        if (idx >= 0) {
          const copy = [...prev];
          copy[idx] = { ...copy[idx], ...entry };
          return copy;
        }
        return [...prev, entry];
      });
    }
  }, []);

  const { connected, sendMessage } = useWebSocket(teamId, handleWSEvent);

  // Initial load
  useEffect(() => {
    async function init() {
      try {
        try { await api.seedDemo(); } catch (e) { console.warn("Seed demo non-fatal:", e); }
        const [projs] = await Promise.all([api.listProjects()]);
        setProjects(projs);
        if (projs.length > 0) setProjectId(projs[0].id);
      } catch (e) { console.error("Init error:", e); }
      finally { setAppLoading(false); }
    }
    init();
  }, []);

  // Load teams when project changes
  useEffect(() => {
    if (!projectId) return;
    Promise.all([api.listTeams(projectId), api.listLearnings(projectId), api.listEntityMemories(projectId, undefined)])
      .then(([tms, lrn, entities]) => {
        setTeams(tms);
        setTeamId(tms.length > 0 ? tms[0].id : null);
        setLearnings(lrn);
        setEntityMemories(entities);
      }).catch(console.error);
  }, [projectId]);

  // Load team data when team changes
  useEffect(() => {
    if (!teamId) { setAgents([]); setMessages([]); setTasks([]); setScreenshots([]); setScratchpads([]); return; }
    Promise.all([api.listAgents(teamId), api.listTasks(teamId), api.listMessages(teamId), api.listScratchpads(teamId)])
      .then(([ags, tks, msgs, pads]) => {
        setAgents(ags);
        setTasks(tks);
        setScratchpads(pads);
        setMessages(msgs.map((m: any) => ({
          ...m,
          id: m.id || makeId(),
          type: m.is_intermediate ? "tool_trace" : "message",
          timestamp: m.created_at,
          reasoning: m.reasoning ?? undefined,
          is_intermediate: m.is_intermediate ?? false,
        })));
      }).catch(console.error);
  }, [teamId]);




  const handleSendMessage = useCallback((text: string, attachments?: any[]) => {
    const fullName = user ? `${user.first_name || ""} ${user.last_name || ""}`.trim() : "You";
    sendMessage(text, "human", fullName || "You", attachments);
  }, [sendMessage, user]);

  const handleProjectCreated = useCallback((p: any) => {
    setProjects(prev => [p, ...prev]);
    setProjectId(p.id);
    toast.success(`Project "${p.name}" created`);
  }, [toast]);

  const handleTeamCreated = useCallback((t: any) => {
    setTeams(prev => [t, ...prev]);
    setTeamId(t.id);
    toast.success(`Team "${t.name}" created`);
  }, [toast]);

  const handleTeamDeleted = useCallback(() => {
    setTeams(prev => prev.filter(t => t.id !== teamId));
    setTeamId(null);
    setActiveView("chat");
  }, [teamId]);

  const handleProjectDeleted = useCallback(() => {
    setProjects(prev => prev.filter(p => p.id !== projectId));
    setProjectId(null);
    setTeamId(null);
  }, [projectId]);

  if (appLoading) {
    return <LoadingScreen steps={["Connecting to API…", "Loading projects…", "Initializing workspace…"]} />;
  }

  return (
    <PanelGroup direction="horizontal" autoSaveId="app-layout" style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Panel id="sidebar-panel" order={1} defaultSize={20} minSize={10} maxSize={40} style={{ display: "flex", flexShrink: 0, minWidth: 0 }}>
        <Sidebar
          activeView={activeView}
          onViewChange={setActiveView}
          connected={connected}
          projects={projects}
          projectId={projectId}
          onProjectChange={setProjectId}
          onProjectCreated={handleProjectCreated}
          teams={teams}
          teamId={teamId}
          onTeamChange={setTeamId}
          onTeamCreated={handleTeamCreated}
        />
      </Panel>
      <PanelResizeHandle className="resize-handle" />

      <Panel id="main-panel" order={2} style={{ display: "flex", flexDirection: "column", minWidth: 0, position: "relative" }}>
        <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, overflow: "hidden", background: "var(--bg-app)", position: "relative" }}>
          {activeView === "chat" && (
            <div className="animate-entrance" style={{ display: "flex", flex: 1, minHeight: 0, width: "100%" }}>
              <PanelGroup direction="horizontal" autoSaveId="chat-layout">
                <Panel id="chat-main-panel" order={1} defaultSize={70} minSize={30} style={{ display: "flex", minWidth: 0, flexDirection: "column" }}>
                  <div style={{ display: "flex", flex: 1, minWidth: 0, minHeight: 0 }}>
                    <ChatInterface
                      messages={messages}
                      agents={agents}
                      onSendMessage={handleSendMessage}
                      onDeleteMessage={(id) => {
                        api.deleteMessage(id).catch(console.error);
                        setMessages(prev => prev.filter(m => m.id !== id));
                      }}
                      onRollbackMessage={(id) => {
                        api.rollbackFromMessage(id).catch(console.error);
                        const pivotMsg = messages.find(m => m.id === id);
                        if (pivotMsg && pivotMsg.timestamp) {
                          const pivot = new Date(pivotMsg.timestamp).getTime();
                          setMessages(prev => prev.filter(m => {
                            const mts = typeof m.timestamp === "number" ? m.timestamp : new Date(m.timestamp || 0).getTime();
                            return mts < pivot;
                          }));
                        }
                      }}
                      onClearChat={() => {
                        setMessages([]);
                        toast.success("Chat cleared");
                      }}
                      teamId={teamId}
                      projectId={projectId}
                      onToggleExplorer={() => setExplorerOpen(o => !o)}
                      onOpenFile={(path: string) => {
                        setExplorerOpen(true);
                        setPendingOpenFile(path);
                      }}
                    />
                  </div>
                </Panel>
                {explorerOpen && (
                  <>
                    <PanelResizeHandle className="resize-handle" />
                    <Panel id="chat-explorer-panel" order={2} defaultSize={30} minSize={20} style={{ display: "flex", minWidth: 0 }}>
                      <FileExplorerPanel
                        onClose={() => setExplorerOpen(false)}
                        projectId={projectId || undefined}
                        teamId={teamId || undefined}
                        lastFileChange={lastFileChange}
                        pendingOpenFile={pendingOpenFile}
                        onPendingOpenConsumed={() => setPendingOpenFile(null)}
                      />
                    </Panel>
                  </>
                )}
              </PanelGroup>
            </div>
          )}
          {activeView === "tasks" && (
            <div className="animate-entrance" style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, width: "100%" }}>
              <KanbanBoard tasks={tasks} agents={agents} teamId={teamId} onTasksChange={setTasks} />
            </div>
          )}
          {activeView === "agents" && (
            <div className="animate-entrance" style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, width: "100%" }}>
              <AgentPanel agents={agents} teamId={teamId} streamingAgents={streamingAgents}
                agentQueues={agentQueues}
                onAgentsChange={setAgents} onToast={(msg, type) => toast.show(msg, type)} />
            </div>
          )}
          {activeView === "browser" && (
            <div className="animate-entrance" style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, width: "100%" }}>
              <BrowserView screenshots={screenshots} />
            </div>
          )}
          {activeView === "memory" && (
            <div className="animate-entrance" style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, width: "100%" }}>
              <MemoryView learnings={learnings} entityMemories={entityMemories} projectId={projectId} teamId={teamId}
                onLearningsChange={setLearnings} onEntityMemoriesChange={setEntityMemories} onToast={(msg, type) => toast.show(msg, type)} />
            </div>
          )}
          {activeView === "scratchpad" && (
            <div className="animate-entrance" style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, width: "100%" }}>
              <ScratchpadPanel teamId={teamId} agents={agents} scratchpads={scratchpads}
                onScratchpadsChange={setScratchpads}
                onToast={(msg, type) => toast.show(msg, type as any)} />
            </div>
          )}
          {activeView === "settings" && (
            <div className="animate-entrance" style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, width: "100%" }}>
              <SettingsPanel teamId={teamId} projectId={projectId} agents={agents}
                onToast={(msg, type) => toast.show(msg, type as any)}
                onTeamDeleted={handleTeamDeleted}
                onProjectDeleted={handleProjectDeleted} />
            </div>
          )}
          {activeView === "plugins" && (
            <div className="animate-entrance" style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, width: "100%" }}>
              <PluginStudio onToast={(msg, type) => toast.show(msg, type as any)} />
            </div>
          )}
          {activeView === "skills" && (
            <div className="animate-entrance" style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, width: "100%" }}>
              <SkillsStudio teamId={teamId} onToast={(msg, type) => toast.show(msg, type as any)} />
            </div>
          )}
          {activeView === "mcp" && (
            <div className="animate-entrance" style={{ padding: "var(--space-6)", height: "100%", overflowY: "auto" }}>
              <div className="card">
                <div className="section-header">
                  <h3 className="display-sm">MCP Servers</h3>
                  <p className="caption">Model Context Protocol server integrations for this team.</p>
                </div>
                <div style={{ padding: "var(--sp-lg)" }}>
                  <McpIntegration teamId={teamId} agents={agents} onToast={(msg, type) => toast.show(msg, type as any)} />
                </div>
              </div>
            </div>
          )}
        </main>

        <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />
        <KeyboardShortcutsModal />
      </Panel>
    </PanelGroup>
  );
}

function AppContent() {
  const { user, loading } = useAuth();
  if (loading) return <LoadingScreen steps={["Checking authentication…"]} />;
  if (!user) return <AuthPage />;
  return <AppShell />;
}

export default function Home() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </ErrorBoundary>
  );
}
