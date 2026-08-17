"use client";
import React, { useEffect, useState } from "react";

interface Props { steps?: string[] }

export default function LoadingScreen({ steps = [] }: Props) {
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    if (steps.length === 0) return;
    const iv = setInterval(() => setActiveStep(s => Math.min(s + 1, steps.length - 1)), 800);
    return () => clearInterval(iv);
  }, [steps.length]);

  return (
    <div style={{
      position: "fixed", inset: 0, background: "var(--color-canvas)",
      display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", gap: "var(--sp-3xl)", zIndex: 9000,
    }}>
      {/* Animated logo */}
      <div style={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{
          position: "absolute", width: 96, height: 96, borderRadius: "50%",
          background: "var(--color-primary-glow)", animation: "pulse 2s ease-in-out infinite",
          filter: "blur(20px)",
        }} />
        <img
          src="/branding/logo-mark-animated.webp"
          alt="Carole.ai"
          width={68}
          height={68}
          style={{
            position: "relative",
            zIndex: 1,
            objectFit: "contain",
            filter: "drop-shadow(0 0 20px var(--color-primary-glow))",
          }}
        />
      </div>

      <div style={{ textAlign: "center" }}>
        <h1 className="display-md" style={{ marginBottom: "var(--sp-2xs)", letterSpacing: "-0.03em" }}>
          Carole<span style={{ color: "var(--color-primary)" }}>.ai</span>
        </h1>
        <p className="caption" style={{ letterSpacing: "0.06em", color: "var(--color-mute)" }}>
          AI AGENTS. REAL WORK.
        </p>
      </div>

      {steps.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-sm)", minWidth: 260 }}>
          {steps.map((step, i) => (
            <div key={step} style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)", opacity: i > activeStep ? 0.3 : 1, transition: "opacity 0.3s" }}>
              <div style={{
                width: 18, height: 18, borderRadius: "50%", flexShrink: 0,
                background: i <= activeStep ? "var(--color-primary)" : "var(--color-canvas-raised)",
                border: "1px solid",
                borderColor: i <= activeStep ? "var(--color-primary)" : "var(--color-hairline)",
                display: "flex", alignItems: "center", justifyContent: "center",
                transition: "all 0.3s",
              }}>
                {i < activeStep && <span style={{ fontSize: 10, color: "var(--color-on-primary)", fontWeight: 700 }}>✓</span>}
                {i === activeStep && <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--color-on-primary)", animation: "pulse 1s infinite" }} />}
              </div>
              <span style={{ fontSize: 13, color: i <= activeStep ? "var(--color-ink)" : "var(--color-mute)" }}>{step}</span>
            </div>
          ))}
        </div>
      )}

      {/* Bottom spinner bar */}
      <div style={{ width: 200, height: 2, background: "var(--color-canvas-raised)", borderRadius: 1, overflow: "hidden" }}>
        <div style={{
          height: "100%", background: "var(--color-primary)",
          animation: "loadBar 1.5s ease-in-out infinite",
          borderRadius: 1,
        }} />
      </div>
      <style>{`@keyframes loadBar{0%{width:0%;margin-left:0}50%{width:60%;margin-left:20%}100%{width:0%;margin-left:100%}}`}</style>
    </div>
  );
}
