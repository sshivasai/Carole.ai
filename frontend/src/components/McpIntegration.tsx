import React, { useState, useEffect, useCallback } from "react";
import { api } from "@/hooks/useApi";
import { AgentConfig } from "@/lib/types";

interface McpIntegrationProps {
  teamId: string | null;
  agents: AgentConfig[];
}

export default function McpIntegration({ teamId, agents }: McpIntegrationProps) {
  const [servers, setServers] = useState<any[]>([]);
  const [serverName, setServerName] = useState("");
  const [command, setCommand] = useState("");
  const [args, setArgs] = useState("");
  const [agentId, setAgentId] = useState("");
  const [loading, setLoading] = useState(false);

  const loadServers = useCallback(async () => {
    if (!teamId) return;
    try {
      const data = await api.listMcpServers(teamId);
      setServers(data);
    } catch (e) {
      console.error(e);
    }
  }, [teamId]);

  useEffect(() => {
    if (teamId) {
      loadServers();
    } else {
      setServers([]);
    }
  }, [teamId, loadServers]);

  const handleAddServer = async () => {
    if (!teamId || !serverName || !command) return;
    setLoading(true);
    try {
      await api.createMcpServer({
        team_id: teamId,
        server_name: serverName,
        command,
        args,
        agent_id: agentId || undefined
      });
      await loadServers();
      setServerName("");
      setCommand("");
      setArgs("");
      setAgentId("");
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  if (!teamId) {
    return <div style={{ padding: "12px", color: "var(--text-tertiary)", fontSize: "13px", textAlign: "center" }}>Select a team to view MCP servers.</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      <div style={{ padding: "12px", background: "var(--bg-surface)", borderRadius: "var(--radius-md)", border: "1px solid var(--border-subtle)" }}>
        <h4 style={{ fontSize: "12px", fontWeight: "600", color: "var(--text-primary)", marginBottom: "8px" }}>Add New MCP Server</h4>
        <input className="input" placeholder="Server Name (e.g. github)" value={serverName} onChange={e => setServerName(e.target.value)} style={{ fontSize: "12px", marginBottom: "8px", width: "100%" }} />
        <input className="input" placeholder="Command (e.g. npx)" value={command} onChange={e => setCommand(e.target.value)} style={{ fontSize: "12px", marginBottom: "8px", width: "100%" }} />
        <input className="input" placeholder="Args (comma separated, e.g. -y,@modelcontextprotocol/server-github)" value={args} onChange={e => setArgs(e.target.value)} style={{ fontSize: "12px", marginBottom: "8px", width: "100%" }} />
        <select className="input" value={agentId} onChange={e => setAgentId(e.target.value)} style={{ fontSize: "12px", marginBottom: "8px", width: "100%" }}>
          <option value="">Global (All Agents)</option>
          {agents.map(a => (
            <option key={a.id} value={a.id}>{a.name} ({a.role})</option>
          ))}
        </select>
        <button className="btn btn-primary" onClick={handleAddServer} disabled={loading} style={{ width: "100%", fontSize: "12px" }}>
          {loading ? "Connecting..." : "Add & Connect Server"}
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        <h4 style={{ fontSize: "11px", fontWeight: "600", color: "var(--text-tertiary)", textTransform: "uppercase", marginBottom: "4px" }}>Connected Servers</h4>
        {servers.length === 0 ? (
          <div style={{ color: "var(--text-tertiary)", fontSize: "12px", textAlign: "center", padding: "12px 0" }}>No MCP servers connected to this team.</div>
        ) : (
          servers.map(s => (
            <div key={s.id} style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--border-subtle)", borderRadius: "6px", padding: "12px" }}>
              <div style={{ fontSize: "12px", fontWeight: "600", color: "var(--text-primary)" }}>{s.server_name}</div>
              <div style={{ fontSize: "10px", color: "var(--text-tertiary)", marginTop: "4px", background: "rgba(0,0,0,0.2)", padding: "4px", borderRadius: "4px" }}>
                <code>{s.command} {s.args?.join(", ")}</code>
              </div>
              <div style={{ fontSize: "10px", color: "var(--text-secondary)", marginTop: "6px" }}>
                Assigned to: {s.agent_id ? agents.find(a => a.id === s.agent_id)?.name || s.agent_id : "Global"}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
