"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { WSEvent } from "@/lib/types";

const WS_BASE = process.env.NEXT_PUBLIC_API_URL?.replace("http", "ws") || "ws://localhost:8000";

// Exponential backoff config
const BACKOFF_BASE_MS = 1000;
const BACKOFF_MAX_MS = 30_000;
const HEARTBEAT_INTERVAL_MS = 25_000;

/**
 * Core WebSocket hook — connects to /ws/chat/{teamId}, handles reconnection
 * with exponential backoff + jitter, sends heartbeat pings, and dispatches
 * parsed events to the subscriber callback.
 *
 * Fixes:
 * - Flat 3s reconnect → exponential backoff with jitter + 30s cap
 * - No heartbeat → 25s ping to keep alive through load balancers / proxies
 * - isMounted guard prevents state updates after unmount (no React warnings)
 */
export function useWebSocket(teamId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<WSEvent[]>([]);
  const reconnectTimer = useRef<NodeJS.Timeout | null>(null);
  const heartbeatTimer = useRef<NodeJS.Timeout | null>(null);
  const attemptRef = useRef(0);
  const isMounted = useRef(true);

  const stopHeartbeat = useCallback(() => {
    if (heartbeatTimer.current) {
      clearInterval(heartbeatTimer.current);
      heartbeatTimer.current = null;
    }
  }, []);

  const startHeartbeat = useCallback((ws: WebSocket) => {
    stopHeartbeat();
    heartbeatTimer.current = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        // Send a lightweight ping frame
        ws.send(JSON.stringify({ type: "ping" }));
      }
    }, HEARTBEAT_INTERVAL_MS);
  }, [stopHeartbeat]);

  const connect = useCallback(() => {
    if (!teamId || !isMounted.current) return;

    const url = `${WS_BASE}/ws/chat/${teamId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!isMounted.current) return;
      attemptRef.current = 0; // reset backoff on success
      setConnected(true);
      startHeartbeat(ws);
      console.log(`🟢 WebSocket connected to ${url}`);
    };

    ws.onmessage = (e) => {
      if (!isMounted.current) return;
      try {
        const event: WSEvent = JSON.parse(e.data);
        // Ignore server pong echoes
        if ((event as any).type === "pong") return;
        setEvents((prev) => [...prev, event]);
      } catch {
        console.warn("Failed to parse WS message:", e.data);
      }
    };

    ws.onclose = () => {
      if (!isMounted.current) return;
      setConnected(false);
      stopHeartbeat();

      // Exponential backoff with ±25% jitter
      const attempt = attemptRef.current;
      attemptRef.current = attempt + 1;
      const base = Math.min(BACKOFF_BASE_MS * 2 ** attempt, BACKOFF_MAX_MS);
      const jitter = base * 0.25 * (Math.random() * 2 - 1);
      const delay = Math.round(base + jitter);

      console.log(`🔴 WebSocket disconnected. Reconnecting in ${delay}ms (attempt ${attempt + 1})...`);
      reconnectTimer.current = setTimeout(() => {
        if (isMounted.current) connect();
      }, delay);
    };

    ws.onerror = () => ws.close();
  }, [teamId, startHeartbeat, stopHeartbeat]);

  useEffect(() => {
    isMounted.current = true;
    connect();
    return () => {
      isMounted.current = false;
      stopHeartbeat();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect, stopHeartbeat]);

  const sendMessage = useCallback((text: string, senderId: string = "human", senderName?: string, attachments?: any[]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ text, sender_id: senderId, sender_name: senderName, attachments }));
    }
  }, []);

  const sendRaw = useCallback((payload: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
    }
  }, []);

  const clearEvents = useCallback(() => setEvents([]), []);

  return { connected, events, sendMessage, sendRaw, clearEvents };
}
