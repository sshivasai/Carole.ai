"use client";
import React, { useState, useEffect, useCallback } from "react";
import { Settings, Trash2, Upload, Loader2, AlertTriangle, CheckCircle, RefreshCw, Key, Eye, EyeOff, Save, MessageSquare, Layers, DollarSign, Globe, ToggleLeft, ToggleRight, RotateCcw, ChevronDown, ChevronUp, Shield } from "lucide-react";
import type { PromptBlock, AccessControlConfig } from "@/lib/types";
import { api } from "@/hooks/useApi";
import PromptsEditor from "./settings/PromptsEditor";
import ModelCatalogEditor from "./settings/ModelCatalogEditor";
import type { AgentConfig } from "@/lib/types";
import Modal from "./Modal";
import { useAuth } from "@/hooks/useAuth";
import AccessControlMatrix, { DEFAULT_ACCESS_CONTROL } from "./AccessControlMatrix";

interface Props {
  teamId: string | null;
  projectId: string | null;
  agents: AgentConfig[];
  onToast: (msg: string, type: "success" | "error" | "info") => void;
  onTeamDeleted: () => void;
  onProjectDeleted: () => void;
}

interface HealthData { status: string; tools_registered?: number; version?: string; }
interface UsageData { total_messages?: number; total_tasks?: number; total_agents?: number; }


// ── Global Access Control Card ─────────────────────────────────────────────────

function GlobalAccessControlCard({ onToast }: { onToast: (msg: string, type: any) => void }) {
  const [config, setConfig] = useState<AccessControlConfig>({ ...DEFAULT_ACCESS_CONTROL, categories: { ...DEFAULT_ACCESS_CONTROL.categories }, overrides: {}, custom_skip_judge: { file_patterns: [], command_prefixes: [] } });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    api.getSettings().then((s: any) => {
      if (s?.access_control && typeof s.access_control === "object" && "categories" in s.access_control) {
        setConfig(s.access_control as AccessControlConfig);
      }
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.saveSettings({ access_control: config });
      onToast("Access Control defaults saved", "success");
    } catch {
      onToast("Failed to save Access Control settings", "error");
    } finally { setSaving(false); }
  };

  return (
    <div className="card" style={{ marginBottom: "var(--sp-xl)", borderRadius: "var(--radius-md)", overflow: "hidden" }}>
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        style={{ width: "100%", background: "none", border: "none", cursor: "pointer", padding: "var(--sp-xl)", display: "flex", alignItems: "center", gap: "var(--sp-md)", textAlign: "left" }}
      >
        <div style={{ width: 40, height: 40, borderRadius: "50%", background: "rgba(167,139,250,0.12)", border: "1.5px solid rgba(167,139,250,0.3)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <Shield size={18} color="#a78bfa" />
        </div>
        <div style={{ flex: 1 }}>
          <div className="body-sm-strong">Access Control &amp; Safety Defaults</div>
          <div className="caption">Global permission defaults for all agents — per-agent settings override these.</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
          <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 10, fontWeight: 700, background: config.enable_judge ? "rgba(167,139,250,0.15)" : "rgba(251,191,36,0.15)", color: config.enable_judge ? "#a78bfa" : "#fbbf24", border: `1px solid ${config.enable_judge ? "rgba(167,139,250,0.35)" : "rgba(251,191,36,0.35)"}` }}>
            {config.enable_judge ? "⚖️ Judge ON" : "⚡ Judge OFF"}
          </span>
          {expanded ? <ChevronUp size={15} color="var(--color-mute)" /> : <ChevronDown size={15} color="var(--color-mute)" />}
        </div>
      </button>

      {expanded && (
        <div style={{ padding: "0 var(--sp-xl) var(--sp-xl)", borderTop: "1px solid var(--color-hairline)" }}>
          {loading ? (
            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", padding: "var(--sp-xl)" }}>
              <Loader2 size={16} className="animate-spin" style={{ color: "var(--color-primary)" }} />
              <span className="caption">Loading settings…</span>
            </div>
          ) : (
            <>
              <div style={{ paddingTop: "var(--sp-xl)" }}>
                <AccessControlMatrix value={config} onChange={setConfig} />
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "var(--sp-xl)", paddingTop: "var(--sp-md)", borderTop: "1px solid var(--color-hairline)" }}>
                <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>
                  {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                  Save Global Defaults
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── Google Account Card ───────────────────────────────────────────────────────

function GoogleAccountCard({ onToast }: { onToast: (msg: string, type: any) => void }) {
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [disconnecting, setDiscon] = useState(false);

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    try { setStatus(await api.getGoogleStatus()); }
    catch { setStatus(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    fetchStatus();
    // If returning from OAuth (query param), refresh status
    if (typeof window !== "undefined" && window.location.search.includes("google_connected")) {
      fetchStatus();
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [fetchStatus]);

  const handleConnect = () => {
    window.location.href = api.getGoogleAuthUrl();
  };

  const handleDisconnect = async () => {
    setDiscon(true);
    try {
      await api.disconnectGoogle();
      setStatus({ connected: false });
      onToast("Google account disconnected", "info");
    } catch {
      onToast("Failed to disconnect", "error");
    } finally { setDiscon(false); }
  };

  const connected = status?.connected;

  return (
    <div className="card" style={{ marginBottom: "var(--sp-xl)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: "var(--sp-lg)" }}>
        {/* Google G icon */}
        <svg width="18" height="18" viewBox="0 0 48 48" style={{ flexShrink: 0 }}>
          <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
          <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
          <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
          <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.18 1.48-4.97 2.31-8.16 2.31-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
        </svg>
        <h3 className="display-sm">Google Account</h3>
      </div>
      <p className="body-sm text-mute" style={{ marginBottom: "var(--sp-xl)" }}>
        Connect your Google account to let agents manage your <strong>Calendar</strong>, schedule <strong>Meet</strong> calls, and send <strong>Gmail</strong> messages.
      </p>

      {loading ? (
        <div className="skeleton skeleton-text" style={{ width: "60%" }} />
      ) : connected ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", padding: "var(--sp-md)", background: "rgba(0,217,146,0.08)", border: "1px solid rgba(0,217,146,0.25)", borderRadius: "var(--radius-sm)" }}>
            <CheckCircle size={14} color="var(--color-primary)" />
            <div>
              <div className="body-sm-strong" style={{ color: "var(--color-primary)" }}>Connected</div>
              {status?.email && <div className="caption">{status.email}</div>}
            </div>
          </div>
          <div style={{ display: "flex", gap: "var(--sp-sm)", flexWrap: "wrap" }}>
            {["📅 Calendar & Meet", "✉️ Gmail Send & Read"].map(s => (
              <span key={s} className="badge badge-gray" style={{ fontSize: 11 }}>{s}</span>
            ))}
          </div>
          <div style={{ display: "flex", gap: "var(--sp-md)", justifyContent: "flex-end" }}>
            <button className="btn btn-ghost btn-sm" onClick={handleDisconnect} disabled={disconnecting}
              style={{ color: "var(--color-danger)", borderColor: "rgba(248,113,113,0.3)" }}>
              {disconnecting ? <Loader2 size={13} className="animate-spin" /> : null}
              Disconnect
            </button>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", padding: "var(--sp-md)", background: "var(--color-canvas-raised)", border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-sm)" }}>
            <AlertTriangle size={14} color="var(--color-mute)" />
            <div className="caption">No Google account connected</div>
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button id="connect-google" className="btn btn-primary btn-sm" onClick={handleConnect}
              style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
              <svg width="14" height="14" viewBox="0 0 48 48">
                <path fill="#fff" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
              </svg>
              Connect Google Account
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── API Keys Card ─────────────────────────────────────────────────────────────

const PROVIDER_FIELDS = [
  { key: "openai", label: "OpenAI", placeholder: "sk-proj-..." },
  { key: "anthropic", label: "Anthropic", placeholder: "sk-ant-api03-..." },
  { key: "google", label: "Google Gemini", placeholder: "AIzaSy..." },
  { key: "openrouter", label: "OpenRouter", placeholder: "sk-or-v1-..." },
  { key: "nvidia", label: "NVIDIA", placeholder: "nvapi-..." },
  { key: "tavily", label: "Tavily (Web Search)", placeholder: "tvly-..." },
];

function ApiKeysCard({ onToast }: { onToast: (msg: string, type: any) => void }) {
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [ollamaUrl, setOllamaUrl] = useState("");
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getAppConfig()
      .then((cfg: any) => { setKeys(cfg.api_keys || {}); setOllamaUrl(cfg.providers?.ollama_base_url || ""); })
      .catch(() => { })
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateAppConfig({ api_keys: keys, providers: { ollama_base_url: ollamaUrl } });
      onToast("API keys saved & router reloaded ✓", "success");
    } catch {
      onToast("Failed to save settings", "error");
    } finally { setSaving(false); }
  };

  return (
    <div className="card" style={{ marginBottom: "var(--sp-xl)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: "var(--sp-lg)" }}>
        <Key size={16} color="var(--color-primary)" />
        <h3 className="display-sm">API Keys &amp; Providers</h3>
      </div>
      <p className="body-sm text-mute" style={{ marginBottom: "var(--sp-xl)" }}>
        Keys are saved to{" "}
        <code style={{ background: "var(--color-canvas-raised)", padding: "1px 6px", borderRadius: 4, fontSize: 12 }}>.carole/config.json</code>
        {" "}and hot-reloaded — no server restart needed.
      </p>

      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {[1, 2, 3].map(i => <div key={i} className="skeleton skeleton-text" />)}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
          {PROVIDER_FIELDS.map(({ key, label, placeholder }) => (
            <div key={key} className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">{label}</label>
              <div style={{ position: "relative" }}>
                <input
                  id={`apikey-${key}`}
                  className="input"
                  type={visible[key] ? "text" : "password"}
                  placeholder={placeholder}
                  value={keys[key] || ""}
                  onChange={e => setKeys(k => ({ ...k, [key]: e.target.value }))}
                  style={{ paddingRight: 40 }}
                />
                <button
                  type="button"
                  onClick={() => setVisible(v => ({ ...v, [key]: !v[key] }))}
                  style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "var(--color-mute)", padding: 0 }}
                >
                  {visible[key] ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>
          ))}

          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Ollama Base URL</label>
            <input id="ollama-url" className="input" type="text" placeholder="http://localhost:11434/v1"
              value={ollamaUrl} onChange={e => setOllamaUrl(e.target.value)} />
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "var(--sp-sm)" }}>
            <button id="save-api-keys" className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save Configuration
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Health Card ───────────────────────────────────────────────────────────────

function HealthCard({ teamId }: { teamId: string | null }) {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [wsStatus, setWsStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [h, ws] = await Promise.all([
        api.healthCheck(),
        teamId ? api.wsStatus(teamId) : Promise.resolve(null),
      ]);
      setHealth(h); setWsStatus(ws);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [teamId]);

  useEffect(() => { refresh(); }, [refresh]);
  const isOk = health?.status === "ok";

  return (
    <div className="card" style={{ marginBottom: "var(--sp-xl)" }}>
      <div className="flex-between" style={{ marginBottom: "var(--sp-lg)" }}>
        <h3 className="display-sm">System Health</h3>
        <button className="btn btn-icon btn-ghost btn-sm" onClick={refresh} disabled={loading} title="Refresh">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="skeleton skeleton-text" /><div className="skeleton skeleton-text" style={{ width: "70%" }} />
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "var(--sp-md)" }}>
          {[
            { label: "API Status", value: health?.status || "—", ok: isOk },
            { label: "Tools", value: health?.tools_registered ?? "—", ok: true },
            { label: "WS Connections", value: wsStatus?.connections ?? (teamId ? "—" : "N/A"), ok: true },
          ].map(r => (
            <div key={r.label} style={{ background: "var(--color-canvas-raised)", border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-sm)", padding: "var(--sp-md)" }}>
              <div className="caption" style={{ marginBottom: 4 }}>{r.label}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                {r.ok ? <CheckCircle size={13} color="var(--color-primary)" /> : <AlertTriangle size={13} color="var(--color-danger)" />}
                <span className="body-sm-strong">{String(r.value)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Usage Card ────────────────────────────────────────────────────────────────

function UsageCard({ projectId }: { projectId: string }) {
  const [usage, setUsage] = useState<UsageData | null>(null);
  useEffect(() => { api.getProjectUsage(projectId).then(setUsage).catch(() => { }); }, [projectId]);
  if (!usage) return null;
  const stats = [
    { label: "Messages", value: usage.total_messages ?? 0 },
    { label: "Tasks", value: usage.total_tasks ?? 0 },
    { label: "Agents", value: usage.total_agents ?? 0 },
  ];
  return (
    <div className="card" style={{ marginBottom: "var(--sp-xl)" }}>
      <h3 className="display-sm" style={{ marginBottom: "var(--sp-lg)" }}>Project Usage</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "var(--sp-md)" }}>
        {stats.map(s => (
          <div key={s.label} style={{ textAlign: "center", padding: "var(--sp-lg)", background: "var(--color-canvas-raised)", borderRadius: "var(--radius-sm)", border: "1px solid var(--color-hairline)" }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: "var(--color-primary)" }}>{s.value.toLocaleString()}</div>
            <div className="caption">{s.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Knowledge Upload ──────────────────────────────────────────────────────────

function KnowledgeUpload({ projectId, teamId, onToast }: { projectId: string; teamId: string | null; onToast: any }) {
  const [uploading, setUploading] = useState(false);
  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    setUploading(true);
    try { await api.uploadKnowledgeFile(projectId, teamId, file); onToast(`Uploaded "${file.name}"`, "success"); }
    catch { onToast("Upload failed", "error"); }
    finally { setUploading(false); e.target.value = ""; }
  };
  return (
    <div className="card" style={{ marginBottom: "var(--sp-xl)" }}>
      <h3 className="display-sm" style={{ marginBottom: "var(--sp-sm)" }}>Knowledge Upload</h3>
      <p className="body-sm text-mute" style={{ marginBottom: "var(--sp-lg)" }}>Upload documents for agents to reference during tasks.</p>
      <label style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)", padding: "var(--sp-lg)", border: "2px dashed var(--color-hairline)", borderRadius: "var(--radius-md)", cursor: "pointer", transition: "border-color var(--t-fast)" }}
        onMouseEnter={e => (e.currentTarget.style.borderColor = "var(--color-primary)")}
        onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--color-hairline)")}>
        {uploading ? <Loader2 size={20} className="animate-spin" color="var(--color-primary)" /> : <Upload size={20} color="var(--color-mute)" />}
        <div>
          <div className="body-sm-strong">{uploading ? "Uploading…" : "Click to upload"}</div>
          <div className="caption">PDF, TXT, MD, DOCX supported</div>
        </div>
        <input type="file" style={{ display: "none" }} accept=".pdf,.txt,.md,.docx" onChange={handleFile} disabled={uploading} />
      </label>
    </div>
  );
}

// ── Agent Runtime Settings Card ────────────────────────────────────────────────
function AgentRuntimeCard({ onToast }: { onToast: (msg: string, type: any) => void }) {
  const [settings, setSettings] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getAppConfig()
      .then((cfg: any) => setSettings(cfg.agent_settings || {}))
      .catch(() => { })
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateAppConfig({ agent_settings: settings });
      onToast("Agent runtime settings saved ✓", "success");
    } catch {
      onToast("Failed to save agent runtime settings", "error");
    } finally { setSaving(false); }
  };

  const fields = [
    { key: "MAX_LOOPS", label: "Max Agent Loops", default: 10 },
    { key: "APPROVAL_TIMEOUT_SECS", label: "Approval Timeout (sec)", default: 300 },
    { key: "MAX_QUEUE_SIZE", label: "Max Event Queue Size", default: 500 },
    { key: "DREAM_INTERVAL_MINUTES", label: "Dream Interval (min)", default: 15 },
    { key: "MEMORY_RETRIEVAL_LIMIT", label: "Memory Retrieval Limit", default: 3 },
    { key: "CONTEXT_COMPACTION_THRESHOLD", label: "Context Compaction Threshold", default: 15 },
  ];

  return (
    <div className="card" style={{ marginBottom: "var(--sp-xl)" }}>
      <h3 className="display-sm" style={{ marginBottom: "var(--sp-lg)" }}>Agent Runtime & Memory Settings</h3>
      <p className="body-sm text-mute" style={{ marginBottom: "var(--sp-xl)" }}>
        Configure execution limits, timeouts, and background processing intervals. Leave blank to use defaults.
      </p>

      {loading ? (
        <div className="skeleton skeleton-text" style={{ width: "60%" }} />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--sp-md)" }}>
            {fields.map(f => (
              <div key={f.key} className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">{f.label}</label>
                <input
                  type="number"
                  className="input"
                  placeholder={`Default: ${f.default}`}
                  value={settings[f.key] || ""}
                  onChange={e => setSettings(d => ({ ...d, [f.key]: parseInt(e.target.value) || f.default }))}
                />
              </div>
            ))}
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "var(--sp-sm)" }}>
            <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save Settings
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Browser Automation Card ────────────────────────────────────────────────────────
function BrowserAutomationCard({ onToast }: { onToast: (msg: string, type: any) => void }) {
  const [settings, setSettings] = useState<any>({ provider: "local", api_keys: {} });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getAppConfig()
      .then((cfg: any) => setSettings(cfg.browser_automation || { provider: "local", api_keys: {} }))
      .catch(() => { })
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateAppConfig({ browser_automation: settings });
      onToast("Browser automation settings saved ✓", "success");
    } catch {
      onToast("Failed to save browser automation settings", "error");
    } finally { setSaving(false); }
  };

  return (
    <div className="card" style={{ marginBottom: "var(--sp-xl)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: "var(--sp-lg)" }}>
        <Globe size={16} color="var(--color-primary)" />
        <h3 className="display-sm">Browser Automation & Anti-Bot Settings</h3>
      </div>
      <p className="body-sm text-mute" style={{ marginBottom: "var(--sp-md)" }}>
        Configure external providers to bypass CAPTCHAs and bot protection during web scraping.
      </p>
      <div className="callout callout-info" style={{ marginBottom: "var(--sp-xl)" }}>
        <strong>Note:</strong> By default, the local browser uses stealth mode. Only external proxy providers (Browserbase, ScraperAPI, ZenRows) will automatically handle advanced CAPTCHA solving.
      </div>

      {loading ? (
        <div className="skeleton skeleton-text" style={{ width: "60%" }} />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
          <div className="form-group">
            <label className="form-label">Active Provider</label>
            <select
              className="input"
              value={settings.provider || "local"}
              onChange={e => setSettings((d: any) => ({ ...d, provider: e.target.value }))}
            >
              <option value="local">Local Playwright (Default Stealth)</option>
              <option value="browserbase">Browserbase (Hosted Headless Browser)</option>
              <option value="scraperapi">ScraperAPI (Proxy API)</option>
              <option value="zenrows">ZenRows (Proxy API)</option>
            </select>
          </div>

          {settings.provider === "browserbase" && (
            <div className="form-group">
              <label className="form-label">Browserbase API Key</label>
              <input
                type="password"
                className="input"
                placeholder="sk-..."
                value={settings.api_keys?.browserbase || ""}
                onChange={e => setSettings((d: any) => ({ ...d, api_keys: { ...d.api_keys, browserbase: e.target.value } }))}
              />
            </div>
          )}

          {settings.provider === "scraperapi" && (
            <div className="form-group">
              <label className="form-label">ScraperAPI Key</label>
              <input
                type="password"
                className="input"
                value={settings.api_keys?.scraperapi || ""}
                onChange={e => setSettings((d: any) => ({ ...d, api_keys: { ...d.api_keys, scraperapi: e.target.value } }))}
              />
            </div>
          )}

          {settings.provider === "zenrows" && (
            <div className="form-group">
              <label className="form-label">ZenRows API Key</label>
              <input
                type="password"
                className="input"
                value={settings.api_keys?.zenrows || ""}
                onChange={e => setSettings((d: any) => ({ ...d, api_keys: { ...d.api_keys, zenrows: e.target.value } }))}
              />
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "var(--sp-sm)" }}>
            <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save Settings
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Cost Management Card ────────────────────────────────────────────────────────

function CostManagementCard({ projectId, onToast }: { projectId: string; onToast: (msg: string, type: any) => void }) {
  const [costStats, setCostStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [budgetLimit, setBudgetLimit] = useState<string>("");

  const fetchCostStats = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getCostStats(projectId);
      setCostStats(data);
      setBudgetLimit(data.budget_limit_usd !== null && data.budget_limit_usd !== undefined ? String(data.budget_limit_usd) : "");
    } catch {
      // Ignore errors
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchCostStats();
  }, [fetchCostStats]);

  const handleSaveBudget = async () => {
    setSaving(true);
    try {
      await api.updateBudget({
        project_id: projectId,
        budget_limit_usd: budgetLimit ? parseFloat(budgetLimit) : null
      });
      onToast("Budget limit updated", "success");
      fetchCostStats();
    } catch {
      onToast("Failed to update budget limit", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card" style={{ marginBottom: "var(--sp-xl)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: "var(--sp-lg)" }}>
        <DollarSign size={16} color="var(--color-primary)" />
        <h3 className="display-sm">Cost Management & Tracking</h3>
      </div>
      <p className="body-sm text-mute" style={{ marginBottom: "var(--sp-xl)" }}>
        Track real-time API token usage and total expenditure across all models in this project.
      </p>

      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {[1, 2, 3].map(i => <div key={i} className="skeleton skeleton-text" />)}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
          {costStats && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "var(--sp-md)", marginBottom: "var(--sp-md)" }}>
              <div style={{ padding: "var(--sp-md)", background: "var(--color-canvas-raised)", border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-sm)" }}>
                <div className="caption">Total Spend</div>
                <div style={{ fontSize: 18, fontWeight: 600, color: "var(--color-primary)" }}>${costStats.total_spend_usd?.toFixed(4) || "0.0000"}</div>
              </div>
              <div style={{ padding: "var(--sp-md)", background: "var(--color-canvas-raised)", border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-sm)" }}>
                <div className="caption">Total Tokens</div>
                <div style={{ fontSize: 18, fontWeight: 600 }}>{costStats.total_tokens?.toLocaleString() || "0"}</div>
              </div>
              <div style={{ padding: "var(--sp-md)", background: "var(--color-canvas-raised)", border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-sm)" }}>
                <div className="caption">Prompt Tokens</div>
                <div style={{ fontSize: 18, fontWeight: 600 }}>{costStats.total_prompt_tokens?.toLocaleString() || "0"}</div>
              </div>
              <div style={{ padding: "var(--sp-md)", background: "var(--color-canvas-raised)", border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-sm)" }}>
                <div className="caption">Completion Tokens</div>
                <div style={{ fontSize: 18, fontWeight: 600 }}>{costStats.total_completion_tokens?.toLocaleString() || "0"}</div>
              </div>
            </div>
          )}

          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Budget Limit (USD)</label>
            <div style={{ display: "flex", gap: "var(--sp-sm)" }}>
              <input
                className="input"
                type="number"
                step="0.01"
                placeholder="No limit"
                value={budgetLimit}
                onChange={e => setBudgetLimit(e.target.value)}
                style={{ maxWidth: 200 }}
              />
              <button className="btn btn-primary btn-sm" onClick={handleSaveBudget} disabled={saving}>
                {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save Budget
              </button>
            </div>
          </div>
          {costStats?.budget_limit_usd && costStats.total_spend_usd > costStats.budget_limit_usd && (
            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", padding: "var(--sp-md)", background: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.3)", borderRadius: "var(--radius-sm)", color: "var(--color-danger)" }}>
              <AlertTriangle size={14} />
              <div className="body-sm-strong">Warning: Budget Limit Exceeded!</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Default Models Card ────────────────────────────────────────────────────────

function DefaultModelsCard({ onToast }: { onToast: (msg: string, type: any) => void }) {
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [catalog, setCatalog] = useState<Record<string, any>>({});

  useEffect(() => {
    Promise.all([api.getAppConfig(), api.getModelCatalog()])
      .then(([cfg, cat]: [any, any]) => {
        setDefaults(cfg.default_models || {});
        setCatalog(cat);
      })
      .catch(() => { })
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateAppConfig({ default_models: defaults });
      onToast("Default models saved ✓", "success");
    } catch {
      onToast("Failed to save defaults", "error");
    } finally { setSaving(false); }
  };

  return (
    <div className="card" style={{ marginBottom: "var(--sp-xl)" }}>
      <h3 className="display-sm" style={{ marginBottom: "var(--sp-lg)" }}>Global Model Defaults</h3>
      <p className="body-sm text-mute" style={{ marginBottom: "var(--sp-xl)" }}>
        These models are used as system-wide defaults (e.g. for the Judge agent, or fallback generation).
      </p>

      {loading ? (
        <div className="skeleton skeleton-text" style={{ width: "60%" }} />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
          {["DEFAULT_FAST_MODEL", "DEFAULT_SMART_MODEL", "DEFAULT_CODER_MODEL", "DEFAULT_JUDGE_MODEL"].map(key => (
            <div key={key} className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">{key.replace("DEFAULT_", "").replace("_MODEL", "")} Model</label>
              <select
                className="input"
                value={defaults[key] || ""}
                onChange={e => setDefaults(d => ({ ...d, [key]: e.target.value }))}
              >
                <option value="">-- Use Environment Variable --</option>
                {Object.entries(catalog).map(([providerId, provider]: [string, any]) => (
                  <optgroup key={providerId} label={provider.label || providerId}>
                    {provider.models?.map((m: any, idx: number) => (
                      <option key={`${m.value}-${idx}`} value={m.value}>
                        {m.label || m.value}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>
          ))}

          <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "var(--sp-sm)" }}>
            <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save Defaults
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Prompt Blocks Editor ────────────────────────────────────────────────────

const CATEGORY_ORDER = ["Memory", "Filesystem", "Automation", "Browser"];

const BLOCK_VARS: Record<string, string[]> = {
  workspace_paths: ["{carole_dir}"],
};

function PromptBlocksEditor({ onToast }: { onToast: (msg: string, type: any) => void }) {
  const [blocks, setBlocks] = useState<PromptBlock[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [dirty, setDirty] = useState<Record<string, { enabled: boolean; content: string }>>({});

  useEffect(() => {
    api.getPromptBlocks()
      .then(setBlocks)
      .catch(() => onToast("Failed to load prompt blocks", "error"))
      .finally(() => setLoading(false));
  }, []);

  const patch = (key: string, field: "enabled" | "content", value: any) => {
    const block = blocks.find(b => b.key === key);
    if (!block) return;
    setDirty(d => ({
      ...d,
      [key]: {
        enabled: field === "enabled" ? value : (d[key]?.enabled ?? block.enabled),
        content: field === "content" ? value : (d[key]?.content ?? block.content),
      },
    }));
  };

  const handleSaveAll = async () => {
    if (!Object.keys(dirty).length) return;
    setSaving(true);
    try {
      const updates = Object.entries(dirty).map(([key, val]) => ({ key, ...val }));
      const updated = await api.savePromptBlocks(updates);
      setBlocks(updated);
      setDirty({});
      onToast("Prompt blocks saved successfully", "success");
    } catch {
      onToast("Failed to save prompt blocks", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async (key: string) => {
    try {
      const updated = await api.resetPromptBlock(key);
      setBlocks(prev => prev.map(b => b.key === key ? { ...b, ...updated, content: updated.content, enabled: updated.enabled, is_customized: false } : b));
      setDirty(d => { const n = { ...d }; delete n[key]; return n; });
      onToast(`"${key}" reset to default`, "success");
    } catch {
      onToast("Failed to reset block", "error");
    }
  };

  if (loading) return <div className="skeleton skeleton-text" style={{ width: "60%", marginTop: "var(--sp-md)" }} />;

  const grouped = CATEGORY_ORDER.map(cat => ({
    cat,
    items: blocks.filter(b => b.category === cat),
  })).filter(g => g.items.length > 0);

  const hasDirty = Object.keys(dirty).length > 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-xl)" }}>
      <div style={{ background: "var(--color-bg-secondary)", border: "1px solid var(--color-hairline)", borderRadius: 8, padding: "var(--sp-md) var(--sp-lg)" }}>
        <p className="text-secondary" style={{ fontSize: "0.82rem", margin: 0, lineHeight: 1.5 }}>
          ⚙️ <strong>System Capability Blocks </strong> are automatically appended to every agent&apos;s context.
          Toggle any capability on or off with 1 click, or click <strong>Customize Prompt</strong> to fine-tune the instructions.
        </p>
      </div>

      {grouped.map(({ cat, items }) => (
        <div key={cat}>
          <div style={{ fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--color-text-tertiary)", marginBottom: "var(--sp-sm)" }}>
            {cat}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-sm)" }}>
            {items.map(block => {
              const override = dirty[block.key];
              const enabled = override ? override.enabled : block.enabled;
              const content = override ? override.content : block.content;
              const isOpen = !!expanded[block.key];
              const isModified = !!override || block.is_customized;
              const requiredVars = BLOCK_VARS[block.key] || [];
              const missingVars = requiredVars.filter(v => !content.includes(v));

              return (
                <div
                  key={block.key}
                  className="card"
                  style={{
                    padding: "var(--sp-lg)",
                    border: `1px solid ${isModified ? "var(--color-brand-primary)" : "var(--color-hairline)"}`,
                    opacity: enabled ? 1 : 0.6,
                    transition: "all 0.2s ease",
                  }}
                >
                  {/* Header Row */}
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)", justifyContent: "space-between" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)", flex: 1, minWidth: 0 }}>
                      {/* Toggle Switch */}
                      <button
                        onClick={() => patch(block.key, "enabled", !enabled)}
                        style={{
                          background: "none",
                          border: "none",
                          cursor: "pointer",
                          padding: 0,
                          color: enabled ? "var(--color-brand-primary)" : "var(--color-text-tertiary)",
                          flexShrink: 0,
                          display: "flex",
                          alignItems: "center",
                        }}
                        title={enabled ? "Click to disable this capability" : "Click to enable this capability"}
                      >
                        {enabled ? <ToggleRight size={28} /> : <ToggleLeft size={28} />}
                      </button>

                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", flexWrap: "wrap" }}>
                          <span style={{ fontWeight: 600, fontSize: "0.88rem" }}>{block.display_name}</span>

                          {/* Status Pills */}
                          <span
                            style={{
                              fontSize: "0.68rem",
                              padding: "1px 6px",
                              borderRadius: 4,
                              background: enabled ? "rgba(16, 185, 129, 0.15)" : "rgba(107, 114, 128, 0.15)",
                              color: enabled ? "var(--color-success)" : "var(--color-text-tertiary)",
                              border: `1px solid ${enabled ? "rgba(16, 185, 129, 0.3)" : "rgba(107, 114, 128, 0.3)"}`,
                              fontWeight: 500,
                            }}
                          >
                            {enabled ? "Active" : "Disabled"}
                          </span>

                          {isModified && (
                            <span style={{ fontSize: "0.68rem", padding: "1px 6px", borderRadius: 4, background: "var(--color-brand-primary)", color: "#fff", fontWeight: 500 }}>
                              customized
                            </span>
                          )}

                          {/* Required Variables Badge */}
                          {requiredVars.map(v => (
                            <span
                              key={v}
                              style={{
                                fontSize: "0.68rem",
                                padding: "1px 6px",
                                borderRadius: 4,
                                fontFamily: "var(--font-mono, monospace)",
                                background: "rgba(99, 102, 241, 0.12)",
                                color: "var(--color-brand-primary)",
                                border: "1px solid rgba(99, 102, 241, 0.25)",
                              }}
                            >
                              Variable: {v}
                            </span>
                          ))}
                        </div>

                        <div className="text-secondary" style={{ fontSize: "0.78rem", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {block.description}
                        </div>
                      </div>
                    </div>

                    {/* Actions */}
                    <div style={{ display: "flex", gap: "var(--sp-sm)", flexShrink: 0, alignItems: "center" }}>
                      {(block.is_customized || override) && (
                        <button
                          className="btn btn-ghost btn-sm"
                          style={{ gap: "var(--sp-xs)", fontSize: "0.78rem" }}
                          onClick={() => handleReset(block.key)}
                          title="Reset to default prompt"
                        >
                          <RotateCcw size={12} /> Reset
                        </button>
                      )}
                      <button
                        className={`btn btn-sm ${isOpen ? "btn-secondary" : "btn-ghost"}`}
                        style={{ gap: "var(--sp-xs)", fontSize: "0.78rem" }}
                        onClick={() => setExpanded(e => ({ ...e, [block.key]: !e[block.key] }))}
                      >
                        {isOpen ? (
                          <>
                            <ChevronUp size={13} /> Hide Prompt
                          </>
                        ) : (
                          <>
                            <ChevronDown size={13} /> Customize Prompt
                          </>
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Expandable Editor (Progressive Disclosure) */}
                  {isOpen && (
                    <div style={{ marginTop: "var(--sp-md)", paddingTop: "var(--sp-md)", borderTop: "1px solid var(--color-hairline)" }}>
                      <textarea
                        value={content}
                        onChange={e => patch(block.key, "content", e.target.value)}
                        rows={Math.min(18, Math.max(6, content.split("\n").length + 2))}
                        spellCheck={false}
                        style={{
                          width: "100%",
                          boxSizing: "border-box",
                          fontFamily: "var(--font-mono, 'Fira Code', monospace)",
                          fontSize: "0.78rem",
                          lineHeight: 1.6,
                          background: "var(--color-bg-tertiary)",
                          border: `1px solid ${missingVars.length > 0 ? "var(--color-warning)" : "var(--color-hairline)"}`,
                          borderRadius: 6,
                          padding: "var(--sp-md)",
                          color: "var(--color-text-primary)",
                          resize: "vertical",
                        }}
                      />

                      {/* Missing Variable Warning */}
                      {missingVars.length > 0 && (
                        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-xs)", color: "var(--color-warning)", fontSize: "0.76rem", marginTop: "var(--sp-xs)" }}>
                          <AlertTriangle size={13} />
                          <span>
                            Warning: Required placeholder <code>{missingVars.join(", ")}</code> is missing from the text.
                          </span>
                        </div>
                      )}

                      {block.key === "workspace_paths" && missingVars.length === 0 && (
                        <p className="text-secondary" style={{ fontSize: "0.75rem", marginTop: "var(--sp-xs)", marginBottom: 0 }}>
                          💡 <code>{`{carole_dir}`}</code> will be automatically replaced at runtime with the scoped project+team path.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "var(--sp-sm)" }}>
        <button className="btn btn-primary btn-sm" onClick={handleSaveAll} disabled={saving || !hasDirty} style={{ gap: "var(--sp-sm)" }}>
          {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
          Save Changes{hasDirty ? ` (${Object.keys(dirty).length})` : ""}
        </button>
      </div>
    </div>
  );
}

// ── Prompts Configuration Section ────────────────────────────────────────────

function PromptsConfigSection({ onToast }: { onToast: (msg: string, type: any) => void }) {
  const [promptSubTab, setPromptSubTab] = useState<"roles" | "capabilities">("roles");

  return (
    <div style={{ marginBottom: "var(--sp-xl)" }}>
      {/* Sub-navigation switcher for Prompts */}
      <div
        style={{
          display: "inline-flex",
          gap: "var(--sp-xs)",
          marginBottom: "var(--sp-md)",
          background: "var(--color-bg-secondary)",
          padding: "4px",
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--color-hairline)",
        }}
      >
        <button
          className={`btn btn-xs ${promptSubTab === "roles" ? "btn-primary" : "btn-ghost"}`}
          style={{ borderRadius: "var(--radius-sm)", gap: "var(--sp-xs)" }}
          onClick={() => setPromptSubTab("roles")}
        >
          🎭 Roles &amp; Personas
        </button>
        <button
          className={`btn btn-xs ${promptSubTab === "capabilities" ? "btn-primary" : "btn-ghost"}`}
          style={{ borderRadius: "var(--radius-sm)", gap: "var(--sp-xs)" }}
          onClick={() => setPromptSubTab("capabilities")}
        >
          ⚙️ System Capabilities
        </button>
      </div>

      {/* Prompts Content */}
      {promptSubTab === "roles" && <PromptsEditor onToast={onToast} />}
      {promptSubTab === "capabilities" && (
        <div className="card" style={{ marginBottom: "var(--sp-xl)" }}>
          <div className="flex-between" style={{ marginBottom: "var(--sp-md)" }}>
            <div>
              <h3 className="display-sm">System Capabilities</h3>
              <p className="caption" style={{ marginTop: 2 }}>
                Modular capability prompts injected into agent context. Toggle on/off or customize.
              </p>
            </div>
          </div>
          <PromptBlocksEditor onToast={onToast} />
        </div>
      )}
    </div>
  );
}

// ── Main ─────────────────────────────────────────────────────────────────────

export default function SettingsPanel({ teamId, projectId, onToast, onTeamDeleted, onProjectDeleted }: Props) {
  const { user } = useAuth();
  const [confirmDelete, setConfirmDelete] = useState<"team" | "project" | null>(null);
  const [deleting, setDeleting] = useState(false);

  const handleDeleteTeam = async (deleteContent: boolean) => {
    if (!teamId) return; setDeleting(true);
    try { await api.deleteTeam(teamId, deleteContent); onTeamDeleted(); onToast("Team deleted", "success"); }
    catch { onToast("Failed to delete team", "error"); }
    finally { setDeleting(false); setConfirmDelete(null); }
  };
  const handleDeleteProject = async (deleteContent: boolean) => {
    if (!projectId) return; setDeleting(true);
    try { await api.deleteProject(projectId, deleteContent); onProjectDeleted(); onToast("Project deleted", "success"); }
    catch { onToast("Failed to delete project", "error"); }
    finally { setDeleting(false); setConfirmDelete(null); }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflowY: "auto", padding: "var(--sp-2xl)" }}>
      <h2 className="display-md" style={{ marginBottom: "var(--sp-3xl)", display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
        <Settings size={20} /> Settings
      </h2>

      {user && (
        <div className="card" style={{ marginBottom: "var(--sp-xl)" }}>
          <h3 className="display-sm" style={{ marginBottom: "var(--sp-lg)" }}>Profile</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--sp-md)" }}>
            <div className="form-group"><label className="form-label">First Name</label><input className="input" value={user.first_name || ""} readOnly /></div>
            <div className="form-group"><label className="form-label">Last Name</label><input className="input" value={user.last_name || ""} readOnly /></div>
            <div className="form-group" style={{ gridColumn: "span 2" }}><label className="form-label">Email</label><input className="input" value={user.email} readOnly /></div>
          </div>
        </div>
      )}

      <GoogleAccountCard onToast={onToast} />
      <ApiKeysCard onToast={onToast} />
      <DefaultModelsCard onToast={onToast} />
      <AgentRuntimeCard onToast={onToast} />
      <BrowserAutomationCard onToast={onToast} />

      {/* ── Prompts & Behavior ── */}
      <PromptsConfigSection onToast={onToast} />

      {/* ── Access Control & Safety Defaults ── */}
      <GlobalAccessControlCard onToast={onToast} />

      {/* ── Model Catalog (Standalone Card) ── */}
      <ModelCatalogEditor onToast={onToast} />

      <HealthCard teamId={teamId} />
      {projectId && <UsageCard projectId={projectId} />}
      {projectId && <CostManagementCard projectId={projectId} onToast={onToast} />}
      {projectId && <KnowledgeUpload projectId={projectId} teamId={teamId} onToast={onToast} />}



      <div className="card card-danger" style={{ marginBottom: "var(--sp-xl)", borderRadius: "var(--radius-md)", padding: "var(--sp-2xl)" }}>
        <h3 className="display-sm text-danger" style={{ marginBottom: "var(--sp-md)" }}>Danger Zone</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
          {teamId && (
            <div className="flex-between" style={{ padding: "var(--sp-md)", border: "1px solid rgba(248,113,113,0.2)", borderRadius: "var(--radius-sm)" }}>
              <div><div className="body-sm-strong">Delete Team</div><div className="caption">Permanently delete this team and all its messages.</div></div>
              <button className="btn btn-danger btn-sm" onClick={() => setConfirmDelete("team")}><Trash2 size={13} /> Delete Team</button>
            </div>
          )}
          {projectId && (
            <div className="flex-between" style={{ padding: "var(--sp-md)", border: "1px solid rgba(248,113,113,0.2)", borderRadius: "var(--radius-sm)" }}>
              <div><div className="body-sm-strong">Delete Project</div><div className="caption">Permanently delete this project and all associated data.</div></div>
              <button className="btn btn-danger btn-sm" onClick={() => setConfirmDelete("project")}><Trash2 size={13} /> Delete Project</button>
            </div>
          )}
        </div>
      </div>

      <Modal open={!!confirmDelete} onClose={() => setConfirmDelete(null)} title="Confirm Deletion" maxWidth={450}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-lg)" }}>
          <p className="body-sm">
            This action <strong>cannot be undone</strong>. You can choose to only delete the {confirmDelete} record from the database, or additionally delete all associated files and folders on disk.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-sm)", marginTop: "var(--sp-sm)" }}>
            <button
              className="btn btn-danger btn-sm"
              onClick={() => confirmDelete === "team" ? handleDeleteTeam(false) : handleDeleteProject(false)}
              disabled={deleting}
              style={{ width: "100%", justifyContent: "center" }}
            >
              {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />} Delete {confirmDelete} Record Only
            </button>
            <button
              className="btn btn-danger btn-sm"
              onClick={() => confirmDelete === "team" ? handleDeleteTeam(true) : handleDeleteProject(true)}
              disabled={deleting}
              style={{ width: "100%", justifyContent: "center", background: "var(--color-danger-dark)", borderColor: "var(--color-danger-dark)" }}
            >
              {deleting ? <Loader2 size={13} className="animate-spin" /> : <AlertTriangle size={13} />} Delete {confirmDelete} AND Content on Disk
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDelete(null)} disabled={deleting} style={{ width: "100%", justifyContent: "center", marginTop: "var(--sp-xs)" }}>
              Cancel
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
