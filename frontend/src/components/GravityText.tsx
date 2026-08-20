"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";

interface GravityTextProps {
  text: string;
  className?: string;
  isGradient?: boolean;
  gravityStrength?: number; // Repulsion / Anti-gravity pull force
  radius?: number; // Radius of mouse influence in px
  style?: React.CSSProperties;
}

interface PhysicsLetter {
  char: string;
  id: number;
  wordIndex: number;
  offsetX: number;
  offsetY: number;
  rotate: number;
  scale: number;
}

/**
 * Interactive Anti-Gravity Physics Typography Component.
 * Letters float upwards against gravity when mouse approaches, and gently settle
 * back into place with elastic spring damping physics when the cursor moves away.
 */
export default function GravityText({
  text,
  className = "",
  isGradient = false,
  gravityStrength = 32,
  radius = 160,
  style = {},
}: GravityTextProps) {
  const containerRef = useRef<HTMLSpanElement>(null);
  const letterRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const mousePos = useRef<{ x: number; y: number } | null>(null);
  const isHovered = useRef(false);
  const [offsets, setOffsets] = useState<{ x: number; y: number; r: number; s: number }[]>([]);

  // Split text into words and characters
  const words = useMemo(() => text.split(" "), [text]);
  const chars = useMemo(() => text.split(""), [text]);

  useEffect(() => {
    setOffsets(chars.map(() => ({ x: 0, y: 0, r: 0, s: 1 })));
    letterRefs.current = letterRefs.current.slice(0, chars.length);
  }, [chars]);

  // RequestAnimationFrame physics simulation loop
  useEffect(() => {
    let animId: number;
    const currentOffsets = chars.map(() => ({ x: 0, y: 0, r: 0, s: 1, vx: 0, vy: 0, vr: 0 }));

    const simulate = () => {
      const mouse = mousePos.current;

      letterRefs.current.forEach((el, i) => {
        if (!el) return;
        const cur = currentOffsets[i];
        if (!cur) return;

        let targetX = 0;
        let targetY = 0;
        let targetR = 0;
        let targetS = 1;

        if (mouse && isHovered.current) {
          const rect = el.getBoundingClientRect();
          const letterCenterX = rect.left + rect.width / 2;
          const letterCenterY = rect.top + rect.height / 2;

          const dx = letterCenterX - mouse.x;
          const dy = letterCenterY - mouse.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < radius) {
            // Anti-gravity repulsion force: closer cursor = higher upward float
            const force = (1 - dist / radius);
            const angle = Math.atan2(dy, dx);

            // Deflect outward and lift upward against gravity (negative Y bias)
            targetX = Math.cos(angle) * force * gravityStrength;
            targetY = Math.sin(angle) * force * gravityStrength - (force * gravityStrength * 0.8);
            targetR = (dx > 0 ? 1 : -1) * force * 18;
            targetS = 1 + force * 0.18;
          }
        }

        // Spring physics damping: Hooke's Law F = -k*x - c*v
        const springK = 0.14;
        const damping = 0.76;

        const ax = (targetX - cur.x) * springK;
        const ay = (targetY - cur.y) * springK;
        const ar = (targetR - cur.r) * springK;

        cur.vx = (cur.vx + ax) * damping;
        cur.vy = (cur.vy + ay) * damping;
        cur.vr = (cur.vr + ar) * damping;

        cur.x += cur.vx;
        cur.y += cur.vy;
        cur.r += cur.vr;
        cur.s += (targetS - cur.s) * 0.2;

        // Directly apply CSS transform for smooth 60fps GPU-accelerated rendering
        el.style.transform = `translate3d(${cur.x.toFixed(2)}px, ${cur.y.toFixed(2)}px, 0) rotate(${cur.r.toFixed(2)}deg) scale(${cur.s.toFixed(3)})`;
        if (cur.s > 1.02) {
          el.style.textShadow = `0 ${-cur.y * 0.4}px 18px rgba(167, 139, 250, ${(cur.s - 1) * 3})`;
        } else {
          el.style.textShadow = "none";
        }
      });

      animId = requestAnimationFrame(simulate);
    };

    animId = requestAnimationFrame(simulate);

    return () => cancelAnimationFrame(animId);
  }, [chars, radius, gravityStrength]);

  const handleMouseMove = (e: React.MouseEvent<HTMLSpanElement>) => {
    isHovered.current = true;
    mousePos.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseLeave = () => {
    isHovered.current = false;
    mousePos.current = null;
  };

  let globalCharIndex = 0;

  return (
    <span
      ref={containerRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      className={className}
      style={{
        display: "inline",
        cursor: "default",
        userSelect: "none",
        perspective: 800,
        ...style,
      }}
    >
      {words.map((word, wIdx) => {
        const wordChars = word.split("");
        const wordStartIndex = globalCharIndex;
        globalCharIndex += wordChars.length + 1; // +1 for space

        return (
          <span
            key={`word-${wIdx}`}
            style={{
              display: "inline-block",
              whiteSpace: "nowrap",
              marginRight: wIdx < words.length - 1 ? "0.28em" : 0,
            }}
          >
            {wordChars.map((char, cIdx) => {
              const charIdx = wordStartIndex + cIdx;
              // Subtle ambient floating wave when idle
              const floatDelay = (charIdx * 0.12).toFixed(2);

              return (
                <span
                  key={`char-${wIdx}-${cIdx}`}
                  ref={(el) => {
                    letterRefs.current[charIdx] = el;
                  }}
                  className={`gravity-char ${isGradient ? "gravity-gradient" : ""}`}
                  style={{
                    display: "inline-block",
                    willChange: "transform",
                    ...(isGradient
                      ? {
                          background:
                            "linear-gradient(135deg, #c4b5fd 0%, #a78bfa 35%, #8376f4 70%, #38bdf8 100%)",
                          WebkitBackgroundClip: "text",
                          WebkitTextFillColor: "transparent",
                        }
                      : {}),
                    animation: `ambientZeroG 3.5s ease-in-out ${floatDelay}s infinite alternate`,
                  }}
                >
                  {char}
                </span>
              );
            })}
          </span>
        );
      })}
    </span>
  );
}
