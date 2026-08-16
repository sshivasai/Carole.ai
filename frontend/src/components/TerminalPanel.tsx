"use client";

import React, { useRef, useEffect } from "react";
import { Terminal as TerminalIcon, Trash2, X } from "lucide-react";
import type { Terminal as TerminalType } from "@xterm/xterm";
import type { FitAddon as FitAddonType } from "@xterm/addon-fit";
import { getWsBase, getWsToken } from "@/hooks/useWebSocket";
import "@xterm/xterm/css/xterm.css";

interface TerminalPanelProps {
  projectId?: string;
  onClose?: () => void;
  triggerCommand?: { cmd: string; ts: number } | null;
}

export default function TerminalPanel({ projectId, onClose, triggerCommand }: TerminalPanelProps) {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<TerminalType | null>(null);
  const fitAddonRef = useRef<FitAddonType | null>(null);

  // Track the timestamp of the last executed trigger command.
  // Using a timestamp instead of a boolean allows the same command text to
  // fire again (e.g., re-running a file) as long as it's a new trigger event.
  const lastExecutedTs = useRef<number>(0);

  const wsRef = useRef<WebSocket | null>(null);

  // Expose executeCmd if a parent passes a command, but handle via WS
  const executeCmd = (cmdToRun: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      // If we need to send raw commands, just write to WS
      wsRef.current.send(JSON.stringify({ action: "input", data: cmdToRun + "\n" }));
    }
  };

  useEffect(() => {
    if (!terminalRef.current) return;

    let term: TerminalType;
    let fitAddon: FitAddonType;
    let resizeObserver: ResizeObserver;

    const initTerminal = async () => {
      const { Terminal } = await import("@xterm/xterm");
      const { FitAddon } = await import("@xterm/addon-fit");

      term = new Terminal({
        cursorBlink: true,
        fontFamily: "var(--font-mono, 'Courier New', monospace)",
        fontSize: 13,
        allowTransparency: true,
        theme: {
          background: "transparent",
          foreground: "var(--color-ink)",
        }
      });

      fitAddon = new FitAddon();
      term.loadAddon(fitAddon);

      term.open(terminalRef.current!);

      // Wait for fonts to load before fitting
      if (document.fonts) {
        await document.fonts.ready;
      }
      fitAddon.fit();

      xtermRef.current = term;
      fitAddonRef.current = fitAddon;

      let ticket = "";
      try {
        const { api } = await import("@/hooks/useApi");
        const res = await api.getWsTicket();
        ticket = res.ticket;
      } catch (err) {
        console.warn("Failed to fetch terminal WS ticket:", err);
      }

      const wsUrl = `${getWsBase()}/api/terminal/ws/${projectId || "default"}${
        ticket ? `?ticket=${encodeURIComponent(ticket)}` : ""
      }`;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      term.onResize(({ cols, rows }) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ action: "resize", cols, rows }));
        }
      });

      ws.onopen = () => {
        // Send initial size
        ws.send(JSON.stringify({ action: "resize", cols: term.cols, rows: term.rows }));
        // Execute trigger command if it arrived before init and hasn't been run yet
        if (triggerCommand && triggerCommand.cmd && triggerCommand.ts > lastExecutedTs.current) {
          ws.send(JSON.stringify({ action: "input", data: triggerCommand.cmd + "\n" }));
          lastExecutedTs.current = triggerCommand.ts;
        }
      };

      ws.onmessage = (event) => {
        if (typeof event.data === "string") {
          term.write(event.data);
        }
      };

      ws.onclose = () => {
        // Do nothing to avoid messing up the final screen state
      };

      term.onData((data) => {
        if (ws.readyState === WebSocket.OPEN) {
          // For ctrl+c
          if (data === '\x03') {
            ws.send(JSON.stringify({ action: "interrupt" }));
          } else {
            ws.send(JSON.stringify({ action: "input", data }));
          }
        }
      });

      const handleResize = () => {
        try {
          // Add a small delay to ensure container dimensions are final
          requestAnimationFrame(() => {
            if (fitAddonRef.current) {
              fitAddonRef.current.fit();
            }
          });
        } catch (e) {
          // ignore fit errors during unmount
        }
      };

      resizeObserver = new ResizeObserver(() => {
        handleResize();
      });
      resizeObserver.observe(terminalRef.current!);
    };

    void initTerminal();

    return () => {
      if (resizeObserver) resizeObserver.disconnect();
      if (wsRef.current) wsRef.current.close();
      if (term) term.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // Handle triggers that happen after terminal is initialized
    if (triggerCommand && triggerCommand.cmd && xtermRef.current && triggerCommand.ts > lastExecutedTs.current) {
      executeCmd(triggerCommand.cmd);
      lastExecutedTs.current = triggerCommand.ts;
    }
  }, [triggerCommand]);

  const handleClear = () => {
    if (xtermRef.current) {
      xtermRef.current.clear();
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "transparent", color: "var(--color-ink)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "4px 12px", background: "var(--bg-surface)", borderBottom: "1px solid var(--border-subtle)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <TerminalIcon size={14} style={{ color: "var(--color-mute)" }} />
          <span style={{ fontWeight: 600, fontSize: 12 }}>Terminal</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            onClick={handleClear}
            style={{ color: "var(--color-mute)", background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", padding: 4 }}
            className="hover:text-white"
            title="Clear Terminal"
          >
            <Trash2 size={14} />
          </button>
          {onClose && (
            <button
              onClick={onClose}
              style={{ color: "var(--color-mute)", background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", padding: 4 }}
              className="hover:text-white"
              title="Close Terminal"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      <div style={{ flex: 1, padding: "8px", overflow: "hidden" }}>
        <div ref={terminalRef} style={{ width: "100%", height: "100%" }} />
      </div>
    </div>
  );
}
