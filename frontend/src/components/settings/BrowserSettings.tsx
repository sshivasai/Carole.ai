"use client";
import React, { useState, useEffect } from "react";
import { Globe, Save, Loader2, Monitor, ShieldCheck, Eye, EyeOff, Layers, Sparkles, Terminal } from "lucide-react";
import { api } from "@/hooks/useApi";
import SettingTooltip from "./SettingTooltip";

interface Props {
  onToast: (msg: string, type: "success" | "error" | "info") => void;
}

export default function BrowserSettings({ onToast }: Props) {
  const [settings, setSettings] = useState<any>({
    engine: "carole",
    infrastructure: "local",
    proxy_provider: "none",
    display_mode: "headless",
    vision_model: "inherit",
    api_keys: {},
    project_id: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});

  useEffect(() => {
    api.getAppConfig()
      .then((cfg: any) => {
        const ba = cfg.browser_automation || {};
        setSettings({
          engine: ba.engine || (ba.provider === "browseruse" ? "browseruse" : "carole"),
          infrastructure: ba.infrastructure || (ba.provider === "browserbase" ? "browserbase" : "local"),
          proxy_provider: ba.proxy_provider || (["scraperapi", "zenrows"].includes(ba.provider) ? ba.provider : "none"),
          display_mode: ba.display_mode || (ba.headless === false ? "windowed" : "headless"),
          vision_model: ba.vision_model || "inherit",
          api_keys: ba.api_keys || {},
          project_id: ba.project_id || "",
        });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {
        ...settings,
        provider: settings.engine === "browseruse"
          ? "browseruse"
          : (settings.infrastructure === "browserbase"
            ? "browserbase"
            : settings.proxy_provider !== "none"
              ? settings.proxy_provider
              : "local"),
        headless: settings.display_mode !== "windowed",
      };
      await api.updateAppConfig({ browser_automation: payload });
      onToast("Browser automation settings saved ✓", "success");
    } catch {
      onToast("Failed to save browser automation settings", "error");
    } finally {
      setSaving(false);
    }
  };

  const toggleKey = (name: string) => setShowKeys(p => ({ ...p, [name]: !p[name] }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2xl)" }}>
      <div className="card" style={{ padding: "var(--sp-xl)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--sp-md)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)" }}>
            <div
              style={{
                width: 38,
                height: 38,
                borderRadius: "var(--radius-sm)",
                background: "rgba(16, 185, 129, 0.12)",
                border: "1px solid rgba(16, 185, 129, 0.3)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--color-success)",
              }}
            >
              <Globe size={18} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                <h3 className="display-sm" style={{ margin: 0 }}>Browser Automation &amp; Anti-Bot Architecture</h3>
                <span className="pill pill-live" style={{ fontSize: 9 }}>
                  Modular 3-Tier
                </span>
              </div>
              <p className="caption text-mute" style={{ margin: 0 }}>
                Configure web crawling, local dev debugging, CAPTCHA bypass, and cloud browser orchestration.
              </p>
            </div>
          </div>
        </div>

        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {[1, 2, 3].map(i => (
              <div key={i} className="skeleton skeleton-text" style={{ height: 40 }} />
            ))}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-xl)" }}>
            {/* ── Tier 1: Automation Engine ───────────────────────────────────── */}
            <div
              style={{
                background: "var(--color-canvas-soft)",
                padding: "var(--sp-lg)",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--color-hairline)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: "var(--sp-xs)" }}>
                <span className="badge badge-blue" style={{ fontSize: 9 }}>Tier 1</span>
                <strong className="body-sm-strong">Automation Engine &amp; DOM Parser</strong>
                <SettingTooltip
                  title="Automation Engine"
                  why="Determines the agent's internal loop for reading the DOM, generating action plans, and clicking elements."
                  how="Carole Native uses built-in XPath snapshots for instant local response. Browser-Use builds an interactive accessibility tree with vision guidance."
                />
              </div>
              <p className="caption text-mute" style={{ marginBottom: "var(--sp-md)" }}>
                Controls how the agent reads the DOM tree and executes clicks, keystrokes, and form inputs.
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(240px, 100%), 1fr))", gap: "var(--sp-md)" }}>
                <label
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                    padding: "var(--sp-md) var(--sp-lg)",
                    borderRadius: "var(--radius-sm)",
                    border: `1.5px solid ${settings.engine === "carole" ? "var(--color-primary)" : "var(--color-hairline)"}`,
                    background: settings.engine === "carole" ? "rgba(99, 102, 241, 0.08)" : "var(--color-canvas)",
                    cursor: "pointer",
                    transition: "all var(--t-fast)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                    <input
                      type="radio"
                      name="engine"
                      value="carole"
                      checked={settings.engine === "carole"}
                      onChange={() => setSettings((s: any) => ({ ...s, engine: "carole" }))}
                    />
                    <strong className="body-sm-strong">Carole Native Agent</strong>
                    <span className="pill pill-safe" style={{ fontSize: 9, marginLeft: "auto" }}>Recommended</span>
                  </div>
                  <span className="caption text-mute" style={{ fontSize: 10 }}>
                    Fast ReACT loop with lightweight XPath snapshots. Instant response, local dev support, and zero extra costs.
                  </span>
                </label>

                <label
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                    padding: "var(--sp-md) var(--sp-lg)",
                    borderRadius: "var(--radius-sm)",
                    border: `1.5px solid ${settings.engine === "browseruse" ? "var(--color-primary)" : "var(--color-hairline)"}`,
                    background: settings.engine === "browseruse" ? "rgba(99, 102, 241, 0.08)" : "var(--color-canvas)",
                    cursor: "pointer",
                    transition: "all var(--t-fast)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                    <input
                      type="radio"
                      name="engine"
                      value="browseruse"
                      checked={settings.engine === "browseruse"}
                      onChange={() => setSettings((s: any) => ({ ...s, engine: "browseruse" }))}
                    />
                    <strong className="body-sm-strong">Browser-Use Framework</strong>
                  </div>
                  <span className="caption text-mute" style={{ fontSize: 10 }}>
                    Deep tree-based DOM extraction with dedicated vision feedback. Best for multi-tab complex workflows.
                  </span>
                </label>
              </div>
            </div>

            {/* ── Tier 2: Browser Runtime / Infrastructure ─────────────────────── */}
            <div
              style={{
                background: "var(--color-canvas-soft)",
                padding: "var(--sp-lg)",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--color-hairline)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: "var(--sp-xs)" }}>
                <span className="badge badge-purple" style={{ fontSize: 9 }}>Tier 2</span>
                <strong className="body-sm-strong">Browser Runtime / Infrastructure</strong>
                <SettingTooltip
                  title="Browser Runtime"
                  why="Selects whether the browser runs locally on your workstation or in a stealthy cloud container."
                  how="Local Playwright runs Chromium on your machine with access to all localhost ports (3000, 5173, etc.). Browserbase executes on residential cloud instances with automated CAPTCHA solving."
                />
              </div>
              <p className="caption text-mute" style={{ marginBottom: "var(--sp-md)" }}>
                Select where the Chromium browser instance runs and executes pages.
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(240px, 100%), 1fr))", gap: "var(--sp-md)" }}>
                <label
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                    padding: "var(--sp-md) var(--sp-lg)",
                    borderRadius: "var(--radius-sm)",
                    border: `1.5px solid ${settings.infrastructure === "local" ? "var(--color-primary)" : "var(--color-hairline)"}`,
                    background: settings.infrastructure === "local" ? "rgba(99, 102, 241, 0.08)" : "var(--color-canvas)",
                    cursor: "pointer",
                    transition: "all var(--t-fast)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                    <input
                      type="radio"
                      name="infrastructure"
                      value="local"
                      checked={settings.infrastructure === "local"}
                      onChange={() => setSettings((s: any) => ({ ...s, infrastructure: "local" }))}
                    />
                    <strong className="body-sm-strong">Local Playwright (On-Machine)</strong>
                    <span className="pill pill-safe" style={{ fontSize: 9, marginLeft: "auto" }}>Free &amp; Localhost</span>
                  </div>
                  <span className="caption text-mute" style={{ fontSize: 10 }}>
                    Executes directly on your workstation. Full access to localhost:3000, 5173, 8080, and private LAN.
                  </span>
                </label>

                <label
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                    padding: "var(--sp-md) var(--sp-lg)",
                    borderRadius: "var(--radius-sm)",
                    border: `1.5px solid ${settings.infrastructure === "browserbase" ? "var(--color-primary)" : "var(--color-hairline)"}`,
                    background: settings.infrastructure === "browserbase" ? "rgba(99, 102, 241, 0.08)" : "var(--color-canvas)",
                    cursor: "pointer",
                    transition: "all var(--t-fast)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                    <input
                      type="radio"
                      name="infrastructure"
                      value="browserbase"
                      checked={settings.infrastructure === "browserbase"}
                      onChange={() => setSettings((s: any) => ({ ...s, infrastructure: "browserbase" }))}
                    />
                    <strong className="body-sm-strong">Browserbase Cloud</strong>
                    <span className="pill pill-live" style={{ fontSize: 9, marginLeft: "auto" }}>Cloud Stealth</span>
                  </div>
                  <span className="caption text-mute" style={{ fontSize: 10 }}>
                    Managed cloud browser with residential IP pool, automatic cloud CAPTCHA solver, and session replays.
                  </span>
                </label>
              </div>

              {settings.infrastructure === "browserbase" && (
                <div style={{ marginTop: "var(--sp-md)", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(220px, 100%), 1fr))", gap: "var(--sp-md)" }}>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <div style={{ display: "flex", alignItems: "center" }}>
                      <label className="form-label" style={{ fontSize: 11 }}>Browserbase API Key</label>
                      <SettingTooltip
                        title="Browserbase API Key"
                        why="Authenticates with your Browserbase cloud account."
                        how="Used to create cloud browser sessions and stream CDP control messages."
                      />
                    </div>
                    <div style={{ position: "relative" }}>
                      <input
                        type={showKeys["browserbase"] ? "text" : "password"}
                        className="input"
                        placeholder="bb_..."
                        value={settings.api_keys?.browserbase || ""}
                        onChange={e => setSettings((d: any) => ({ ...d, api_keys: { ...d.api_keys, browserbase: e.target.value } }))}
                        style={{ fontSize: 11, paddingRight: 36, fontFamily: "var(--font-mono)" }}
                      />
                      <button
                        type="button"
                        onClick={() => toggleKey("browserbase")}
                        style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "var(--color-mute)" }}
                      >
                        {showKeys["browserbase"] ? <EyeOff size={13} /> : <Eye size={13} />}
                      </button>
                    </div>
                  </div>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label" style={{ fontSize: 11 }}>Browserbase Project ID (Optional)</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="project_id"
                      value={settings.project_id || ""}
                      onChange={e => setSettings((d: any) => ({ ...d, project_id: e.target.value }))}
                      style={{ fontSize: 11, fontFamily: "var(--font-mono)" }}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* ── Tier 3: Proxy & Anti-Bot Service ─────────────────────────────── */}
            <div
              style={{
                background: "var(--color-canvas-soft)",
                padding: "var(--sp-lg)",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--color-hairline)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: "var(--sp-xs)" }}>
                <span className="badge badge-yellow" style={{ fontSize: 9 }}>Tier 3</span>
                <strong className="body-sm-strong">Proxy &amp; Anti-Bot Provider</strong>
                <SettingTooltip
                  title="Proxy Provider"
                  why="Protects against IP bans, rate limits, and Cloudflare Turnstile bot blocks."
                  how="When enabled, Playwright routes network traffic through rotating residential proxy pools before hitting destination sites."
                />
              </div>
              <p className="caption text-mute" style={{ marginBottom: "var(--sp-md)" }}>
                Residential proxy routing to bypass IP rate-limiting, Cloudflare Turnstile, and geo-blocks.
              </p>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <select
                  className="input"
                  value={settings.proxy_provider || "none"}
                  onChange={e => setSettings((d: any) => ({ ...d, proxy_provider: e.target.value }))}
                  style={{ fontSize: 11 }}
                >
                  <option value="none">Direct Connection (No Proxy / Local Dev)</option>
                  <option value="scraperapi">ScraperAPI (Smart Rotating Residential Proxy)</option>
                  <option value="zenrows">ZenRows (Anti-Bypass Smart Proxy)</option>
                </select>
              </div>

              {settings.proxy_provider === "scraperapi" && (
                <div className="form-group" style={{ marginTop: "var(--sp-sm)", marginBottom: 0 }}>
                  <label className="form-label" style={{ fontSize: 11 }}>ScraperAPI Key</label>
                  <div style={{ position: "relative" }}>
                    <input
                      type={showKeys["scraperapi"] ? "text" : "password"}
                      className="input"
                      value={settings.api_keys?.scraperapi || ""}
                      onChange={e => setSettings((d: any) => ({ ...d, api_keys: { ...d.api_keys, scraperapi: e.target.value } }))}
                      style={{ fontSize: 11, paddingRight: 36, fontFamily: "var(--font-mono)" }}
                    />
                    <button
                      type="button"
                      onClick={() => toggleKey("scraperapi")}
                      style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "var(--color-mute)" }}
                    >
                      {showKeys["scraperapi"] ? <EyeOff size={13} /> : <Eye size={13} />}
                    </button>
                  </div>
                </div>
              )}

              {settings.proxy_provider === "zenrows" && (
                <div className="form-group" style={{ marginTop: "var(--sp-sm)", marginBottom: 0 }}>
                  <label className="form-label" style={{ fontSize: 11 }}>ZenRows API Key</label>
                  <div style={{ position: "relative" }}>
                    <input
                      type={showKeys["zenrows"] ? "text" : "password"}
                      className="input"
                      value={settings.api_keys?.zenrows || ""}
                      onChange={e => setSettings((d: any) => ({ ...d, api_keys: { ...d.api_keys, zenrows: e.target.value } }))}
                      style={{ fontSize: 11, paddingRight: 36, fontFamily: "var(--font-mono)" }}
                    />
                    <button
                      type="button"
                      onClick={() => toggleKey("zenrows")}
                      style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "var(--color-mute)" }}
                    >
                      {showKeys["zenrows"] ? <EyeOff size={13} /> : <Eye size={13} />}
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* ── Display Mode & Vision Model ── */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(240px, 100%), 1fr))", gap: "var(--sp-md)" }}>
              <div
                style={{
                  background: "var(--color-canvas-soft)",
                  border: "1px solid var(--color-hairline)",
                  borderRadius: "var(--radius-sm)",
                  padding: "var(--sp-md) var(--sp-lg)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                }}
              >
                <div style={{ display: "flex", alignItems: "center" }}>
                  <label className="form-label" style={{ fontSize: 11, fontWeight: 600, margin: 0 }}>
                    Display Mode
                  </label>
                  <SettingTooltip
                    title="Display Mode"
                    why="Controls whether the Chromium browser window is visible on your desktop screen."
                    how="Headless runs quietly in the background while streaming screenshots to your chat card. Windowed pops up a real Chrome window so you can interact alongside the agent."
                  />
                </div>
                <select
                  className="input"
                  value={settings.display_mode || "headless"}
                  onChange={e => setSettings((d: any) => ({ ...d, display_mode: e.target.value }))}
                  style={{ fontSize: 11 }}
                >
                  <option value="headless">Headless: ON (Background + In-Chat Card / Canvas)</option>
                  <option value="windowed">Headless: OFF (Real Desktop Chromium Window)</option>
                </select>
                <span className="caption text-mute" style={{ fontSize: 10 }}>
                  {settings.display_mode === "windowed"
                    ? "🖥️ A real browser window pops up on your machine for direct interaction."
                    : "⚡ Zero window popups. View live screenshots and interact via the In-Chat Card or BrowserView."}
                </span>
              </div>

              <div
                style={{
                  background: "var(--color-canvas-soft)",
                  border: "1px solid var(--color-hairline)",
                  borderRadius: "var(--radius-sm)",
                  padding: "var(--sp-md) var(--sp-lg)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                }}
              >
                <div style={{ display: "flex", alignItems: "center" }}>
                  <label className="form-label" style={{ fontSize: 11, fontWeight: 600, margin: 0 }}>
                    Vision Guidance Model
                  </label>
                  <SettingTooltip
                    title="Vision Guidance Model"
                    why="Some complex pages require visual bounding-box comprehension beyond raw HTML parsing."
                    how="When set, screenshots of the viewport are sent to this model (e.g. GPT-4o or Claude 3.5 Sonnet) to detect visual elements, modals, and buttons."
                  />
                </div>
                <select
                  className="input"
                  value={settings.vision_model || "inherit"}
                  onChange={e => setSettings((d: any) => ({ ...d, vision_model: e.target.value }))}
                  style={{ fontSize: 11 }}
                >
                  <option value="inherit">Inherit Calling Agent's Active Model</option>
                  <option value="gpt-4o">OpenAI GPT-4o (High-Accuracy Vision)</option>
                  <option value="claude-3-5-sonnet">Claude 3.5 Sonnet (Best Reasoning &amp; DOM)</option>
                  <option value="gemini-3.6-flash">Google Gemini 3.6 Flash (Fast &amp; Accurate Vision)</option>
                  <option value="gemini-1.5-pro">Google Gemini 1.5 Pro (Massive Context)</option>
                </select>
                <span className="caption text-mute" style={{ fontSize: 10 }}>
                  Designate a dedicated high-accuracy vision model for visual screenshot analysis.
                </span>
              </div>
            </div>

            {/* ── Policy Callout ── */}
            <div
              style={{
                padding: "var(--sp-md) var(--sp-lg)",
                background: "rgba(99, 102, 241, 0.06)",
                border: "1px solid rgba(99, 102, 241, 0.2)",
                borderRadius: "var(--radius-sm)",
                fontSize: 11,
                lineHeight: 1.5,
              }}
            >
              <strong style={{ color: "var(--color-primary)" }}>Human-in-the-Loop (HIL) &amp; Roadblock Handling:</strong>
              <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
                <li><code>ask_user</code>: Used for text input or missing parameters.</li>
                <li><code>browser_human_takeover</code>: Triggered for CAPTCHAs, 2FA SMS codes, and logins. Solved in the In-Chat Card or BrowserView.</li>
                <li><strong>Local Dev Servers:</strong> All local dev ports and services (<code>localhost:3000</code>, <code>5173</code>, <code>8000</code>, <code>8080</code>, or any custom port) are 100% accessible under Local Playwright runtime.</li>
              </ul>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "var(--sp-sm)" }}>
              <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
                {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save Browser Settings
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
