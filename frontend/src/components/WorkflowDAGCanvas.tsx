"use client";

import React, { useState, useEffect } from "react";
import { Network, RefreshCw, Activity, ArrowRight, ShieldCheck, Layers } from "lucide-react";
import { api } from "@/hooks/useApi";
import AgentAvatar from "./AgentAvatar";

interface DAGNode {
  id: string;
  name: string;
  role: string;
  model: string;
  status: "idle" | "active" | "executing_tool" | "completed" | "error";
  is_coordinator?: boolean;
}

interface DAGEdge {
  id: string;
  source: string;
  target: string;
  type: string;
}

export default function WorkflowDAGCanvas({ teamId }: { teamId?: string | null }) {
  const [nodes, setNodes] = useState<DAGNode[]>([]);
  const [edges, setEdges] = useState<DAGEdge[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState<DAGNode | null>(null);

  useEffect(() => {
    fetchDAG();
  }, [teamId]);

  const fetchDAG = async () => {
    setLoading(true);
    try {
      const data = await api.getWorkflowDAG(teamId || undefined);
      if (data) {
        setNodes(data.nodes || []);
        setEdges(data.edges || []);
      }
    } catch (err) {
      console.error("Failed to load workflow DAG", err);
    } finally {
      setLoading(false);
    }
  };

  const coordinator = nodes.find(n => n.is_coordinator) || (nodes.length > 0 ? nodes.find(n => (n.role || "").toLowerCase().includes("orchestrat") || n.name.toLowerCase() === "archer") : undefined);
  const workers = coordinator ? nodes.filter(n => n.id !== coordinator.id) : nodes;

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
      {/* Header bar */}
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
            <Network size={16} />
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--color-ink-strong)" }}>
              Multi-Agent Swarm Topology
            </div>
            <div style={{ fontSize: 11, color: "var(--color-mute)" }}>
              Interactive Delegation DAG & Real-Time Agent Roles
            </div>
          </div>
        </div>

        <button
          onClick={fetchDAG}
          disabled={loading}
          className="btn btn-ghost btn-sm"
          style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          Refresh Swarm
        </button>
      </div>

      {/* Main Canvas */}
      <div style={{ flex: 1, display: "flex", position: "relative", overflow: "hidden" }}>
        {/* Visual Graph View */}
        <div style={{
          flex: 1,
          padding: 32,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          overflowY: "auto"
        }}>
          {nodes.length === 0 ? (
            <div style={{ textAlign: "center", color: "var(--color-mute)" }}>
              <Layers size={40} style={{ margin: "0 auto 12px", opacity: 0.5 }} />
              <div style={{ fontSize: 14, fontWeight: 600 }}>No active agents in swarm</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>Initialize a team with coordinator and worker agents.</div>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 48, maxWidth: 860, width: "100%" }}>
              {/* Coordinator Level */}
              {coordinator && (
                <div
                  onClick={() => setSelectedNode(coordinator)}
                  style={{
                    padding: "16px 24px",
                    borderRadius: 14,
                    background: "linear-gradient(135deg, rgba(79, 70, 229, 0.25), rgba(18, 18, 37, 0.95))",
                    border: selectedNode?.id === coordinator.id ? "2px solid #818cf8" : "1px solid rgba(99, 102, 241, 0.4)",
                    boxShadow: "0 8px 32px -8px rgba(79, 70, 229, 0.35)",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 16,
                    minWidth: 280,
                    transition: "all 0.2s ease"
                  }}
                >
                  <AgentAvatar
                    name={coordinator.name}
                    id={coordinator.id}
                    role={coordinator.role}
                    size={46}
                    hideBadge
                  />
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 15, fontWeight: 700, color: "#fff" }}>{coordinator.name}</span>
                      <span style={{
                        fontSize: 10,
                        fontWeight: 700,
                        padding: "2px 8px",
                        borderRadius: 10,
                        background: "rgba(99, 102, 241, 0.3)",
                        color: "#c7d2fe"
                      }}>
                        {coordinator.role || "Lead Orchestrator"}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 2, fontFamily: "var(--font-mono)" }}>
                      {coordinator.model}
                    </div>
                  </div>
                </div>
              )}

              {/* Connecting Delegation Lines */}
              {workers.length > 0 && coordinator && (
                <div style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 8,
                  color: "#6366f1",
                  fontSize: 12,
                  fontWeight: 600
                }}>
                  <div style={{ width: 60, height: 1, background: "linear-gradient(90deg, transparent, #6366f1)" }} />
                  <span>Dispatches & Delegates</span>
                  <ArrowRight size={14} />
                  <div style={{ width: 60, height: 1, background: "linear-gradient(90deg, #6366f1, transparent)" }} />
                </div>
              )}

              {/* Workers Row */}
              <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 20, width: "100%" }}>
                {workers.map(worker => (
                  <div
                    key={worker.id}
                    onClick={() => setSelectedNode(worker)}
                    style={{
                      padding: "14px 18px",
                      borderRadius: 12,
                      background: "rgba(18, 18, 37, 0.75)",
                      border: selectedNode?.id === worker.id ? "2px solid #818cf8" : "1px solid var(--color-hairline)",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: 14,
                      minWidth: 220,
                      boxShadow: "0 4px 16px rgba(0,0,0,0.2)",
                      transition: "all 0.15s ease"
                    }}
                  >
                    <AgentAvatar
                      name={worker.name}
                      id={worker.id}
                      role={worker.role}
                      size={40}
                      hideBadge
                    />
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--color-ink-strong)" }}>
                        {worker.name}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--color-mute)" }}>
                        {worker.role}
                      </div>
                      <div style={{ fontSize: 10, color: "#64748b", fontFamily: "var(--font-mono)" }}>
                        {worker.model}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Node Detail Drawer */}
        {selectedNode && (
          <div style={{
            width: 280,
            borderLeft: "1px solid var(--color-hairline)",
            background: "rgba(12, 12, 26, 0.95)",
            backdropFilter: "blur(16px)",
            padding: 20,
            display: "flex",
            flexDirection: "column",
            gap: 16
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--color-ink-strong)" }}>Agent Details</div>
              <button
                onClick={() => setSelectedNode(null)}
                style={{ background: "none", border: "none", color: "var(--color-mute)", cursor: "pointer", fontSize: 14 }}
              >
                ✕
              </button>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <AgentAvatar
                name={selectedNode.name}
                id={selectedNode.id}
                role={selectedNode.role}
                size={44}
                hideBadge
              />
              <div>
                <div style={{ fontSize: 16, fontWeight: 700, color: "#fff" }}>{selectedNode.name}</div>
                <div style={{ fontSize: 12, color: "#818cf8", fontWeight: 600 }}>{selectedNode.role}</div>
              </div>
            </div>

            <div style={{
              background: "rgba(255, 255, 255, 0.03)",
              border: "1px solid var(--color-hairline)",
              borderRadius: 8,
              padding: 12,
              display: "flex",
              flexDirection: "column",
              gap: 8,
              fontSize: 12
            }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--color-mute)" }}>Model</span>
                <span style={{ fontFamily: "var(--font-mono)", color: "#cbd5e1" }}>{selectedNode.model}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--color-mute)" }}>Status</span>
                <span style={{ color: "#10b981", fontWeight: 600 }}>Active</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--color-mute)" }}>Judge Gated</span>
                <span style={{ color: "#38bdf8" }}>Tier 0-3 Protected</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
