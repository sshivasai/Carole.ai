import React, { useState, useEffect, useCallback } from "react";
import { api } from "@/hooks/useApi";
import { FileCode, ChevronDown, ChevronRight, Activity, Trash2, RefreshCw } from "lucide-react";
import { DiffEditor } from "@monaco-editor/react";

interface ActivityLogPanelProps {
  teamId: string;
}

const isValidTeamId = (t?: string) => !!t && t !== "undefined" && /^[0-9a-fA-F-]{8,}$/.test(t);

export default function ActivityLogPanel({ teamId }: ActivityLogPanelProps) {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getFileLogs(teamId);
      setLogs(Array.isArray(data) ? data : []);
    } catch (err: any) {
      // A TypeError "Failed to fetch" means the backend wasn't reachable
      // (down / wrong port / CORS). Surface it clearly instead of silently
      // showing "No recent file modifications."
      const msg = err?.status
        ? `Server error (${err.status}).`
        : "Couldn't reach the backend. Is it running on port 8000?";
      setError(msg);
      console.error("Failed to load file logs", err);
    } finally {
      setLoading(false);
    }
  }, [teamId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!isValidTeamId(teamId)) { setLoading(false); setError(null); return; }
      try {
        setLoading(true); setError(null);
        const data = await api.getFileLogs(teamId);
        if (!cancelled) setLogs(Array.isArray(data) ? data : []);
      } catch (err: any) {
        if (cancelled) return;
        const msg = err?.status ? `Server error (${err.status}).` : "Couldn't reach the backend. Is it running on port 8000?";
        setError(msg);
        console.error("Failed to load file logs", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [teamId]);

  const handleDeleteLog = async (e: React.MouseEvent, logId: string) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this file activity log?")) return;
    try {
      await api.deleteFileLog(logId);
      setLogs(logs.filter(l => l.id !== logId));
      if (expandedId === logId) setExpandedId(null);
    } catch (err) {
      console.error("Failed to delete log", err);
      alert("Failed to delete log. See console for details.");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "var(--sp-sm) var(--sp-md)", borderBottom: "1px solid var(--color-hairline)", display: "flex", alignItems: "center", gap: 6 }}>
        <Activity size={14} color="var(--color-primary)" />
        <span className="body-sm-strong" style={{ textTransform: "uppercase", fontSize: "11px", letterSpacing: "0.5px", color: "var(--color-mute)" }}>
          Activity Log
        </span>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "8px" }} className="scrollbar-custom">
        {loading ? (
          <div className="body-sm caption text-center" style={{ marginTop: 20 }}>Loading logs...</div>
        ) : error ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, marginTop: 24, padding: "0 12px", textAlign: "center" }}>
            <span className="caption" style={{ color: "var(--color-error, #ef4444)" }}>{error}</span>
            <button className="btn btn-sm btn-secondary" onClick={reload} style={{ padding: "4px 12px", fontSize: 12 }}>
              <RefreshCw size={12} className="mr-1" />Retry
            </button>
          </div>
        ) : logs.length === 0 ? (
          <div className="body-sm caption text-center" style={{ marginTop: 20 }}>No recent file modifications.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {logs.map((log) => {
              const isExpanded = expandedId === log.id;
              const date = new Date(log.timestamp);
              const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
              
              return (
                <div key={log.id} style={{ border: "1px solid var(--color-hairline)", borderRadius: 6, overflow: "hidden", background: "var(--bg-glass-card)" }}>
                  <div 
                    style={{ 
                      padding: "8px", 
                      display: "flex", 
                      alignItems: "center", 
                      cursor: "pointer",
                      background: isExpanded ? "var(--bg-glass-panel)" : "transparent"
                    }}
                    onClick={() => setExpandedId(isExpanded ? null : log.id)}
                    className="hover:bg-[var(--bg-glass-panel)] transition-colors"
                  >
                    <div style={{ flexShrink: 0, marginRight: 6 }}>
                      {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </div>
                    <FileCode size={14} color="var(--color-brand)" style={{ marginRight: 6, flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
                      <span className="body-sm truncate" style={{ fontWeight: 500 }} title={log.file_path}>
                        {log.file_path.split("/").pop()}
                      </span>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, opacity: 0.7 }}>
                        <span className="caption" style={{ fontSize: 10 }}>{timeStr}</span>
                        <span className="caption" style={{ fontSize: 10 }}>&bull;</span>
                        <span className="caption truncate" style={{ fontSize: 10 }}>by {log.agent_name}</span>
                        <span className="caption" style={{ fontSize: 10 }}>&bull;</span>
                        <span className="caption" style={{ fontSize: 10, textTransform: "capitalize" }}>{log.operation.replace("_", " ")}</span>
                      </div>
                    </div>
                    <button 
                      className="btn-ghost" 
                      style={{ padding: "4px", borderRadius: "4px", opacity: 0.6 }}
                      onClick={(e) => handleDeleteLog(e, log.id)}
                      title="Delete Log"
                    >
                      <Trash2 size={14} color="var(--color-danger)" />
                    </button>
                  </div>
                  
                  {isExpanded && (
                    <div style={{ height: "400px", borderTop: "1px solid var(--color-hairline)" }}>
                      <DiffEditor
                        original={log.original_content}
                        modified={log.new_content}
                        language={log.file_path.split('.').pop() === 'ts' ? 'typescript' : log.file_path.split('.').pop() === 'tsx' ? 'typescript' : log.file_path.split('.').pop()}
                        theme="vs-dark"
                        options={{
                          readOnly: true,
                          minimap: { enabled: false },
                          scrollBeyondLastLine: false,
                          renderSideBySide: false
                        }}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
