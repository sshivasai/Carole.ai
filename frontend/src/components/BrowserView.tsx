"use client";
import React, { useState } from "react";
import type { BrowserScreenshotEvent } from "@/lib/types";
import { Monitor, Camera, Globe } from "lucide-react";

interface Props {
  screenshots: BrowserScreenshotEvent[];
}

export default function BrowserView({ screenshots }: Props) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  // Filter agents that have sent screenshots
  const agentsWithScreenshots = Array.from(new Set(screenshots.map(s => s.sender_name || "Unknown Agent")));
  
  // FIX: use latest screenshot (last in array) not first
  const activeScreenshot = selectedIndex !== null
    ? screenshots[selectedIndex]
    : screenshots[screenshots.length - 1];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "var(--sp-2xl)" }}>
      <header style={{ marginBottom: "var(--sp-2xl)", display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <h2 className="display-lg">Live Browser Observer</h2>
          <p className="body-md" style={{ color: "var(--color-mute)" }}>
            Watch your agents navigate the web in real-time.
          </p>
        </div>
        
        {/* Agent Filter */}
        {agentsWithScreenshots.length > 0 && (
          <div style={{ display: "flex", gap: "var(--sp-sm)" }}>
            <button 
              className={`btn ${selectedIndex === null ? "btn-primary" : "btn-outline"}`}
              onClick={() => setSelectedIndex(null)}
            >
              Latest
            </button>
            {agentsWithScreenshots.map(name => (
              <button 
                key={name}
                className={`btn btn-outline`}
                onClick={() => {
                  // Find latest screenshot from this agent
                  const idx = screenshots.map(s => s.sender_name).lastIndexOf(name);
                  setSelectedIndex(idx >= 0 ? idx : null);
                }}
              >
                {name}
              </button>
            ))}
          </div>
        )}
      </header>

      {activeScreenshot ? (
        <div className="card card-emphasized" style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", padding: 0 }}>
          {/* Browser Chrome Header */}
          <div style={{ background: "var(--color-canvas-soft)", borderBottom: "1px solid var(--color-hairline)", padding: "var(--sp-sm) var(--sp-lg)", display: "flex", alignItems: "center", gap: "var(--sp-lg)" }}>
            <div style={{ display: "flex", gap: "6px" }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: "var(--color-danger)" }} />
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: "var(--color-warning)" }} />
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: "var(--color-primary)" }} />
            </div>
            <div style={{ flex: 1, background: "var(--color-canvas)", border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-xs)", padding: "var(--sp-xs) var(--sp-md)", display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
              <Globe size={14} color="var(--color-mute)" />
              <span className="code-inline" style={{ background: "transparent", padding: 0 }}>{activeScreenshot.url || "about:blank"}</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
              <span className="pill pill-live"><div className="live-dot" style={{ width: 6, height: 6 }}/> Streaming</span>
              <span className="caption">Agent: {activeScreenshot.sender_name}</span>
            </div>
          </div>
          
          {/* History thumbnail strip */}
          {screenshots.length > 1 && (
            <div style={{
              display: "flex", gap: 6, padding: "var(--sp-sm) var(--sp-lg)",
              overflowX: "auto", background: "var(--color-canvas)",
              borderTop: "1px solid var(--color-hairline)",
            }}>
              {screenshots.map((s, idx) => (
                <button
                  key={idx}
                  onClick={() => setSelectedIndex(idx)}
                  style={{
                    flexShrink: 0, width: 64, height: 40, padding: 0,
                    border: `2px solid ${selectedIndex === idx ? "var(--color-primary)" : "var(--color-hairline)"}`,
                    borderRadius: "var(--radius-xs)", overflow: "hidden", cursor: "pointer", background: "#000",
                  }}
                >
                  {s.image_base64 && (
                    <img src={`data:image/jpeg;base64,${s.image_base64}`} alt={`Screenshot ${idx + 1}`}
                      style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                  )}
                </button>
              ))}
            </div>
          )}
          <div style={{ flex: 1, background: "#000", position: "relative", overflow: "auto", display: "flex", justifyContent: "center" }}>
            {activeScreenshot.image_base64 ? (
              <img 
                src={`data:image/jpeg;base64,${activeScreenshot.image_base64}`} 
                alt="Agent Browser View"
                style={{ maxWidth: "100%", height: "auto", objectFit: "contain" }}
              />
            ) : (
              <div style={{ margin: "auto", color: "var(--color-mute)", display: "flex", flexDirection: "column", alignItems: "center", gap: "var(--sp-sm)" }}>
                <Monitor size={48} />
                <p>Waiting for visual feed...</p>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ textAlign: "center", color: "var(--color-mute)" }}>
            <Camera size={48} style={{ margin: "0 auto var(--sp-md)", opacity: 0.5 }} />
            <h3 className="display-sm">No Browser Activity</h3>
            <p className="body-sm">Agents have not used the browser automation tool yet.</p>
          </div>
        </div>
      )}
    </div>
  );
}
