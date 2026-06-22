"use client";
import React, { useState, useEffect } from "react";
import { Code2, Wand2, Save, Plus, FileCode2, Loader2, Trash2 } from "lucide-react";
import { api } from "@/hooks/useApi";
import Modal from "./Modal";

export default function PluginStudio({ onToast }: { onToast: (msg: string, type: "success"|"error"|"info") => void }) {
  const [plugins, setPlugins] = useState<{filename: string, content: string}[]>([]);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [code, setCode] = useState("");
  
  const [prompt, setPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  // Modals state
  const [promptOpen, setPromptOpen] = useState(false);
  const [promptValue, setPromptValue] = useState("new_tool.py");
  
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmFile, setConfirmFile] = useState<string | null>(null);

  useEffect(() => {
    fetchPlugins();
  }, []);

  const fetchPlugins = async () => {
    setLoading(true);
    try {
      const data = await api.listPlugins();
      setPlugins(data);
      if (data.length > 0 && !activeFile) {
        selectFile(data[0]);
      }
    } catch (err) {
      console.error(err);
      onToast("Failed to load plugins", "error");
    } finally {
      setLoading(false);
    }
  };

  const selectFile = (p: {filename: string, content: string}) => {
    setActiveFile(p.filename);
    setCode(p.content);
  };

  const handleNew = () => {
    setPromptValue("new_tool.py");
    setPromptOpen(true);
  };

  const handleNewConfirm = () => {
    const name = promptValue.trim();
    if (!name) return;
    if (!name.endsWith(".py")) {
      onToast("Filename must end with .py", "error");
      return;
    }
    const newPlugin = { filename: name, content: "from core.tools.tool_registry import tool\n\n@tool\ndef new_function():\n    \"\"\"Description here.\"\"\"\n    pass\n" };
    setPlugins([...plugins, newPlugin]);
    selectFile(newPlugin);
    setPromptOpen(false);
  };

  const handleSave = async () => {
    if (!activeFile) return;
    setSaving(true);
    try {
      await api.savePlugin(activeFile, code);
      onToast(`Saved and loaded ${activeFile}`, "success");
      // Update local state
      setPlugins(prev => prev.map(p => p.filename === activeFile ? { ...p, content: code } : p));
    } catch (err: any) {
      onToast(`Save error: ${err.message || "Failed"}`, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = () => {
    if (!activeFile) return;
    setConfirmFile(activeFile);
    setConfirmOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!confirmFile) return;
    
    setSaving(true);
    setConfirmOpen(false);
    try {
      await api.deletePlugin(confirmFile);
      onToast(`Deleted ${confirmFile}`, "success");
      setPlugins(prev => prev.filter(p => p.filename !== confirmFile));
      if (activeFile === confirmFile) {
        setActiveFile(null);
        setCode("");
      }
    } catch (err: any) {
      onToast(`Delete error: ${err.message || "Failed"}`, "error");
    } finally {
      setSaving(false);
      setConfirmFile(null);
    }
  };

  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    setGenerating(true);
    try {
      const res = await api.generatePlugin(prompt);
      if (res.code) {
        setCode(res.code);
        
        if (!activeFile) {
          const sanitizedPrompt = prompt.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').substring(0, 20);
          const newName = `${sanitizedPrompt || 'new_generated'}_tool.py`;
          setActiveFile(newName);
          setPlugins(prev => {
            if (prev.some(p => p.filename === newName)) {
              return prev.map(p => p.filename === newName ? { ...p, content: res.code } : p);
            }
            return [...prev, { filename: newName, content: res.code }];
          });
        }
        
        onToast("Code generated!", "success");
      }
    } catch {
      onToast("Failed to generate code", "error");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div style={{ display: "flex", height: "100%", width: "100%", overflow: "hidden", background: "var(--color-canvas)" }}>
      {/* Sidebar */}
      <div style={{ width: 280, borderRight: "1px solid var(--color-hairline)", display: "flex", flexDirection: "column", background: "var(--color-canvas-soft)" }}>
        <div style={{ padding: "var(--sp-md) var(--sp-lg)", borderBottom: "1px solid var(--color-hairline)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", fontWeight: 600 }}>
            <Code2 size={16} color="var(--color-primary)" />
            <span>Local Plugins</span>
          </div>
          <button className="btn btn-icon btn-ghost btn-sm" onClick={handleNew} title="New Plugin">
            <Plus size={16} />
          </button>
        </div>
        
        <div style={{ flex: 1, overflowY: "auto", padding: "var(--sp-sm)" }}>
          {loading ? (
            <div style={{ padding: "var(--sp-md)", color: "var(--color-mute)" }}>Loading...</div>
          ) : plugins.length === 0 ? (
            <div style={{ padding: "var(--sp-md)", color: "var(--color-mute)", fontSize: 13, textAlign: "center" }}>
              No plugins found.<br/>Create one to get started.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              {plugins.map(p => (
                <button
                  key={p.filename}
                  onClick={() => selectFile(p)}
                  style={{
                    display: "flex", alignItems: "center", gap: "var(--sp-sm)",
                    padding: "8px 12px", width: "100%", textAlign: "left",
                    background: activeFile === p.filename ? "var(--color-primary-glow-sm)" : "transparent",
                    color: activeFile === p.filename ? "var(--color-primary)" : "var(--color-ink)",
                    border: "none", borderRadius: "var(--radius-sm)", cursor: "pointer",
                    fontSize: 13, fontWeight: activeFile === p.filename ? 500 : 400
                  }}
                >
                  <FileCode2 size={14} />
                  {p.filename}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Editor Main */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* Header toolbar */}
        <div style={{ padding: "var(--sp-md) var(--sp-lg)", borderBottom: "1px solid var(--color-hairline)", display: "flex", gap: "var(--sp-md)", alignItems: "center" }}>
          <div style={{ flex: 1, display: "flex", gap: "var(--sp-sm)", alignItems: "center", background: "var(--color-canvas-raised)", padding: "4px 4px 4px 12px", borderRadius: "var(--radius-full)", border: "1px solid var(--color-hairline)" }}>
            <Wand2 size={14} color="var(--color-primary)" />
            <input 
              className="input-bare" 
              style={{ flex: 1, fontSize: 13 }} 
              placeholder="Describe a tool you want to build (e.g. 'A tool that searches Wikipedia')" 
              value={prompt} 
              onChange={e => setPrompt(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleGenerate()}
            />
            <button className="btn btn-primary btn-sm" style={{ borderRadius: "var(--radius-full)" }} onClick={handleGenerate} disabled={generating || !prompt.trim()}>
              {generating ? <Loader2 size={14} className="animate-spin" /> : "Generate Code"}
            </button>
          </div>
          
          <div style={{ display: "flex", gap: "var(--sp-sm)" }}>
            <button className="btn btn-ghost btn-sm" onClick={handleSave} disabled={saving || !activeFile}>
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save & Reload
            </button>
            <button className="btn btn-icon btn-ghost btn-sm text-danger" onClick={handleDelete} disabled={saving || !activeFile} title="Delete Plugin">
              <Trash2 size={14} />
            </button>
          </div>
        </div>

        {/* Text Area */}
        {activeFile ? (
          <div style={{ flex: 1, padding: "var(--sp-lg)", display: "flex", flexDirection: "column" }}>
            <div style={{ marginBottom: "var(--sp-sm)", fontSize: 13, color: "var(--color-mute)", display: "flex", justifyContent: "space-between" }}>
              <span>Editing: <strong>{activeFile}</strong></span>
              <span>Python</span>
            </div>
            <textarea
              value={code}
              onChange={e => setCode(e.target.value)}
              style={{
                flex: 1,
                width: "100%",
                background: "#1e1e1e",
                color: "#d4d4d4",
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                fontSize: 14,
                lineHeight: 1.5,
                padding: "var(--sp-md)",
                border: "1px solid var(--color-hairline)",
                borderRadius: "var(--radius-md)",
                resize: "none",
                outline: "none"
              }}
              spellCheck={false}
            />
          </div>
        ) : (
          <div style={{ flex: 1, padding: "var(--sp-lg)", display: "flex", flexDirection: "column" }}>
            <div style={{ marginBottom: "var(--sp-sm)", fontSize: 13, color: "var(--color-mute)", display: "flex", justifyContent: "space-between" }}>
              <span><strong>Example Tool Code</strong> (Read Only - Create a plugin to edit)</span>
              <span>Python</span>
            </div>
            <textarea
              readOnly
              value={'from core.tools.tool_registry import tool\n\n@tool\ndef example_tool(query: str):\n    """\n    Example tool that does something.\n    Args:\n        query: The search query.\n    """\n    return f"Result for {query}"\n'}
              style={{
                flex: 1,
                width: "100%",
                background: "#1e1e1e",
                color: "#d4d4d4",
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                fontSize: 14,
                lineHeight: 1.5,
                padding: "var(--sp-md)",
                border: "1px solid var(--color-hairline)",
                borderRadius: "var(--radius-md)",
                resize: "none",
                outline: "none",
                opacity: 0.7
              }}
              spellCheck={false}
            />
          </div>
        )}
      </div>

      {/* Modals */}
      <Modal open={promptOpen} onClose={() => setPromptOpen(false)} title="New Plugin">
        <p className="body-sm text-mute" style={{ marginBottom: "var(--sp-md)" }}>Plugin filename (e.g., my_tool.py):</p>
        <input 
          className="input" 
          value={promptValue} 
          onChange={e => setPromptValue(e.target.value)} 
          onKeyDown={e => e.key === "Enter" && handleNewConfirm()}
          autoFocus 
        />
        <div style={{ display: "flex", gap: "var(--sp-sm)", justifyContent: "flex-end", marginTop: "var(--sp-xl)" }}>
          <button className="btn btn-ghost" onClick={() => setPromptOpen(false)}>Cancel</button>
          <button className="btn btn-primary" onClick={handleNewConfirm}>Create</button>
        </div>
      </Modal>

      <Modal open={confirmOpen} onClose={() => setConfirmOpen(false)} title="Delete Plugin">
        <p className="body-sm">Are you sure you want to delete <strong style={{ color: "var(--color-danger)" }}>{confirmFile}</strong>? This cannot be undone.</p>
        <div style={{ display: "flex", gap: "var(--sp-sm)", justifyContent: "flex-end", marginTop: "var(--sp-xl)" }}>
          <button className="btn btn-ghost" onClick={() => setConfirmOpen(false)}>Cancel</button>
          <button className="btn btn-danger" onClick={handleDeleteConfirm}>Delete</button>
        </div>
      </Modal>
    </div>
  );
}
