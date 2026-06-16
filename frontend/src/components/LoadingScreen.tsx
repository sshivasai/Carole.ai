"use client";
import React, { useEffect, useState } from "react";

interface Step { label: string; done: boolean }
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
          position: "absolute", width: 80, height: 80, borderRadius: "50%",
          background: "var(--color-primary-glow)", animation: "pulse 2s ease-in-out infinite",
        }} />
        <div style={{
          width: 56, height: 56, borderRadius: "var(--radius-md)",
          background: "var(--color-primary)", display: "flex", alignItems: "center",
          justifyContent: "center", fontSize: 28, fontWeight: 700, color: "#051a10",
          position: "relative", zIndex: 1, boxShadow: "0 0 30px var(--color-primary-glow)",
        }}>
          C
        </div>
      </div>

      <div style={{ textAlign: "center" }}>
        <h1 className="display-md" style={{ marginBottom: "var(--sp-xs)" }}>Carole.ai</h1>
        <p className="caption">Multi-Agent Collaboration Platform</p>
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
                {i < activeStep && <span style={{ fontSize: 10, color: "#051a10", fontWeight: 700 }}>✓</span>}
                {i === activeStep && <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#051a10", animation: "pulse 1s infinite" }} />}
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
