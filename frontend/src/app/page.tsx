"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { PanelGroup, Panel, PanelResizeHandle, ImperativePanelHandle } from "react-resizable-panels";
import { Maximize2, Minimize2, X, GripHorizontal } from "lucide-react";
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
import AuthModal from "@/components/AuthModal";
import LandingPage from "@/components/LandingPage";
import ToastContainer from "@/components/Toast";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { AuthProvider, useAuth } from "@/hooks/useAuth";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useToast } from "@/hooks/useToast";
import { api } from "@/hooks/useApi";
import FileExplorerPanel from "@/components/FileExplorerPanel";
import KeyboardShortcutsModal from "@/components/KeyboardShortcutsModal";
import type { AgentConfig, ChatMessage, TaskItem, BrowserScreenshotEvent, LearningItem, ScratchpadItem, CompactionEvent } from "@/lib/types";

const makeId = () => `${Date.now()}-${Math.random().toString(36).slice(2)}`;

function applyWSEvent(prev: ChatMessage[], evt: any, user: any): ChatMessage[] {
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
        attachments: evt.attachments || [],
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
    case "file_change": {
      // If the file change was made by the human User, do not append it to the chat messages history.
      if (
        evt.sender_name === "User" ||
        evt.sender_id === "human" ||
        (user && evt.sender_id === user.id) ||
        (user && evt.sender_name === `${user.first_name || ""} ${user.last_name || ""}`.trim()) ||
        (user && evt.sender_name === user.email.split("@")[0])
      ) {
        return prev;
      }
      // Dedup: if the last file_change in chat is for the same path by the same agent,
      // update it in-place instead of appending a new pill (prevents flood during retries).
      const last = prev[prev.length - 1];
      if (last && last.type === "file_change" && last.path === evt.path && last.sender_id === (evt.sender_id || "agent")) {
        return [...prev.slice(0, -1), { ...last, timestamp: ts, action: evt.action, diff: evt.diff }];
      }
      return [...prev, { id: makeId(), sender_id: evt.sender_id || "agent", sender_name: evt.sender_name, type: "file_change", path: evt.path, action: evt.action, diff: evt.diff, text: evt.text || "", timestamp: ts }];
    }
    case "agent_question":
      return [...prev, { id: makeId(), sender_id: evt.agent_id || evt.sender_id || "agent", sender_name: evt.agent_name || evt.sender_name, text: evt.text || "", type: "agent_question", question_id: evt.question_id, question: evt.question, options: evt.options, timestamp: ts }];
    case "browser_intervention":
      return [...prev, { id: makeId(), sender_id: evt.agent_id || evt.sender_id || "agent", sender_name: evt.agent_name || evt.sender_name, text: evt.text || "", type: "browser_intervention", question_id: evt.question_id, reason: evt.reason, captcha_image: evt.captcha_image, timestamp: ts }];
    case "llm_error":
      return [...prev, { id: makeId(), sender_id: evt.sender_id || "agent", type: "llm_error", text: evt.error?.message || "LLM Error", llm_error: evt.error, timestamp: ts }];
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
    case "message_rewind": {
      const fromId = evt.from_message_id;
      if (fromId) {
        const idx = prev.findIndex(m => m.id === fromId);
        if (idx >= 0) {
          return prev.slice(0, idx);
        }
      }
      if (evt.from_timestamp) {
        const pivotStr = typeof evt.from_timestamp === "string" && !evt.from_timestamp.endsWith("Z") && !evt.from_timestamp.includes("+")
          ? evt.from_timestamp + "Z"
          : evt.from_timestamp;
        const pivot = new Date(pivotStr).getTime();
        if (!isNaN(pivot)) {
          return prev.filter(m => {
            if (!m.timestamp) return false;
            const mtsStr = typeof m.timestamp === "string" && !m.timestamp.endsWith("Z") && !m.timestamp.includes("+")
              ? m.timestamp + "Z"
              : m.timestamp;
            const mts = typeof mtsStr === "number" ? mtsStr : new Date(mtsStr).getTime();
            return !isNaN(mts) && mts < pivot;
          });
        }
      }
      return prev;
    }
    default:
      return prev;
  }
}

function AppShell() {
  const { user, logout } = useAuth();
  const toast = useToast();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  }, []);

  const [widgetPos, setWidgetPos] = useState<{ x: number, y: number } | null>(null);
  const [isDraggingWidget, setIsDraggingWidget] = useState(false);
  const dragRef = useRef<{ startX: number, startY: number, initX: number, initY: number } | null>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("carole_widget_pos");
      if (saved) {
        setWidgetPos(JSON.parse(saved));
      } else {
        setWidgetPos({ x: window.innerWidth - 110, y: 12 });
      }
    } catch {
        setWidgetPos({ x: window.innerWidth - 110, y: 12 });
    }
  }, []);

  useEffect(() => {
    if (widgetPos && !isDraggingWidget) {
      try {
        localStorage.setItem("carole_widget_pos", JSON.stringify(widgetPos));
      } catch {}
    }
  }, [widgetPos, isDraggingWidget]);

  const handlePointerDown = (e: React.PointerEvent) => {
    if (!widgetPos) return;
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      initX: widgetPos.x,
      initY: widgetPos.y
    };
    setIsDraggingWidget(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDraggingWidget || !dragRef.current) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    setWidgetPos({
      x: dragRef.current.initX + dx,
      y: dragRef.current.initY + dy
    });
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (isDraggingWidget) {
      setIsDraggingWidget(false);
      dragRef.current = null;
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
  };

  const [activeView, setActiveView] = useState("chat");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(260);

  useEffect(() => {
    try {
      const savedCollapsed = localStorage.getItem("carole_sidebar_collapsed");
      if (savedCollapsed !== null) {
        setSidebarCollapsed(savedCollapsed === "true");
      } else {
        setSidebarCollapsed(true);
      }
      const savedWidth = localStorage.getItem("carole_sidebar_width");
      if (savedWidth !== null) {
        const parsed = parseInt(savedWidth, 10);
        if (!isNaN(parsed) && parsed >= 180 && parsed <= 500) {
          setSidebarWidth(parsed);
        }
      }
    } catch {}
  }, []);

  const handleToggleSidebar = useCallback((forceState?: boolean) => {
    setSidebarCollapsed(prev => {
      const next = forceState !== undefined ? forceState : !prev;
      try {
        localStorage.setItem("carole_sidebar_collapsed", String(next));
      } catch {}
      return next;
    });
  }, []);

  const handleWidthChange = useCallback((newWidth: number) => {
    setSidebarWidth(newWidth);
    try {
      localStorage.setItem("carole_sidebar_width", String(newWidth));
    } catch {}
  }, []);
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
  const [isChatPanelCollapsed, setIsChatPanelCollapsed] = useState(false);
  const chatPanelRef = useRef<ImperativePanelHandle>(null);
  const [pendingChatInputAppend, setPendingChatInputAppend] = useState<string | null>(null);

  const handleAppendToChat = useCallback((text: string) => {
    setPendingChatInputAppend(text);
    const chatPanel = chatPanelRef.current;
    if (chatPanel && chatPanel.isCollapsed()) {
      chatPanel.expand();
    }
    setIsChatPanelCollapsed(false);
  }, []);

  const handleViewChange = useCallback((view: string) => {
    if (view === "chat") {
      if (activeView === "chat") {
        const chatPanel = chatPanelRef.current;
        if (chatPanel) {
          if (chatPanel.isCollapsed()) {
            chatPanel.expand();
          } else {
            chatPanel.collapse();
          }
        }
      } else {
        setActiveView("chat");
        const chatPanel = chatPanelRef.current;
        if (chatPanel && chatPanel.isCollapsed()) {
          chatPanel.expand();
        }
      }
    } else {
      setActiveView(view);
    }
  }, [activeView]);

  // Automatically collapse left sidebar when file explorer is opened to maximize workspace
  useEffect(() => {
    if (explorerOpen) {
      setSidebarCollapsed(true);
      try {
        localStorage.setItem("carole_sidebar_collapsed", "true");
      } catch {}
    }
  }, [explorerOpen]);

  // Latest file_change WS event, fed to the FileExplorerPanel for realtime sync.
  const [lastFileChange, setLastFileChange] = useState<any | null>(null);
  // A file path the explorer should open automatically (set when the user
  // clicks a file-change card in chat).
  const [pendingOpenFile, setPendingOpenFile] = useState<string | null>(null);
  const [agentQueues, setAgentQueues] = useState<Record<string, number>>({});
  const [scratchpads, setScratchpads] = useState<ScratchpadItem[]>([]);
  const [lastTokenEvent, setLastTokenEvent] = useState<any | null>(null);
  const [contextUsage, setContextUsage] = useState<any | null>(null);
  // Compaction events — rendered as visible dividers in the chat timeline.
  // Populated on team load (from DB) and updated live via SSE.
  const [compactionEvents, setCompactionEvents] = useState<CompactionEvent[]>([]);

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

    if (["thought_delta", "thought_reset", "stream_reasoning", "message", "approval_request", "approval_update", "approval_resolved", "agent_question", "browser_intervention", "tool_start", "tool_end", "tool_progress", "agent_status", "message_deleted", "message_rewind", "chat_cleared", "file_change", "collapse_to_reasoning", "llm_error"].includes(evt.type)) {
      setMessages(prev => {
        const updated = applyWSEvent(prev, evt, user);
        
        if (evt.type.startsWith("approval_") && teamId) {
          const pending = updated.filter(m => 
            (m.type === "approval_request" && m.status !== "approved" && m.status !== "denied") ||
            (m.pending_approval && m.pending_approval.status !== "approved" && m.pending_approval.status !== "denied")
          ).map(m => m.pending_approval ? { id: makeId(), sender_id: m.sender_id, sender_name: m.sender_name, text: m.pending_approval.text || "", type: "approval_request", tx_id: m.pending_approval.tx_id, tool_name: m.pending_approval.tool_name, arguments: m.pending_approval.arguments, timestamp: m.timestamp } : m);
          try { localStorage.setItem(`carole_pending_approvals_${teamId}`, JSON.stringify(pending)); } catch {}
        }
        
        return updated.length > 150 ? updated.slice(-150) : updated;
      });
    }

    if (evt.type === "file_change" || evt.type === "file_system_updated") {
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
    if (evt.type === "token_usage") {
      setLastTokenEvent(evt);
    }
    if (evt.type === "context_usage") {
      setContextUsage(evt);
    }
    // ── Compaction events: render a visible divider in chat ──
    if (evt.type === "compaction_event" && evt.id) {
      setCompactionEvents(prev => {
        if (prev.some(e => e.id === evt.id)) return prev; // dedup
        return [...prev, {
          id: evt.id,
          triggered_by: evt.triggered_by ?? "auto",
          message_count_before: evt.message_count_before,
          summary_preview: evt.summary_preview,
          created_at: evt.created_at,
        }];
      });
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
    if (evt.type === "agent_created" && evt.agent) {
      setAgents(prev => {
        if (prev.some(a => a.id === evt.agent.id)) return prev;
        return [...prev, evt.agent];
      });
    }
    if (evt.type === "agent_updated" && evt.agent) {
      setAgents(prev => prev.map(a => a.id === evt.agent.id ? { ...a, ...evt.agent } : a));
    }
    if (evt.type === "agent_deleted" && evt.agent_id) {
      setAgents(prev => prev.filter(a => a.id !== evt.agent_id));
    }
  }, [user, teamId]);

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
    if (!teamId) { setAgents([]); setMessages([]); setTasks([]); setScreenshots([]); setScratchpads([]); setCompactionEvents([]); return; }
    Promise.all([
      api.listAgents(teamId),
      api.listTasks(teamId),
      api.listMessages(teamId),
      api.listScratchpads(teamId),
      api.listCompactions(teamId).catch(() => [] as any[]),
    ])
      .then(([ags, tks, msgs, pads, cpEvents]) => {
        setAgents(ags);
        setTasks(tks);
        setScratchpads(pads);
        const fetchedMsgs = msgs.map((m: any) => ({
          ...m,
          id: m.id || makeId(),
          type: m.is_intermediate ? "tool_trace" : (m.type || "message"),
          timestamp: m.created_at,
          reasoning: m.reasoning ?? undefined,
          is_intermediate: m.is_intermediate ?? false,
        }));
        
        // Fold approval_resolved events into their corresponding approval_request messages
        const resolvedMap = new Map();
        fetchedMsgs.forEach((m: any) => {
           if (m.type === "approval_resolved" && m.tx_id) {
               resolvedMap.set(m.tx_id, m.status || m.action || "resolved");
           }
        });
        
        const finalMsgs = fetchedMsgs.map((m: any) => {
           if (m.type === "approval_request" && m.tx_id && resolvedMap.has(m.tx_id)) {
               return { ...m, status: resolvedMap.get(m.tx_id) };
           }
           return m;
        });
        
        let hydratedApprovals = [];
        try {
          const saved = localStorage.getItem(`carole_pending_approvals_${teamId}`);
          if (saved) hydratedApprovals = JSON.parse(saved);
        } catch {}
        
        setMessages([...finalMsgs, ...hydratedApprovals]);
        setCompactionEvents((cpEvents as any[]).map((e: any) => ({
          id: e.id,
          triggered_by: e.triggered_by ?? "auto",
          message_count_before: e.message_count_before,
          summary_preview: e.summary_preview,
          created_at: e.created_at,
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
    <div className="schematic-bg" style={{ display: "flex", width: "100vw", height: "100vh", overflow: "hidden", background: "var(--bg-app)", position: "relative" }}>
      {widgetPos && (
        <div 
          style={{ 
            position: "absolute", 
            left: `${widgetPos.x}px`, 
            top: `${widgetPos.y}px`, 
            zIndex: 9999, 
            display: "flex", 
            gap: "4px", 
            background: "rgba(10, 10, 26, 0.6)", 
            backdropFilter: "blur(12px)", 
            padding: "4px 6px", 
            borderRadius: "10px", 
            border: "1px solid rgba(255, 255, 255, 0.1)",
            alignItems: "center",
            boxShadow: isDraggingWidget ? "0 8px 32px rgba(0,0,0,0.4)" : "0 4px 12px rgba(0,0,0,0.2)",
            transition: isDraggingWidget ? "none" : "box-shadow 0.2s ease"
          }}
        >
          <div 
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            style={{
              cursor: isDraggingWidget ? "grabbing" : "grab",
              padding: "4px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              touchAction: "none"
            }}
            title="Drag to move"
          >
            <GripHorizontal size={14} style={{ color: "var(--color-mute)" }} />
          </div>
          <button 
            className="btn btn-icon-sm btn-ghost" 
            onClick={toggleFullscreen} 
            title={isFullscreen ? "Exit Fullscreen (Minimize)" : "Enter Fullscreen"}
            style={{ width: "26px", height: "26px", color: "var(--color-body)", background: "transparent", border: "none" }}
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
          <button 
            className="btn btn-icon-sm btn-ghost" 
            onClick={() => {
              if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
              logout();
            }} 
            title="Close (Sign Out)"
            style={{ width: "26px", height: "26px", color: "var(--color-danger, #ef4444)", background: "transparent", border: "none" }}
          >
            <X size={14} />
          </button>
        </div>
      )}
      <Sidebar
        activeView={activeView === "chat" && isChatPanelCollapsed ? "" : activeView}
        onViewChange={handleViewChange}
        connected={connected}
        projects={projects}
        projectId={projectId}
        onProjectChange={setProjectId}
        onProjectCreated={handleProjectCreated}
        teams={teams}
        teamId={teamId}
        onTeamChange={setTeamId}
        onTeamCreated={handleTeamCreated}
        isCollapsed={sidebarCollapsed}
        onToggleCollapse={handleToggleSidebar}
        width={sidebarWidth}
        onWidthChange={handleWidthChange}
      />

      <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, overflow: "hidden", background: "transparent", position: "relative", width: "100%" }}>
        {activeView === "chat" && (
          <div className="animate-entrance" style={{ display: "flex", flex: 1, minHeight: 0, width: "100%" }}>
            <PanelGroup direction="horizontal" autoSaveId="chat-layout-v2">
              <Panel
                ref={chatPanelRef}
                id="chat-main-panel"
                order={1}
                collapsible={explorerOpen}
                defaultSize={45}
                minSize={30}
                onCollapse={() => setIsChatPanelCollapsed(true)}
                onExpand={() => setIsChatPanelCollapsed(false)}
                style={{ display: "flex", minWidth: 0, flexDirection: "column" }}
              >
                <div style={{ display: "flex", flex: 1, minWidth: 0, minHeight: 0 }}>
                  <ChatInterface
                    messages={messages}
                    agents={agents}
                    onSendMessage={handleSendMessage}
                    pendingChatInputAppend={pendingChatInputAppend}
                    onAppendConsumed={() => setPendingChatInputAppend(null)}
                    compactionEvents={compactionEvents}
                    onCompact={async () => {
                      if (!teamId) return;
                      try {
                        await api.compactTeam(teamId);
                        // SSE will deliver the compaction_event back to us;
                        // no need to update state here — handleWSEvent handles it.
                      } catch (err: any) {
                        toast.error(err?.message || "Compaction failed");
                      }
                    }}
                    onDeleteMessage={async (id) => {
                      setMessages(prev => prev.filter(m => m.id !== id));
                      try {
                        await api.deleteMessage(id);
                      } catch (err: any) {
                        if (err?.status !== 404) {
                          toast.error(err?.message || "Failed to delete message");
                        }
                      }
                    }}
                    onRollbackMessage={async (id) => {
                      // Optimistically slice away the target message and all newer messages
                      setMessages(prev => {
                        const idx = prev.findIndex(m => m.id === id);
                        if (idx >= 0) return prev.slice(0, idx);
                        const pivotMsg = prev.find(m => m.id === id);
                        if (pivotMsg && pivotMsg.timestamp) {
                          const pivotStr = typeof pivotMsg.timestamp === "string" && !pivotMsg.timestamp.endsWith("Z" ) && !pivotMsg.timestamp.includes("+")
                            ? pivotMsg.timestamp + "Z"
                            : pivotMsg.timestamp;
                          const pivot = new Date(pivotStr).getTime();
                          if (!isNaN(pivot)) {
                            return prev.filter(m => {
                              if (!m.timestamp) return false;
                              const mtsStr = typeof m.timestamp === "string" && !m.timestamp.endsWith("Z" ) && !m.timestamp.includes("+")
                                ? m.timestamp + "Z"
                                : m.timestamp;
                              const mts = typeof mtsStr === "number" ? mtsStr : new Date(mtsStr).getTime();
                              return !isNaN(mts) && mts < pivot;
                            });
                          }
                        }
                        return prev;
                      });

                      try {
                        const res = await api.rollbackFromMessage(id);
                        const restoredCount = res?.restored_files?.length ?? 0;
                        const deletedCount = res?.deleted_files?.length ?? 0;
                        const msgCount = res?.deleted_count ?? 1;
                        toast.success(`Rolled back ${msgCount} message(s)${restoredCount + deletedCount > 0 ? ` and restored ${restoredCount + deletedCount} file(s)` : ""}`);
                      } catch (err: any) {
                        if (err?.status !== 404) {
                          toast.error(err?.message || "Failed to rollback");
                        }
                      }
                    }}
                    onClearChat={() => {
                      setMessages([]);
                      toast.success("Chat cleared");
                    }}
                    teamId={teamId}
                    projectId={projectId}
                    lastTokenEvent={lastTokenEvent}
                    contextUsage={contextUsage}
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
                  <Panel id="chat-explorer-panel" order={2} defaultSize={55} minSize={20} style={{ display: "flex", minWidth: 0 }}>
                    <FileExplorerPanel
                      onClose={() => setExplorerOpen(false)}
                      projectId={projectId || undefined}
                      teamId={teamId || undefined}
                      lastFileChange={lastFileChange}
                      pendingOpenFile={pendingOpenFile}
                      onPendingOpenConsumed={() => setPendingOpenFile(null)}
                      onAppendToChat={handleAppendToChat}
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
    </div>
  );
}

function AppContent() {
  const { user, loading } = useAuth();
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "signup">("login");

  if (loading) return <LoadingScreen steps={["Checking authentication…"]} />;
  
  if (!user) {
    return (
      <>
        <LandingPage
          onLaunchApp={() => {
            setAuthMode("login");
            setShowAuthModal(true);
          }}
          onSignIn={() => {
            setAuthMode("login");
            setShowAuthModal(true);
          }}
          onSignUp={() => {
            setAuthMode("signup");
            setShowAuthModal(true);
          }}
        />
        <AuthModal
          isOpen={showAuthModal}
          initialMode={authMode}
          onClose={() => setShowAuthModal(false)}
        />
      </>
    );
  }

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
