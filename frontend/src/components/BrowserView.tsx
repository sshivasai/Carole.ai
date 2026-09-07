"use client";
import React, { useState, useRef, useEffect } from "react";
import type { BrowserScreenshotEvent } from "@/lib/types";
import {
  Monitor,
  Camera,
  Globe,
  Maximize2,
  Minimize2,
  Download,
  Copy,
  MousePointer,
  ArrowDown,
  ArrowUp,
  ArrowLeft,
  RotateCcw,
  CornerDownLeft,
  CheckCircle2,
  Loader2,
  Keyboard,
  Zap,
  Wifi,
} from "lucide-react";
import { api } from "@/hooks/useApi";

interface Props {
  screenshots: BrowserScreenshotEvent[];
}

export default function BrowserView({ screenshots }: Props) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [copiedUrl, setCopiedUrl] = useState(false);

  // Interactive Takeover Mode
  const [takeoverActive, setTakeoverActive] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [textInput, setTextInput] = useState("");
  const [navUrl, setNavUrl] = useState("");
  const [lastClickPos, setLastClickPos] = useState<{ x: number; y: number } | null>(null);
  const [currentLiveShot, setCurrentLiveShot] = useState<string | null>(null);

  // Real-time WebSocket CDP Screencast Stream
  const [wsConnected, setWsConnected] = useState(false);
  const [streamMode, setStreamMode] = useState<"cdp" | "snapshot" | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const imgRef = useRef<HTMLImageElement>(null);

  const active = selectedIndex !== null ? screenshots[selectedIndex] : screenshots[screenshots.length - 1];
  const agentNames = Array.from(new Set(screenshots.map(s => s.sender_name || "Unknown")));

  useEffect(() => {
    if (active?.url) {
      setNavUrl(active.url);
    }
  }, [active?.url]);

  // Connect to WebSocket CDP Screencast
  useEffect(() => {
    const agentId = active?.sender_id || "global";
    if (typeof window === "undefined") return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    // Map dev frontend port 3000 -> backend port 8000
    const backendHost = host.includes(":3000") ? host.replace(":3000", ":8000") : host;
    const wsUrl = `${protocol}//${backendHost}/api/browser/stream?agent_id=${encodeURIComponent(agentId)}`;

    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "frame" && data.image) {
            setCurrentLiveShot(data.image);
            if (data.url) {
              setNavUrl(data.url);
            }
          } else if (data.type === "connected") {
            setStreamMode(data.mode);
          } else if (data.type === "action_result") {
            setActionLoading(false);
          }
        } catch {}
      };

      ws.onclose = () => {
        setWsConnected(false);
        setStreamMode(null);
      };

      ws.onerror = () => {
        setWsConnected(false);
      };
    } catch {}

    return () => {
      if (ws) {
        try {
          ws.close();
        } catch {}
      }
    };
  }, [active?.sender_id]);

  const download = () => {
    const src = currentLiveShot || active?.image_base64;
    if (!src) return;
    const a = document.createElement("a");
    a.href = src.startsWith("data:") ? src : `data:image/jpeg;base64,${src}`;
    a.download = `screenshot-${Date.now()}.jpg`;
    a.click();
  };

  const copyUrl = () => {
    const urlToCopy = navUrl || active?.url;
    if (!urlToCopy) return;
    navigator.clipboard.writeText(urlToCopy);
    setCopiedUrl(true);
    setTimeout(() => setCopiedUrl(false), 1500);
  };

  const handleCanvasClick = async (e: React.MouseEvent<HTMLImageElement>) => {
    if (!takeoverActive || actionLoading || !imgRef.current) return;

    const rect = imgRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    // Viewport is rendered with standard width=1280, height=900 in Playwright
    const normX = Math.round((clickX / rect.width) * 1280);
    const normY = Math.round((clickY / rect.height) * 900);

    setLastClickPos({ x: clickX, y: clickY });
    setTimeout(() => setLastClickPos(null), 1000);

    setActionLoading(true);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: "act",
        kind: "coords",
        x: normX,
        y: normY,
      }));
    } else {
      try {
        const res = await api.browserAct({
          agent_id: active?.sender_id || "global",
          kind: "coords",
          x: normX,
          y: normY,
        });
        if (res.screenshot) {
          setCurrentLiveShot(res.screenshot);
        }
      } catch (err) {
        console.error("Canvas click action failed:", err);
      } finally {
        setActionLoading(false);
      }
    }
  };

  const handleSendText = async () => {
    if (!textInput.trim() || actionLoading) return;
    setActionLoading(true);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: "act",
        kind: "type",
        text: textInput,
      }));
      setTextInput("");
    } else {
      try {
        const res = await api.browserAct({
          agent_id: active?.sender_id || "global",
          kind: "type",
          text: textInput,
        });
        if (res.screenshot) setCurrentLiveShot(res.screenshot);
        setTextInput("");
      } catch (err) {
        console.error("Send text failed:", err);
      } finally {
        setActionLoading(false);
      }
    }
  };

  const handleKeyPress = async (keyName: string) => {
    if (actionLoading) return;
    setActionLoading(true);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: "act",
        kind: "press",
        key: keyName,
      }));
    } else {
      try {
        const res = await api.browserAct({
          agent_id: active?.sender_id || "global",
          kind: "press",
          key: keyName,
        });
        if (res.screenshot) setCurrentLiveShot(res.screenshot);
      } catch (err) {
        console.error("Key press failed:", err);
      } finally {
        setActionLoading(false);
      }
    }
  };

  const handleScroll = async (direction: "down" | "up") => {
    if (actionLoading) return;
    setActionLoading(true);
    const kind = direction === "down" ? "scroll_down" : "scroll_up";
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "act", kind }));
    } else {
      try {
        const res = await api.browserAct({
          agent_id: active?.sender_id || "global",
          kind,
        });
        if (res.screenshot) setCurrentLiveShot(res.screenshot);
      } catch (err) {
        console.error("Scroll failed:", err);
      } finally {
        setActionLoading(false);
      }
    }
  };

  const handleNavigate = async (urlToGo: string) => {
    if (!urlToGo.trim() || actionLoading) return;
    setActionLoading(true);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "act", kind: "navigate", url: urlToGo }));
    } else {
      try {
        const res = await api.browserAct({
          agent_id: active?.sender_id || "global",
          kind: "navigate",
          url: urlToGo,
        });
        if (res.screenshot) setCurrentLiveShot(res.screenshot);
      } catch (e) {
        console.error("Navigation failed:", e);
      } finally {
        setActionLoading(false);
      }
    }
  };

  const handleBack = async () => {
    if (actionLoading) return;
    setActionLoading(true);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "act", kind: "go_back" }));
    } else {
      try {
        const res = await api.browserAct({
          agent_id: active?.sender_id || "global",
          kind: "go_back",
        });
        if (res.screenshot) setCurrentLiveShot(res.screenshot);
      } catch (e) {
        console.error("Go back failed:", e);
      } finally {
        setActionLoading(false);
      }
    }
  };

  const handleReload = async () => {
    if (actionLoading) return;
    setActionLoading(true);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "act", kind: "reload" }));
    } else {
      try {
        const res = await api.browserAct({
          agent_id: active?.sender_id || "global",
          kind: "reload",
        });
        if (res.screenshot) setCurrentLiveShot(res.screenshot);
      } catch (e) {
        console.error("Reload failed:", e);
      } finally {
        setActionLoading(false);
      }
    }
  };

  const handleRefresh = async () => {
    setActionLoading(true);
    try {
      const res = await api.getBrowserScreenshot(active?.sender_id || "global");
      if (res.screenshot) setCurrentLiveShot(res.screenshot);
    } catch (err) {
      console.error("Screenshot refresh failed:", err);
    } finally {
      setActionLoading(false);
    }
  };

  const displayImage = currentLiveShot || (active?.image_base64
    ? (active.image_base64.startsWith("data:") ? active.image_base64 : `data:image/jpeg;base64,${active.image_base64}`)
    : null);

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      height: "100%",
      ...(fullscreen ? {
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 99999,
        background: "var(--bg-surface, #0a0a14)",
        padding: 0
      } : {
        padding: "var(--sp-2xl)"
      })
    }}>
      {!fullscreen && (
        <header className="flex-between" style={{ marginBottom: "var(--sp-xl)" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
              <h2 className="display-md" style={{ margin: 0 }}>Live Browser Observer &amp; Takeover</h2>
              {wsConnected && streamMode === "cdp" ? (
                <span className="pill pill-live" style={{ fontSize: 10 }}>
                  <Zap size={10} style={{ marginRight: 3 }} /> CDP Stream 30 FPS
                </span>
              ) : wsConnected ? (
                <span className="pill pill-safe" style={{ fontSize: 10 }}>
                  <Wifi size={10} style={{ marginRight: 3 }} /> Live Stream
                </span>
              ) : (
                <span className="pill" style={{ fontSize: 10, background: "var(--color-hairline)" }}>
                  Visual Feed
                </span>
              )}
            </div>
            <p className="body-sm text-mute">Watch autonomous agents navigate in real-time or take over interactive control.</p>
          </div>
          {agentNames.length > 0 && (
            <div style={{ display: "flex", gap: "var(--sp-sm)", flexWrap: "wrap", alignItems: "center" }}>
              <button className={`btn btn-sm ${selectedIndex === null ? "btn-primary" : "btn-outline"}`} onClick={() => { setSelectedIndex(null); setCurrentLiveShot(null); }}>
                Latest
              </button>
              {agentNames.map(name => (
                <button key={name} className="btn btn-outline btn-sm" onClick={() => {
                  const idx = screenshots.map(s => s.sender_name).lastIndexOf(name);
                  setSelectedIndex(idx >= 0 ? idx : null);
                  setCurrentLiveShot(null);
                }}>{name}</button>
              ))}
            </div>
          )}
        </header>
      )}

      {active || currentLiveShot ? (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", border: "1px solid var(--color-hairline)", borderRadius: fullscreen ? 0 : "var(--radius-md)", overflow: "hidden" }}>
          {/* Browser chrome toolbar */}
          <div style={{ background: "var(--color-canvas-soft)", borderBottom: "1px solid var(--color-hairline)", padding: "var(--sp-sm) var(--sp-lg)", display: "flex", alignItems: "center", gap: "var(--sp-md)", flexShrink: 0, flexWrap: "wrap" }}>
            <div style={{ display: "flex", gap: 6 }}>
              {["var(--color-danger)", "var(--color-warning)", "var(--color-primary)"].map((c, i) => (
                <div key={i} style={{ width: 10, height: 10, borderRadius: "50%", background: c }} />
              ))}
            </div>

            {/* Navigation Controls */}
            <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <button
                className="btn btn-icon-sm btn-ghost"
                onClick={handleBack}
                disabled={actionLoading}
                title="Go Back"
              >
                <ArrowLeft size={13} />
              </button>
              <button
                className="btn btn-icon-sm btn-ghost"
                onClick={handleReload}
                disabled={actionLoading}
                title="Reload Page"
              >
                <RotateCcw size={13} className={actionLoading ? "animate-spin" : ""} />
              </button>
            </div>

            {/* URL Address Bar */}
            <div style={{ flex: 1, minWidth: 200, display: "flex", alignItems: "center", background: "var(--color-canvas)", border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-xs)", padding: "2px var(--sp-sm)" }}>
              <Globe size={12} color="var(--color-mute)" style={{ marginRight: 6, flexShrink: 0 }} />
              {takeoverActive ? (
                <input
                  type="text"
                  value={navUrl}
                  onChange={e => setNavUrl(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") handleNavigate(navUrl); }}
                  placeholder="https://..."
                  style={{
                    flex: 1,
                    background: "transparent",
                    border: "none",
                    outline: "none",
                    fontSize: 12,
                    fontFamily: "var(--font-mono)",
                    color: "var(--color-text)",
                  }}
                />
              ) : (
                <span style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--color-mute)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {navUrl || active?.url || "about:blank"}
                </span>
              )}
              <button onClick={copyUrl} style={{ background: "none", border: "none", cursor: "pointer", padding: 2 }} title="Copy URL">
                <Copy size={11} color={copiedUrl ? "var(--color-primary)" : "var(--color-mute)"} />
              </button>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
              <button
                className={`btn btn-sm ${takeoverActive ? "btn-danger" : "btn-primary"}`}
                onClick={() => setTakeoverActive(v => !v)}
                title="Toggle interactive click & keyboard takeover"
                style={{ fontSize: 11, padding: "3px 10px", display: "flex", alignItems: "center", gap: 5 }}
              >
                <MousePointer size={12} />
                {takeoverActive ? "Exit Takeover" : "Takeover Control"}
              </button>
              <button className="btn btn-icon-sm btn-ghost" onClick={handleRefresh} disabled={actionLoading} title="Refresh Live View">
                <RotateCcw size={12} className={actionLoading ? "animate-spin" : ""} />
              </button>
              <span className="pill pill-live" style={{ fontSize: 10 }}>
                <div className="live-dot" style={{ width: 5, height: 5 }} /> Live
              </span>
              <span className="caption">{active?.sender_name || "Browser"}</span>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-xs)" }}>
              <button className="btn btn-icon-sm btn-ghost" onClick={download} title="Download screenshot"><Download size={13} /></button>
              <button className="btn btn-icon-sm btn-ghost" onClick={() => setFullscreen(f => !f)} title={fullscreen ? "Exit fullscreen" : "Fullscreen"}>
                {fullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
              </button>
            </div>
          </div>

          {/* Interactive Takeover Control Toolbar */}
          {takeoverActive && (
            <div style={{
              background: "rgba(99, 102, 241, 0.08)",
              borderBottom: "1px solid var(--color-primary)",
              padding: "var(--sp-sm) var(--sp-lg)",
              display: "flex",
              alignItems: "center",
              gap: "var(--sp-sm)",
              flexWrap: "wrap",
              flexShrink: 0
            }}>
              <span className="badge badge-primary" style={{ fontSize: 10 }}>Interactive Canvas Active</span>
              <span className="caption text-mute">Click anywhere on page to forward clicks.</span>

              <div style={{ display: "flex", gap: 4, marginLeft: "auto", alignItems: "center" }}>
                <input
                  type="text"
                  className="input input-sm"
                  placeholder="Type text into focused element..."
                  value={textInput}
                  onChange={e => setTextInput(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") handleSendText(); }}
                  style={{ width: 220, height: 26, fontSize: 11 }}
                />
                <button className="btn btn-outline btn-sm" style={{ padding: "2px 8px", fontSize: 11 }} onClick={handleSendText} disabled={actionLoading || !textInput.trim()}>
                  <Keyboard size={11} /> Send Text
                </button>
                <button className="btn btn-outline btn-sm" style={{ padding: "2px 8px", fontSize: 11 }} onClick={() => handleKeyPress("Enter")} disabled={actionLoading} title="Press Enter">
                  <CornerDownLeft size={11} /> Enter
                </button>
                <button className="btn btn-outline btn-sm" style={{ padding: "2px 8px", fontSize: 11 }} onClick={() => handleScroll("down")} disabled={actionLoading} title="Scroll Down">
                  <ArrowDown size={11} /> Scroll
                </button>
                <button className="btn btn-outline btn-sm" style={{ padding: "2px 8px", fontSize: 11 }} onClick={() => handleScroll("up")} disabled={actionLoading} title="Scroll Up">
                  <ArrowUp size={11} />
                </button>
              </div>
            </div>
          )}

          {/* Thumbnail strip */}
          {screenshots.length > 1 && (
            <div style={{ display: "flex", gap: 5, padding: "var(--sp-sm) var(--sp-lg)", overflowX: "auto", background: "var(--color-canvas)", borderBottom: "1px solid var(--color-hairline)", flexShrink: 0 }}>
              {screenshots.map((s, idx) => (
                <button key={idx} onClick={() => { setSelectedIndex(idx); setCurrentLiveShot(null); }}
                  style={{ flexShrink: 0, width: 60, height: 38, padding: 0, border: `2px solid ${selectedIndex === idx || (selectedIndex === null && idx === screenshots.length - 1) ? "var(--color-primary)" : "var(--color-hairline)"}`, borderRadius: "var(--radius-xs)", overflow: "hidden", cursor: "pointer", background: "#000", transition: "border-color var(--t-fast)" }}>
                  {s.image_base64 && <img src={s.image_base64.startsWith("data:") ? s.image_base64 : `data:image/jpeg;base64,${s.image_base64}`} alt={`Shot ${idx + 1}`} style={{ width: "100%", height: "100%", objectFit: "cover" }} />}
                </button>
              ))}
            </div>
          )}

          {/* Live Canvas View */}
          <div style={{ flex: 1, background: "#000", display: "flex", justifyContent: "center", alignItems: "center", position: "relative", overflow: "auto" }}>
            {displayImage ? (
              <div style={{ position: "relative", display: "inline-block", maxWidth: "100%", maxHeight: "100%" }}>
                <img
                  ref={imgRef}
                  src={displayImage}
                  alt="Live Browser view"
                  onClick={handleCanvasClick}
                  style={{
                    maxWidth: "100%",
                    height: "auto",
                    objectFit: "contain",
                    cursor: takeoverActive ? "crosshair" : "default",
                    userSelect: "none",
                  }}
                />

                {/* Animated Click Ripple Feedback */}
                {lastClickPos && (
                  <div style={{
                    position: "absolute",
                    left: lastClickPos.x - 12,
                    top: lastClickPos.y - 12,
                    width: 24,
                    height: 24,
                    borderRadius: "50%",
                    border: "2px solid #6366f1",
                    backgroundColor: "rgba(99, 102, 241, 0.4)",
                    pointerEvents: "none",
                    animation: "ping 0.6s cubic-bezier(0, 0, 0.2, 1) infinite",
                  }} />
                )}

                {actionLoading && (
                  <div style={{
                    position: "absolute",
                    top: 12,
                    right: 12,
                    background: "rgba(0,0,0,0.75)",
                    color: "#fff",
                    padding: "4px 10px",
                    borderRadius: "var(--radius-sm)",
                    fontSize: 11,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    backdropFilter: "blur(4px)",
                  }}>
                    <Loader2 size={12} className="animate-spin" /> Executing Action...
                  </div>
                )}
              </div>
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
