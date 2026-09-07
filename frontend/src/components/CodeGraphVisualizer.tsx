"use client";

import React, { useState, useEffect } from "react";
import { GitBranch, Search, FileCode, Layers, RefreshCw, ZoomIn, ZoomOut, Code } from "lucide-react";
import { api } from "@/hooks/useApi";

interface CodeNode {
  id: string;
  label: string;
  path: string;
  type: string;
  symbols?: string[];
}

interface CodeEdge {
  source: string;
  target: string;
  type: string;
}

export default function CodeGraphVisualizer({ projectId }: { projectId?: string | null }) {
  const [nodes, setNodes] = useState<CodeNode[]>([]);
  const [edges, setEdges] = useState<CodeEdge[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedNode, setSelectedNode] = useState<CodeNode | null>(null);
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    fetchCodeGraph(false);
  }, [projectId]);

  const fetchCodeGraph = async (forceRefresh = false) => {
    setLoading(true);
    try {
      const data = await api.getCodeGraph(projectId || undefined, forceRefresh);
      if (data) {
        setNodes(data.nodes || []);
        setEdges(data.edges || []);
      }
    } catch (err) {
      console.error("Failed to load code graph", err);
    } finally {
      setLoading(false);
    }
  };

  const filteredNodes = nodes.filter(n =>
    n.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
    n.path.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div style={{
      width: "100%",
      height: "100%",
      display: "flex",
      flexDirection: "column",
      background: "var(--color-canvas)",
      color: "var(--color-ink)",
      overflow: "hidden"
    }}>
      {/* Top Header */}
      <div style={{
        padding: "12px 20px",
        borderBottom: "1px solid var(--color-hairline)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        background: "rgba(18, 18, 37, 0.7)",
        backdropFilter: "blur(12px)"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 30,
            height: 30,
            borderRadius: 8,
            background: "linear-gradient(135deg, rgba(79, 70, 229, 0.25), rgba(99, 102, 241, 0.35))",
            border: "1px solid rgba(99, 102, 241, 0.4)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#a5b4fc"
          }}>
            <GitBranch size={16} />
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: "var(--color-ink-strong)" }}>
                Repository Code Knowledge Graph
              </span>
              <span style={{
                fontSize: 10,
                fontWeight: 600,
                padding: "2px 7px",
                borderRadius: 999,
                background: "rgba(99, 102, 241, 0.15)",
                color: "#a5b4fc",
                border: "1px solid rgba(99, 102, 241, 0.25)"
              }}>
                {nodes.length} {nodes.length === 1 ? "file" : "files"} • {edges.length} {edges.length === 1 ? "dep" : "deps"}
              </span>
            </div>
            <div style={{ fontSize: 11, color: "var(--color-mute)" }}>
              Cross-file AST symbol dependencies and import topology
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ position: "relative" }}>
            <Search size={14} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--color-mute)" }} />
            <input
              type="text"
              placeholder="Search file or symbol..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="input"
              style={{ paddingLeft: 30, width: 200, fontSize: 12, height: 32 }}
            />
          </div>

          <button
            onClick={() => fetchCodeGraph(true)}
            disabled={loading}
            className="btn btn-ghost btn-sm"
            style={{ fontSize: 12 }}
            title="Rescan workspace files & refresh AST graph"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Main Layout */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Nodes Grid */}
        <div style={{ flex: 1, overflowY: "auto", padding: 24 }}>
          {filteredNodes.length === 0 ? (
            <div style={{
              height: "100%",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--color-mute)"
            }}>
              <Code size={40} style={{ opacity: 0.4, marginBottom: 12 }} />
              <div style={{ fontSize: 14, fontWeight: 600 }}>No code graph nodes found</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>Workspace has no tracked code files, or AST will index files on edit/read operations.</div>
              <button
                onClick={() => fetchCodeGraph(true)}
                disabled={loading}
                className="btn btn-primary btn-sm"
                style={{ marginTop: 16, fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}
              >
                <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
                Rescan Workspace Files
              </button>
            </div>
          ) : (
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
              gap: 14
            }}>
              {filteredNodes.map(node => (
                <div
                  key={node.id}
                  onClick={() => setSelectedNode(node)}
                  style={{
                    padding: 14,
                    borderRadius: 10,
                    background: "rgba(18, 18, 37, 0.7)",
                    border: selectedNode?.id === node.id ? "1px solid #818cf8" : "1px solid var(--color-hairline)",
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                    boxShadow: selectedNode?.id === node.id ? "0 0 16px rgba(129, 140, 248, 0.2)" : "none"
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <FileCode size={16} color="#818cf8" />
                    <span style={{ fontSize: 13, fontWeight: 600, color: "var(--color-ink-strong)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {node.label}
                    </span>
                  </div>

                  <div style={{ fontSize: 11, color: "var(--color-mute)", fontFamily: "var(--font-mono)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {node.path}
                  </div>

                  {node.symbols && node.symbols.length > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                      {node.symbols.slice(0, 3).map((s, idx) => (
                        <span key={idx} style={{
                          fontSize: 9,
                          fontFamily: "var(--font-mono)",
                          padding: "1px 5px",
                          borderRadius: 4,
                          background: "rgba(255, 255, 255, 0.05)",
                          color: "#cbd5e1"
                        }}>
                          {s}
                        </span>
                      ))}
                      {node.symbols.length > 3 && (
                        <span style={{ fontSize: 9, color: "var(--color-mute)" }}>+{node.symbols.length - 3}</span>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Selected Node Inspector Drawer */}
        {selectedNode && (
          <div style={{
            width: 320,
            borderLeft: "1px solid var(--color-hairline)",
            background: "rgba(12, 12, 26, 0.95)",
            backdropFilter: "blur(16px)",
            padding: 20,
            display: "flex",
            flexDirection: "column",
            gap: 16,
            overflowY: "auto"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--color-ink-strong)" }}>File Symbol Inspector</div>
              <button
                onClick={() => setSelectedNode(null)}
                style={{ background: "none", border: "none", color: "var(--color-mute)", cursor: "pointer", fontSize: 14 }}
              >
                ✕
              </button>
            </div>

            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: "#fff" }}>{selectedNode.label}</div>
              <div style={{ fontSize: 11, color: "var(--color-mute)", fontFamily: "var(--font-mono)", wordBreak: "break-all", marginTop: 4 }}>
                {selectedNode.path}
              </div>
            </div>

            {selectedNode.symbols && selectedNode.symbols.length > 0 ? (
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--color-mute)", marginBottom: 8 }}>
                  Exported Symbols ({selectedNode.symbols.length})
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {selectedNode.symbols.map((sym, idx) => (
                    <div key={idx} style={{
                      padding: "6px 10px",
                      borderRadius: 6,
                      background: "rgba(255, 255, 255, 0.03)",
                      border: "1px solid var(--color-hairline)",
                      fontFamily: "var(--font-mono)",
                      fontSize: 11,
                      color: "#a5b4fc"
                    }}>
                      {sym}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div style={{ fontSize: 12, color: "var(--color-mute)" }}>No symbols indexed for this node yet.</div>
            )}

            {/* Cross-file dependencies */}
            {(() => {
              const fileImports = edges.filter(e => e.source === selectedNode.id).map(e => e.target);
              const importedBy = edges.filter(e => e.target === selectedNode.id).map(e => e.source);
              if (fileImports.length === 0 && importedBy.length === 0) return null;
              return (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  {fileImports.length > 0 && (
                    <div>
                      <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--color-mute)", marginBottom: 6 }}>
                        Imports ({fileImports.length})
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        {fileImports.map((dep, idx) => (
                          <div key={idx} style={{
                            padding: "4px 8px",
                            borderRadius: 4,
                            background: "rgba(99, 102, 241, 0.08)",
                            border: "1px solid rgba(99, 102, 241, 0.2)",
                            fontFamily: "var(--font-mono)",
                            fontSize: 11,
                            color: "#c7d2fe"
                          }}>
                            {dep}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {importedBy.length > 0 && (
                    <div>
                      <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--color-mute)", marginBottom: 6 }}>
                        Imported By ({importedBy.length})
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        {importedBy.map((src, idx) => (
                          <div key={idx} style={{
                            padding: "4px 8px",
                            borderRadius: 4,
                            background: "rgba(16, 185, 129, 0.08)",
                            border: "1px solid rgba(16, 185, 129, 0.2)",
                            fontFamily: "var(--font-mono)",
                            fontSize: 11,
                            color: "#a7f3d0"
                          }}>
                            {src}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })()}
          </div>
        )}
      </div>
    </div>
  );
}
