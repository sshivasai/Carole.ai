"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { WSEvent } from "@/lib/types";

const WS_BASE = process.env.NEXT_PUBLIC_API_URL?.replace("http", "ws") || "ws://localhost:8000";

/**
 * Core WebSocket hook — connects to /ws/chat/{teamId}, handles reconnection,
 * and dispatches parsed events to the subscriber callback.
 */
export function useWebSocket(teamId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<WSEvent[]>([]);
  const reconnectTimer = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    if (!teamId) return;
    const url = `${WS_BASE}/ws/chat/${teamId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      console.log(`🟢 WebSocket connected to ${url}`);
    };

    ws.onmessage = (e) => {
      try {
        const event: WSEvent = JSON.parse(e.data);
        setEvents((prev) => [...prev, event]);
      } catch {
        console.warn("Failed to parse WS message:", e.data);
      }
    };

    ws.onclose = () => {
      setConnected(false);
      console.log("🔴 WebSocket disconnected. Reconnecting in 3s...");
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => ws.close();
  }, [teamId]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((text: string, senderId: string = "human") => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ text, sender_id: senderId }));
    }
  }, []);

  const clearEvents = useCallback(() => setEvents([]), []);

  return { connected, events, sendMessage, clearEvents };
}
