"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { WSEvent } from "@/lib/types";
import { api } from "@/hooks/useApi";

export function getWsBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL.replace(/^http/, "ws");
  }
  if (typeof window !== "undefined") {
    const host = window.location.hostname || "localhost";
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${host}:8000`;
  }
  return "ws://localhost:8000";
}

/** Read the JWT from localStorage (same key used everywhere in the app). */
export function getWsToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("carole_token") ?? "";
}

// Exponential backoff config
const BACKOFF_BASE_MS = 1000;
const BACKOFF_MAX_MS = 30_000;
const HEARTBEAT_INTERVAL_MS = 25_000;

export type ConnectionState = "connecting" | "connected" | "reconnecting" | "offline" | "auth_required";

export interface SendResult {
  success: boolean;
  error?: string;
}

/**
 * Core WebSocket hook — connects to /ws/chat/{teamId}, handles reconnection
 * with exponential backoff + jitter, sends heartbeat pings, and dispatches
 * parsed events to the subscriber callback.
 */
export function useWebSocket(teamId: string | null, onEvent?: (evt: WSEvent) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
  const eventQueue = useRef<WSEvent[]>([]);
  const flushTimer = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimer = useRef<NodeJS.Timeout | null>(null);
  const heartbeatTimer = useRef<NodeJS.Timeout | null>(null);
  const attemptRef = useRef(0);
  const isMounted = useRef(true);
  const connectionVersion = useRef(0);
  const onEventRef = useRef(onEvent);
  const connectRef = useRef<() => void>(() => { });

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

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
        ws.send(JSON.stringify({ type: "ping" }));
      }
    }, HEARTBEAT_INTERVAL_MS);
  }, [stopHeartbeat]);

  const scheduleReconnect = useCallback(() => {
    if (!isMounted.current) return;
    setConnected(false);
    setConnectionState("reconnecting");
    stopHeartbeat();

    const attempt = attemptRef.current;
    attemptRef.current = attempt + 1;
    const base = Math.min(BACKOFF_BASE_MS * 2 ** attempt, BACKOFF_MAX_MS);
    const jitter = base * 0.25 * (Math.random() * 2 - 1);
    const delay = Math.round(base + jitter);

    console.log(`🔴 WebSocket disconnected. Reconnecting in ${delay}ms (attempt ${attempt + 1})...`);
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    reconnectTimer.current = setTimeout(() => {
      if (isMounted.current) connectRef.current();
    }, delay);
  }, [stopHeartbeat]);

  const connect = useCallback(async () => {
    const version = ++connectionVersion.current;
    const isCurrent = () => isMounted.current && connectionVersion.current === version;
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    stopHeartbeat();
    const previousSocket = wsRef.current;
    wsRef.current = null;
    previousSocket?.close();
    setConnected(false);
    if (!teamId || !isMounted.current) {
      setConnectionState("offline");
      return;
    }
    const token = getWsToken();
    if (!token) {
      setConnectionState("auth_required");
      return;
    }

    setConnectionState(attemptRef.current > 0 ? "reconnecting" : "connecting");

    let ticket = "";
    try {
      const res = await api.getWsTicket();
      ticket = res.ticket;
    } catch (err) {
      if (!isCurrent()) return;
      console.warn("Failed to fetch WS ticket, scheduling retry:", err);
      scheduleReconnect();
      return;
    }

    if (!isCurrent()) return;
    if (!ticket) { scheduleReconnect(); return; }

    try {
      const url = `${getWsBase()}/ws/chat/${teamId}?ticket=${encodeURIComponent(ticket)}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isCurrent()) return;
        attemptRef.current = 0;
        setConnected(true);
        setConnectionState("connected");
        startHeartbeat(ws);
        console.log("WebSocket connected");
      };

      ws.onmessage = (e) => {
        if (!isCurrent()) return;
        try {
          const event: WSEvent = JSON.parse(e.data);
          if ((event as any).type === "pong") return;

          eventQueue.current.push(event);
          if (!flushTimer.current) {
            flushTimer.current = setTimeout(() => {
              if (isMounted.current) {
                const currentEvents = [...eventQueue.current];
                if (onEventRef.current) {
                  currentEvents.forEach(evt => onEventRef.current?.(evt));
                }
              }
              eventQueue.current = [];
              flushTimer.current = null;
            }, 0);
          }
        } catch {
          console.warn("Failed to parse WS message:", e.data);
        }
      };

      ws.onclose = () => {
        if (isCurrent()) scheduleReconnect();
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch (e) {
      console.warn("Error creating WebSocket:", e);
      scheduleReconnect();
    }
  }, [teamId, startHeartbeat, stopHeartbeat, scheduleReconnect]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    isMounted.current = true;
    const connectTimer = setTimeout(() => {
      if (isMounted.current) {
        connect();
      }
    }, 0);
    return () => {
      clearTimeout(connectTimer);
      isMounted.current = false;
      connectionVersion.current += 1;
      attemptRef.current = 0;
      stopHeartbeat();
      if (flushTimer.current) clearTimeout(flushTimer.current);
      flushTimer.current = null;
      eventQueue.current = [];
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect, stopHeartbeat]);

  const sendMessage = useCallback((text: string, senderId: string = "human", senderName?: string, attachments?: any[]): SendResult => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return { success: false, error: "Connection offline. Please wait for reconnect or retry." };
    }
    try {
      wsRef.current.send(JSON.stringify({ text, sender_id: senderId, sender_name: senderName, attachments }));
      return { success: true };
    } catch (err: any) {
      return { success: false, error: err?.message || "Failed to send message" };
    }
  }, []);

  const sendRaw = useCallback((payload: object): SendResult => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return { success: false, error: "Connection offline" };
    }
    try {
      wsRef.current.send(JSON.stringify(payload));
      return { success: true };
    } catch (err: any) {
      return { success: false, error: err?.message || "Failed to send payload" };
    }
  }, []);

  const clearEvents = useCallback(() => {
    eventQueue.current = [];
  }, []);

  return { connected, connectionState, sendMessage, sendRaw, clearEvents, reconnect: connect };
}
