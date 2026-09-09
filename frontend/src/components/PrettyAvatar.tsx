"use client";

import React from "react";
import { Crown, Code2, Shield, Brain, CheckCircle2, Bot, Palette, LineChart, UserCheck } from "lucide-react";

export type PrettyAvatarPreset = 
  | "archer"
  | "coder"
  | "judge"
  | "researcher"
  | "qa"
  | "subagent"
  | "designer"
  | "analyst"
  | "admin";

interface PrettyAvatarProps {
  preset?: PrettyAvatarPreset | string;
  name?: string;
  role?: string;
  seed?: string;
  size?: number;
  isWorking?: boolean;
  showBadge?: boolean;
  hideBadge?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

function stringToHash(str: string): number {
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (let i = 0; i < str.length; i++) {
    const ch = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return ((h1 ^ h2) >>> 0);
}

// 12 curated vibrant dual-tone dark gradients
const GRADIENTS: [string, string][] = [
  ["#10b981", "#047857"], // Emerald
  ["#8b5cf6", "#6d28d9"], // Violet
  ["#3b82f6", "#1d4ed8"], // Cobalt
  ["#ec4899", "#be185d"], // Rose Pink
  ["#f59e0b", "#b45309"], // Amber
  ["#06b6d4", "#0e7490"], // Cyan Ocean
  ["#6366f1", "#4338ca"], // Indigo
  ["#14b8a6", "#0f766e"], // Teal
  ["#f43f5e", "#be123c"], // Crimson
  ["#84cc16", "#4d7c0f"], // Lime
  ["#a855f7", "#7e22ce"], // Electric Purple
  ["#f97316", "#c2410c"], // Sunset Orange
];

const ACCENTS = [
  "#34d399", "#a78bfa", "#38bdf8", "#f472b6", "#fbbf24", "#22d3ee",
  "#818cf8", "#2dd4bf", "#fda4af", "#a3e635", "#c084fc", "#fb923c"
];

const SKINS = ["#fed7aa", "#ffedd5", "#fde68a", "#fecdd3", "#f5d0c5", "#e2b897"];
const HAIR_COLORS = ["#0f172a", "#312e81", "#78350f", "#1e3a8a", "#881337", "#831843", "#1e1b4b", "#18181b", "#134e4a", "#431407"];
const HAIR_TYPES = ["stylish", "curly", "sleek", "wavy", "bun", "pompadour", "spiky"];
const EYE_TYPES = ["tech", "focused", "human", "laser", "robot", "curious", "sharp"];
const ACCESSORIES = ["headphones", "glasses", "visor", "monocle", "antenna", "badge", "none"];

export function getCanonicalAgentKey(name?: string, role?: string, seed?: string): string {
  // Prefer name over seed, strip leading '@'
  let cleanName = (name || seed || "agent")
    .replace(/^@/, "")
    .trim()
    .toLowerCase();

  // Normalize role: strip generic transport/turn roles
  let cleanRole = (role || "").trim().toLowerCase();
  if (["assistant", "user", "agent", "active agent", "active", "system", "model"].includes(cleanRole)) {
    if (cleanName.includes("archer")) cleanRole = "orchestrator";
    else if (cleanName.includes("nova") || cleanName.includes("coder")) cleanRole = "coder";
    else if (cleanName.includes("judge") || cleanName.includes("judy") || cleanName.includes("sentinel")) cleanRole = "judge";
    else cleanRole = "";
  }

  // Canonical format: "name:role" if role is known, else "name"
  return cleanRole ? `${cleanName}:${cleanRole}` : cleanName;
}

export function getAvatarTheme(name?: string, role?: string, seed?: string, preset?: string) {
  const n = (name || "agent").toLowerCase().trim();
  const r = (role || "").toLowerCase().trim();

  // Special System / Human Singleton Presets
  if (preset === "admin" || n === "admin" || n === "human" || r === "human") {
    return {
      bgGrad: ["#2563eb", "#1e1b4b"] as [string, string],
      skin: "#fed7aa",
      hair: "#0f172a",
      hairType: "pompadour",
      eyes: "human",
      accessory: "badge",
      accentColor: "#38bdf8",
      hash: 1,
    };
  }

  if (preset === "subagent" || n.startsWith("sub-") || n.startsWith("subagent-") || r.includes("subagent")) {
    return {
      bgGrad: ["#fbbf24", "#d97706"] as [string, string],
      skin: "#ffedd5",
      hair: "#451a03",
      hairType: "spiky",
      eyes: "robot",
      accessory: "antenna",
      accentColor: "#f59e0b",
      hash: 2,
    };
  }

  // Deterministic Seed Generation strictly based on canonical name + role
  const canonicalKey = getCanonicalAgentKey(name, role, seed);
  const hash = stringToHash(canonicalKey);

  const gradIdx = hash % GRADIENTS.length;
  const bgGrad = GRADIENTS[gradIdx];
  const accentColor = ACCENTS[((hash >>> 4) % ACCENTS.length)];

  const skin = SKINS[((hash >>> 8) % SKINS.length)];
  const hair = HAIR_COLORS[((hash >>> 12) % HAIR_COLORS.length)];
  const hairType = HAIR_TYPES[((hash >>> 16) % HAIR_TYPES.length)];
  const eyes = EYE_TYPES[((hash >>> 20) % EYE_TYPES.length)];
  const accessory = ACCESSORIES[((hash >>> 24) % ACCESSORIES.length)];

  return {
    bgGrad,
    skin,
    hair,
    hairType,
    eyes,
    accessory,
    accentColor,
    hash,
  };
}

/**
 * Beautiful SVG Character Avatars with Dynamic Seed Generation
 * Generates 100% constant, deterministic, unique character traits per agent.
 */
export default function PrettyAvatar({
  preset,
  name = "Agent",
  role,
  seed,
  size = 64,
  isWorking = false,
  showBadge,
  hideBadge = false,
  className = "",
  style = {},
}: PrettyAvatarProps) {
  const iconSize = Math.max(10, Math.round(size * 0.18));
  const cfg = getAvatarTheme(name, role, seed, preset);

  const getBadge = () => {
    const r = (role || "").toLowerCase();
    const n = (name || "").toLowerCase();
    if (preset === "admin" || n === "admin" || n === "human" || r === "human") {
      return <UserCheck size={iconSize} color={cfg.accentColor} />;
    }
    if (preset === "subagent" || n.startsWith("sub-") || r.includes("subagent")) {
      return <Bot size={iconSize} color={cfg.accentColor} />;
    }
    if (r.includes("orchestrator") || r.includes("coordinator") || r.includes("lead") || r.includes("manager") || n.includes("archer")) {
      return <Crown size={iconSize} color={cfg.accentColor} />;
    }
    if (r.includes("coder") || r.includes("developer") || r.includes("engineer") || r.includes("fullstack") || r.includes("backend") || r.includes("frontend")) {
      return <Code2 size={iconSize} color={cfg.accentColor} />;
    }
    if (r.includes("judge") || r.includes("security") || r.includes("guard") || r.includes("audit")) {
      return <Shield size={iconSize} color={cfg.accentColor} />;
    }
    if (r.includes("research") || r.includes("science") || r.includes("ai") || r.includes("data")) {
      return <Brain size={iconSize} color={cfg.accentColor} />;
    }
    if (r.includes("qa") || r.includes("test") || r.includes("sre") || r.includes("devops")) {
      return <CheckCircle2 size={iconSize} color={cfg.accentColor} />;
    }
    if (r.includes("design") || r.includes("ui") || r.includes("ux")) {
      return <Palette size={iconSize} color={cfg.accentColor} />;
    }
    if (r.includes("analyst") || r.includes("writer") || r.includes("doc")) {
      return <LineChart size={iconSize} color={cfg.accentColor} />;
    }
    const icons = [
      <Code2 size={iconSize} color={cfg.accentColor} />,
      <Crown size={iconSize} color={cfg.accentColor} />,
      <Shield size={iconSize} color={cfg.accentColor} />,
      <Brain size={iconSize} color={cfg.accentColor} />,
      <CheckCircle2 size={iconSize} color={cfg.accentColor} />,
      <Bot size={iconSize} color={cfg.accentColor} />,
      <Palette size={iconSize} color={cfg.accentColor} />,
      <LineChart size={iconSize} color={cfg.accentColor} />,
    ];
    return icons[((cfg.hash || 0) >>> 27) % icons.length];
  };

  const badgeIcon = getBadge();
  const defId = `av-${cfg.hash || "def"}`;

  return (
    <div
      className={`pretty-avatar-container ${isWorking ? "pretty-avatar-working" : ""} ${className}`}
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        position: "relative",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        boxShadow: `0 6px 20px ${cfg.bgGrad[0]}40`,
        ...style,
      }}
    >
      {/* Animated Orbiting Ring when working */}
      {isWorking && (
        <svg
          style={{
            position: "absolute",
            inset: -4,
            width: size + 8,
            height: size + 8,
            pointerEvents: "none",
            animation: "avatarSpinAura 3s linear infinite",
          }}
          viewBox="0 0 100 100"
        >
          <circle
            cx="50"
            cy="50"
            r="47"
            fill="none"
            stroke={cfg.accentColor}
            strokeWidth="3"
            strokeDasharray="20 10"
            strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 6px ${cfg.accentColor})` }}
          />
        </svg>
      )}

      {/* SVG Avatar Illustration */}
      <svg
        width={size}
        height={size}
        viewBox="0 0 100 100"
        style={{
          borderRadius: "50%",
          overflow: "hidden",
          background: `linear-gradient(135deg, ${cfg.bgGrad[0]} 0%, ${cfg.bgGrad[1]} 100%)`,
        }}
      >
        <defs>
          <radialGradient id={`glow-${defId}`} cx="50%" cy="30%" r="60%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
          </radialGradient>
          <linearGradient id={`skin-${defId}`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={cfg.skin} />
            <stop offset="100%" stopColor="#fca5a5" stopOpacity="0.8" />
          </linearGradient>
        </defs>

        {/* Ambient Top Light */}
        <circle cx="50" cy="50" r="50" fill={`url(#glow-${defId})`} />

        {/* Body / Shoulders */}
        <path
          d="M20 96 C20 74, 34 68, 50 68 C66 68, 80 74, 80 96 Z"
          fill="#1e1b4b"
          opacity="0.9"
        />
        {/* Shirt Collar / Accent */}
        <path
          d="M38 72 L50 84 L62 72 Z"
          fill={cfg.accentColor}
          opacity="0.9"
        />

        {/* Neck */}
        <rect x="43" y="54" width="14" height="16" rx="4" fill={`url(#skin-${defId})`} />

        {/* Head Base */}
        <ellipse cx="50" cy="42" rx="22" ry="24" fill={`url(#skin-${defId})`} />

        {/* Hair Styles */}
        {cfg.hairType === "stylish" && (
          <path
            d="M26 36 C26 20, 36 14, 50 14 C64 14, 74 20, 74 36 C74 38, 70 30, 64 26 C58 22, 42 22, 36 26 C30 30, 26 38, 26 36 Z"
            fill={cfg.hair}
          />
        )}
        {cfg.hairType === "curly" && (
          <g fill={cfg.hair}>
            <circle cx="32" cy="24" r="10" />
            <circle cx="44" cy="18" r="11" />
            <circle cx="56" cy="18" r="11" />
            <circle cx="68" cy="24" r="10" />
            <circle cx="26" cy="34" r="8" />
            <circle cx="74" cy="34" r="8" />
          </g>
        )}
        {cfg.hairType === "sleek" && (
          <path
            d="M26 38 C26 16, 40 12, 50 12 C60 12, 74 16, 74 38 C68 28, 58 24, 50 24 C42 24, 32 28, 26 38 Z"
            fill={cfg.hair}
          />
        )}
        {cfg.hairType === "wavy" && (
          <path
            d="M24 38 C22 18, 38 14, 50 14 C62 14, 78 18, 76 38 C70 26, 62 22, 50 24 C38 22, 30 26, 24 38 Z"
            fill={cfg.hair}
          />
        )}
        {cfg.hairType === "bun" && (
          <g fill={cfg.hair}>
            <circle cx="50" cy="12" r="10" />
            <path d="M26 36 C26 20, 36 16, 50 16 C64 16, 74 20, 74 36 C70 26, 60 22, 50 22 C40 22, 30 26, 26 36 Z" />
          </g>
        )}
        {cfg.hairType === "pompadour" && (
          <path
            d="M24 36 C24 16, 34 10, 52 10 C66 10, 76 16, 76 36 C76 38, 72 26, 62 20 C52 14, 38 18, 32 24 C28 28, 24 36, 24 36 Z"
            fill={cfg.hair}
          />
        )}
        {cfg.hairType === "spiky" && (
          <path
            d="M24 34 L30 18 L38 24 L48 12 L56 22 L66 16 L72 32 C66 24, 58 22, 50 22 C42 22, 32 24, 24 34 Z"
            fill={cfg.hair}
          />
        )}

        {/* Eyes & Expressions */}
        {cfg.eyes === "laser" ? (
          <g>
            <rect x="34" y="38" width="32" height="7" rx="3.5" fill="#1e1b4b" />
            <rect x="36" y="40" width="28" height="3" rx="1.5" fill="#ef4444" style={{ filter: "drop-shadow(0 0 3px #ef4444)" }} />
          </g>
        ) : cfg.eyes === "robot" ? (
          <g fill="#0284c7">
            <rect x="36" y="38" width="9" height="7" rx="2" fill="#0284c7" />
            <rect x="55" y="38" width="9" height="7" rx="2" fill="#0284c7" />
            <circle cx="40" cy="41" r="1.5" fill="#ffffff" />
            <circle cx="59" cy="41" r="1.5" fill="#ffffff" />
          </g>
        ) : cfg.eyes === "human" ? (
          <g fill="#0f172a">
            {/* Left Eye */}
            <ellipse cx="39" cy="42" rx="3.5" ry="4.2" />
            <circle cx="40.8" cy="40.2" r="1.4" fill="#ffffff" />
            <circle cx="38" cy="43.2" r="0.8" fill="#ffffff" opacity="0.85" />
            {/* Right Eye */}
            <ellipse cx="61" cy="42" rx="3.5" ry="4.2" />
            <circle cx="62.8" cy="40.2" r="1.4" fill="#ffffff" />
            <circle cx="60" cy="43.2" r="0.8" fill="#ffffff" opacity="0.85" />
            {/* Eyebrows */}
            <path d="M34 33 Q40 29 45 32" stroke="#0f172a" strokeWidth="2.2" strokeLinecap="round" fill="none" />
            <path d="M55 32 Q60 29 66 33" stroke="#0f172a" strokeWidth="2.2" strokeLinecap="round" fill="none" />
          </g>
        ) : (
          <g fill="#1e1b4b">
            {/* Left Eye */}
            <ellipse cx="40" cy="42" rx="3.2" ry="4" />
            <circle cx="41.5" cy="40.5" r="1.2" fill="#ffffff" />
            {/* Right Eye */}
            <ellipse cx="60" cy="42" rx="3.2" ry="4" />
            <circle cx="61.5" cy="40.5" r="1.2" fill="#ffffff" />
            {/* Eyebrows */}
            <path d="M36 34 Q40 32 44 34" stroke="#1e1b4b" strokeWidth="1.8" strokeLinecap="round" fill="none" />
            <path d="M56 34 Q60 32 64 34" stroke="#1e1b4b" strokeWidth="1.8" strokeLinecap="round" fill="none" />
          </g>
        )}

        {/* Cheeks Blush */}
        <ellipse cx="33" cy="47" rx="4" ry="2.5" fill="#f87171" opacity="0.4" />
        <ellipse cx="67" cy="47" rx="4" ry="2.5" fill="#f87171" opacity="0.4" />

        {/* Nose & Smile */}
        <circle cx="50" cy="47" r="1.5" fill="#ea580c" opacity="0.5" />
        <path
          d="M45 52 Q50 56 55 52"
          stroke="#1e1b4b"
          strokeWidth="1.8"
          strokeLinecap="round"
          fill="none"
        />

        {/* Accessories */}
        {cfg.accessory === "badge" && (
          <g>
            <line x1="50" y1="72" x2="50" y2="86" stroke="#38bdf8" strokeWidth="1.8" strokeLinecap="round" />
            <rect x="46" y="84" width="8" height="9" rx="1.5" fill="#38bdf8" />
            <circle cx="50" cy="87" r="1.5" fill="#0f172a" />
          </g>
        )}
        {cfg.accessory === "glasses" && (
          <g stroke="#1e1b4b" strokeWidth="2" fill="none">
            <rect x="33" y="36" width="14" height="12" rx="3" stroke="#a78bfa" fill="rgba(167,139,250,0.15)" />
            <rect x="53" y="36" width="14" height="12" rx="3" stroke="#a78bfa" fill="rgba(167,139,250,0.15)" />
            <line x1="47" y1="42" x2="53" y2="42" stroke="#a78bfa" />
          </g>
        )}
        {cfg.accessory === "headphones" && (
          <g>
            <path d="M22 42 C22 24, 34 18, 50 18 C66 18, 78 24, 78 42" stroke="#10b981" strokeWidth="3" fill="none" strokeLinecap="round" />
            <rect x="20" y="36" width="6" height="14" rx="3" fill="#10b981" />
            <rect x="74" y="36" width="6" height="14" rx="3" fill="#10b981" />
          </g>
        )}
        {cfg.accessory === "visor" && (
          <path d="M30 38 Q50 34 70 38 L68 44 Q50 40 32 44 Z" fill="rgba(251,191,36,0.5)" stroke="#fbbf24" strokeWidth="1.5" />
        )}
        {cfg.accessory === "monocle" && (
          <g>
            <circle cx="60" cy="42" r="7" stroke="#38bdf8" strokeWidth="1.8" fill="rgba(56,189,248,0.2)" />
            <line x1="65" y1="47" x2="72" y2="60" stroke="#38bdf8" strokeWidth="1" />
          </g>
        )}
        {cfg.accessory === "antenna" && (
          <g>
            <line x1="50" y1="14" x2="50" y2="6" stroke="#fbbf24" strokeWidth="2" />
            <circle cx="50" cy="5" r="3" fill="#fbbf24" style={{ filter: "drop-shadow(0 0 4px #fbbf24)" }} />
          </g>
        )}
      </svg>

      {/* Mini Role Badge */}
      {(showBadge ?? (!hideBadge && size >= 26)) && (
        <span
          style={{
            position: "absolute",
            bottom: -2,
            right: -2,
            width: Math.max(14, Math.round(size * 0.3)),
            height: Math.max(14, Math.round(size * 0.3)),
            borderRadius: "50%",
            background: "var(--color-canvas-raised, #18182f)",
            border: `1.5px solid ${cfg.accentColor}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: Math.max(9, Math.round(size * 0.18)),
            boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
            userSelect: "none",
          }}
        >
          {badgeIcon}
        </span>
      )}
    </div>
  );
}
