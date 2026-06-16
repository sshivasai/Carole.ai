"use client";
import React, { useState } from "react";
import type { BrowserScreenshotEvent } from "@/lib/types";
import { Monitor, Camera, Globe, Maximize2, Minimize2, Download, Copy } from "lucide-react";

interface Props { screenshots: BrowserScreenshotEvent[]; }

export default function BrowserView({ screenshots }: Props) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [fullscreen,    setFullscreen]    = useState(false);
  const [copiedUrl,     setCopiedUrl]     = useState(false);

  const active = selectedIndex !== null ? screenshots[selectedIndex] : screenshots[screenshots.length - 1];
  const agentNames = Array.from(new Set(screenshots.map(s => s.sender_name || "Unknown")));

  const download = () => {
    if (!active?.image_base64) return;
    const a = document.createElement("a");
    a.href = `data:image/jpeg;base64,${active.image_base64}`;
    a.download = `screenshot-${Date.now()}.jpg`;
    a.click();
  };

  const copyUrl = () => {
    if (!active?.url) return;
    navigator.clipboard.writeText(active.url);
    setCopiedUrl(true);
    setTimeout(() => setCopiedUrl(false), 1500);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: fullscreen ? 0 : "var(--sp-2xl)" }}>
      {!fullscreen && (
        <header className="flex-between" style={{ marginBottom: "var(--sp-xl)" }}>
          <div>
            <h2 className="display-md">Live Browser Observer</h2>
            <p className="body-sm text-mute">Watch agents navigate the web in real-time.</p>
          </div>
          {agentNames.length > 0 && (
            <div style={{ display: "flex", gap: "var(--sp-sm)", flexWrap: "wrap" }}>
              <button className={`btn btn-sm ${selectedIndex === null ? "btn-primary" : "btn-outline"}`} onClick={() => setSelectedIndex(null)}>Latest</button>
              {agentNames.map(name => (
                <button key={name} className="btn btn-outline btn-sm" onClick={() => {
                  const idx = screenshots.map(s => s.sender_name).lastIndexOf(name);
                  setSelectedIndex(idx >= 0 ? idx : null);
                }}>{name}</button>
              ))}
            </div>
          )}
        </header>
      )}

      {active ? (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", border: "1px solid var(--color-hairline)", borderRadius: fullscreen ? 0 : "var(--radius-md)", overflow: "hidden" }}>
          {/* Browser chrome */}
          <div style={{ background: "var(--color-canvas-soft)", borderBottom: "1px solid var(--color-hairline)", padding: "var(--sp-sm) var(--sp-lg)", display: "flex", alignItems: "center", gap: "var(--sp-lg)", flexShrink: 0 }}>
            <div style={{ display: "flex", gap: 6 }}>
              {["var(--color-danger)","var(--color-warning)","var(--color-primary)"].map((c, i) => (
                <div key={i} style={{ width: 10, height: 10, borderRadius: "50%", background: c }} />
              ))}
            </div>
            <button onClick={copyUrl} style={{ flex: 1, background: "var(--color-canvas)", border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-xs)", padding: "3px var(--sp-md)", display: "flex", alignItems: "center", gap: "var(--sp-sm)", cursor: "pointer", textAlign: "left" }}>
              <Globe size={12} color="var(--color-mute)" />
              <span style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--color-mute)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {active.url || "about:blank"}
              </span>
              <Copy size={10} color={copiedUrl ? "var(--color-primary)" : "var(--color-mute)"} />
            </button>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
              <span className="pill pill-live" style={{ fontSize: 10 }}><div className="live-dot" style={{ width: 5, height: 5 }} /> Live</span>
              <span className="caption">{active.sender_name}</span>
            </div>
            <button className="btn btn-icon-sm btn-ghost" onClick={download} title="Download screenshot"><Download size={13} /></button>
            <button className="btn btn-icon-sm btn-ghost" onClick={() => setFullscreen(f => !f)} title={fullscreen ? "Exit fullscreen" : "Fullscreen"}>
              {fullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
            </button>
          </div>

          {/* Thumbnail strip */}
          {screenshots.length > 1 && (
            <div style={{ display: "flex", gap: 5, padding: "var(--sp-sm) var(--sp-lg)", overflowX: "auto", background: "var(--color-canvas)", borderBottom: "1px solid var(--color-hairline)", flexShrink: 0 }}>
              {screenshots.map((s, idx) => (
                <button key={idx} onClick={() => setSelectedIndex(idx)}
                  style={{ flexShrink: 0, width: 60, height: 38, padding: 0, border: `2px solid ${selectedIndex === idx || (selectedIndex === null && idx === screenshots.length - 1) ? "var(--color-primary)" : "var(--color-hairline)"}`, borderRadius: "var(--radius-xs)", overflow: "hidden", cursor: "pointer", background: "#000", transition: "border-color var(--t-fast)" }}>
                  {s.image_base64 && <img src={`data:image/jpeg;base64,${s.image_base64}`} alt={`Shot ${idx + 1}`} style={{ width: "100%", height: "100%", objectFit: "cover" }} />}
                </button>
              ))}
            </div>
          )}

          <div style={{ flex: 1, background: "#000", display: "flex", justifyContent: "center", overflow: "auto" }}>
            {active.image_base64 ? (
              <img src={`data:image/jpeg;base64,${active.image_base64}`} alt="Browser view" style={{ maxWidth: "100%", height: "auto", objectFit: "contain" }} />
            ) : (
              <div className="empty-state"><Monitor size={40} className="empty-state-icon" /><p>Waiting for visual feed…</p></div>
            )}
          </div>
        </div>
      ) : (
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div className="empty-state">
            <Camera size={40} className="empty-state-icon" />
            <h3>No Browser Activity</h3>
            <p>Agents have not used the browser tool yet.</p>
          </div>
        </div>
      )}
    </div>
  );
}
