"use client";

import React, { useState, useEffect } from "react";

export type CaroleLogoVariant = "mark" | "horizontal" | "full";
export type CaroleLogoState = "idle" | "awake" | "sleeping" | "thinking";

interface CaroleLogoProps {
  variant?: CaroleLogoVariant;
  state?: CaroleLogoState;
  size?: number;
  animated?: boolean;
  className?: string;
  style?: React.CSSProperties;
  onClick?: () => void;
}

export default function CaroleLogo({
  variant = "mark",
  state = "idle",
  size = 32,
  animated = true,
  className = "",
  style = {},
  onClick,
}: CaroleLogoProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [isSleeping, setIsSleeping] = useState(state === "sleeping");

  useEffect(() => {
    setIsSleeping(state === "sleeping");
  }, [state]);

  // Determine image source based on state and variant
  const getSrc = () => {
    if (state === "sleeping" || isSleeping) {
      if (variant === "full") return "/branding/logo-full-closed.png";
      if (variant === "horizontal") return "/branding/logo-horizontal-closed.png";
      return "/branding/logo-mark-closed.png";
    }

    if (state === "awake" || !animated) {
      if (variant === "full") return "/branding/logo-full.png";
      if (variant === "horizontal") return "/branding/logo-horizontal.png";
      return "/branding/logo-mark.png";
    }

    // Animated looping (blinking naturally)
    if (variant === "full") return "/branding/logo-full-animated.webp";
    if (variant === "horizontal") return "/branding/logo-horizontal-animated.webp";
    return "/branding/logo-mark-animated.webp";
  };

  // Dimensions
  let width = size;
  let height = size;

  if (variant === "horizontal") {
    width = Math.round(size * 3.62); // 869/240 ratio
    height = size;
  } else if (variant === "full") {
    width = size;
    height = Math.round(size * 0.95);
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
            background: "radial-gradient(circle, rgba(0, 217, 146, 0.45) 0%, rgba(0, 217, 146, 0) 70%)",
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
            ? "drop-shadow(0 0 12px rgba(0, 217, 146, 0.6))"
            : "drop-shadow(0 0 8px rgba(0, 217, 146, 0.3))",
          transform: isHovered ? "scale(1.04)" : "scale(1)",
          transition: "transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), filter 0.2s ease",
        }}
      />
    </div>
  );
}
