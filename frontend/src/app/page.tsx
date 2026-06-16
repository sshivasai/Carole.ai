"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import Sidebar from "@/components/Sidebar";
import ChatInterface from "@/components/ChatInterface";
import KanbanBoard from "@/components/KanbanBoard";
import BrowserView from "@/components/BrowserView";
import MemoryView from "@/components/MemoryView";
import AgentPanel from "@/components/AgentPanel";
import SettingsPanel from "@/components/SettingsPanel";
import LoadingScreen from "@/components/LoadingScreen";
import AuthPage from "@/components/AuthPage";
import ToastContainer from "@/components/Toast";
import { AuthProvider, useAuth } from "@/hooks/useAuth";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useToast } from "@/hooks/useToast";
import { api } from "@/hooks/useApi";
import FileExplorerPanel from "@/components/FileExplorerPanel";
import type { AgentConfig, ChatMessage, TaskItem, BrowserScreenshotEvent, LearningItem } from "@/lib/types";

const makeId = () => `${Date.now()}-${Math.random().toString(36).slice(2)}`;

function applyWSEvent(prev: ChatMessage[], evt: any): ChatMessage[] {
  const ts = Date.now();
  switch (evt.type) {
    case "thought_delta": {
      const sid = `streaming-${evt.sender_id}`;
      const ex = prev.find(m => m.id === sid);
      if (ex) return prev.map(m => m.id === sid ? { ...m, text: m.text + (evt.delta || "") } : m);
      return [...prev, { id: sid, sender_id: evt.sender_id || "agent", sender_name: evt.sender_name, role: evt.role, text: evt.delta || "", type: "streaming", timestamp: ts }];
    }
    case "stream_reasoning": {
      // Append reasoning chunk to the streaming bubble for this agent
      const sid = `streaming-${evt.sender_id}`;
      const ex = prev.find(m => m.id === sid);
      const appended = (ex?.reasoning || "") + (evt.chunk || "");
      if (ex) return prev.map(m => m.id === sid ? { ...m, reasoning: appended } : m);
      // No streaming bubble yet — create one to hold the reasoning
      return [...prev, { id: sid, sender_id: evt.sender_id || "agent", sender_name: evt.sender_name, role: evt.role, text: "", reasoning: appended, type: "streaming", timestamp: ts }];
    }
    case "tool_start": {
      // Append a tool-call entry to the streaming agent's reasoning trace
      const sid = `streaming-${evt.sender_id}`;
      const args = evt.arguments ? JSON.stringify(evt.arguments, null, 2) : "";
      const entry = `\n🛠️ **${evt.tool_name}**\n\`\`\`json\n${args}\n\`\`\`\n`;
      const ex = prev.find(m => m.id === sid);
      if (ex) return prev.map(m => m.id === sid ? { ...m, reasoning: (m.reasoning || "") + entry } : m);
      return [...prev, { id: sid, sender_id: evt.sender_id || "agent", sender_name: evt.sender_name, role: evt.role, text: "", reasoning: entry, type: "streaming", timestamp: ts }];
    }
    case "tool_end": {
      // Append tool result to the streaming agent's reasoning trace
      const sid = `streaming-${evt.sender_id}`;
      const obs = (evt.observation || "").slice(0, 1000);
      const entry = `📄 **Result:**\n\`\`\`\n${obs}\n\`\`\`\n`;
      return prev.map(m => m.id === sid ? { ...m, reasoning: (m.reasoning || "") + entry } : m);
    }
    case "message": {
      const sid = `streaming-${evt.sender_id}`;
      const streamingMsg = prev.find(m => m.id === sid);
      const newId = evt.id || makeId();
      // Preserve the accumulated reasoning into the final message, and remove existing duplicate IDs
      return [...prev.filter(m => m.id !== sid && m.id !== `thinking-${evt.sender_id}` && m.id !== newId), {
        id: newId, sender_id: evt.sender_id || "agent", sender_name: evt.sender_name,
        role: evt.role, text: evt.text || "", type: "message", timestamp: ts,
        reasoning: streamingMsg?.reasoning || undefined,
      }];
    }
    case "agent_status": {
      if (evt.status === "thinking") {
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
    case "approval_request":
      return [...prev, { id: makeId(), sender_id: evt.agent_id || evt.sender_id || "agent", sender_name: evt.agent_name || evt.sender_name, text: evt.text || "", type: "approval_request", tx_id: evt.tx_id, tool_name: evt.tool_name, arguments: evt.arguments, timestamp: ts }];
    case "file_change":
      return [...prev, { id: makeId(), sender_id: evt.sender_id || "agent", sender_name: evt.sender_name, type: "file_change", path: evt.path, action: evt.action, diff: evt.diff, text: evt.text || "", timestamp: ts }];
    case "agent_question":
      return [...prev, { id: makeId(), sender_id: evt.agent_id || evt.sender_id || "agent", sender_name: evt.agent_name || evt.sender_name, text: evt.text || "", type: "agent_question", question_id: evt.question_id, question: evt.question, timestamp: ts }];
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

  const [activeView,  setActiveView]  = useState("chat");
  const [projects,    setProjects]    = useState<any[]>([]);
  const [projectId,   setProjectId]   = useState<string | null>(null);
  const [teams,       setTeams]       = useState<any[]>([]);
  const [teamId,      setTeamId]      = useState<string | null>(null);
  const [agents,      setAgents]      = useState<AgentConfig[]>([]);
  const [messages,    setMessages]    = useState<ChatMessage[]>([]);
  const [tasks,       setTasks]       = useState<TaskItem[]>([]);
  const [learnings,   setLearnings]   = useState<LearningItem[]>([]);
  const [screenshots, setScreenshots] = useState<BrowserScreenshotEvent[]>([]);
  const [appLoading,  setAppLoading]  = useState(true);
  const [streamingAgents, setStreamingAgents] = useState<Set<string>>(new Set());
  const [explorerOpen, setExplorerOpen] = useState(false);

  const { connected, events, sendMessage } = useWebSocket(teamId);

  // Track which agents are currently streaming
  useEffect(() => {
    if (events.length === 0) return;
    const evt = events[events.length - 1];
    if (evt.type === "thought_delta" && evt.sender_id) {
      setStreamingAgents(s => new Set([...s, evt.sender_id!]));
    } else if (evt.type === "message" && evt.sender_id) {
      setStreamingAgents(s => { const n = new Set(s); n.delete(evt.sender_id!); return n; });
    }
  }, [events]);

  // Initial load
  useEffect(() => {
    async function init() {
      try {
        await api.seedDemo();
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
    Promise.all([api.listTeams(projectId), api.listLearnings(projectId)])
      .then(([tms, lrn]) => {
        setTeams(tms);
        setTeamId(tms.length > 0 ? tms[0].id : null);
        setLearnings(lrn);
      }).catch(console.error);
  }, [projectId]);

  // Load team data when team changes
  useEffect(() => {
    if (!teamId) { setAgents([]); setMessages([]); setTasks([]); setScreenshots([]); return; }
    Promise.all([api.listAgents(teamId), api.listTasks(teamId), api.listMessages(teamId)])
      .then(([ags, tks, msgs]) => {
        setAgents(ags);
        setTasks(tks);
        setMessages(msgs.map((m: any) => ({ ...m, id: m.id || makeId(), type: "message", timestamp: m.created_at })));
      }).catch(console.error);
  }, [teamId]);

  // WebSocket event handler
  useEffect(() => {
    if (events.length === 0) return;
    const evt = events[events.length - 1];
    if (["thought_delta","stream_reasoning","message","approval_request","agent_question","tool_start","tool_end","agent_status","message_deleted","message_rewind", "file_change"].includes(evt.type)) {
      setMessages(prev => applyWSEvent(prev, evt));
    }
    if (evt.type === "browser_screenshot") {
      setScreenshots(prev => [...prev, evt as BrowserScreenshotEvent].slice(-50));
    }
    if (evt.type === "task_update" && evt.task) {
      if (evt.action === "created") setTasks(prev => [evt.task!, ...prev]);
      else if (evt.action === "updated") setTasks(prev => prev.map(t => t.id === evt.task!.id ? { ...t, ...evt.task! } : t));
    }
  }, [events]);


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
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
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

      <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, background: "var(--color-canvas)", position: "relative" }}>
        {activeView === "chat" && (
          <div style={{ display: "flex", height: "100%", width: "100%" }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <ChatInterface 
                messages={messages} 
                agents={agents} 
                onSendMessage={handleSendMessage} 
                onDeleteMessage={(id) => setMessages(prev => prev.filter(m => m.id !== id))}
                onRollbackMessage={(id) => {
                  const pivotMsg = messages.find(m => m.id === id);
                  if (pivotMsg && pivotMsg.timestamp) {
                    const pivot = new Date(pivotMsg.timestamp).getTime();
                    setMessages(prev => prev.filter(m => {
                      const mts = typeof m.timestamp === "number" ? m.timestamp : new Date(m.timestamp || 0).getTime();
                      return mts < pivot;
                    }));
                  }
                }}
                teamId={teamId}
                onToggleExplorer={() => setExplorerOpen(o => !o)}
              />
            </div>
            {explorerOpen && (
              <FileExplorerPanel onClose={() => setExplorerOpen(false)} projectId={projectId || undefined} />
            )}
          </div>
        )}
        {activeView === "tasks" && (
          <KanbanBoard tasks={tasks} agents={agents} teamId={teamId} onTasksChange={setTasks} />
        )}
        {activeView === "agents" && (
          <AgentPanel agents={agents} teamId={teamId} streamingAgents={streamingAgents}
            onAgentsChange={setAgents} onToast={(msg, type) => toast.show(msg, type)} />
        )}
        {activeView === "browser" && (
          <BrowserView screenshots={screenshots} />
        )}
        {activeView === "memory" && (
          <MemoryView learnings={learnings} projectId={projectId} teamId={teamId}
            onLearningsChange={setLearnings} onToast={(msg, type) => toast.show(msg, type)} />
        )}
        {activeView === "settings" && (
          <SettingsPanel teamId={teamId} projectId={projectId} agents={agents}
            onToast={(msg, type) => toast.show(msg, type as any)}
            onTeamDeleted={handleTeamDeleted}
            onProjectDeleted={handleProjectDeleted} />
        )}
      </main>

      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />
    </div>
  );
}

function AppContent() {
  const { user, loading } = useAuth();
  if (loading) return <LoadingScreen steps={["Checking authentication…"]} />;
  if (!user)   return <AuthPage />;
  return <AppShell />;
}

export default function Home() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
