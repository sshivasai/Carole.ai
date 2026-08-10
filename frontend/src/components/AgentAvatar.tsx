"use client";

import React from "react";
import Avatar from "boring-avatars";
import { User, Shield } from "lucide-react";

interface AgentAvatarProps {
  name: string;
  id?: string;
  avatarSeed?: string;
  size?: number;
  isStreaming?: boolean;
  isThinking?: boolean;
  role?: string;
  className?: string;
  style?: React.CSSProperties;
}

// 5 curated vibrant color palettes
const PALETTES = [
  ["#00d992", "#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b"],
  ["#06b6d4", "#3b82f6", "#6366f1", "#8b5cf6", "#d946ef"],
  ["#10b981", "#14b8a6", "#06b6d4", "#0284c7", "#2563eb"],
  ["#f59e0b", "#f97316", "#ef4444", "#ec4899", "#8b5cf6"],
  ["#84cc16", "#10b981", "#06b6d4", "#3b82f6", "#a855f7"],
];

const VARIANTS: ("beam" | "marble" | "pixel" | "sunset" | "ring" | "bauhaus")[] = [
  "beam", "marble", "pixel", "sunset", "ring", "bauhaus"
];

function stringToHash(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

export default function AgentAvatar({
  name,
  id,
  avatarSeed,
  size = 32,
  isStreaming = false,
  isThinking = false,
  role,
  className = "",
  style = {},
}: AgentAvatarProps) {
  const seed = avatarSeed || id || name || "agent";
  const hash = stringToHash(seed);
  const variant = VARIANTS[hash % VARIANTS.length];
  const palette = PALETTES[hash % PALETTES.length];
  const isActive = isStreaming || isThinking;

  const isHuman = name.toLowerCase() === "human" || name.toLowerCase() === "user" || role === "human";
  const isSystem = name.toLowerCase() === "system" || role === "system";

  return (
    <div
      className={`agent-avatar-wrapper ${isActive ? "agent-avatar-active" : ""} ${className}`}
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        position: "relative",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        ...style,
      }}
    >
      {/* Motion Aura Ring when agent is actively thinking or streaming */}
      {isActive && (
        <span
          className="agent-avatar-aura"
          style={{
            position: "absolute",
            inset: -3,
            borderRadius: "50%",
            background: "conic-gradient(from 0deg, #00d992, #3b82f6, #8b5cf6, #ec4899, #00d992)",
            animation: "avatarSpinAura 2.5s linear infinite",
            opacity: 0.85,
            zIndex: 0,
            filter: "blur(2px)",
          }}
        />
      )}

      {/* Avatar Body */}
      <div
        className="agent-avatar-inner"
        style={{
          width: size,
          height: size,
          borderRadius: "50%",
          overflow: "hidden",
          position: "relative",
          zIndex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: isHuman
            ? "linear-gradient(135deg, #3b82f6, #1d4ed8)"
            : isSystem
            ? "linear-gradient(135deg, #64748b, #334155)"
            : "var(--color-surface)",
          boxShadow: isActive
            ? "0 0 12px var(--color-primary-glow, rgba(0, 217, 146, 0.4))"
            : "0 2px 6px rgba(0, 0, 0, 0.2)",
          transition: "transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.2s ease",
        }}
      >
        {isHuman ? (
          <User size={size * 0.55} color="#ffffff" />
        ) : isSystem ? (
          <Shield size={size * 0.55} color="#38bdf8" />
        ) : (
          <Avatar size={size} name={seed} variant={variant} colors={palette} />
        )}
      </div>
    </div>
  );
}
