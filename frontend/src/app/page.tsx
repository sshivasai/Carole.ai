"use client";

import React, { useState, useEffect } from "react";
import Sidebar from "@/components/Sidebar";
import ChatInterface from "@/components/ChatInterface";
import KanbanBoard from "@/components/KanbanBoard";
import BrowserView from "@/components/BrowserView";
import MemoryView from "@/components/MemoryView";
import { useWebSocket } from "@/hooks/useWebSocket";
import { api } from "@/hooks/useApi";
import type { AgentConfig, ChatMessage, TaskItem, BrowserScreenshotEvent, LearningItem } from "@/lib/types";

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
      setMessages(msgs.map((m: any) => ({ ...m, type: "message" })));
    });
  }, [teamId]);

  // Handle WebSocket Events
  useEffect(() => {
    if (events.length === 0) return;
    const evt = events[events.length - 1];
    
    if (evt.type === "message") {
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        sender_id: evt.sender_id || "unknown",
        sender_name: evt.sender_name,
        text: evt.text || "",
        type: "message",
      }]);
    } else if (evt.type === "browser_screenshot") {
      setBrowserScreenshots(prev => [evt as BrowserScreenshotEvent, ...prev].slice(0, 50));
    } else if (evt.type === "task_update" && evt.task) {
      if (evt.action === "created") setTasks(prev => [evt.task!, ...prev]);
      else if (evt.action === "updated") setTasks(prev => prev.map(t => t.id === evt.task!.id ? { ...t, ...evt.task! } : t));
    }
  }, [events]);

  const handleSendMessage = (text: string) => {
    sendMessage(text);
    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      sender_id: "human",
      sender_name: "You",
      text,
      type: "message",
    }]);
  };

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
