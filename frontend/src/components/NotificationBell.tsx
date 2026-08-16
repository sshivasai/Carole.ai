"use client";
import React, { useState, useEffect, useRef, useCallback } from "react";
import { Bell, Trash2, X } from "lucide-react";
import { api } from "@/hooks/useApi";
import type { Notification } from "@/lib/types";

const TYPE_COLORS: Record<string, string> = {
  info: "#60a5fa",
  success: "#34d399",
  warning: "#fbbf24",
  error: "#f87171",
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

interface Props {
  className?: string;
}

export default function NotificationBell({ className }: Props = {}) {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const fetchNotifications = useCallback(async () => {
    try {
      const res = await api.listNotifications();
      setNotifications(res.notifications);
      setUnread(res.unread_count);
    } catch {
      // silently ignore — user may not be logged in yet
    }
  }, []);

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 30_000);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const handleOpen = async () => {
    const willOpen = !open;
    setOpen(willOpen);
    if (willOpen && unread > 0) {
      try {
        await api.markNotificationsRead();
        setNotifications(n => n.map(x => ({ ...x, is_read: true })));
        setUnread(0);
      } catch { /* ignore */ }
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.deleteNotification(id);
      setNotifications(n => n.filter(x => x.id !== id));
    } catch { /* ignore */ }
  };

  const handleClearAll = async () => {
    setLoading(true);
    try {
      await api.clearAllNotifications();
      setNotifications([]);
      setUnread(0);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-flex" }}>
      <button
        id="notification-bell-btn"
        className={`btn btn-icon btn-ghost ${className ?? ""}`}
        onClick={handleOpen}
        title="Notifications"
        style={{ position: "relative" }}
      >
        <Bell size={15} />
        {unread > 0 && (
          <span style={{
            position: "absolute",
            top: 2,
            right: 2,
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: "var(--color-danger, #f87171)",
            border: "2px solid var(--bg-primary, #111)",
          }} />
        )}
      </button>

      {open && (
        <div
          id="notification-panel"
          className="animate-slide-up"
          style={{
            position: "absolute",
            top: "calc(100% + 8px)",
            right: 0,
            width: 360,
            maxHeight: 480,
            background: "var(--bg-secondary, #1a1a1a)",
            border: "1px solid var(--border, rgba(255,255,255,0.08))",
            borderRadius: "var(--radius-lg, 12px)",
            boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            zIndex: 1000,
          }}
        >
          {/* Header */}
          <div style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "12px 16px",
            borderBottom: "1px solid var(--border, rgba(255,255,255,0.06))",
            flexShrink: 0,
          }}>
            <span style={{ fontWeight: 600, fontSize: 14 }}>Notifications</span>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              {notifications.length > 0 && (
                <button
                  className="btn btn-ghost"
                  style={{ fontSize: 12, padding: "2px 8px", color: "var(--color-mute)", gap: 4 }}
                  onClick={handleClearAll}
                  disabled={loading}
                  title="Clear all"
                >
                  <Trash2 size={11} /> Clear all
                </button>
              )}
              <button className="btn btn-icon-sm btn-ghost" onClick={() => setOpen(false)}>
                <X size={14} />
              </button>
            </div>
          </div>

          {/* List */}
          <div style={{ overflowY: "auto", flex: 1 }}>
            {notifications.length === 0 ? (
              <div style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                height: 160,
                gap: 8,
                color: "var(--color-mute)",
              }}>
                <Bell size={28} style={{ opacity: 0.3 }} />
                <span style={{ fontSize: 13 }}>You&apos;re all caught up!</span>
              </div>
            ) : (
              notifications.map(n => (
                <div
                  key={n.id}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 10,
                    padding: "12px 16px",
                    borderBottom: "1px solid var(--border, rgba(255,255,255,0.04))",
                    background: n.is_read ? "transparent" : "rgba(255,255,255,0.025)",
                    transition: "background 0.2s",
                  }}
                >
                  <div style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: TYPE_COLORS[n.type] ?? TYPE_COLORS.info,
                    marginTop: 5,
                    flexShrink: 0,
                    boxShadow: `0 0 6px ${TYPE_COLORS[n.type] ?? TYPE_COLORS.info}66`,
                  }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: n.is_read ? 400 : 600, marginBottom: 2 }}>
                      {n.title}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--color-mute)", lineHeight: 1.4, wordBreak: "break-word" }}>
                      {n.message}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--color-mute)", marginTop: 4, opacity: 0.6 }}>
                      {timeAgo(n.created_at)}
                    </div>
                  </div>
                  <button
                    className="btn btn-icon-sm btn-ghost"
                    style={{ opacity: 0.5, flexShrink: 0 }}
                    onClick={(e) => handleDelete(n.id, e)}
                    title="Dismiss"
                  >
                    <X size={12} />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
