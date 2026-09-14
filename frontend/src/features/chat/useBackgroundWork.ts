"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getApiBase } from "@/hooks/useApi";

export interface ChatProcess {
  pid: number; command: string; team_id: string; cwd: string; background: boolean;
  status: string; started_at: string; returncode: number | null;
}
export function useBackgroundWork(teamId: string | null) {
  const [snapshot, setSnapshot] = useState<{ team: string | null; jobs: ChatProcess[]; error: string; checked: boolean }>({ team: null, jobs: [], error: "", checked: false });
  const [stopping, setStopping] = useState<number | null>(null);
  const [revision, setRevision] = useState(0);
  const currentTeam = useRef(teamId);
  currentTeam.current = teamId;
  useEffect(() => {
    if (!teamId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const token = localStorage.getItem("carole_token");
        const response = await fetch(`${getApiBase()}/api/tasks?team_id=${encodeURIComponent(teamId)}`, { headers: { Authorization: `Bearer ${token || ""}` }, signal: controller.signal });
        if (!response.ok) throw new Error("Background status is unavailable. Retry to reconnect.");
        const jobs: ChatProcess[] = await response.json();
        if (!Array.isArray(jobs)) throw new Error("Unexpected background status response.");
        if (!controller.signal.aborted) setSnapshot({ team: teamId, jobs, error: "", checked: true });
      } catch (error) {
        if (!controller.signal.aborted) setSnapshot(prev => ({ team: teamId, jobs: prev.team === teamId ? prev.jobs : [], error: error instanceof Error ? error.message : "Unable to load background work.", checked: true }));
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, document.hidden ? 15000 : 4000);
      }
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [teamId, revision]);
  const stop = useCallback(async (job: ChatProcess) => {
    if (!teamId || stopping !== null) return;
    setStopping(job.pid);
    try {
      const headers = { Authorization: `Bearer ${localStorage.getItem("carole_token") || ""}` };
      const latest = await fetch(`${getApiBase()}/api/tasks?team_id=${encodeURIComponent(teamId)}`, { headers });
      if (!latest.ok) throw new Error("Could not verify the process. Refresh and try again.");
      const jobs: ChatProcess[] = await latest.json();
      if (!jobs.some(j => j.pid === job.pid && j.started_at === job.started_at && j.status === "running")) throw new Error("This process is no longer running. Refresh its status.");
      const response = await fetch(`${getApiBase()}/api/tasks/${job.pid}/kill`, { method: "POST", headers });
      if (!response.ok) throw new Error("Could not stop the process. Refresh and try again.");
      if (currentTeam.current === teamId) setRevision(v => v + 1);
    } catch (error) {
      if (currentTeam.current === teamId) setSnapshot(prev => ({ ...prev, error: error instanceof Error ? error.message : "Unable to stop process." }));
    } finally { setStopping(null); }
  }, [teamId, stopping]);
  return { jobs: snapshot.team === teamId ? snapshot.jobs : [], error: snapshot.team === teamId ? snapshot.error : "", loading: !!teamId && (snapshot.team !== teamId || !snapshot.checked), stopping, stop, refresh: () => setRevision(v => v + 1) };
}
