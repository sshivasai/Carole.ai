"use client";

import React, { useRef, useEffect } from "react";
import { api } from "@/hooks/useApi";
import { Terminal as TerminalIcon, Trash2, X } from "lucide-react";
import type { Terminal as TerminalType } from "@xterm/xterm";
import type { FitAddon as FitAddonType } from "@xterm/addon-fit";

interface TerminalPanelProps {
  projectId?: string;
  onClose?: () => void;
  triggerCommand?: { cmd: string; ts: number } | null;
}

export default function TerminalPanel({ projectId, onClose, triggerCommand }: TerminalPanelProps) {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<TerminalType | null>(null);
  const fitAddonRef = useRef<FitAddonType | null>(null);
  
  const commandBuffer = useRef("");
  const isRunning = useRef(false);

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

    const initTerminal = async () => {
      const { Terminal } = await import("@xterm/xterm");
      const { FitAddon } = await import("@xterm/addon-fit");
      await import("@xterm/xterm/css/xterm.css");

      term = new Terminal({
        cursorBlink: true,
        fontFamily: "var(--font-mono, monospace)",
        fontSize: 13,
        theme: {
          background: "#1e1e1e",
          foreground: "#d4d4d4",
        }
      });
      
      fitAddon = new FitAddon();
      term.loadAddon(fitAddon);
      
      term.open(terminalRef.current!);
      fitAddon.fit();
      
      xtermRef.current = term;
      fitAddonRef.current = fitAddon;

      // Connect WebSocket
      const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const wsUrl = apiBaseUrl.replace(/^http/, "ws") + `/api/terminal/ws/${projectId || "default"}`;
      
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        // Send initial size
        ws.send(JSON.stringify({ action: "resize", cols: term.cols, rows: term.rows }));
        // Execute trigger command if it arrived before init
        if (triggerCommand && triggerCommand.cmd && !isRunning.current) {
           ws.send(JSON.stringify({ action: "input", data: triggerCommand.cmd + "\n" }));
           isRunning.current = true; // Mark as running so we don't repeat
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
        fitAddon.fit();
        if (ws.readyState === WebSocket.OPEN) {
           ws.send(JSON.stringify({ action: "resize", cols: term.cols, rows: term.rows }));
        }
      };
      window.addEventListener("resize", handleResize);
    };

    void initTerminal();

    return () => {
      if (wsRef.current) wsRef.current.close();
      if (term) term.dispose();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // Handle triggers that happen after terminal is initialized
    if (triggerCommand && triggerCommand.cmd && xtermRef.current && !isRunning.current) {
       executeCmd(triggerCommand.cmd);
       isRunning.current = true;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [triggerCommand]);

  const handleClear = () => {
    if (xtermRef.current) {
      xtermRef.current.clear();
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#1e1e1e", color: "#d4d4d4" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "4px 12px", background: "#2d2d2d", borderBottom: "1px solid #3c3c3c" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <TerminalIcon size={14} className="text-gray-400" />
          <span style={{ fontWeight: 600, fontSize: 12 }}>Terminal</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button 
            onClick={handleClear}
            className="text-gray-400 hover:text-white"
            title="Clear Terminal"
            style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 4 }}
          >
            <Trash2 size={14} />
          </button>
          {onClose && (
            <button 
              onClick={onClose}
              className="text-gray-400 hover:text-white"
              title="Close Terminal"
              style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 4 }}
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
