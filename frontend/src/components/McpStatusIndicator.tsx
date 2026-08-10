import React, { useState, useEffect, useRef } from "react";
import { Server, Loader2, AlertCircle, CheckCircle2, Plug } from "lucide-react";
import { api } from "../hooks/useApi";

export const McpStatusIndicator: React.FC = () => {
  const [statuses, setStatuses] = useState<Record<string, any>>({});
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const fetchStatus = async () => {
    try {
      const data = await api.getMcpStatus();
      setStatuses(data);
    } catch (e) {
      console.error("Failed to fetch MCP status", e);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  const statusList = Object.values(statuses);
  if (statusList.length === 0) return null; // Don't show if no MCPs

  const isLoading = statusList.some((s) => s.status === "loading");
  const hasError = statusList.some((s) => s.status === "error");

  let Icon = Server;
  let color = "var(--text-secondary)";
  if (isLoading) {
    Icon = Loader2;
    color = "var(--color-primary)";
  } else if (hasError) {
    Icon = AlertCircle;
    color = "var(--color-danger)";
  }

  return (
    <div style={{ position: "relative" }} ref={containerRef}>
      <button
        className="btn btn-icon btn-outline btn-sm"
        onClick={() => {
          if (!isOpen) fetchStatus();
          setIsOpen(!isOpen);
        }}
        title="MCP Servers Status"
        style={{ color, borderColor: isOpen ? "var(--color-primary)" : undefined }}
      >
        <Icon size={14} className={isLoading ? "animate-spin" : ""} />
      </button>

      {isOpen && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            right: 0,
            marginTop: "8px",
            width: "320px",
            background: "var(--bg-surface)",
            border: "1px solid var(--color-hairline)",
            borderRadius: "var(--radius-md)",
            boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
            zIndex: 100,
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ padding: "12px", borderBottom: "1px solid var(--color-hairline)", background: "var(--bg-surface-elevated)" }}>
            <h3 style={{ fontSize: "14px", fontWeight: 600, margin: 0, display: "flex", alignItems: "center", gap: "6px" }}>
              <Plug size={16} /> MCP Connections
            </h3>
          </div>
          
          <div style={{ maxHeight: "300px", overflowY: "auto", padding: "8px" }}>
            {statusList.map((server, i) => (
              <div key={i} style={{ padding: "8px", borderBottom: i < statusList.length - 1 ? "1px solid var(--color-hairline)" : "none" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "4px" }}>
                  <span style={{ fontWeight: 500, fontSize: "13px" }}>{server.server_name}</span>
                  {server.status === "connected" && <CheckCircle2 size={14} color="var(--color-success)" />}
                  {server.status === "loading" && <Loader2 size={14} className="animate-spin" color="var(--color-primary)" />}
                  {server.status === "error" && <AlertCircle size={14} color="var(--color-danger)" />}
                </div>
                
                {server.status === "error" && (
                  <div style={{ fontSize: "11px", color: "var(--color-danger)", marginTop: "4px" }}>
                    {server.error}
                  </div>
                )}
                
                {server.status === "connected" && server.tools && (
                  <div style={{ fontSize: "11px", color: "var(--text-secondary)", marginTop: "4px" }}>
                    {server.tools.length} tool(s) registered
                  </div>
                )}
                
                {server.team_id && server.team_id !== "None" && (
                  <span style={{ display: "inline-block", fontSize: "10px", padding: "2px 6px", background: "var(--bg-surface-elevated)", borderRadius: "4px", marginTop: "6px" }}>
                    Team specific
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
