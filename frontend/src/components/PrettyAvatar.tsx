"use client";

import React from "react";
import { Crown, Code2, Shield, Brain, CheckCircle2, Bot, Palette, LineChart } from "lucide-react";

export type PrettyAvatarPreset = 
  | "archer"
  | "coder"
  | "judge"
  | "researcher"
  | "qa"
  | "subagent"
  | "designer"
  | "analyst";

interface PrettyAvatarProps {
  preset?: PrettyAvatarPreset;
  name?: string;
  size?: number;
  isWorking?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Beautiful SVG Character Avatars inspired by PrettyAvatars.com
 * Vector-sharp, themed palettes, expressive facial features, accessories, and glowing aura.
 */
export default function PrettyAvatar({
  preset = "archer",
  name = "Agent",
  size = 64,
  isWorking = false,
  className = "",
  style = {},
}: PrettyAvatarProps) {
  // Determine color theme & avatar elements based on preset or name
  const getAvatarConfig = () => {
    const iconSize = Math.max(10, Math.round(size * 0.18));
    switch (preset) {
      case "archer": // Swarm Coordinator (Purple / Violet)
        return {
          bgGrad: ["#8b5cf6", "#6d28d9"],
          skin: "#fed7aa",
          hair: "#312e81",
          hairType: "stylish",
          eyes: "focused",
          accessory: "glasses",
          accentColor: "#a78bfa",
          badgeIcon: <Crown size={iconSize} color="#a78bfa" />,
        };
      case "coder": // Full-stack Engineer (Emerald / Teal)
        return {
          bgGrad: ["#10b981", "#047857"],
          skin: "#ffedd5",
          hair: "#0f172a",
          hairType: "curly",
          eyes: "tech",
          accessory: "headphones",
          accentColor: "#34d399",
          badgeIcon: <Code2 size={iconSize} color="#34d399" />,
        };
      case "judge": // Security Gate / Judge AI (Gold / Amber)
        return {
          bgGrad: ["#f59e0b", "#b45309"],
          skin: "#fde68a",
          hair: "#78350f",
          hairType: "sleek",
          eyes: "laser",
          accessory: "visor",
          accentColor: "#fbbf24",
          badgeIcon: <Shield size={iconSize} color="#fbbf24" />,
        };
      case "researcher": // Intelligence & GraphRAG (Sky Blue)
        return {
          bgGrad: ["#38bdf8", "#0284c7"],
          skin: "#fed7aa",
          hair: "#1e3a8a",
          hairType: "wavy",
          eyes: "curious",
          accessory: "monocle",
          accentColor: "#7dd3fc",
          badgeIcon: <Brain size={iconSize} color="#7dd3fc" />,
        };
      case "qa": // Playwright / QA Runner (Rose / Pink)
        return {
          bgGrad: ["#f43f5e", "#be123c"],
          skin: "#fecdd3",
          hair: "#881337",
          hairType: "bun",
          eyes: "sharp",
          accessory: "earpiece",
          accentColor: "#fda4af",
          badgeIcon: <CheckCircle2 size={iconSize} color="#fda4af" />,
        };
      case "subagent": // Temporary Guarded Subagent (Amber / Gold)
        return {
          bgGrad: ["#fbbf24", "#d97706"],
          skin: "#ffedd5",
          hair: "#451a03",
          hairType: "spiky",
          eyes: "robot",
          accessory: "antenna",
          accentColor: "#f59e0b",
          badgeIcon: <Bot size={iconSize} color="#f59e0b" />,
        };
      case "designer":
        return {
          bgGrad: ["#ec4899", "#be185d"],
          skin: "#fde68a",
          hair: "#831843",
          hairType: "stylish",
          eyes: "curious",
          accessory: "glasses",
          accentColor: "#f472b6",
          badgeIcon: <Palette size={iconSize} color="#f472b6" />,
        };
      case "analyst":
      default:
        return {
          bgGrad: ["#6366f1", "#4338ca"],
          skin: "#fed7aa",
          hair: "#1e1b4b",
          hairType: "sleek",
          eyes: "focused",
          accessory: "glasses",
          accentColor: "#818cf8",
          badgeIcon: <LineChart size={iconSize} color="#818cf8" />,
        };
    }
  };

  const cfg = getAvatarConfig();

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
        boxShadow: `0 8px 24px ${cfg.bgGrad[0]}40`,
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
          <radialGradient id={`glow-${preset}`} cx="50%" cy="30%" r="60%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
          </radialGradient>
          <linearGradient id={`skin-${preset}`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={cfg.skin} />
            <stop offset="100%" stopColor="#fca5a5" stopOpacity="0.8" />
          </linearGradient>
        </defs>

        {/* Ambient Top Light */}
        <circle cx="50" cy="50" r="50" fill={`url(#glow-${preset})`} />

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
        <rect x="43" y="54" width="14" height="16" rx="4" fill={`url(#skin-${preset})`} />

        {/* Head Base */}
        <ellipse cx="50" cy="42" rx="22" ry="24" fill={`url(#skin-${preset})`} />

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
      <span
        style={{
          position: "absolute",
          bottom: -2,
          right: -2,
          width: Math.max(18, Math.round(size * 0.3)),
          height: Math.max(18, Math.round(size * 0.3)),
          borderRadius: "50%",
          background: "var(--color-canvas-raised, #18182f)",
          border: `1.5px solid ${cfg.accentColor}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: Math.max(10, Math.round(size * 0.18)),
          boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
          userSelect: "none",
        }}
      >
        {cfg.badgeIcon}
      </span>
    </div>
  );
}
