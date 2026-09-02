"use client";

import React, { useEffect, useRef } from "react";
import { useTheme } from "@/hooks/useTheme";

interface ConvergingLinesProps {
  lineCount?: number;
  className?: string;
  style?: React.CSSProperties;
}

// Optimized distance from point (px, py) to line segment (x1, y1)-(x2, y2)
function distanceToSegment(
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number
): { dist: number; t: number } {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) {
    return { dist: Math.hypot(px - x1, py - y1), t: 0 };
  }
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lenSq));
  const projX = x1 + t * dx;
  const projY = y1 + t * dy;
  return { dist: Math.hypot(px - projX, py - projY), t };
}

export default function ConvergingLines({
  lineCount = 44,
  className,
  style,
}: ConvergingLinesProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const { theme } = useTheme();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    // Focal convergence point (tracks pointer with smooth damping)
    let targetX = width * 0.5;
    let targetY = height * 0.38;
    let currentX = width * 0.5;
    let currentY = height * 0.38;
    let isHovering = false;

    // Mouse velocity & position tracking
    let mouseX = width * 0.5;
    let mouseY = height * 0.38;
    let lastMouseX = mouseX;
    let lastMouseY = mouseY;
    let mouseVx = 0;
    let mouseVy = 0;

    const handleResize = () => {
      if (!canvas) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.scale(dpr, dpr);
    };

    handleResize();
    window.addEventListener("resize", handleResize);

    const handleMouseMove = (e: MouseEvent) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
      targetX = mouseX;
      targetY = mouseY;
      isHovering = true;
    };

    const handleMouseLeave = () => {
      isHovering = false;
      targetX = width * 0.5;
      targetY = height * 0.38;
      mouseVx = 0;
      mouseVy = 0;
    };

    window.addEventListener("mousemove", handleMouseMove, { passive: true });
    window.addEventListener("mouseleave", handleMouseLeave);

    // Tensile Rod Physics State
    interface TensileRod {
      sx: number; // Source boundary X
      sy: number; // Source boundary Y
      cx: number; // Control point X
      cy: number; // Control point Y
      vx: number; // Control point velocity X
      vy: number; // Control point velocity Y
    }

    let rods: TensileRod[] = [];

    const initRods = () => {
      rods = [];
      const perimeter = 2 * (width + height);
      const step = perimeter / lineCount;

      for (let i = 0; i < lineCount; i++) {
        const dist = i * step;
        let sx = 0;
        let sy = 0;

        if (dist < width) {
          sx = dist;
          sy = 0;
        } else if (dist < width + height) {
          sx = width;
          sy = dist - width;
        } else if (dist < 2 * width + height) {
          sx = width - (dist - width - height);
          sy = height;
        } else {
          sx = 0;
          sy = height - (dist - 2 * width - height);
        }

        const midX = (sx + currentX) * 0.5;
        const midY = (sy + currentY) * 0.5;

        rods.push({
          sx,
          sy,
          cx: midX,
          cy: midY,
          vx: 0,
          vy: 0,
        });
      }
    };

    initRods();

    // Pulse wave particles moving along tensile rods
    interface Pulse {
      rodIndex: number;
      progress: number;
      speed: number;
      size: number;
    }

    const pulses: Pulse[] = Array.from({ length: 26 }, () => ({
      rodIndex: Math.floor(Math.random() * lineCount),
      progress: Math.random(),
      speed: 0.003 + Math.random() * 0.005,
      size: 1.5 + Math.random() * 2,
    }));

    // Spring-mass physics parameters (elastic tensile rod simulation)
    const springK = 0.09; // Hooke's spring restoration constant
    const damping = 0.88; // Damping ratio for smooth oscillation & fast straight settle
    const influenceRadius = 220; // Radius where cursor movement deflects rods

    const render = () => {
      // Calculate mouse velocity
      mouseVx = (mouseX - lastMouseX) * 0.85;
      mouseVy = (mouseY - lastMouseY) * 0.85;
      lastMouseX = mouseX;
      lastMouseY = mouseY;

      const speed = Math.hypot(mouseVx, mouseVy);

      // Smooth lerp of convergence focal point towards cursor
      const lerpFactor = isHovering ? 0.08 : 0.03;
      currentX += (targetX - currentX) * lerpFactor;
      currentY += (targetY - currentY) * lerpFactor;

      ctx.clearRect(0, 0, width, height);

      const isDark =
        theme === "dark" || document.documentElement.classList.contains("dark");

      // Dynamic theme color palette (+10% visibility enhancement)
      const baseLineColor = isDark
        ? "rgba(167, 139, 250, 0.065)"
        : "rgba(99, 102, 241, 0.075)";
      const focalLineColor = isDark
        ? "rgba(167, 139, 250, 0.18)"
        : "rgba(79, 70, 229, 0.20)";
      const pulseColor = isDark
        ? "rgba(192, 132, 252, 0.50)"
        : "rgba(99, 102, 241, 0.50)";
      const ringColor = isDark
        ? "rgba(167, 139, 250, 0.038)"
        : "rgba(99, 102, 241, 0.048)";

      // Draw perspective rings around focal convergence
      const ringRadii = [60, 130, 220, 340, 500, 700];
      for (const r of ringRadii) {
        ctx.beginPath();
        ctx.arc(currentX, currentY, r, 0, Math.PI * 2);
        ctx.strokeStyle = ringColor;
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // Physics update & render for each tensile rod
      for (let i = 0; i < rods.length; i++) {
        const rod = rods[i];

        // Straight baseline midpoint (where the straight rod rests)
        const restX = (rod.sx + currentX) * 0.5;
        const restY = (rod.sy + currentY) * 0.5;

        // Mouse deflection impulse (plucking & bending the rod)
        if (speed > 0.4) {
          const { dist } = distanceToSegment(
            mouseX,
            mouseY,
            rod.sx,
            rod.sy,
            currentX,
            currentY
          );

          if (dist < influenceRadius) {
            const influence = Math.pow(1 - dist / influenceRadius, 1.8);
            // Push rod in the direction of mouse movement with lateral bowing
            rod.vx += mouseVx * influence * 0.42;
            rod.vy += mouseVy * influence * 0.42;
          }
        }

        // Spring restoration force pulling control point back to straight rest position
        const dispX = rod.cx - restX;
        const dispY = rod.cy - restY;

        const springForceX = -springK * dispX;
        const springForceY = -springK * dispY;

        // Integrate velocity with damping
        rod.vx = (rod.vx + springForceX) * damping;
        rod.vy = (rod.vy + springForceY) * damping;

        rod.cx += rod.vx;
        rod.cy += rod.vy;

        const deflection = Math.hypot(dispX, dispY);

        // Draw the tensile rod Bezier curve with constant, uniform color
        const grad = ctx.createLinearGradient(
          rod.sx,
          rod.sy,
          currentX,
          currentY
        );
        grad.addColorStop(0, baseLineColor);
        grad.addColorStop(0.75, focalLineColor);
        grad.addColorStop(1, "rgba(255, 255, 255, 0.02)");

        ctx.beginPath();
        ctx.moveTo(rod.sx, rod.sy);
        ctx.quadraticCurveTo(rod.cx, rod.cy, currentX, currentY);
        ctx.strokeStyle = grad;
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // Draw traveling pulse packets along deformed tensile rods
      for (const p of pulses) {
        p.progress += p.speed;
        if (p.progress > 1) {
          p.progress = 0;
          p.rodIndex = Math.floor(Math.random() * rods.length);
        }

        const rod = rods[p.rodIndex] || rods[0];
        const t = p.progress;

        // Quadratic Bezier point calculation along the actual bent rod
        const px =
          (1 - t) * (1 - t) * rod.sx +
          2 * (1 - t) * t * rod.cx +
          t * t * currentX;
        const py =
          (1 - t) * (1 - t) * rod.sy +
          2 * (1 - t) * t * rod.cy +
          t * t * currentY;

        ctx.beginPath();
        ctx.arc(px, py, p.size * (1 - t * 0.25), 0, Math.PI * 2);
        ctx.fillStyle = pulseColor;
        ctx.shadowColor = isDark ? "#a78bfa" : "#6366f1";
        ctx.shadowBlur = 6;
        ctx.fill();
        ctx.shadowBlur = 0;
      }

      // Soft focal convergence glow
      const focalGlow = ctx.createRadialGradient(
        currentX,
        currentY,
        0,
        currentX,
        currentY,
        45
      );
      focalGlow.addColorStop(
        0,
        isDark ? "rgba(167, 139, 250, 0.22)" : "rgba(99, 102, 241, 0.20)"
      );
      focalGlow.addColorStop(1, "transparent");

      ctx.beginPath();
      ctx.arc(currentX, currentY, 45, 0, Math.PI * 2);
      ctx.fillStyle = focalGlow;
      ctx.fill();

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseleave", handleMouseLeave);
    };
  }, [lineCount, theme]);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{
        position: "fixed",
        inset: 0,
        pointerEvents: "none",
        zIndex: 0,
        width: "100vw",
        height: "100vh",
        ...style,
      }}
    />
  );
}
