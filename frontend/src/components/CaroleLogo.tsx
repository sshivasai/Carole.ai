"use client";

import React, { useState, useEffect } from "react";
import { useTheme } from "../hooks/useTheme";

export type CaroleLogoVariant = "mark" | "horizontal" | "full" | "wordmark" | "name";
export type CaroleLogoState = "idle" | "awake" | "sleeping" | "thinking";

interface CaroleLogoProps {
  variant?: CaroleLogoVariant;
  state?: CaroleLogoState;
  theme?: "light" | "dark";
  size?: number;
  animated?: boolean;
  className?: string;
  style?: React.CSSProperties;
  onClick?: () => void;
}

export default function CaroleLogo({
  variant = "mark",
  state = "idle",
  theme: explicitTheme,
  size = 32,
  animated = true,
  className = "",
  style = {},
  onClick,
}: CaroleLogoProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [isSleeping, setIsSleeping] = useState(state === "sleeping");
  
  let hookTheme = "light";
  try {
    const ctx = useTheme();
    if (ctx?.theme) hookTheme = ctx.theme;
  } catch {
    // fallback if outside ThemeProvider
  }

  const effectiveTheme = explicitTheme || hookTheme || "light";

  useEffect(() => {
    setIsSleeping(state === "sleeping");
  }, [state]);

  // Determine image source based on state, variant, and theme
  const getSrc = () => {
    const isDark = effectiveTheme === "dark";
    const sfx = isDark ? "-dark" : "";

    if (variant === "wordmark") return `/branding/logo-wordmark${sfx}.png`;
    if (variant === "name") return `/branding/logo-name${sfx}.png`;

    if (state === "sleeping" || isSleeping) {
      if (variant === "full") return `/branding/logo-full${sfx}-closed.png`;
      if (variant === "horizontal") return `/branding/logo-horizontal${sfx}-closed.png`;
      return "/branding/logo-mark-closed.png";
    }

    if (state === "awake" || !animated) {
      if (variant === "full") return `/branding/logo-full${sfx}.png`;
      if (variant === "horizontal") return `/branding/logo-horizontal${sfx}.png`;
      return "/branding/logo-mark.png";
    }

    // Animated looping (blinking naturally)
    if (variant === "full") return `/branding/logo-full${sfx}-animated.webp`;
    if (variant === "horizontal") return `/branding/logo-horizontal${sfx}-animated.webp`;
    return "/branding/logo-mark-animated.webp";
  };

  // Dimensions
  let width = size;
  let height = size;

  if (variant === "horizontal") {
    width = Math.round(size * 2.84); // 660/232 ratio
    height = size;
  } else if (variant === "full") {
    width = size;
    height = Math.round(size * 0.95); // 710/747 ratio
  } else if (variant === "wordmark") {
    height = size;
    width = Math.round(size * 3.58); // 691/193 ratio
  } else if (variant === "name") {
    height = size;
    width = Math.round(size * 5.32); // 691/130 ratio
  }

  const isThinking = state === "thinking";

  return (
    <div
      className={`carole-logo-root ${isThinking ? "carole-logo-thinking" : ""} ${className}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
        cursor: onClick ? "pointer" : "default",
        userSelect: "none",
        ...style,
      }}
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Ambient Thinking / Breathing Aura */}
      {isThinking && (
        <div
          style={{
            position: "absolute",
            width: size * 1.3,
            height: size * 1.3,
            borderRadius: "50%",
            background: "radial-gradient(circle, rgba(131, 118, 244, 0.45) 0%, rgba(131, 118, 244, 0) 70%)",
            animation: "pulse 1.6s ease-in-out infinite",
            pointerEvents: "none",
            filter: "blur(4px)",
            zIndex: 0,
          }}
        />
      )}

      {/* Main Logo Image */}
      <img
        src={getSrc()}
        alt="Carole.ai Logo"
        width={width}
        height={height}
        style={{
          width: width,
          height: height,
          objectFit: "contain",
          position: "relative",
          zIndex: 1,
          filter: isHovered
            ? "drop-shadow(0 0 12px rgba(131, 118, 244, 0.6))"
            : "drop-shadow(0 0 8px rgba(131, 118, 244, 0.3))",
          transform: isHovered ? "scale(1.04)" : "scale(1)",
          transition: "transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), filter 0.2s ease",
        }}
      />
    </div>
  );
}
