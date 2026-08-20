"use client";

import React, { useRef, useState, useEffect } from "react";

interface MagneticCardProps {
  children: React.ReactNode;
  className?: string;
  tiltMaxAngle?: number; // Max tilt in deg
  glowColor?: string;
  liftAmount?: number; // translateZ lift in px
  style?: React.CSSProperties;
  onClick?: () => void;
}

/**
 * 3D Physics Magnetic Card.
 * Tilts dynamically based on cursor angle with spring-return physics,
 * elevation lift, and realistic specular light glare following the pointer.
 */
export default function MagneticCard({
  children,
  className = "",
  tiltMaxAngle = 12,
  glowColor = "rgba(167, 139, 250, 0.25)",
  liftAmount = 14,
  style = {},
  onClick,
}: MagneticCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [transform, setTransform] = useState("perspective(1000px) rotateX(0deg) rotateY(0deg) translateZ(0px)");
  const [glare, setGlare] = useState<{ x: number; y: number; opacity: number }>({
    x: 50,
    y: 50,
    opacity: 0,
  });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const card = cardRef.current;
    if (!card) return;

    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const centerX = rect.width / 2;
    const centerY = rect.height / 2;

    const rotateX = -((y - centerY) / centerY) * tiltMaxAngle;
    const rotateY = ((x - centerX) / centerX) * tiltMaxAngle;

    setTransform(
      `perspective(1000px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(
        2
      )}deg) translateZ(${liftAmount}px) scale3d(1.02, 1.02, 1.02)`
    );

    const glareX = (x / rect.width) * 100;
    const glareY = (y / rect.height) * 100;

    setGlare({
      x: glareX,
      y: glareY,
      opacity: 0.65,
    });
  };

  const handleMouseLeave = () => {
    setTransform("perspective(1000px) rotateX(0deg) rotateY(0deg) translateZ(0px) scale3d(1, 1, 1)");
    setGlare(prev => ({ ...prev, opacity: 0 }));
  };

  return (
    <div
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      onClick={onClick}
      className={className}
      style={{
        position: "relative",
        transformStyle: "preserve-3d",
        transform,
        transition: "transform 0.18s cubic-bezier(0.23, 1, 0.32, 1), box-shadow 0.25s ease",
        willChange: "transform",
        ...style,
      }}
    >
      {children}

      {/* Dynamic Specular Light Glare following cursor physics */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          borderRadius: "inherit",
          pointerEvents: "none",
          background: `radial-gradient(circle at ${glare.x}% ${glare.y}%, ${glowColor} 0%, transparent 65%)`,
          opacity: glare.opacity,
          transition: "opacity 0.25s ease",
          mixBlendMode: "screen",
          zIndex: 2,
        }}
      />
    </div>
  );
}
