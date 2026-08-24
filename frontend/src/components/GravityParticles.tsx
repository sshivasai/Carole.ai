"use client";

import React, { useRef, useEffect } from "react";

interface AgentParticle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  baseRadius: number;
  mass: number;
  color: string;
  glowColor: string;

  // Blinking animation states
  blinkTimer: number;
  nextBlinkTime: number;
  blinkDuration: number;
  isBlinking: boolean;
  blinkProgress: number; // 0 = open, 1 = closed (arc)

  // Floating bobbing
  floatAngle: number;
  floatSpeed: number;
}

interface GravityParticlesProps {
  particleCount?: number;
  connectionDistance?: number;
  mouseRadius?: number;
  repelStrength?: number;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Interactive Anti-Gravity Canvas with Floating Blinking Agent Spheres.
 * Dense, rich distribution of small, delicate mascot agent spheres floating across the viewport
 * with realistic zero-g physics, glowing micro-eyes, and natural periodic blinking.
 */
export default function GravityParticles({
  particleCount = 88,
  connectionDistance = 125,
  mouseRadius = 170,
  repelStrength = 4.5,
  className = "",
  style = {},
}: GravityParticlesProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mouseRef = useRef<{ x: number; y: number; active: boolean }>({
    x: -1000,
    y: -1000,
    active: false,
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let width = (canvas.width = canvas.offsetWidth);
    let height = (canvas.height = canvas.offsetHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = canvas.offsetWidth;
      height = canvas.height = canvas.offsetHeight;
    };

    window.addEventListener("resize", handleResize);

    const themeColors = [
      { eye: "#c084fc", glow: "rgba(192, 132, 252, 0.85)" }, // Signature Purple
      { eye: "#38bdf8", glow: "rgba(56, 189, 248, 0.85)" },  // Cyber Cyan
      { eye: "#a78bfa", glow: "rgba(167, 139, 250, 0.85)" }, // Soft Lavender
      { eye: "#34d399", glow: "rgba(52, 211, 153, 0.85)" },  // Emerald
      { eye: "#f472b6", glow: "rgba(244, 114, 182, 0.85)" }, // Rose Pink
    ];

    const particles: AgentParticle[] = [];
    for (let i = 0; i < particleCount; i++) {
      const palette = themeColors[Math.floor(Math.random() * themeColors.length)];
      // Small delicate radius (2.8px to 5.2px) matching original particle scale
      const baseR = Math.random() * 2.4 + 2.8;

      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.7,
        vy: (Math.random() - 0.5) * 0.7 - 0.12, // Subtle upward zero-g drift
        radius: baseR,
        baseRadius: baseR,
        mass: Math.random() * 0.7 + 0.6,
        color: palette.eye,
        glowColor: palette.glow,

        blinkTimer: 0,
        nextBlinkTime: Math.floor(Math.random() * 200 + 60),
        blinkDuration: 16,
        isBlinking: false,
        blinkProgress: 0,

        floatAngle: Math.random() * Math.PI * 2,
        floatSpeed: Math.random() * 0.02 + 0.01,
      });
    }

    const onMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      mouseRef.current.x = e.clientX - rect.left;
      mouseRef.current.y = e.clientY - rect.top;
      mouseRef.current.active = true;
    };

    const onMouseLeave = () => {
      mouseRef.current.active = false;
    };

    window.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseleave", onMouseLeave);

    const render = () => {
      ctx.clearRect(0, 0, width, height);
      const mouse = mouseRef.current;

      // 1. Draw subtle constellation lines between close agent particles
      for (let i = 0; i < particles.length; i++) {
        const p1 = particles[i];
        for (let j = i + 1; j < particles.length; j++) {
          const p2 = particles[j];
          const cdx = p1.x - p2.x;
          const cdy = p1.y - p2.y;
          const cdist = Math.sqrt(cdx * cdx + cdy * cdy);

          if (cdist < connectionDistance) {
            const lineAlpha = (1 - cdist / connectionDistance) * 0.16;
            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.strokeStyle = `rgba(167, 139, 250, ${lineAlpha})`;
            ctx.lineWidth = 0.75;
            ctx.stroke();
          }
        }
      }

      // 2. Update & Draw Mascot Agent Spheres
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];

        // --- Physics & Cursor Repulsion ---
        if (mouse.active) {
          const dx = p.x - mouse.x;
          const dy = p.y - mouse.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < mouseRadius && dist > 0) {
            const force = (1 - dist / mouseRadius) * repelStrength;
            const angle = Math.atan2(dy, dx);

            p.vx += (Math.cos(angle) * force * 0.35) / p.mass;
            p.vy += (Math.sin(angle) * force * 0.35 - force * 0.2) / p.mass;
            p.radius = p.baseRadius * (1 + force * 0.3);

            if (!p.isBlinking && Math.random() < 0.05) {
              p.isBlinking = true;
              p.blinkTimer = 0;
            }
          } else {
            p.radius += (p.baseRadius - p.radius) * 0.1;
          }
        } else {
          p.radius += (p.baseRadius - p.radius) * 0.1;
        }

        p.vx *= 0.96;
        p.vy *= 0.96;
        p.floatAngle += p.floatSpeed;
        p.x += p.vx + Math.sin(p.floatAngle) * 0.15;
        p.y += p.vy + Math.cos(p.floatAngle * 0.7) * 0.15;

        // Screen wrap-around with soft margin
        if (p.x < -12) p.x = width + 12;
        if (p.x > width + 12) p.x = -12;
        if (p.y < -12) p.y = height + 12;
        if (p.y > height + 12) p.y = -12;

        // --- Blinking Logic ---
        p.blinkTimer++;
        if (!p.isBlinking && p.blinkTimer >= p.nextBlinkTime) {
          p.isBlinking = true;
          p.blinkTimer = 0;
        }

        if (p.isBlinking) {
          const half = p.blinkDuration / 2;
          if (p.blinkTimer < half) {
            p.blinkProgress = p.blinkTimer / half;
          } else if (p.blinkTimer < p.blinkDuration) {
            p.blinkProgress = 1 - (p.blinkTimer - half) / half;
          } else {
            p.isBlinking = false;
            p.blinkProgress = 0;
            p.blinkTimer = 0;
            p.nextBlinkTime = Math.floor(Math.random() * 220 + 80);
          }
        }

        const r = p.radius;
        const x = p.x;
        const y = p.y;

        // --- Interactive Eye-Tracking Offset ---
        let eyeLookX = 0;
        let eyeLookY = 0;
        if (mouse.active) {
          const mdx = mouse.x - x;
          const mdy = mouse.y - y;
          const mdist = Math.sqrt(mdx * mdx + mdy * mdy);
          if (mdist > 0) {
            const maxLook = r * 0.16;
            eyeLookX = (mdx / mdist) * Math.min(maxLook, mdist * 0.04);
            eyeLookY = (mdy / mdist) * Math.min(maxLook, mdist * 0.04);
          }
        }

        // --- DRAW COMPACT AGENT MASCOT SPHERE ---

        // 1. Ambient Halo Glow
        ctx.save();
        ctx.beginPath();
        ctx.arc(x, y, r * 1.5, 0, Math.PI * 2);
        const haloGrad = ctx.createRadialGradient(x, y, r * 0.4, x, y, r * 1.5);
        haloGrad.addColorStop(0, p.glowColor.replace("0.85", "0.35"));
        haloGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
        ctx.fillStyle = haloGrad;
        ctx.fill();

        // 2. Glossy Dark Sphere Body (Spherical 3D Light)
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        const bodyGrad = ctx.createRadialGradient(
          x - r * 0.3,
          y - r * 0.35,
          r * 0.1,
          x,
          y,
          r
        );
        bodyGrad.addColorStop(0, "#2c2f54");
        bodyGrad.addColorStop(0.4, "#14152b");
        bodyGrad.addColorStop(0.85, "#080916");
        bodyGrad.addColorStop(1, "#03040a");
        ctx.fillStyle = bodyGrad;
        ctx.shadowColor = p.glowColor;
        ctx.shadowBlur = r * 1.4;
        ctx.fill();
        ctx.restore();

        // 3. Draw Glowing Micro-Eyes
        const eyeRadius = Math.max(0.7, r * 0.22);
        const eyeSpacing = r * 0.33;
        const eyeBaseY = y - r * 0.04 + eyeLookY;

        const leftEyeX = x - eyeSpacing + eyeLookX;
        const rightEyeX = x + eyeSpacing + eyeLookX;

        ctx.save();
        ctx.shadowColor = p.glowColor;
        ctx.shadowBlur = eyeRadius * 3.5;

        if (p.blinkProgress > 0.4) {
          // --- Blinking State: Micro Smile Arcs (◡  ◡) ---
          ctx.strokeStyle = p.color;
          ctx.lineWidth = Math.max(1.0, eyeRadius * 0.7);
          ctx.lineCap = "round";

          // Left Eye Arc
          ctx.beginPath();
          ctx.arc(
            leftEyeX,
            eyeBaseY - eyeRadius * 0.2,
            eyeRadius * 0.9,
            0.15 * Math.PI,
            0.85 * Math.PI,
            false
          );
          ctx.stroke();

          // Right Eye Arc
          ctx.beginPath();
          ctx.arc(
            rightEyeX,
            eyeBaseY - eyeRadius * 0.2,
            eyeRadius * 0.9,
            0.15 * Math.PI,
            0.85 * Math.PI,
            false
          );
          ctx.stroke();
        } else {
          // --- Open State: Glowing Micro-Dots (●  ●) ---
          const currentEyeR = eyeRadius * (1 - p.blinkProgress * 0.7);

          // Left Eye
          ctx.beginPath();
          ctx.arc(leftEyeX, eyeBaseY, currentEyeR, 0, Math.PI * 2);
          ctx.fillStyle = p.color;
          ctx.fill();

          // Right Eye
          ctx.beginPath();
          ctx.arc(rightEyeX, eyeBaseY, currentEyeR, 0, Math.PI * 2);
          ctx.fillStyle = p.color;
          ctx.fill();
        }

        ctx.restore();
      }

      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseleave", onMouseLeave);
    };
  }, [particleCount, connectionDistance, mouseRadius, repelStrength]);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        zIndex: 0,
        ...style,
      }}
    />
  );
}
