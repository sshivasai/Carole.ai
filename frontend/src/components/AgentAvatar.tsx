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
  showBadge?: boolean;
  hideBadge?: boolean;
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

const PRESET_LIST: PrettyAvatarPreset[] = [
  "archer",
  "coder",
  "judge",
  "researcher",
  "qa",
  "designer",
  "analyst"
];

function getPresetFromName(name: string, role?: string, id?: string): PrettyAvatarPreset {
  const n = (name || "").toLowerCase();
  const rawRole = (role || "").toLowerCase();
  const r = (rawRole === "assistant" || rawRole === "user" || rawRole === "active agent") ? "" : rawRole;

  if (n.startsWith("sub-") || n.startsWith("subagent") || r.includes("subagent")) return "subagent";
  if (n.includes("archer") || r.includes("orchestrator") || r.includes("coordinator") || r.includes("manager")) return "archer";
  if (
    n.includes("nova") || n.includes("coder") || n.includes("dev") || n.includes("engineer") || n.includes("alex") || n.includes("ada") ||
    r.includes("coder") || r.includes("engineer") || r.includes("developer") || r.includes("software") ||
    r.includes("fullstack") || r.includes("frontend") || r.includes("backend") || r.includes("architect")
  ) {
    return "coder";
  }
  if (n.includes("judge") || n.includes("judy") || n.includes("sentinel") || r.includes("judge") || r.includes("security") || r.includes("guard")) return "judge";
  if (n.includes("sherlock") || n.includes("watson") || n.includes("research") || r.includes("researcher") || r.includes("science") || r.includes("ai")) return "researcher";
  if (n.includes("qa") || n.includes("test") || r.includes("qa") || r.includes("tester") || r.includes("sre") || r.includes("devops")) return "qa";
  if (n.includes("design") || r.includes("design") || r.includes("ui") || r.includes("ux")) return "designer";
  if (n.includes("turing") || n.includes("analyst") || r.includes("analyst") || r.includes("data") || r.includes("writer") || r.includes("doc")) return "analyst";

  // Deterministic fallback based on agent name or id
  const seed = name || id || "agent";
  const hash = stringToHash(seed);
  return PRESET_LIST[hash % PRESET_LIST.length];
}

function getHumanInitials(name?: string): string {
  if (!name || !name.trim()) return "A";
  const clean = name.replace(/@/g, "").trim();
  if (clean.toLowerCase() === "admin" || clean.toLowerCase() === "human" || clean.toLowerCase() === "user" || clean.toLowerCase() === "you") {
    return "A";
  }
  if (clean.includes("@")) {
    const userPart = clean.split("@")[0];
    return userPart.slice(0, 2).toUpperCase();
  }
  const parts = clean.split(/[\s._-]+/).filter(Boolean);
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
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
  showBadge,
  hideBadge = false,
  className = "",
  style = {},
}: AgentAvatarProps) {
  const isSubagent = explicitSubagent || name.startsWith("Sub-") || name.startsWith("Subagent-") || role?.toLowerCase() === "subagent";
  const isActive = isStreaming || isThinking;

  const isHuman = name.toLowerCase() === "human" || name.toLowerCase() === "user" || name.toLowerCase() === "admin" || name.toLowerCase() === "you" || role === "human";
  const isSystem = name.toLowerCase() === "system" || role === "system";

  if (isHuman) {
    const initials = getHumanInitials(name);
    const fontSize = Math.max(9, Math.round(size * 0.40));
    return (
      <div
        className={`human-avatar-wrapper ${className}`}
        style={{
          width: size,
          height: size,
          borderRadius: "50%",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          background: "linear-gradient(135deg, #3b82f6 0%, #1d4ed8 55%, #1e1b4b 100%)",
          border: "1.5px solid rgba(147, 197, 253, 0.45)",
          boxShadow: "0 2px 8px rgba(37, 99, 235, 0.35)",
          color: "#ffffff",
          fontFamily: "var(--font-sans, system-ui, -apple-system, sans-serif)",
          fontWeight: 700,
          fontSize,
          letterSpacing: initials.length > 1 ? "-0.4px" : "0px",
          userSelect: "none",
          textShadow: "0 1px 2px rgba(0, 0, 0, 0.3)",
          position: "relative",
          ...style,
        }}
        title={name || "Admin"}
      >
        {initials}
      </div>
    );
  }

  if (!isSystem) {
    const preset = isSubagent ? "subagent" : undefined;
    return (
      <PrettyAvatar
        preset={preset}
        name={name}
        role={role}
        seed={avatarSeed || id || name}
        size={size}
        isWorking={isActive}
        showBadge={showBadge}
        hideBadge={hideBadge}
        className={className}
        style={style}
      />
    );
  }

  const seed = avatarSeed || id || name || "agent";
  const hash = stringToHash(seed);
  const variant = VARIANTS[hash % VARIANTS.length];
  const palette = isSubagent ? SUBAGENT_PALETTE : PALETTES[hash % PALETTES.length];

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
        {isSystem ? (
          <Shield size={size * 0.55} color="#38bdf8" />
        ) : (
          <User size={size * 0.55} color="#ffffff" />
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

