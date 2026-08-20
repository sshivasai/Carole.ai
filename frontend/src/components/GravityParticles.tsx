"use client";

import React, { useRef, useEffect } from "react";

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  baseRadius: number;
  color: string;
  alpha: number;
  mass: number;
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
 * Interactive Anti-Gravity Canvas Physics Background.
 * Particles float in zero-g, repel dynamically from cursor with momentum & spring damping,
 * and form luminous constellation lines with neighboring particles.
 */
export default function GravityParticles({
  particleCount = 55,
  connectionDistance = 120,
  mouseRadius = 160,
  repelStrength = 4,
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

    const colors = [
      "rgba(167, 139, 250, ", // Primary Purple
      "rgba(56, 189, 248, ",  // Cyan
      "rgba(129, 140, 248, ", // Indigo
      "rgba(244, 114, 182, ", // Rose
      "rgba(16, 185, 129, ",  // Emerald
    ];

    const particles: Particle[] = [];
    for (let i = 0; i < particleCount; i++) {
      const colorPrefix = colors[Math.floor(Math.random() * colors.length)];
      const baseR = Math.random() * 2 + 1.2;
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.7,
        vy: (Math.random() - 0.5) * 0.7 - 0.15, // Subtle upward zero-g drift
        radius: baseR,
        baseRadius: baseR,
        color: colorPrefix,
        alpha: Math.random() * 0.45 + 0.25,
        mass: Math.random() * 0.8 + 0.6,
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

      // Update & Draw Particles
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];

        // Zero-G Physics: Cursor Repulsion & Anti-Gravity Lift
        if (mouse.active) {
          const dx = p.x - mouse.x;
          const dy = p.y - mouse.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < mouseRadius && dist > 0) {
            const force = (1 - dist / mouseRadius) * repelStrength;
            const angle = Math.atan2(dy, dx);
            
            // Push particle away and lift slightly upward
            p.vx += (Math.cos(angle) * force * 0.35) / p.mass;
            p.vy += (Math.sin(angle) * force * 0.35 - force * 0.2) / p.mass;
            p.radius = p.baseRadius * (1 + force * 0.5);
          } else {
            p.radius += (p.baseRadius - p.radius) * 0.1;
          }
        } else {
          p.radius += (p.baseRadius - p.radius) * 0.1;
        }

        // Friction / Air resistance damping
        p.vx *= 0.96;
        p.vy *= 0.96;

        // Maintain ambient cosmic drift
        p.vx += (Math.random() - 0.5) * 0.04;
        p.vy += (Math.random() - 0.5) * 0.04 - 0.01;

        p.x += p.vx;
        p.y += p.vy;

        // Screen wrap-around with soft edge bounce
        if (p.x < -10) p.x = width + 10;
        if (p.x > width + 10) p.x = -10;
        if (p.y < -10) p.y = height + 10;
        if (p.y > height + 10) p.y = -10;

        // Draw particle glow orb
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = `${p.color}${p.alpha})`;
        ctx.shadowBlur = p.radius * 3;
        ctx.shadowColor = `${p.color}0.8)`;
        ctx.fill();

        // Connect particles with spring constellation lines
        for (let j = i + 1; j < particles.length; j++) {
          const p2 = particles[j];
          const cdx = p.x - p2.x;
          const cdy = p.y - p2.y;
          const cdist = Math.sqrt(cdx * cdx + cdy * cdy);

          if (cdist < connectionDistance) {
            const lineAlpha = (1 - cdist / connectionDistance) * 0.18;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.strokeStyle = `rgba(167, 139, 250, ${lineAlpha})`;
            ctx.lineWidth = 0.8;
            ctx.stroke();
          }
        }
      }

      ctx.shadowBlur = 0;
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
