"use client";
import React, { useState, useEffect, useRef, useCallback } from "react";
import { Server, Loader2, AlertCircle, CheckCircle2, Plug, Trash2, RefreshCw } from "lucide-react";
import { api } from "../hooks/useApi";

export const McpStatusIndicator: React.FC = () => {
  const [statuses, setStatuses] = useState<Record<string, any>>({});
  const [isOpen, setIsOpen] = useState(false);
  const [disconnecting, setDisconnecting] = useState<string | null>(null);
  const [reloading, setReloading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await api.getMcpStatus();
      setStatuses(data || {});
    } catch (e) {
      console.error("Failed to fetch MCP status", e);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Poll while popover is open
  useEffect(() => {
    if (!isOpen) return;
    fetchStatus();
    const interval = setInterval(fetchStatus, 3500);
    return () => clearInterval(interval);
  }, [isOpen, fetchStatus]);

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

  const handleDisconnect = async (server: any, keyStr: string) => {
    const name = server.server_name;
    setDisconnecting(name);
    try {
      // Optimistically remove from state immediately
      setStatuses(prev => {
        const next = { ...prev };
        delete next[keyStr];
        return next;
      });

      if (server.id) {
        await api.deleteMcpServer(server.id);
      } else {
        await api.deleteMcpServer(name);
      }
      await fetchStatus();
    } catch (e) {
      console.error("Failed to disconnect MCP server", e);
    } finally {
      setDisconnecting(null);
    }
  };

  const handleReload = async () => {
    setReloading(true);
    try {
      await api.reloadMcpServers();
      // Poll quickly after reload to show "loading" state right away
      await fetchStatus();
      setTimeout(fetchStatus, 2000);
      setTimeout(fetchStatus, 5000);
    } catch (e) {
      console.error("Failed to reload MCP servers", e);
    } finally {
      setReloading(false);
    }
  };

  const statusEntries = Object.entries(statuses);
  if (statusEntries.length === 0) return null; // Don't show if no MCPs

  const statusList = statusEntries.map(([k, v]) => ({ keyStr: k, ...v }));
  const isLoading = statusList.some((s) => s.status === "loading");
  const hasError = statusList.some((s) => s.status === "error");
  const hasErrored = statusList.filter((s) => s.status === "error");

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
            width: "340px",
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
          <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--color-hairline)", background: "var(--bg-surface-elevated)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <h3 style={{ fontSize: "14px", fontWeight: 600, margin: 0, display: "flex", alignItems: "center", gap: "6px" }}>
              <Plug size={16} /> MCP Connections
            </h3>
            <button
              className="btn btn-ghost btn-xs"
              style={{ display: "flex", alignItems: "center", gap: "4px", fontSize: "11px", color: hasErrored.length > 0 ? "var(--color-danger)" : "var(--text-secondary)", padding: "3px 7px", height: "auto" }}
              onClick={handleReload}
              disabled={reloading}
              title={hasErrored.length > 0 ? `Reload ${hasErrored.length} failed server(s)` : "Hot-reload all MCP servers"}
            >
              <RefreshCw size={11} className={reloading ? "animate-spin" : ""} />
              {reloading ? "Reloading…" : hasErrored.length > 0 ? `Retry (${hasErrored.length})` : "Reload"}
            </button>
          </div>

          <div style={{ maxHeight: "300px", overflowY: "auto", padding: "8px" }}>
            {statusList.map((server, i) => {
              const isGlobal = !server.team_id || server.team_id === "None";
              const isBusy = disconnecting === server.server_name;
              const attemptInfo = server.attempt && server.max_attempts
                ? `Attempt ${server.attempt}/${server.max_attempts}`
                : null;
              return (
                <div key={server.keyStr || i} style={{ padding: "8px", borderBottom: i < statusList.length - 1 ? "1px solid var(--color-hairline)" : "none" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "4px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                      <span style={{ fontWeight: 500, fontSize: "13px" }}>{server.server_name}</span>
                      {server.status === "connected" && <CheckCircle2 size={13} color="var(--color-success)" />}
                      {server.status === "loading" && <Loader2 size={13} className="animate-spin" color="var(--color-primary)" />}
                      {server.status === "error" && <AlertCircle size={13} color="var(--color-danger)" />}
                    </div>

                    {!isGlobal && (
                      <button
                        className="btn btn-ghost btn-xs"
                        style={{ padding: "2px 6px", color: "var(--color-mute)", height: "auto" }}
                        title={`Disconnect ${server.server_name}`}
                        onClick={() => handleDisconnect(server, server.keyStr)}
                        disabled={isBusy}
                      >
                        {isBusy ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
                      </button>
                    )}
                  </div>

                  {server.status === "error" && (
                    <div style={{ fontSize: "11px", color: "var(--color-danger)", marginTop: "4px" }}>
                      {server.error || "Failed to initialize"}
                    </div>
                  )}

                  {server.status === "loading" && attemptInfo && (
                    <div style={{ fontSize: "11px", color: "var(--color-primary)", marginTop: "4px" }}>
                      {attemptInfo}
                    </div>
                  )}

                  {server.status === "connected" && server.tools && (
                    <div style={{ fontSize: "11px", color: "var(--text-secondary)", marginTop: "4px" }}>
                      {server.tools.length} tool(s) registered
                    </div>
                  )}

                  {server.team_id && server.team_id !== "None" && (
                    <span style={{ display: "inline-block", fontSize: "10px", padding: "2px 6px", background: "var(--bg-surface-elevated)", borderRadius: "4px", marginTop: "4px" }}>
                      Team specific
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
