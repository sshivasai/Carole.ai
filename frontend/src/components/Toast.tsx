"use client";
import React from "react";
import { CheckCircle, XCircle, Info, AlertTriangle, X } from "lucide-react";
import type { Toast, ToastType } from "@/hooks/useToast";

const CONFIG: Record<ToastType, { icon: React.ReactNode; color: string; bg: string; border: string }> = {
  success: { icon: <CheckCircle size={16} />, color: "#34d399", bg: "rgba(52,211,153,0.10)", border: "rgba(52,211,153,0.25)" },
  error:   { icon: <XCircle size={16} />,     color: "#f87171", bg: "rgba(248,113,113,0.10)", border: "rgba(248,113,113,0.25)" },
  info:    { icon: <Info size={16} />,         color: "#60a5fa", bg: "rgba(96,165,250,0.10)",  border: "rgba(96,165,250,0.25)" },
  warning: { icon: <AlertTriangle size={16} />, color: "#fbbf24", bg: "rgba(251,191,36,0.10)", border: "rgba(251,191,36,0.25)" },
};

interface Props { toasts: Toast[]; onDismiss: (id: string) => void; }

export default function ToastContainer({ toasts, onDismiss }: Props) {
  if (!toasts.length) return null;
  return (
    <div style={{ position: "fixed", bottom: 24, right: 24, zIndex: 9999, display: "flex", flexDirection: "column", gap: 10, alignItems: "flex-end", pointerEvents: "none" }}>
      {toasts.map(t => {
        const cfg = CONFIG[t.type];
        return (
          <div
            key={t.id}
            className="animate-slide-up"
            style={{
              pointerEvents: "all",
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              padding: "12px 14px",
              background: cfg.bg,
              border: `1px solid ${cfg.border}`,
              borderRadius: "var(--radius-md)",
              backdropFilter: "blur(8px)",
              maxWidth: 360,
              minWidth: 240,
              boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
            }}
          >
            <span style={{ color: cfg.color, flexShrink: 0, marginTop: 1 }}>{cfg.icon}</span>
            <span style={{ fontSize: 13, color: "var(--color-ink)", flex: 1, lineHeight: 1.4 }}>{t.message}</span>
            <button
              onClick={() => onDismiss(t.id)}
              style={{ background: "none", border: "none", cursor: "pointer", color: "var(--color-mute)", padding: 0, flexShrink: 0 }}
              aria-label="Dismiss"
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
