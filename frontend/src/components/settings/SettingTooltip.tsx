"use client";
import React, { useState, useRef, useEffect } from "react";
import { HelpCircle, Info } from "lucide-react";

interface SettingTooltipProps {
  title?: string;
  why: string;
  how: string;
  placement?: "top" | "bottom" | "right" | "left";
  iconSize?: number;
  children?: React.ReactNode;
}

export default function SettingTooltip({
  title,
  why,
  how,
  placement = "top",
  iconSize = 13,
  children,
}: SettingTooltipProps) {
  const [visible, setVisible] = useState(false);
  const triggerRef = useRef<HTMLDivElement>(null);
  const [coords, setCoords] = useState<{ top: number; left: number }>({ top: 0, left: 0 });

  const handleMouseEnter = () => {
    if (triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      let top = 0;
      let left = 0;

      if (placement === "top") {
        top = rect.top - 8;
        left = rect.left + rect.width / 2;
      } else if (placement === "bottom") {
        top = rect.bottom + 8;
        left = rect.left + rect.width / 2;
      } else if (placement === "right") {
        top = rect.top + rect.height / 2;
        left = rect.right + 8;
      } else {
        top = rect.top + rect.height / 2;
        left = rect.left - 8;
      }

      setCoords({ top, left });
    }
    setVisible(true);
  };

  const handleMouseLeave = () => {
    setVisible(false);
  };

  return (
    <span
      ref={triggerRef}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      style={{
        display: "inline-flex",
        alignItems: "center",
        position: "relative",
        cursor: "help",
        userSelect: "none",
        verticalAlign: "middle",
      }}
    >
      {children || (
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--color-mute)",
            transition: "color var(--t-fast)",
            marginLeft: 4,
          }}
          onMouseEnter={e => (e.currentTarget.style.color = "var(--color-primary-soft)")}
          onMouseLeave={e => (e.currentTarget.style.color = "var(--color-mute)")}
        >
          <HelpCircle size={iconSize} />
        </span>
      )}

      {visible && (
        <div
          style={{
            position: "fixed",
            top: coords.top,
            left: coords.left,
            transform:
              placement === "top"
                ? "translate(-50%, -100%)"
                : placement === "bottom"
                ? "translate(-50%, 0)"
                : placement === "right"
                ? "translate(0, -50%)"
                : "translate(-100%, -50%)",
            zIndex: 99999,
            width: "max-content",
            maxWidth: 290,
            background: "rgba(10, 10, 26, 0.96)",
            backdropFilter: "blur(12px)",
            WebkitBackdropFilter: "blur(12px)",
            border: "1px solid rgba(99, 102, 241, 0.35)",
            borderRadius: 7,
            padding: "9px 12px",
            boxShadow: "0 10px 30px rgba(0, 0, 0, 0.6), 0 0 15px rgba(79, 70, 229, 0.2)",
            color: "var(--color-ink)",
            fontSize: 11,
            lineHeight: 1.45,
            pointerEvents: "none",
            animation: "fadeInTooltip 0.15s ease-out forwards",
          }}
        >
          {title && (
            <div
              style={{
                fontWeight: 700,
                fontSize: 11.5,
                color: "#ffffff",
                marginBottom: 6,
                display: "flex",
                alignItems: "center",
                gap: 5,
                borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
                paddingBottom: 4,
              }}
            >
              <Info size={12} color="var(--color-primary-soft)" />
              {title}
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            <div>
              <span
                style={{
                  fontWeight: 700,
                  fontSize: 9.5,
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  color: "#a78bfa",
                  marginRight: 5,
                }}
              >
                Why:
              </span>
              <span style={{ color: "var(--color-body)" }}>{why}</span>
            </div>

            <div>
              <span
                style={{
                  fontWeight: 700,
                  fontSize: 9.5,
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  color: "#34d399",
                  marginRight: 5,
                }}
              >
                How:
              </span>
              <span style={{ color: "var(--color-body)" }}>{how}</span>
            </div>
          </div>
        </div>
      )}
    </span>
  );
}
