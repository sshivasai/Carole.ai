"use client";

import React from "react";
import Avatar from "boring-avatars";
import { User, Shield, Sparkles, Cpu } from "lucide-react";
import PrettyAvatar, { PrettyAvatarPreset } from "./PrettyAvatar";

interface AgentAvatarProps {
  name: string;
  id?: string;
  avatarSeed?: string;
  size?: number;
  isStreaming?: boolean;
  isThinking?: boolean;
  isSubagent?: boolean;
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

const SUBAGENT_PALETTE = ["#fbbf24", "#f59e0b", "#d97706", "#b45309", "#78350f"];

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

function getPresetFromName(name: string, role?: string): PrettyAvatarPreset | null {
  const n = (name || "").toLowerCase();
  const r = (role || "").toLowerCase();
  if (n.includes("archer") || r.includes("orchestrator") || r.includes("coordinator")) return "archer";
  if (n.includes("coder") || n.includes("dev") || r.includes("coder") || r.includes("engineer")) return "coder";
  if (n.includes("judge") || r.includes("judge") || r.includes("security")) return "judge";
  if (n.includes("research") || r.includes("researcher") || r.includes("analyst")) return "researcher";
  if (n.includes("qa") || n.includes("test") || r.includes("qa")) return "qa";
  if (n.startsWith("sub-") || n.startsWith("subagent") || r.includes("subagent")) return "subagent";
  return null;
}

export default function AgentAvatar({
  name,
  id,
  avatarSeed,
  size = 32,
  isStreaming = false,
  isThinking = false,
  isSubagent: explicitSubagent,
  role,
  className = "",
  style = {},
}: AgentAvatarProps) {
  const isSubagent = explicitSubagent || name.startsWith("Sub-") || name.startsWith("Subagent-") || role?.toLowerCase() === "subagent";
  const seed = avatarSeed || id || name || "agent";
  const hash = stringToHash(seed);
  const variant = VARIANTS[hash % VARIANTS.length];
  const palette = isSubagent ? SUBAGENT_PALETTE : PALETTES[hash % PALETTES.length];
  const isActive = isStreaming || isThinking;

  const isHuman = name.toLowerCase() === "human" || name.toLowerCase() === "user" || role === "human";
  const isSystem = name.toLowerCase() === "system" || role === "system";

  const preset = getPresetFromName(name, role);

  if (!isHuman && !isSystem && preset && size >= 28) {
    return (
      <PrettyAvatar
        preset={preset}
        name={name}
        size={size}
        isWorking={isActive}
        className={className}
        style={style}
      />
    );
  }

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
            background: isSubagent
              ? "conic-gradient(from 0deg, #f59e0b, #fbbf24, #d97706, #f59e0b)"
              : "conic-gradient(from 0deg, var(--color-primary), #3b82f6, #8b5cf6, #ec4899, var(--color-primary))",
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
            : isSubagent
            ? "linear-gradient(135deg, #78350f, #451a03)"
            : "var(--color-surface)",
          boxShadow: isActive
            ? isSubagent
              ? "0 0 12px rgba(245, 158, 11, 0.5)"
              : "0 0 12px var(--color-primary-glow, rgba(167, 139, 250, 0.4))"
            : "0 2px 6px rgba(0, 0, 0, 0.2)",
          border: isSubagent ? "1.5px solid rgba(251, 191, 36, 0.6)" : "none",
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

      {/* Subagent Mini Badge Overlay */}
      {isSubagent && (
        <span
          title="Temporary Subagent"
          style={{
            position: "absolute",
            bottom: -2,
            right: -2,
            width: Math.max(12, size * 0.38),
            height: Math.max(12, size * 0.38),
            borderRadius: "50%",
            background: "#f59e0b",
            border: "1.5px solid var(--color-canvas)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 2,
            boxShadow: "0 1px 4px rgba(0,0,0,0.4)",
          }}
        >
          <Cpu size={Math.max(7, size * 0.22)} color="#ffffff" />
        </span>
      )}
    </div>
  );
}

