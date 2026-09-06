import React, { useEffect, useState } from "react";
import { Terminal, XCircle, SkipForward, Loader2, Info } from "lucide-react";
import { api } from "@/hooks/useApi";

export interface TaskInfo {
  pid: number;
  command: string;
  team_id: string;
  cwd: string;
  background: boolean;
  status: string;
  started_at: string;
  returncode: number | null;
}

export function TaskManagerPanel({ teamId, onClose }: { teamId: string | null; onClose?: () => void }) {
  const [tasks, setTasks] = useState<TaskInfo[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchTasks = async () => {
    if (!teamId) return;
    try {
      const res = await apiFetch(`/api/tasks?team_id=${teamId}`);
      if (res && Array.isArray(res)) setTasks(res);
    } catch (e) {
      console.error("Failed to fetch tasks", e);
    }
  };

  useEffect(() => {
    fetchTasks();
    const intv = setInterval(fetchTasks, 3000);
    return () => clearInterval(intv);
  }, [teamId]);

  const killTask = async (pid: number) => {
    setLoading(true);
    try {
      await apiFetch(`/api/tasks/${pid}/kill`, { method: "POST" });
      await fetchTasks();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  // Polyfill for standalone apiFetch since it's not exported normally
  const apiFetch = async (url: string, opts: RequestInit = {}) => {
    const token = localStorage.getItem("carole_token");
    if (token) {
      opts.headers = { ...opts.headers, Authorization: `Bearer ${token}` };
    }
    const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
    const res = await fetch(`${base}${url}`, opts);
    if (!res.ok) throw new Error("API Error");
    return res.json();
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#0f172a", color: "#e2e8f0" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px", borderBottom: "1px solid #1e293b", background: "#1e293b" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <Terminal size={16} color="#38bdf8" />
          <span style={{ fontSize: "14px", fontWeight: 600 }}>Task Manager</span>
        </div>
        {onClose && (
          <button onClick={onClose} style={{ background: "transparent", border: "none", color: "#94a3b8", cursor: "pointer" }}>
            <XCircle size={16} />
          </button>
        )}
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "12px", display: "flex", flexDirection: "column", gap: "8px" }}>
        {tasks.length === 0 ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", color: "#64748b", gap: "8px" }}>
            <Info size={24} />
            <span style={{ fontSize: "13px" }}>No active background tasks</span>
          </div>
        ) : (
          tasks.map(task => (
            <div key={task.pid} style={{ background: "#1e293b", padding: "12px", borderRadius: "6px", display: "flex", flexDirection: "column", gap: "8px", border: "1px solid #334155" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "12px", color: "#94a3b8", fontFamily: "monospace" }}>PID: {task.pid}</span>
                <span style={{ 
                  fontSize: "11px", 
                  padding: "2px 6px", 
                  borderRadius: "12px", 
                  background: task.status === "running" ? "rgba(52,211,153,0.1)" : "rgba(148,163,184,0.1)",
                  color: task.status === "running" ? "#34d399" : "#94a3b8",
                  textTransform: "uppercase"
                }}>
                  {task.status}
                </span>
              </div>
              
              <div style={{ fontSize: "13px", fontFamily: "monospace", color: "#e2e8f0", wordBreak: "break-all", background: "#0f172a", padding: "8px", borderRadius: "4px" }}>
                {task.command}
              </div>

              {task.status === "running" && (
                <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "4px" }}>
                  <button 
                    onClick={() => killTask(task.pid)}
                    disabled={loading}
                    style={{
                      display: "flex", alignItems: "center", gap: "6px",
                      background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)",
                      color: "#ef4444", padding: "6px 12px", borderRadius: "4px",
                      fontSize: "12px", cursor: "pointer", opacity: loading ? 0.5 : 1
                    }}
                    className="hover:bg-red-500 hover:text-white"
                  >
                    {loading ? <Loader2 size={12} className="animate-spin" /> : <XCircle size={12} />}
                    Kill
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
