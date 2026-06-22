"use client";
import React, { useState, useEffect, useCallback } from "react";
import {
  Save, Loader2, Plus, Trash2, ChevronDown, ChevronUp,
  GripVertical, AlertCircle, RefreshCw, RotateCcw, AlertTriangle,
} from "lucide-react";
import { api } from "@/hooks/useApi";

interface ModelEntry {
  value: string;
  label: string;
  special?: boolean;
}

interface ProviderData {
  label: string;
  key_name: string | null;
  models: ModelEntry[];
}

type Catalog = Record<string, ProviderData>;

interface Props {
  onToast: (msg: string, type: "success" | "error" | "info") => void;
}

// ── Provider badge colours ────────────────────────────────────────────────────

const PROVIDER_COLORS: Record<string, string> = {
  openrouter: "#7c3aed",
  anthropic:  "#d97706",
  openai:     "#059669",
  google:     "#2563eb",
  nvidia:     "#16a34a",
  ollama:     "#dc2626",
};

function providerColor(id: string) {
  return PROVIDER_COLORS[id] ?? "#6b7280";
}

// ── Model row (editable) ──────────────────────────────────────────────────────

function ModelRow({
  model,
  index,
  onChange,
  onDelete,
}: {
  model: ModelEntry;
  index: number;
  providerId: string;
  onChange: (i: number, field: keyof ModelEntry, v: any) => void;
  onDelete: (i: number) => void;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "16px 1fr 1.4fr auto auto",
        gap: "var(--sp-sm)",
        alignItems: "center",
        padding: "var(--sp-sm) var(--sp-md)",
        background: "var(--color-canvas)",
        border: "1px solid var(--color-hairline)",
        borderRadius: "var(--radius-sm)",
      }}
    >
      <GripVertical size={12} color="var(--color-mute)" style={{ cursor: "grab" }} />
      <input
        className="input"
        style={{ fontSize: 12, fontFamily: "monospace", padding: "4px 8px" }}
        placeholder="provider/model-id"
        value={model.value}
        onChange={e => onChange(index, "value", e.target.value)}
      />
      <input
        className="input"
        style={{ fontSize: 12, padding: "4px 8px" }}
        placeholder="Display label (e.g. GPT-4o · $10/M)"
        value={model.label}
        onChange={e => onChange(index, "label", e.target.value)}
      />
      <label
        title="Mark as special (router mode)"
        style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--color-mute)", cursor: "pointer", whiteSpace: "nowrap" }}
      >
        <input
          type="checkbox"
          checked={!!model.special}
          onChange={e => onChange(index, "special", e.target.checked)}
          style={{ accentColor: "var(--color-primary)" }}
        />
        special
      </label>
      <button
        className="btn btn-icon btn-ghost btn-sm"
        style={{ color: "var(--color-danger)" }}
        onClick={() => onDelete(index)}
        title="Remove model"
      >
        <Trash2 size={12} />
      </button>
    </div>
  );
}

// ── Provider card (collapsible) ───────────────────────────────────────────────

function ProviderCard({
  providerId,
  data,
  onChange,
  onDelete,
}: {
  providerId: string;
  data: ProviderData;
  onChange: (updated: ProviderData) => void;
  onDelete: () => void;
}) {
  const [open, setOpen] = useState(false);
  const color = providerColor(providerId);

  const handleModelChange = (i: number, field: keyof ModelEntry, v: any) => {
    const updated = [...data.models];
    updated[i] = { ...updated[i], [field]: v };
    onChange({ ...data, models: updated });
  };

  const handleModelDelete = (i: number) => {
    onChange({ ...data, models: data.models.filter((_, idx) => idx !== i) });
  };

  const handleAddModel = () => {
    onChange({
      ...data,
      models: [...data.models, { value: "", label: "" }],
    });
    setOpen(true);
  };

  return (
    <div
      style={{
        border: `1px solid var(--color-hairline)`,
        borderLeft: `3px solid ${color}`,
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
      }}
    >
      {/* Provider header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-md)",
          padding: "var(--sp-md) var(--sp-lg)",
          background: "var(--color-canvas-raised)",
          cursor: "pointer",
        }}
        onClick={() => setOpen(o => !o)}
      >
        <span
          style={{
            width: 10, height: 10, borderRadius: "50%",
            background: color, flexShrink: 0,
          }}
        />
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
            <span className="body-sm-strong">{data.label}</span>
            <code style={{ fontSize: 10, color: "var(--color-mute)", background: "var(--color-canvas)", padding: "1px 5px", borderRadius: 3 }}>
              {providerId}
            </code>
            <span className="badge badge-gray" style={{ fontSize: 9 }}>
              {data.models.length} model{data.models.length !== 1 ? "s" : ""}
            </span>
          </div>
          <p className="caption" style={{ marginTop: 1 }}>
            key: <code style={{ fontSize: 10 }}>{data.key_name ?? "none (local)"}</code>
          </p>
        </div>
        <div style={{ display: "flex", gap: "var(--sp-sm)" }} onClick={e => e.stopPropagation()}>
          <button
            className="btn btn-ghost btn-sm"
            style={{ fontSize: 11 }}
            onClick={handleAddModel}
          >
            <Plus size={11} /> Add model
          </button>
          <button
            className="btn btn-icon btn-ghost btn-sm"
            style={{ color: "var(--color-danger)" }}
            title={`Remove ${data.label} provider`}
            onClick={onDelete}
          >
            <Trash2 size={12} />
          </button>
        </div>
        {open ? <ChevronUp size={14} color="var(--color-mute)" /> : <ChevronDown size={14} color="var(--color-mute)" />}
      </div>

      {/* Model list */}
      {open && (
        <div style={{ padding: "var(--sp-md)", display: "flex", flexDirection: "column", gap: "var(--sp-xs)" }}>
          {/* Column labels */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "16px 1fr 1.4fr auto auto",
              gap: "var(--sp-sm)",
              paddingLeft: "var(--sp-md)",
            }}
          >
            {["", "Model ID (value)", "Display Label", "Special", ""].map((h, i) => (
              <span key={i} style={{ fontSize: 10, color: "var(--color-mute)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                {h}
              </span>
            ))}
          </div>

          {data.models.length === 0 ? (
            <p className="caption" style={{ padding: "var(--sp-lg)", textAlign: "center", color: "var(--color-mute)" }}>
              No models — click &quot;Add model&quot; to add one.
            </p>
          ) : (
            data.models.map((m, i) => (
              <ModelRow
                key={i}
                model={m}
                index={i}
                providerId={providerId}
                onChange={handleModelChange}
                onDelete={handleModelDelete}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ── Add Provider modal (inline) ───────────────────────────────────────────────

function AddProviderRow({ onAdd }: { onAdd: (id: string, label: string, keyName: string) => void }) {
  const [id, setId]       = useState("");
  const [label, setLabel] = useState("");
  const [key, setKey]     = useState("");

  const submit = () => {
    if (!id.trim() || !label.trim()) return;
    onAdd(id.trim(), label.trim(), key.trim() || id.trim());
    setId(""); setLabel(""); setKey("");
  };

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr 1fr auto",
        gap: "var(--sp-sm)",
        padding: "var(--sp-md)",
        background: "var(--color-canvas-raised)",
        border: "1px dashed var(--color-hairline)",
        borderRadius: "var(--radius-md)",
      }}
    >
      <div className="form-group" style={{ marginBottom: 0 }}>
        <label className="form-label" style={{ fontSize: 10 }}>Provider ID</label>
        <input className="input" style={{ fontSize: 12 }} placeholder="my_provider" value={id} onChange={e => setId(e.target.value)} />
      </div>
      <div className="form-group" style={{ marginBottom: 0 }}>
        <label className="form-label" style={{ fontSize: 10 }}>Display Label</label>
        <input className="input" style={{ fontSize: 12 }} placeholder="My Provider" value={label} onChange={e => setLabel(e.target.value)} />
      </div>
      <div className="form-group" style={{ marginBottom: 0 }}>
        <label className="form-label" style={{ fontSize: 10 }}>Key name (in config.json)</label>
        <input className="input" style={{ fontSize: 12 }} placeholder="my_provider (or blank)" value={key} onChange={e => setKey(e.target.value)} />
      </div>
      <button
        className="btn btn-primary btn-sm"
        style={{ alignSelf: "flex-end", marginBottom: 0 }}
        onClick={submit}
        disabled={!id.trim() || !label.trim()}
      >
        <Plus size={13} /> Add
      </button>
    </div>
  );
}

// ── Main editor ───────────────────────────────────────────────────────────────

export default function ModelCatalogEditor({ onToast }: Props) {
  const [catalog, setCatalog]         = useState<Catalog>({});
  const [original, setOriginal]       = useState<Catalog>({});
  const [loading, setLoading]         = useState(true);
  const [saving, setSaving]           = useState(false);
  const [resetting, setResetting]     = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [showAdd, setShowAdd]         = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getModelCatalog();
      setCatalog(data);
      setOriginal(data);
    } catch {
      onToast("Failed to load model catalog", "error");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleProviderChange = (id: string, updated: ProviderData) => {
    setCatalog(c => ({ ...c, [id]: updated }));
  };

  const handleProviderDelete = (id: string) => {
    setCatalog(c => { const next = { ...c }; delete next[id]; return next; });
  };

  const handleAddProvider = (id: string, label: string, keyName: string) => {
    if (catalog[id]) { onToast(`Provider "${id}" already exists`, "error"); return; }
    setCatalog(c => ({
      ...c,
      [id]: { label, key_name: keyName || null, models: [] },
    }));
    setShowAdd(false);
    onToast(`Provider "${id}" added — add models below`, "info");
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.saveModelCatalog(catalog);
      setOriginal({ ...catalog });
      onToast("Model catalog saved to .carole/supported_models.json ✓", "success");
    } catch {
      onToast("Failed to save catalog", "error");
    } finally { setSaving(false); }
  };

  const handleResetToDefaults = async () => {
    setResetting(true);
    try {
      const factoryDefaults = await api.resetModelCatalog();
      setCatalog(factoryDefaults);
      setOriginal(factoryDefaults);
      setConfirmReset(false);
      onToast("Model catalog reset to factory defaults ✓", "success");
    } catch {
      onToast("Failed to reset catalog", "error");
    } finally { setResetting(false); }
  };

  const isDirty = JSON.stringify(catalog) !== JSON.stringify(original);
  const totalModels = Object.values(catalog).reduce((n, p) => n + p.models.length, 0);

  return (
    <div className="card" style={{ marginBottom: "var(--sp-xl)" }}>
      {/* Header */}
      <div className="flex-between" style={{ marginBottom: "var(--sp-lg)" }}>
        <div>
          <h3 className="display-sm">Model Catalog</h3>
          <p className="caption" style={{ marginTop: 2 }}>
            Stored in{" "}
            <code style={{ background: "var(--color-canvas-raised)", padding: "1px 5px", borderRadius: 4, fontSize: 11 }}>
              .carole/supported_models.json
            </code>
            {" "}— {Object.keys(catalog).length} providers · {totalModels} models
            {isDirty && <span style={{ marginLeft: 8, color: "var(--color-primary)" }}>· unsaved changes</span>}
          </p>
        </div>
        <div style={{ display: "flex", gap: "var(--sp-sm)", flexWrap: "wrap", justifyContent: "flex-end" }}>
          <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading} title="Reload from server">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setShowAdd(s => !s)}
          >
            <Plus size={13} /> Add Provider
          </button>
          {/* Reset to defaults */}
          {!confirmReset ? (
            <button
              className="btn btn-ghost btn-sm"
              style={{ color: "var(--color-danger)", borderColor: "rgba(248,113,113,0.3)" }}
              onClick={() => setConfirmReset(true)}
              disabled={resetting}
            >
              <RotateCcw size={13} /> Reset to Defaults
            </button>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.3)", borderRadius: "var(--radius-sm)", padding: "4px 10px" }}>
              <AlertTriangle size={12} color="var(--color-danger)" />
              <span style={{ fontSize: 12 }}>Reset entire catalog?</span>
              <button className="btn btn-danger btn-sm" onClick={handleResetToDefaults} disabled={resetting}>
                {resetting ? <Loader2 size={12} className="animate-spin" /> : null} Yes, reset
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => setConfirmReset(false)}>Cancel</button>
            </div>
          )}
          <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving || loading}>
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            Save Catalog
          </button>
        </div>
      </div>

      {/* Warning */}
      <div style={{ display: "flex", gap: "var(--sp-sm)", alignItems: "flex-start", padding: "var(--sp-md)", background: "rgba(251,191,36,0.06)", border: "1px solid rgba(251,191,36,0.2)", borderRadius: "var(--radius-sm)", marginBottom: "var(--sp-lg)" }}>
        <AlertCircle size={14} color="#f59e0b" style={{ flexShrink: 0, marginTop: 2 }} />
        <p className="caption">
          Edits here are saved to <code style={{ fontSize: 11 }}>.carole/supported_models.json</code> and override
          the shipped <code style={{ fontSize: 11 }}>core/defaults/supported_models.json</code>. To restore all defaults,
          delete your user file and reload.
        </p>
      </div>

      {/* Add provider row */}
      {showAdd && (
        <div style={{ marginBottom: "var(--sp-md)" }}>
          <AddProviderRow onAdd={handleAddProvider} />
        </div>
      )}

      {/* Provider cards */}
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-sm)" }}>
          {[1, 2, 3].map(i => (
            <div key={i} className="skeleton" style={{ height: 56, borderRadius: "var(--radius-md)" }} />
          ))}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-sm)" }}>
          {Object.entries(catalog).map(([id, data]) => (
            <ProviderCard
              key={id}
              providerId={id}
              data={data}
              onChange={updated => handleProviderChange(id, updated)}
              onDelete={() => handleProviderDelete(id)}
            />
          ))}
          {Object.keys(catalog).length === 0 && (
            <p className="caption" style={{ padding: "var(--sp-2xl)", textAlign: "center", color: "var(--color-mute)" }}>
              No providers configured. Click &quot;Add Provider&quot; to start.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
