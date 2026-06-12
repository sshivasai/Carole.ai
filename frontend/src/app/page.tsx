"use client";

import React, { useState, useEffect, useCallback } from "react";
import Sidebar from "@/components/Sidebar";
import ChatInterface from "@/components/ChatInterface";
import KanbanBoard from "@/components/KanbanBoard";
import BrowserView from "@/components/BrowserView";
import MemoryView from "@/components/MemoryView";
import { useWebSocket } from "@/hooks/useWebSocket";
import { api } from "@/hooks/useApi";
import type { AgentConfig, ChatMessage, TaskItem, BrowserScreenshotEvent, LearningItem } from "@/lib/types";

// Stable ID helper
const makeId = () => `${Date.now()}-${Math.random().toString(36).slice(2)}`;

// ─── WS Event Reducer ────────────────────────────────────────────────────────
/**
 * Applies a single WebSocket event to the messages array.
 *
 * Key behaviours:
 * - `thought_delta` → accumulates into a single `streaming` bubble per
 *   sender, instead of creating hundreds of individual message entries.
 * - `message` from an agent → replaces the streaming bubble with the
 *   final committed message so there is no flash/duplication.
 * - `approval_request` → adds an inline approval card message.
 * - `agent_question` → adds an inline ask_user card message.
 * - `tool_start` / `tool_end` → adds compact tool-event rows.
 */
function applyWSEvent(prev: ChatMessage[], evt: any): ChatMessage[] {
  const ts = Date.now();

  switch (evt.type) {
    case "thought_delta": {
      const streamId = `streaming-${evt.sender_id}`;
      const existing = prev.find(m => m.id === streamId);
      if (existing) {
        return prev.map(m =>
          m.id === streamId ? { ...m, text: m.text + (evt.delta || "") } : m
        );
      }
      return [...prev, {
        id: streamId,
        sender_id: evt.sender_id || "agent",
        sender_name: evt.sender_name,
        role: evt.role,
        text: evt.delta || "",
        type: "streaming",
        timestamp: ts,
      }];
    }

    case "message": {
      // When an agent emits its final message, replace the streaming bubble
      const streamId = `streaming-${evt.sender_id}`;
      const filtered = prev.filter(m => m.id !== streamId);
      return [...filtered, {
        id: makeId(),
        sender_id: evt.sender_id || "agent",
        sender_name: evt.sender_name,
        role: evt.role,
        text: evt.text || "",
        type: "message",
        timestamp: ts,
      }];
    }

    case "approval_request": {
      return [...prev, {
        id: makeId(),
        sender_id: evt.agent_id || evt.sender_id || "agent",
        sender_name: evt.agent_name || evt.sender_name,
        text: evt.text || "",
        type: "approval_request",
        tx_id: evt.tx_id,
        tool_name: evt.tool_name,
        arguments: evt.arguments,
        timestamp: ts,
      }];
    }

    case "agent_question": {
      return [...prev, {
        id: makeId(),
        sender_id: evt.agent_id || evt.sender_id || "agent",
        sender_name: evt.agent_name || evt.sender_name,
        text: evt.text || "",
        type: "agent_question",
        question_id: evt.question_id,
        question: evt.question,
        timestamp: ts,
      }];
    }

    case "tool_start": {
      return [...prev, {
        id: makeId(),
        sender_id: evt.sender_id || "agent",
        sender_name: evt.sender_name,
        text: `Running ${evt.tool_name}...`,
        type: "tool_start",
        tool_name: evt.tool_name,
        arguments: evt.arguments,
        timestamp: ts,
      }];
    }

    case "tool_end": {
      return [...prev, {
        id: makeId(),
        sender_id: evt.sender_id || "agent",
        sender_name: evt.sender_name,
        text: evt.observation || "",
        type: "tool_end",
        tool_name: evt.tool_name,
        timestamp: ts,
      }];
    }

    default:
      return prev;
  }
}

export default function Home() {
  const [activeView, setActiveView] = useState("chat");
  const [userId, setUserId] = useState<string | null>(null);
  
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projects, setProjects] = useState<any[]>([]);
  
  const [teamId, setTeamId] = useState<string | null>(null);
  const [teams, setTeams] = useState<any[]>([]);
  
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [learnings, setLearnings] = useState<LearningItem[]>([]);
  const [browserScreenshots, setBrowserScreenshots] = useState<BrowserScreenshotEvent[]>([]);
  const [loading, setLoading] = useState(true);

  // WebSocket hook
  const { connected, events, sendMessage } = useWebSocket(teamId);

  // Initial Load
  useEffect(() => {
    async function init() {
      try {
        await api.seedDemo();
        const usersRes = await api.listUsers();
        if (usersRes.length > 0) setUserId(usersRes[0].id);
        
        const projs = await api.listProjects();
        setProjects(projs);
        if (projs.length > 0) setProjectId(projs[0].id);
      } catch (e) {
        console.error("Init load error:", e);
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  // Load Teams when Project changes
  useEffect(() => {
    if (!projectId) return;
    api.listTeams(projectId).then(tms => {
      setTeams(tms);
      setTeamId(tms.length > 0 ? tms[0].id : null);
    });
    api.listLearnings(projectId).then(setLearnings);
  }, [projectId]);

  // Load Team Data (Agents, Messages, Tasks)
  useEffect(() => {
    if (!teamId) {
      setAgents([]); setMessages([]); setTasks([]); setBrowserScreenshots([]);
      return;
    }
    api.listAgents(teamId).then(setAgents);
    api.listTasks(teamId).then(setTasks);
    api.listMessages(teamId).then(msgs => {
      setMessages(msgs.map((m: any) => ({
        ...m,
        id: m.id || makeId(),
        type: "message",
        timestamp: m.created_at,
      })));
    });
  }, [teamId]);

  // Handle WebSocket Events via the reducer
  useEffect(() => {
    if (events.length === 0) return;
    const evt = events[events.length - 1];

    // Chat message events → reducer
    if (["thought_delta", "message", "approval_request", "agent_question", "tool_start", "tool_end"].includes(evt.type)) {
      setMessages(prev => applyWSEvent(prev, evt));
    }

    // Browser screenshot events
    if (evt.type === "browser_screenshot") {
      setBrowserScreenshots(prev => [...prev, evt as BrowserScreenshotEvent].slice(-50));
    }

    // Task board events
    if (evt.type === "task_update" && evt.task) {
      if (evt.action === "created") setTasks(prev => [evt.task!, ...prev]);
      else if (evt.action === "updated") setTasks(prev => prev.map(t => t.id === evt.task!.id ? { ...t, ...evt.task! } : t));
    }
  }, [events]);

  const handleSendMessage = useCallback((text: string) => {
    sendMessage(text);
    setMessages(prev => [...prev, {
      id: makeId(),
      sender_id: "human",
      sender_name: "You",
      text,
      type: "message",
      timestamp: Date.now(),
    }]);
  }, [sendMessage]);

  if (loading) {
    return <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center' }}>Loading Carole.ai...</div>;
  }

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar 
        activeView={activeView}
        onViewChange={setActiveView}
        connected={connected}
        projects={projects}
        projectId={projectId}
        onProjectChange={setProjectId}
        onAddProject={() => {}} // Placeholder
        teams={teams}
        teamId={teamId}
        onTeamChange={setTeamId}
        onAddTeam={() => {}} // Placeholder
      />
      
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, background: 'var(--color-canvas)', position: 'relative' }}>
        {activeView === "chat" && (
          <ChatInterface 
            messages={messages} 
            agents={agents} 
            onSendMessage={handleSendMessage} 
          />
        )}
        {activeView === "tasks" && (
          <KanbanBoard tasks={tasks} agents={agents} teamId={teamId} />
        )}
        {activeView === "browser" && (
          <BrowserView screenshots={browserScreenshots} />
        )}
        {activeView === "memory" && (
          <MemoryView learnings={learnings} />
        )}
        {activeView === "agents" && (
          <div style={{ padding: 'var(--sp-4xl)' }}>
            <h2 className="display-lg" style={{ marginBottom: 'var(--sp-2xl)' }}>Team Agents</h2>
            <div style={{ display: 'grid', gap: 'var(--sp-lg)', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))' }}>
              {agents.map(agent => (
                <div key={agent.id} className="card">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-sm)', marginBottom: 'var(--sp-sm)' }}>
                    <h3 className="display-sm">{agent.name}</h3>
                    <span className="pill pill-idle" style={{ zoom: 0.8 }}>{agent.role}</span>
                  </div>
                  <p className="body-sm" style={{ color: 'var(--color-mute)' }}>Model: {agent.model}</p>
                  {agent.skills && agent.skills.length > 0 && (
                    <div style={{ marginTop: 'var(--sp-md)', display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                      {agent.skills.map(s => <span key={s} className="code-inline">{s}</span>)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
