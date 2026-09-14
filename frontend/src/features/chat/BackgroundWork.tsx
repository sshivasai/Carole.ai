"use client";
import { Terminal, RefreshCw, Square, Loader2, Check, AlertCircle, X } from "lucide-react";
import type { useBackgroundWork } from "./useBackgroundWork";

export default function BackgroundWork({ work, onClose }: { work: ReturnType<typeof useBackgroundWork>; onClose: () => void }) {
  return <section className="cw-background" aria-label="Background work">
    <div className="cw-background-heading"><div><h3>Background work</h3><p>Processes can keep running after a response.</p></div><button className="cw-icon-button" onClick={work.refresh} aria-label="Refresh background work"><RefreshCw size={15} /></button><button className="cw-icon-button" onClick={onClose} aria-label="Close background work"><X size={16} /></button></div>
    {work.error && <p role="alert" className="cw-inline-error">{work.error} <button className="cw-text-button" onClick={work.refresh}>Retry</button></p>}
    {work.loading && <p className="cw-muted"><Loader2 size={14} className="cw-spin" /> Checking processes…</p>}
    {!work.loading && !work.error && !work.jobs.length && <div className="cw-background-empty"><Terminal size={24} /><strong>Nothing running in the background</strong><span>Commands and long-running processes will appear here.</span></div>}
    <div className="cw-job-list">{work.jobs.map(job => <details className="cw-job" key={`${job.pid}:${job.started_at}`}>
      <summary>{job.status === "running" ? <Loader2 size={14} className={work.error ? "" : "cw-spin"} /> : job.status === "completed" ? <Check size={14} /> : <AlertCircle size={14} />}<code>{job.command}</code><span>{work.error ? "Status stale" : job.status}</span></summary>
      <div className="cw-job-detail"><pre>{job.command}</pre><dl><dt>Working directory</dt><dd>{job.cwd}</dd><dt>Started</dt><dd>{new Date(job.started_at).toLocaleString()}</dd><dt>Process</dt><dd>{job.pid}</dd>{job.returncode !== null && <><dt>Exit code</dt><dd>{job.returncode}</dd></>}</dl>
        {job.status === "running" && <button className="cw-button" disabled={work.stopping !== null || !!work.error} onClick={() => void work.stop(job)}>{work.stopping === job.pid ? <Loader2 size={13} className="cw-spin" /> : <Square size={13} />}{work.stopping === job.pid ? "Stopping…" : "Stop process"}</button>}
      </div>
    </details>)}</div>
  </section>;
}
