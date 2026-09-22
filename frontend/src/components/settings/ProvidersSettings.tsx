"use client";
import React, { useState, useEffect, useCallback } from "react";
import { Key, Eye, EyeOff, Save, Loader2, Cpu, CheckCircle, Sparkles, Globe, Terminal } from "lucide-react";
import { api } from "@/hooks/useApi";
import SettingTooltip from "./SettingTooltip";

interface Props {
  onToast: (msg: string, type: "success" | "error" | "info") => void;
}

interface ProviderField {
  key: string;
  label: string;
  placeholder: string;
  description?: string;
  why: string;
  how: string;
}

const PROVIDER_FIELDS: ProviderField[] = [
  {
    key: "openai",
    label: "OpenAI",
    placeholder: "sk-proj-...",
    description: "GPT-4o, GPT-4o-mini, o1, o3-mini",
    why: "Enables top-tier reasoning, vision parsing, and reliable tool calling.",
    how: "Used when agents are assigned OpenAI models for code generation, vision, or autonomous planning.",
  },
  {
    key: "anthropic",
    label: "Anthropic",
    placeholder: "sk-ant-api03-...",
    description: "Claude 3.5 Sonnet, Claude 3.7 Sonnet, Claude 3.5 Haiku",
    why: "Industry gold standard for complex coding tasks, architecture design, and nuanced reasoning.",
    how: "Powers coding agents and DOM analysis where high precision and safety are paramount.",
  },
  {
    key: "google",
    label: "Google Gemini",
    placeholder: "AIzaSy...",
    description: "Gemini 2.0 Flash, Gemini 1.5 Pro, Flash Thinking",
    why: "Massive context windows (up to 2M tokens) and ultra-fast generation with multimodal capabilities.",
    how: "Ideal for full-repo codebase ingestion, extensive document analysis, and speedy sub-agent routines.",
  },
  {
    key: "openrouter",
    label: "OpenRouter",
    placeholder: "sk-or-v1-...",
    description: "Universal LLM gateway covering DeepSeek R1, Llama 3, Qwen",
    why: "Provides unified access to dozens of open-source and proprietary models through a single API key.",
    how: "Routes requests to models like DeepSeek-R1, Meta Llama 3, and Qwen without managing multiple accounts.",
  },
  {
    key: "nvidia",
    label: "NVIDIA NIM",
    placeholder: "nvapi-...",
    description: "High-throughput hosted open-source models",
    why: "Enterprise-grade accelerated inference for open-weights models.",
    how: "Enables fast response times for agent thoughts and background loop iterations.",
  },
  {
    key: "tavily",
    label: "Tavily (Search)",
    placeholder: "tvly-...",
    description: "High-accuracy live web search & grounding engine",
    why: "Optimized for LLM agents to fetch real-time, clean, pre-parsed search results from the web.",
    how: "Called automatically by the web search tool to ground answers with latest documentation and live facts.",
  },
  {
    key: "browseruse",
    label: "Browser Use Cloud",
    placeholder: "Leave blank for free local Playwright...",
    description: "Optional: only if using commercial Browser-Use Cloud. Local runs 100% free with your standard LLM key.",
    why: "Provides hosted cloud execution for browser sessions without consuming local CPU.",
    how: "Offloads heavy browser sessions to Browser-Use's cloud infrastructure if configured.",
  },
];

export default function ProvidersSettings({ onToast }: Props) {
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [ollamaUrl, setOllamaUrl] = useState("");
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [loadError, setLoadError] = useState("");
  const loadConfig = useCallback(() => {
    setLoading(true);
    setLoadError("");
    api.getAppConfig()
      .then((cfg: any) => {
        setKeys(cfg.api_keys || {});
        setOllamaUrl(cfg.providers?.ollama_base_url || "");
      })
      .catch(() => setLoadError("Provider settings could not be loaded. Check your connection and account access, then retry."))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => { loadConfig(); }, [loadConfig]);

  const handleSave = async () => {
    if (loading || saving || loadError) return;
    setSaving(true);
    try {
      await api.updateAppConfig({
        api_keys: keys,
        providers: { ollama_base_url: ollamaUrl },
      });
      onToast("API keys saved & hot-reloaded ✓", "success");
    } catch {
      onToast("Failed to save provider settings", "error");
    } finally {
      setSaving(false);
    }
  };

  const configuredCount = Object.values(keys).filter(k => k && k.trim().length > 0).length + (ollamaUrl ? 1 : 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2xl)" }}>
      {/* ── Header Card ── */}
      <div className="card" style={{ padding: "var(--sp-xl)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--sp-md)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)" }}>
            <div
              style={{
                width: 38,
                height: 38,
                borderRadius: "var(--radius-sm)",
                background: "rgba(79, 70, 229, 0.12)",
                border: "1px solid rgba(79, 70, 229, 0.3)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--color-primary)",
              }}
            >
              <Key size={18} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                <h3 className="display-sm" style={{ margin: 0 }}>API Keys &amp; Model Providers</h3>
                <span className="pill pill-live" style={{ fontSize: 9 }}>
                  {configuredCount} configured
                </span>
              </div>
              <p className="caption text-mute" style={{ margin: 0 }}>
                Connect your providers here. Saved changes apply without restarting the workspace.
              </p>
            </div>
          </div>
        </div>

        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: "var(--sp-lg) 0" }}>
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="skeleton skeleton-text" style={{ height: 36 }} />
            ))}
          </div>
        ) : loadError ? <div role="alert" style={{ display: "grid", gap: 12, padding: 16, border: "1px solid var(--color-hairline)", borderRadius: 12 }}><p className="body-sm">{loadError}</p><button className="btn btn-outline" onClick={loadConfig}>Retry loading settings</button></div> : (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-lg)" }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(280px, 100%), 1fr))", gap: "var(--sp-md)" }}>
              {PROVIDER_FIELDS.map(({ key, label, placeholder, description, why, how }) => {
                const isSet = !!(keys[key] && keys[key].trim().length > 0);
                return (
                  <div
                    key={key}
                    style={{
                      background: "var(--color-canvas-soft)",
                      border: `1px solid ${isSet ? "rgba(99, 102, 241, 0.3)" : "var(--color-hairline)"}`,
                      borderRadius: "var(--radius-sm)",
                      padding: "var(--sp-md) var(--sp-lg)",
                      display: "flex",
                      flexDirection: "column",
                      gap: 6,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <div style={{ display: "flex", alignItems: "center" }}>
                        <label htmlFor={`apikey-${key}`} className="form-label" style={{ fontSize: 11, fontWeight: 600, margin: 0 }}>
                          {label}
                        </label>
                        <SettingTooltip title={`${label} API Key`} why={why} how={how} />
                      </div>
                      {isSet ? (
                        <span style={{ fontSize: 10, color: "var(--color-success)", display: "flex", alignItems: "center", gap: 4 }}>
                          <CheckCircle size={10} /> Active
                        </span>
                      ) : (
                        <span style={{ fontSize: 10, color: "var(--color-mute)" }}>Optional</span>
                      )}
                    </div>
                    <div style={{ position: "relative" }}>
                      <input
                        id={`apikey-${key}`}
                        disabled={saving}
                        autoComplete="off"
                        spellCheck={false}
                        className="input"
                        type={visible[key] ? "text" : "password"}
                        placeholder={placeholder}
                        value={keys[key] || ""}
                        onChange={e => setKeys(k => ({ ...k, [key]: e.target.value }))}
                        style={{ paddingRight: 36, fontSize: 11, fontFamily: "var(--font-mono)" }}
                      />
                      <button
                        type="button"
                        onClick={() => setVisible(v => ({ ...v, [key]: !v[key] }))}
                        style={{
                          position: "absolute",
                          right: 8,
                          top: "50%",
                          transform: "translateY(-50%)",
                          background: "none",
                          border: "none",
                          cursor: "pointer",
                          color: "var(--color-mute)",
                          padding: 2,
                        }}
                        aria-label={`${visible[key] ? "Hide" : "Show"} ${label} API key`}
                        aria-pressed={!!visible[key]}
                        title={visible[key] ? "Hide API key" : "Show API key"}
                      >
                        {visible[key] ? <EyeOff size={13} /> : <Eye size={13} />}
                      </button>
                    </div>
                    {description && (
                      <span className="caption text-mute" style={{ fontSize: 10, lineHeight: 1.2 }}>
                        {description}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>

            {/* ── Ollama Local Instance ── */}
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
                <Terminal size={14} color="var(--color-primary)" style={{ marginRight: 6 }} />
                <label htmlFor="ollama-url" className="form-label" style={{ fontSize: 11, fontWeight: 600, margin: 0 }}>
                  Ollama Local Inference Gateway
                </label>
                <SettingTooltip
                  title="Ollama Base URL"
                  why="Enables 100% private, offline, and cost-free local AI model execution using your own GPU."
                  how="Carole forwards inference calls to your local Ollama instance (default: http://localhost:11434/v1) for any configured open model."
                />
              </div>
              <input
                id="ollama-url"
                disabled={saving}
                className="input"
                type="text"
                placeholder="http://localhost:11434/v1"
                value={ollamaUrl}
                onChange={e => setOllamaUrl(e.target.value)}
                style={{ fontSize: 11, fontFamily: "var(--font-mono)" }}
              />
              <span className="caption text-mute" style={{ fontSize: 10 }}>
                Allows connecting fully local, offline LLMs (Llama 3, DeepSeek, Mistral, Qwen) running on your workstation.
              </span>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "var(--sp-sm)" }}>
              <button id="save-api-keys" className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
                {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save &amp; Reload Configuration
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
