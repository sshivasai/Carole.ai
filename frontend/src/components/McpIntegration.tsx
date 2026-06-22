"use client";
import React, { useState, useEffect, useCallback } from "react";
import { api } from "@/hooks/useApi";
import { AgentConfig } from "@/lib/types";
import { Plus, Loader2, Server, Trash2 } from "lucide-react";

interface Props {
  teamId: string | null;
  agents: AgentConfig[];
  onToast?: (msg: string, type: "success"|"error") => void;
}

export default function McpIntegration({ teamId, agents, onToast }: Props) {
  const [servers,    setServers]    = useState<any[]>([]);
  const [serverName, setServerName] = useState("");
  const [command,    setCommand]    = useState("");
  const [args,       setArgs]       = useState("");
  const [envVars,    setEnvVars]    = useState("");
  const [agentId,    setAgentId]    = useState("");
  const [loading,    setLoading]    = useState(false);
  const [fetching,   setFetching]   = useState(false);

  const loadServers = useCallback(async () => {
    if (!teamId) return;
    setFetching(true);
    try { setServers(await api.listMcpServers(teamId)); }
    catch { /* ignore */ }
    finally { setFetching(false); }
  }, [teamId]);

  useEffect(() => { if (teamId) loadServers(); else setServers([]); }, [teamId, loadServers]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!teamId || !serverName || !command) return;
    setLoading(true);
    try {
      // Parse env vars from KEY=VALUE format
      const parsedEnv: Record<string, string> = {};
      if (envVars.trim()) {
        envVars.split("\n").forEach(line => {
          const idx = line.indexOf("=");
          if (idx > 0) parsedEnv[line.substring(0, idx).trim()] = line.substring(idx + 1).trim();
        });
      }
      await api.createMcpServer({ team_id: teamId, server_name: serverName, command, args, agent_id: agentId || undefined, env_vars: Object.keys(parsedEnv).length > 0 ? parsedEnv : undefined });
      await loadServers();
      setServerName(""); setCommand(""); setArgs(""); setAgentId(""); setEnvVars("");
      onToast?.("MCP server added", "success");
    } catch { onToast?.("Failed to add server", "error"); }
    finally { setLoading(false); }
  };

  if (!teamId) return <p className="caption" style={{ padding: "var(--sp-md)", textAlign: "center" }}>Select a team to manage MCP servers.</p>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-lg)" }}>
      {/* Add form */}
      <form onSubmit={handleAdd} style={{ display: "flex", flexDirection: "column", gap: "var(--sp-sm)" }}>
        <h4 className="label">Add New MCP Server</h4>
        <input className="input" placeholder="Server name (e.g. github)" value={serverName} onChange={e => setServerName(e.target.value)} style={{ fontSize: 12 }} />
        <input className="input" placeholder="Command (e.g. npx)" value={command} onChange={e => setCommand(e.target.value)} style={{ fontSize: 12 }} />
        <input className="input" placeholder="Args comma-separated (e.g. -y,@mcp/server-github)" value={args} onChange={e => setArgs(e.target.value)} style={{ fontSize: 12 }} />
        <textarea className="input" placeholder="Environment Variables (optional)&#10;e.g. GITHUB_PERSONAL_ACCESS_TOKEN=xxx" value={envVars} onChange={e => setEnvVars(e.target.value)} style={{ fontSize: 12, minHeight: "60px", resize: "vertical" }} />
        <select className="input" value={agentId} onChange={e => setAgentId(e.target.value)} style={{ fontSize: 12 }}>
          <option value="">Global (all agents)</option>
          {agents.map(a => <option key={a.id} value={a.id}>{a.name} ({a.role})</option>)}
        </select>
        <button type="submit" className="btn btn-primary btn-sm" disabled={loading || !serverName || !command} style={{ justifyContent: "center" }}>
          {loading ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Add Server
        </button>
      </form>

      {/* List */}
      <div>
        <h4 className="label" style={{ marginBottom: "var(--sp-sm)" }}>Connected Servers</h4>
        {fetching ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {[1,2].map(i => <div key={i} className="skeleton" style={{ height: 60 }} />)}
          </div>
        ) : servers.length === 0 ? (
          <p className="caption" style={{ textAlign: "center", padding: "var(--sp-lg) 0" }}>No MCP servers connected.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-sm)" }}>
            {servers.map(s => (
              <div key={s.id} style={{ background: "var(--color-canvas-raised)", border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-sm)", padding: "var(--sp-md)" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                    <Server size={12} color="var(--color-primary)" />
                    <span className="body-sm-strong">{s.server_name}</span>
                  </div>
                  <button 
                    className="btn btn-icon-sm btn-ghost text-danger" 
                    title="Delete Server"
                    onClick={async () => {
                      try {
                        await api.deleteMcpServer(s.id);
                        onToast?.("Server deleted", "success");
                        loadServers();
                      } catch {
                        onToast?.("Failed to delete server", "error");
                      }
                    }}
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
                <code style={{ fontSize: 10, color: "var(--color-mute)", display: "block", marginTop: 4 }}>{s.command} {s.args?.join(" ")}</code>
                <div className="caption" style={{ marginTop: 4 }}>
                  {s.agent_id ? agents.find(a => a.id === s.agent_id)?.name || "Unknown agent" : "Global"}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
