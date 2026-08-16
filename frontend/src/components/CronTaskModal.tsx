"use client";
import React, { useState, useEffect } from "react";
import Modal from "./Modal";
import { api } from "@/hooks/useApi";
import type { ScheduledTask, AgentConfig } from "@/lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
  teamId: string;
  agents: AgentConfig[];
  existingTask?: ScheduledTask | null;
  onSave: (task: ScheduledTask) => void;
}

export default function CronTaskModal({ open, onClose, teamId, agents, existingTask, onSave }: Props) {
  const [name, setName] = useState("");
  const [agentId, setAgentId] = useState("");
  const [cronExp, setCronExp] = useState("");
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) {
      if (existingTask) {
        setName(existingTask.name);
        setAgentId(existingTask.agent_id);
        setCronExp(existingTask.cron_expression);
        setPrompt(existingTask.prompt);
      } else {
        setName("");
        setAgentId(agents[0]?.id || "");
        setCronExp("");
        setPrompt("");
      }
      setError("");
    }
  }, [open, existingTask, agents]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !agentId || !cronExp.trim() || !prompt.trim()) {
      setError("All fields are required.");
      return;
    }
    
    setLoading(true);
    setError("");
    try {
      if (existingTask) {
        const res = await api.updateScheduledTask(existingTask.id, {
          name: name.trim(),
          cron_expression: cronExp.trim(),
          prompt: prompt.trim()
        });
        onSave(res);
      } else {
        const res = await api.createScheduledTask(teamId, {
          name: name.trim(),
          agent_id: agentId,
          cron_expression: cronExp.trim(),
          prompt: prompt.trim()
        });
        onSave(res);
      }
      onClose();
    } catch (err: any) {
      setError(err.body || err.message || "Failed to save scheduled task");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={existingTask ? "Edit Scheduled Task" : "New Scheduled Task"} maxWidth={500}>
      <form onSubmit={handleSubmit} className="flex-col gap-4">
        {error && <div className="text-danger text-sm">{error}</div>}
        
        <div className="flex-col gap-1">
          <label className="text-sm font-medium">Task Name</label>
          <input 
            className="input" 
            placeholder="e.g. Nightly Build" 
            value={name}
            onChange={e => setName(e.target.value)}
            autoFocus
          />
        </div>

        <div className="flex-col gap-1">
          <label className="text-sm font-medium">Target Agent</label>
          <select 
            className="input" 
            value={agentId} 
            onChange={e => setAgentId(e.target.value)}
          >
            {agents.map(a => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
        </div>

        <div className="flex-col gap-1">
          <label className="text-sm font-medium">
            Cron Expression 
            <a href="https://crontab.guru/" target="_blank" rel="noreferrer" className="text-muted ml-2" style={{ textDecoration: 'underline' }}>
              (Need help?)
            </a>
          </label>
          <input 
            className="input" 
            placeholder="* * * * *" 
            value={cronExp}
            onChange={e => setCronExp(e.target.value)}
          />
          <div className="text-xs text-muted">Format: minute hour day month day-of-week</div>
        </div>

        <div className="flex-col gap-1">
          <label className="text-sm font-medium">System Prompt</label>
          <textarea 
            className="input" 
            style={{ minHeight: '80px', resize: 'vertical' }}
            placeholder="e.g. Please run the test suite and report any errors." 
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
          />
        </div>

        <div className="flex justify-end gap-2 mt-2">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={loading}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? "Saving..." : "Save Task"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
