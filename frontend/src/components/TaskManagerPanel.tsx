import React, { useEffect, useState, useCallback } from "react";
import { Terminal, XCircle, Loader2, Info } from "lucide-react";
import { getApiBase } from "@/hooks/useApi";

const apiFetch = async (url: string, opts: RequestInit = {}) => {
    const token = localStorage.getItem("carole_token");
    if (token) {
      opts.headers = { ...opts.headers, Authorization: `Bearer ${token}` };
    }
    const base = getApiBase();
    const res = await fetch(`${base}${url}`, opts);
    if (!res.ok) throw new Error("API Error");
    return res.json();
  };


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

export function TaskManagerPanel(props: { teamId: string | null; onClose?: () => void }) {
  return <TaskManagerContent key={props.teamId || "none"} {...props} />;
}

function TaskManagerContent({ teamId, onClose }: { teamId: string | null; onClose?: () => void }) {
  const [tasks, setTasks] = useState<TaskInfo[]>([]);
  const [loading, setLoading] = useState(false);

  const [error, setError] = useState("");
  const fetchTasks = useCallback(async (signal?: AbortSignal) => {
    if (!teamId) return;
    try {
      const res = await apiFetch(`/api/tasks?team_id=${encodeURIComponent(teamId)}`, { signal });
      if (res && Array.isArray(res)) setTasks(res);
      setError("");
    } catch {
      if (!signal?.aborted) setError("Unable to load background tasks. Retrying shortly.");
    }
  }, [teamId]);

  useEffect(() => {
    const controller = new AbortController();
    // Starts external I/O; state updates occur only after the response resolves.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchTasks(controller.signal);
    const intv = setInterval(() => void fetchTasks(controller.signal), 3000);
    return () => { controller.abort(); clearInterval(intv); };
  }, [fetchTasks]);

  const killTask = async (pid: number) => {
    setLoading(true);
    try {
      await apiFetch(`/api/tasks/${pid}/kill`, { method: "POST" });
      await fetchTasks();
    } catch {
      setError("Could not stop the task. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "var(--color-canvas)", color: "var(--color-ink)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px", borderBottom: "1px solid var(--color-canvas-raised)", background: "var(--color-canvas-raised)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <Terminal size={16} color="var(--color-primary-soft)" />
          <span style={{ fontSize: "14px", fontWeight: 600 }}>Task Manager</span>
        </div>
        {onClose && (
          <button aria-label="Close task manager" onClick={onClose} style={{ background: "transparent", border: "none", color: "var(--color-mute)", cursor: "pointer" }}>
            <XCircle size={16} />
          </button>
        )}
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "12px", display: "flex", flexDirection: "column", gap: "8px" }}>
        {error && <p role="alert" style={{ color: "var(--color-danger)", fontSize: 13 }}>{error}</p>}
        {tasks.length === 0 ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--color-mute)", gap: "8px" }}>
            <Info size={24} />
            <span style={{ fontSize: "13px" }}>{teamId ? "No active background tasks" : "Select a team to view its tasks"}</span>
          </div>
        ) : (
          tasks.map(task => (
            <div key={task.pid} style={{ background: "var(--color-canvas-raised)", padding: "12px", borderRadius: "6px", display: "flex", flexDirection: "column", gap: "8px", border: "1px solid var(--color-hairline)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "12px", color: "var(--color-mute)", fontFamily: "monospace" }}>PID: {task.pid}</span>
                <span style={{ 
                  fontSize: "11px", 
                  padding: "2px 6px", 
                  borderRadius: "12px", 
                  background: task.status === "running" ? "rgba(52,211,153,0.1)" : "rgba(148,163,184,0.1)",
                  color: task.status === "running" ? "var(--color-success)" : "var(--color-mute)",
                  textTransform: "uppercase"
                }}>
                  {task.status}
                </span>
              </div>
              
              <div style={{ fontSize: "13px", fontFamily: "monospace", color: "var(--color-ink)", wordBreak: "break-all", background: "var(--color-canvas)", padding: "8px", borderRadius: "4px" }}>
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
