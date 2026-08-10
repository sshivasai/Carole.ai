"use client";

import React from "react";

interface AppSpinnerProps {
  size?: "sm" | "md" | "lg" | number;
  color?: string;
  className?: string;
  style?: React.CSSProperties;
}

const SIZE_MAP = {
  sm: 14,
  md: 20,
  lg: 32,
};

export default function AppSpinner({
  size = "md",
  color = "var(--color-primary, #00d992)",
  className = "",
  style = {},
}: AppSpinnerProps) {
  const pxSize = typeof size === "number" ? size : SIZE_MAP[size] || 20;
  const strokeWidth = Math.max(2, Math.round(pxSize / 7));

  return (
    <span
      className={`app-kinetic-spinner ${className}`}
      style={{
        width: pxSize,
        height: pxSize,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
        verticalAlign: "middle",
        flexShrink: 0,
        ...style,
      }}
    >
      <svg
        width={pxSize}
        height={pxSize}
        viewBox="0 0 32 32"
        fill="none"
        style={{ animation: "spinnerRotate 1.2s cubic-bezier(0.5, 0, 0.5, 1) infinite" }}
      >
        <circle
          cx="16"
          cy="16"
          r={14 - strokeWidth}
          stroke="rgba(255, 255, 255, 0.1)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx="16"
          cy="16"
          r={14 - strokeWidth}
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray="60 30"
          strokeLinecap="round"
        />
      </svg>
      <span
        style={{
          position: "absolute",
          width: Math.max(3, Math.round(pxSize / 5)),
          height: Math.max(3, Math.round(pxSize / 5)),
          borderRadius: "50%",
          backgroundColor: color,
          boxShadow: `0 0 6px ${color}`,
          animation: "corePulse 1.4s ease-in-out infinite",
        }}
      />
      <style>{`
        @keyframes spinnerRotate { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
      `}</style>
    </span>
  );
}
