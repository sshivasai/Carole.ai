"use client";

import React, { useRef, useEffect, useState } from "react";
import { Terminal as TerminalIcon, Trash2, X, RotateCw } from "lucide-react";
import type { Terminal as TerminalType } from "@xterm/xterm";
import { getWsBase } from "@/hooks/useWebSocket";
import "@xterm/xterm/css/xterm.css";
import styles from "./TerminalPanel.module.css";

interface TerminalPanelProps {
  projectId?: string;
  onClose?: () => void;
  triggerCommand?: { cmd: string; ts: number } | null;
  shell?: "bash" | "powershell" | "cmd" | "default";
}

type Connection = "connecting" | "connected" | "disconnected" | "error";

export default function TerminalPanel({ projectId, onClose, triggerCommand, shell = "default" }: TerminalPanelProps) {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<TerminalType | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pendingCommand = useRef(triggerCommand);
  const lastExecutedTs = useRef<number | null>(null);
  const sessionIds = useRef(new Map<string, string>());
  const [connection, setConnection] = useState<Connection>("connecting");
  const [error, setError] = useState("");
  const [session, setSession] = useState(0);

  useEffect(() => {
    pendingCommand.current = triggerCommand;
  }, [triggerCommand]);

  useEffect(() => {
    const container = terminalRef.current;
    if (!container) return;
    let disposed = false;
    let term: TerminalType | undefined;
    let ws: WebSocket | undefined;
    let resizeObserver: ResizeObserver | undefined;
    let themeObserver: MutationObserver | undefined;
    let frame = 0;
    setConnection("connecting");
    setError("");

    const init = async () => {
      const [{ Terminal }, { FitAddon }, { api }] = await Promise.all([
        import("@xterm/xterm"), import("@xterm/addon-fit"), import("@/hooks/useApi"),
      ]);
      if (disposed) return;
      const palette = () => {
        const css = getComputedStyle(container);
        return {
          background: css.getPropertyValue("--color-canvas").trim() || "#09090b",
          foreground: css.getPropertyValue("--color-ink").trim() || "#f8fafc",
          cursor: css.getPropertyValue("--color-primary-soft").trim() || "#7c8cff",
          selectionBackground: "#5d6ff755",
        };
      };
      term = new Terminal({ cursorBlink: true, fontFamily: getComputedStyle(container).getPropertyValue("--font-family-mono").trim() || "monospace", fontSize: 13, lineHeight: 1.3, scrollback: 5000, theme: palette() });
      const fit = new FitAddon();
      term.loadAddon(fit);
      term.open(container);
      xtermRef.current = term;
      const resize = () => {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => {
          if (!disposed && container.clientWidth > 0 && container.clientHeight > 0) fit.fit();
        });
      };
      resizeObserver = new ResizeObserver(resize);
      resizeObserver.observe(container);
      themeObserver = new MutationObserver(() => { if (term && !disposed) term.options.theme = palette(); });
      // Theme classes can live on the document or on a preview/workspace ancestor.
      for (let el: HTMLElement | null = container; el; el = el.parentElement) themeObserver.observe(el, { attributes: true, attributeFilter: ["class"] });
      term.attachCustomKeyEventHandler(event => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "c" && term?.hasSelection()) {
          if (event.type === "keydown") void navigator.clipboard.writeText(term.getSelection()).catch(() => setError("Could not copy the selection. Check clipboard permissions."));
          return false;
        }
        // Let xterm handle paste, Tab and control sequences natively.
        return true;
      });
      await document.fonts.ready;
      if (disposed) return;
      resize();
      const { ticket } = await api.getWsTicket();
      if (disposed) return;
      if (!ticket) throw new Error("Could not authenticate the terminal. Sign in and reconnect.");
      const key = `${projectId || "default"}:${shell}`;
      if (!sessionIds.current.has(key)) sessionIds.current.set(key, crypto.randomUUID());
      const params = new URLSearchParams({ ticket, shell, session_id: sessionIds.current.get(key)! });
      ws = new WebSocket(`${getWsBase()}/api/terminal/ws/${encodeURIComponent(projectId || "default")}?${params}`);
      wsRef.current = ws;
      const socket = ws;
      term.onResize(({ cols, rows }) => { if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ action: "resize", cols, rows })); });
      term.onData(data => {
        if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(data === "\x03" ? { action: "interrupt" } : { action: "input", data }));
      });
      socket.onopen = () => {
        if (disposed || !term) return;
        setConnection("connected");
        setError("");
        socket.send(JSON.stringify({ action: "resize", cols: term.cols, rows: term.rows }));
        const command = pendingCommand.current;
        if (command?.cmd && command.ts !== lastExecutedTs.current) {
          socket.send(JSON.stringify({ action: "input", data: command.cmd + "\r" }));
          lastExecutedTs.current = command.ts;
        }
      };
      socket.onmessage = event => { if (!disposed && typeof event.data === "string") term?.write(event.data); };
      socket.onerror = () => { if (!disposed) { setConnection("error"); setError("Terminal connection failed. Check that the backend is running and you have terminal access."); } };
      socket.onclose = () => { if (!disposed) setConnection(current => current === "error" ? "error" : "disconnected"); };
    };
    void init().catch(reason => {
      if (!disposed) { setConnection("error"); setError(reason instanceof Error ? reason.message : "Unable to start the terminal."); }
    });
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      resizeObserver?.disconnect();
      themeObserver?.disconnect();
      ws?.close();
      term?.dispose();
      if (wsRef.current === ws) wsRef.current = null;
      if (xtermRef.current === term) xtermRef.current = null;
    };
  }, [projectId, shell, session]);

  useEffect(() => {
    const ws = wsRef.current;
    if (triggerCommand?.cmd && ws?.readyState === WebSocket.OPEN && triggerCommand.ts !== lastExecutedTs.current) {
      ws.send(JSON.stringify({ action: "input", data: triggerCommand.cmd + "\r" }));
      lastExecutedTs.current = triggerCommand.ts;
    }
  }, [triggerCommand, projectId, shell]);

  return <section className={styles.panel} aria-label="Terminal">
    <header className={styles.header}>
      <div className={styles.identity}><TerminalIcon size={16} /><strong>Terminal</strong><span className={styles.shell}>{shell === "default" ? "Default shell" : shell}</span></div>
      <div className={styles.actions}>
        <span className={styles.status} data-state={connection} role="status"><i />{connection}</span>
        <button onClick={() => { xtermRef.current?.clear(); xtermRef.current?.focus(); }} aria-label="Clear terminal" title="Clear terminal"><Trash2 size={15} /></button>
        {(connection === "disconnected" || connection === "error") && <button onClick={() => setSession(value => value + 1)} aria-label="Reconnect terminal" title="Reconnect terminal"><RotateCw size={15} /></button>}
        {onClose && <button onClick={onClose} aria-label="Close terminal" title="Close terminal"><X size={16} /></button>}
      </div>
    </header>
    {error && <div className={styles.notice} role="alert">{error}</div>}
    {connection === "disconnected" && <div className={styles.notice}>Connection closed. Reconnect to resume your terminal.</div>}
    <div className={styles.viewport}><div ref={terminalRef} /></div>
    <footer className={styles.footer}><span>Ctrl+C to interrupt · Select text to copy</span><span>{connection === "connected" ? "Shell ready" : "Input unavailable"}</span></footer>
  </section>;
}
