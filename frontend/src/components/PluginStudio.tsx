"use client";
import React, { useState, useEffect, useMemo } from "react";
import { Code2, Wand2, Save, Plus, FileCode2, Loader2, Trash2, Shield, Wrench, Search } from "lucide-react";
import { api } from "@/hooks/useApi";
import Modal from "./Modal";

export default function PluginStudio({ onToast }: { onToast: (msg: string, type: "success"|"error"|"info") => void }) {
  const [activeTab, setActiveTab] = useState<"custom" | "builtin">("custom");
  const [plugins, setPlugins] = useState<{filename: string, content: string}[]>([]);
  const [builtInTools, setBuiltInTools] = useState<any[]>([]);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [code, setCode] = useState("");
  
  const [prompt, setPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  
  const [searchQuery, setSearchQuery] = useState("");

  // Modals state
  const [promptOpen, setPromptOpen] = useState(false);
  const [promptValue, setPromptValue] = useState("new_tool.py");
  
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmFile, setConfirmFile] = useState<string | null>(null);

  useEffect(() => {
    fetchPluginsAndTools();
  }, []);

  const fetchPluginsAndTools = async () => {
    setLoading(true);
    try {
      const [pluginData, toolData] = await Promise.all([
        api.listPlugins(),
        api.listTools()
      ]);
      setPlugins(pluginData);
      setBuiltInTools(toolData);
      if (pluginData.length > 0 && !activeFile) {
        selectFile(pluginData[0]);
      }
    } catch (err) {
      console.error(err);
      onToast("Failed to load plugins or tools", "error");
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
      // Update local state and reload tools to reflect any newly exported tools
      setPlugins(prev => prev.map(p => p.filename === activeFile ? { ...p, content: code } : p));
      setBuiltInTools(await api.listTools());
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
      setBuiltInTools(await api.listTools());
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

  const filteredTools = useMemo(() => {
    if (!searchQuery) return builtInTools;
    const q = searchQuery.toLowerCase();
    return builtInTools.filter(t => 
      t.name.toLowerCase().includes(q) || 
      t.description.toLowerCase().includes(q) ||
      t.category.toLowerCase().includes(q)
    );
  }, [builtInTools, searchQuery]);

  return (
    <div className="plugin-studio" style={{ display: "flex", height: "100%", width: "100%", overflow: "hidden", background: "var(--color-canvas)" }}>
      {/* Sidebar Navigation */}
      <div className="plugin-navigation" style={{ width: 280, borderRight: "1px solid var(--color-hairline)", display: "flex", flexDirection: "column", background: "var(--color-canvas-soft)" }}>
        
        {/* Tabs */}
        <div style={{ display: "flex", borderBottom: "1px solid var(--color-hairline)" }}>
          <button 
            onClick={() => setActiveTab("custom")}
            style={{ 
              flex: 1, padding: "var(--sp-md) var(--sp-sm)", fontSize: 13, fontWeight: activeTab === "custom" ? 600 : 400,
              background: activeTab === "custom" ? "var(--color-canvas)" : "transparent",
              color: activeTab === "custom" ? "var(--color-primary)" : "var(--color-mute)",
              border: "none", borderBottom: activeTab === "custom" ? "2px solid var(--color-primary)" : "2px solid transparent",
              cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 6
            }}
          >
            <Code2 size={14} /> My Plugins
          </button>
          <button 
            onClick={() => setActiveTab("builtin")}
            style={{ 
              flex: 1, padding: "var(--sp-md) var(--sp-sm)", fontSize: 13, fontWeight: activeTab === "builtin" ? 600 : 400,
              background: activeTab === "builtin" ? "var(--color-canvas)" : "transparent",
              color: activeTab === "builtin" ? "var(--color-primary)" : "var(--color-mute)",
              border: "none", borderBottom: activeTab === "builtin" ? "2px solid var(--color-primary)" : "2px solid transparent",
              cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 6
            }}
          >
            <Wrench size={14} /> Built-in Tools
          </button>
        </div>
        
        {activeTab === "custom" ? (
          <>
            <div style={{ padding: "var(--sp-sm) var(--sp-md)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="caption">Edit python scripts loaded as tools.</span>
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
                        background: activeFile === p.filename ? "var(--color-primary-glow)" : "transparent",
                        color: activeFile === p.filename ? "var(--color-ink-strong)" : "var(--color-ink)",
                        border: activeFile === p.filename ? "1px solid rgba(167, 139, 250, 0.35)" : "1px solid transparent",
                        borderRadius: "var(--radius-sm, 7px)", cursor: "pointer",
                        fontSize: 13, fontWeight: activeFile === p.filename ? 700 : 500,
                        transition: "all var(--t-fast)",
                      }}
                    >
                      <FileCode2 size={14} />
                      {p.filename}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : (
          <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
            <div style={{ padding: "var(--sp-md)" }}>
              <div style={{ position: "relative" }}>
                <Search size={14} style={{ position: "absolute", left: 10, top: 10, color: "var(--color-mute)" }} />
                <input 
                  className="input" 
                  placeholder="Search tools..." 
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  style={{ width: "100%", paddingLeft: 32, fontSize: 13 }}
                />
              </div>
            </div>
            <div style={{ flex: 1, overflowY: "auto" }}>
               {loading ? (
                 <div style={{ padding: "var(--sp-md)", color: "var(--color-mute)" }}>Loading...</div>
               ) : (
                 <div style={{ display: "flex", flexDirection: "column" }}>
                   <div style={{ padding: "var(--sp-sm) var(--sp-md)", background: "var(--color-canvas-inset)", fontSize: 11, fontWeight: 600, color: "var(--color-mute)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                     {filteredTools.length} Tools Loaded
                   </div>
                 </div>
               )}
            </div>
          </div>
        )}
      </div>

      {/* Main Content Area */}
      {activeTab === "custom" ? (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {/* Header toolbar */}
          <div className="plugin-toolbar" style={{ padding: "var(--sp-md) var(--sp-lg)", borderBottom: "1px solid var(--color-hairline)", display: "flex", gap: "var(--sp-md)", alignItems: "center" }}>
            <div style={{ flex: 1, display: "flex", gap: "var(--sp-sm)", alignItems: "center", background: "var(--color-canvas-raised)", padding: "4px 4px 4px 12px", borderRadius: "var(--radius-full)", border: "1px solid var(--color-hairline)" }}>
              <Wand2 size={14} color="var(--color-primary)" />
              <input 
                className="input-bare" 
                style={{ flex: 1, minWidth: 0, fontSize: 13 }} 
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
                  background: "var(--color-canvas)",
                  color: "var(--color-ink)",
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
                  background: "var(--color-canvas)",
                  color: "var(--color-ink)",
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
      ) : (
        <div style={{ flex: 1, padding: "var(--sp-xl)", overflowY: "auto", display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
          <div style={{ marginBottom: "var(--sp-md)" }}>
            <h2 style={{ fontSize: 20, fontWeight: 600, marginBottom: "var(--sp-sm)" }}>Built-in Tools ({filteredTools.length})</h2>
            <p className="body-sm text-mute">These tools are loaded into the registry by default and can be assigned to any agent.</p>
          </div>
          
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(320px, 100%), 1fr))", gap: "var(--sp-md)" }}>
            {filteredTools.map(t => (
              <div key={t.name} style={{ background: "var(--color-canvas-raised)", border: "1px solid var(--color-hairline)", borderRadius: "var(--radius-md)", padding: "var(--sp-md)", display: "flex", flexDirection: "column", gap: "var(--sp-sm)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div style={{ fontWeight: 600, fontSize: 14, color: "var(--color-ink)", display: "flex", alignItems: "center", gap: 6 }}>
                    <Wrench size={14} color="var(--color-primary)" />
                    {t.name}
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 10, background: "var(--color-canvas-inset)", color: "var(--color-mute)", border: "1px solid var(--color-hairline)" }}>
                      {t.category}
                    </span>
                  </div>
                </div>
                
                <p style={{ fontSize: 13, color: "var(--color-mute)", lineHeight: 1.4 }}>{t.description}</p>
                
                <div style={{ marginTop: "auto", paddingTop: "var(--sp-sm)", borderTop: "1px solid var(--color-hairline)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 11, color: "var(--color-mute)", display: "flex", alignItems: "center", gap: 4 }}>
                    <Shield size={12} color={t.permission_default === 'safe' ? "var(--color-success)" : t.permission_default === 'human' ? "var(--color-danger)" : "var(--color-warning)"} />
                    {t.permission_default}
                  </span>
                  
                  {Object.keys(t.parameters || {}).length > 0 && (
                    <span style={{ fontSize: 11, color: "var(--color-primary)", fontWeight: 500 }}>
                      {Object.keys(t.parameters).length} args
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

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
