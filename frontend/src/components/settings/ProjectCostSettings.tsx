"use client";
import React, { useState, useEffect, useCallback } from "react";
import { DollarSign, BarChart3, Upload, Trash2, AlertTriangle, Loader2, Save, CheckCircle, FileText } from "lucide-react";
import { api } from "@/hooks/useApi";
import SettingTooltip from "./SettingTooltip";

interface Props {
  teamId: string | null;
  projectId: string | null;
  onToast: (msg: string, type: "success" | "error" | "info") => void;
  onRequestDelete: (type: "team" | "project") => void;
}

interface CostStats {
  total_spend_usd?: number;
  total_tokens?: number;
  total_prompt_tokens?: number;
  total_completion_tokens?: number;
  budget_limit_usd?: number | null;
  unknown_cost_calls?: number;
}

interface UsageData {
  total_messages?: number;
  total_tasks?: number;
  total_agents?: number;
}

export default function ProjectCostSettings({ teamId, projectId, onToast, onRequestDelete }: Props) {
  // ── Cost Tracking State ──
  const [costStats, setCostStats] = useState<CostStats | null>(null);
  const [costLoading, setCostLoading] = useState(true);
  const [costSaving, setCostSaving] = useState(false);
  const [budgetLimit, setBudgetLimit] = useState<string>("");

  const fetchCostStats = useCallback(async () => {
    if (!projectId) {
      setCostLoading(false);
      return;
    }
    setCostLoading(true);
    try {
      const data = await api.getCostStats(projectId);
      setCostStats(data);
      setBudgetLimit(data.budget_limit_usd !== null && data.budget_limit_usd !== undefined ? String(data.budget_limit_usd) : "");
    } catch {
      // Ignore errors
    } finally {
      setCostLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchCostStats();
  }, [fetchCostStats]);

  const handleSaveBudget = async () => {
    if (!projectId) return;
    setCostSaving(true);
    try {
      await api.updateBudget({
        project_id: projectId,
        budget_limit_usd: budgetLimit ? parseFloat(budgetLimit) : null,
      });
      onToast("Budget limit updated ✓", "success");
      fetchCostStats();
    } catch {
      onToast("Failed to update budget limit", "error");
    } finally {
      setCostSaving(false);
    }
  };

  // ── Usage State ──
  const [usage, setUsage] = useState<UsageData | null>(null);
  useEffect(() => {
    if (projectId) {
      api.getProjectUsage(projectId).then(setUsage).catch(() => {});
    }
  }, [projectId]);

  // ── Knowledge Upload State ──
  const [uploading, setUploading] = useState(false);
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !projectId) return;
    setUploading(true);
    try {
      await api.uploadKnowledgeFile(projectId, teamId, file);
      onToast(`Uploaded "${file.name}" to project knowledge`, "success");
    } catch {
      onToast("Failed to upload knowledge document", "error");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const isOverBudget = costStats?.budget_limit_usd && (costStats.total_spend_usd ?? 0) > costStats.budget_limit_usd;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2xl)" }}>
      {/* ── Cost Tracking & Budget Limit Card ── */}
      {projectId && (
        <div className="card" style={{ padding: "var(--sp-xl)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)", marginBottom: "var(--sp-lg)" }}>
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
              <DollarSign size={18} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center" }}>
                <h3 className="display-sm" style={{ margin: 0 }}>Cost &amp; Token Expenditure</h3>
                <SettingTooltip
                  title="Token Cost Tracking"
                  why="Helps you monitor and control API consumption costs across all models in this workspace."
                  how="Carole tracks prompt tokens and completion tokens on every turn and calculates USD expenditure in real time."
                />
              </div>
              <p className="caption text-mute" style={{ margin: 0 }}>
                Real-time tracking of token consumption, cost calculations, and monthly spend thresholds.
              </p>
            </div>
          </div>

          {costLoading ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="skeleton skeleton-text" style={{ height: 60 }} />
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-lg)" }}>
              {costStats && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(160px, 100%), 1fr))", gap: "var(--sp-md)" }}>
                  <div
                    style={{
                      padding: "var(--sp-md) var(--sp-lg)",
                      background: "var(--color-canvas-soft)",
                      border: "1px solid var(--color-hairline)",
                      borderRadius: "var(--radius-sm)",
                    }}
                  >
                    <div className="caption text-mute">Recorded Spend</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: "var(--color-primary)", marginTop: 4 }}>
                      ${costStats.total_spend_usd?.toFixed(4) || "0.0000"}
                    </div>
                    {(costStats.unknown_cost_calls ?? 0) > 0 && <div className="caption text-mute">
                      Cost unavailable for {costStats.unknown_cost_calls} calls; total is incomplete.
                    </div>}
                  </div>
                  <div
                    style={{
                      padding: "var(--sp-md) var(--sp-lg)",
                      background: "var(--color-canvas-soft)",
                      border: "1px solid var(--color-hairline)",
                      borderRadius: "var(--radius-sm)",
                    }}
                  >
                    <div className="caption text-mute">Total Tokens</div>
                    <div style={{ fontSize: 20, fontWeight: 700, marginTop: 4 }}>
                      {costStats.total_tokens?.toLocaleString() || "0"}
                    </div>
                  </div>
                  <div
                    style={{
                      padding: "var(--sp-md) var(--sp-lg)",
                      background: "var(--color-canvas-soft)",
                      border: "1px solid var(--color-hairline)",
                      borderRadius: "var(--radius-sm)",
                    }}
                  >
                    <div className="caption text-mute">Prompt Tokens</div>
                    <div style={{ fontSize: 20, fontWeight: 700, marginTop: 4 }}>
                      {costStats.total_prompt_tokens?.toLocaleString() || "0"}
                    </div>
                  </div>
                  <div
                    style={{
                      padding: "var(--sp-md) var(--sp-lg)",
                      background: "var(--color-canvas-soft)",
                      border: "1px solid var(--color-hairline)",
                      borderRadius: "var(--radius-sm)",
                    }}
                  >
                    <div className="caption text-mute">Completion Tokens</div>
                    <div style={{ fontSize: 20, fontWeight: 700, marginTop: 4 }}>
                      {costStats.total_completion_tokens?.toLocaleString() || "0"}
                    </div>
                  </div>
                </div>
              )}

              <div
                style={{
                  background: "var(--color-canvas-soft)",
                  padding: "var(--sp-md) var(--sp-lg)",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--color-hairline)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: "var(--sp-md)",
                }}
              >
                <div>
                  <div style={{ display: "flex", alignItems: "center" }}>
                    <label className="form-label" style={{ fontSize: 11, fontWeight: 600, margin: 0 }}>
                      Monthly Budget Limit (USD)
                    </label>
                    <SettingTooltip
                      title="Budget Cap"
                      why="Prevents accidental over-spending from automated multi-agent tasks."
                      how="When your project spend exceeds this USD number, Carole displays high-priority warnings in the UI."
                    />
                  </div>
                  <p className="caption text-mute" style={{ margin: 0 }}>
                    Set a hard spending cap to trigger safety warnings when exceeded.
                  </p>
                </div>
                <div style={{ display: "flex", gap: "var(--sp-sm)", alignItems: "center" }}>
                  <input
                    className="input"
                    type="number"
                    step="0.01"
                    placeholder="No limit"
                    value={budgetLimit}
                    onChange={e => setBudgetLimit(e.target.value)}
                    style={{ maxWidth: 140, fontSize: 11 }}
                  />
                  <button className="btn btn-primary btn-sm" onClick={handleSaveBudget} disabled={costSaving}>
                    {costSaving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save
                  </button>
                </div>
              </div>

              {isOverBudget && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--sp-sm)",
                    padding: "var(--sp-md)",
                    background: "rgba(248,113,113,0.1)",
                    border: "1px solid rgba(248,113,113,0.3)",
                    borderRadius: "var(--radius-sm)",
                    color: "var(--color-danger)",
                  }}
                >
                  <AlertTriangle size={15} />
                  <div className="body-sm-strong">Warning: Current project spend exceeds budget limit!</div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Project Usage Analytics Card ── */}
      {projectId && usage && (
        <div className="card" style={{ padding: "var(--sp-xl)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)", marginBottom: "var(--sp-lg)" }}>
            <div
              style={{
                width: 38,
                height: 38,
                borderRadius: "var(--radius-sm)",
                background: "rgba(59, 130, 246, 0.12)",
                border: "1px solid rgba(59, 130, 246, 0.3)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--color-info)",
              }}
            >
              <BarChart3 size={18} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center" }}>
                <h3 className="display-sm" style={{ margin: 0 }}>Project Usage Analytics</h3>
                <SettingTooltip
                  title="Usage Analytics"
                  why="Aggregates productivity volume across all agents."
                  how="Summarizes total message exchanges, subagent delegation tasks, and configured agents."
                />
              </div>
              <p className="caption text-mute" style={{ margin: 0 }}>
                Cumulative message throughput, background tasks, and active agents.
              </p>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(180px, 100%), 1fr))", gap: "var(--sp-md)" }}>
            <div
              style={{
                textAlign: "center",
                padding: "var(--sp-lg)",
                background: "var(--color-canvas-soft)",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--color-hairline)",
              }}
            >
              <div style={{ fontSize: 24, fontWeight: 700, color: "var(--color-primary)" }}>
                {(usage.total_messages ?? 0).toLocaleString()}
              </div>
              <div className="caption text-mute" style={{ marginTop: 2 }}>Messages</div>
            </div>
            <div
              style={{
                textAlign: "center",
                padding: "var(--sp-lg)",
                background: "var(--color-canvas-soft)",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--color-hairline)",
              }}
            >
              <div style={{ fontSize: 24, fontWeight: 700, color: "var(--color-primary)" }}>
                {(usage.total_tasks ?? 0).toLocaleString()}
              </div>
              <div className="caption text-mute" style={{ marginTop: 2 }}>Tasks</div>
            </div>
            <div
              style={{
                textAlign: "center",
                padding: "var(--sp-lg)",
                background: "var(--color-canvas-soft)",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--color-hairline)",
              }}
            >
              <div style={{ fontSize: 24, fontWeight: 700, color: "var(--color-primary)" }}>
                {(usage.total_agents ?? 0).toLocaleString()}
              </div>
              <div className="caption text-mute" style={{ marginTop: 2 }}>Agents</div>
            </div>
          </div>
        </div>
      )}

      {/* ── Knowledge Base Upload Card ── */}
      {projectId && (
        <div className="card" style={{ padding: "var(--sp-xl)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)", marginBottom: "var(--sp-md)" }}>
            <div
              style={{
                width: 38,
                height: 38,
                borderRadius: "var(--radius-sm)",
                background: "rgba(167, 139, 250, 0.12)",
                border: "1px solid rgba(167, 139, 250, 0.3)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#a78bfa",
              }}
            >
              <FileText size={18} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center" }}>
                <h3 className="display-sm" style={{ margin: 0 }}>Knowledge Base Documents</h3>
                <SettingTooltip
                  title="Knowledge Base"
                  why="Provides persistent domain documentation to ground agent generation (RAG)."
                  how="Uploaded documents are chunked and indexed into the local vector database for semantic search during task execution."
                />
              </div>
              <p className="caption text-mute" style={{ margin: 0 }}>
                Upload documentation, requirements, or architecture manuals for agents to ground their answers.
              </p>
            </div>
          </div>

          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--sp-md)",
              padding: "var(--sp-lg)",
              border: "2px dashed var(--color-hairline)",
              borderRadius: "var(--radius-md)",
              background: "var(--color-canvas-soft)",
              cursor: "pointer",
              transition: "border-color var(--t-fast)",
            }}
            onMouseEnter={e => (e.currentTarget.style.borderColor = "var(--color-primary)")}
            onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--color-hairline)")}
          >
            {uploading ? (
              <Loader2 size={22} className="animate-spin" color="var(--color-primary)" />
            ) : (
              <Upload size={22} color="var(--color-mute)" />
            )}
            <div>
              <div className="body-sm-strong">{uploading ? "Ingesting document…" : "Click or drop file to upload"}</div>
              <div className="caption text-mute">Supports PDF, TXT, Markdown (.md), and DOCX</div>
            </div>
            <input
              type="file"
              style={{ display: "none" }}
              accept=".pdf,.txt,.md,.docx"
              onChange={handleFileUpload}
              disabled={uploading}
            />
          </label>
        </div>
      )}

      {/* ── Danger Zone Card ── */}
      <div
        className="card"
        style={{
          padding: "var(--sp-xl)",
          border: "1px solid rgba(248, 113, 113, 0.3)",
          background: "rgba(248, 113, 113, 0.03)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)", marginBottom: "var(--sp-lg)" }}>
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: "var(--radius-sm)",
              background: "rgba(248, 113, 113, 0.15)",
              border: "1px solid rgba(248, 113, 113, 0.3)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--color-danger)",
            }}
          >
            <Trash2 size={18} />
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center" }}>
              <h3 className="display-sm text-danger" style={{ margin: 0 }}>Danger Zone</h3>
              <SettingTooltip
                title="Danger Zone"
                why="Contains irreversible administrative actions."
                how="Lets you delete team threads or completely erase project databases and on-disk files with two-step confirmation."
              />
            </div>
            <p className="caption text-mute" style={{ margin: 0 }}>
              Destructive actions for removing teams and workspace data.
            </p>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
          {teamId && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "var(--sp-md) var(--sp-lg)",
                background: "var(--color-canvas)",
                border: "1px solid rgba(248, 113, 113, 0.2)",
                borderRadius: "var(--radius-sm)",
              }}
            >
              <div>
                <div className="body-sm-strong">Delete Current Team</div>
                <div className="caption text-mute">Permanently remove this team and all associated chat threads.</div>
              </div>
              <button className="btn btn-danger btn-sm" onClick={() => onRequestDelete("team")}>
                <Trash2 size={12} /> Delete Team
              </button>
            </div>
          )}

          {projectId && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "var(--sp-md) var(--sp-lg)",
                background: "var(--color-canvas)",
                border: "1px solid rgba(248, 113, 113, 0.2)",
                borderRadius: "var(--radius-sm)",
              }}
            >
              <div>
                <div className="body-sm-strong">Delete Current Project</div>
                <div className="caption text-mute">Permanently remove this project record and associated data files.</div>
              </div>
              <button className="btn btn-danger btn-sm" onClick={() => onRequestDelete("project")}>
                <Trash2 size={12} /> Delete Project
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
