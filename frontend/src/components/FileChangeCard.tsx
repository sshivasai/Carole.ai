"use client";
import React, { useState } from "react";
import { FileCode2, ChevronDown, ExternalLink } from "lucide-react";
import { DiffViewer } from "./DiffViewer";
import "./chat-workspace.css";
export interface ChangedFileItem { path: string; diff?: string; content?: string; action?: string; additions?: number; deletions?: number; }
interface Props {
  files?: ChangedFileItem[] | ChangedFileItem; senderName?: string; path?: string; diff?: string; content?: string;
  action?: string; timestamp?: string | number; onOpenFile?: (path: string) => void; onOpenDiffFile?: (path: string) => void;
}
export default function FileChangeCard({ files, senderName, path, diff, content, action, onOpenFile, onOpenDiffFile }: Props) {
  const list = Array.isArray(files) ? files : files ? [files] : path ? [{ path, diff, content, action }] : [];
  const [open, setOpen] = useState<Record<string, boolean>>({});
  if (!list.length) return null;
  return <section className="cw-changes" aria-label="File changes">
    <div className="cw-changes-heading"><FileCode2 size={15} /><strong>{list.length} {list.length === 1 ? "file changed" : "files changed"}</strong>{senderName && <small className="cw-muted">by {senderName}</small>}</div>
    {list.map((file, index) => {
      const key = file.path + ":" + index;
      const added = file.additions ?? (file.diff ? file.diff.split("\n").filter(line => line.startsWith("+") && !line.startsWith("+++")).length : undefined);
      const removed = file.deletions ?? (file.diff ? file.diff.split("\n").filter(line => line.startsWith("-") && !line.startsWith("---")).length : undefined);
      return <div key={key}>
        <div className="cw-change-row"><button className="cw-change-path" onClick={() => onOpenFile ? onOpenFile(file.path) : setOpen(v => ({ ...v, [key]: !v[key] }))}>{file.path}</button>{file.action && <small>{file.action}</small>}{added !== undefined && removed !== undefined && <small>+{added} −{removed}</small>}<button className="cw-text-button" aria-expanded={!!open[key]} onClick={() => setOpen(v => ({ ...v, [key]: !v[key] }))}><ChevronDown size={13} />{open[key] ? "Hide" : "Review"}</button>{onOpenDiffFile && <button className="cw-icon-button" aria-label={"Open diff for " + file.path} onClick={() => onOpenDiffFile(file.path)}><ExternalLink size={13} /></button>}</div>
        {open[key] && <div className="cw-tool-content">{file.diff ? <DiffViewer diff={file.diff} path={file.path} /> : file.content !== undefined ? <><p className="cw-muted">Full content preview · no patch available</p><pre>{file.content}</pre></> : <p className="cw-muted">No diff was recorded for this change. Open the file to inspect its current state.</p>}</div>}
      </div>;
    })}
  </section>;
}
