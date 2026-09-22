"use client";

import React, { useState } from "react";
import {
  Sparkles,
  ArrowRight,
  ShieldCheck,
  Zap,
  Code2,
  GitPullRequest,
  CheckCircle2,
  Clock,
  AlertTriangle,
  FolderGit2,
  Users,
  MessageSquare,
  FileCode2,
  LayoutGrid,
  Play,
  Terminal,
  Layers,
  Search,
} from "lucide-react";
import { isPendingApproval } from "@/features/chat/approval";
import AgentAvatar from "./AgentAvatar";
import type { AgentConfig, TaskItem, ChatMessage } from "@/lib/types";
import styles from "./WorkspaceHome.module.css";

interface WorkspaceHomeProps {
  projects: any[];
  projectId: string | null;
  onProjectChange: (id: string) => void;
  teams: any[];
  teamId: string | null;
  onTeamChange: (id: string) => void;
  agents: AgentConfig[];
  tasks: TaskItem[];
  messages: ChatMessage[];
  onStartObjective: (text: string) => void;
  onNavigateToChat: () => void;
  onNavigateToTasks: () => void;
  onOpenFile?: (path: string) => void;
}

export default function WorkspaceHome({
  projects,
  projectId,
  onProjectChange,
  teams,
  teamId,
  onTeamChange,
  agents,
  tasks,
  messages,
  onStartObjective,
  onNavigateToChat,
  onNavigateToTasks,
  onOpenFile,
}: WorkspaceHomeProps) {
  const [objectiveInput, setObjectiveInput] = useState("");

  const currentProject = projects.find((p) => p.id === projectId);
  const currentTeam = teams.find((t) => t.id === teamId);

  // Derive pending approvals & questions
  const pendingApprovals = messages.filter(isPendingApproval);

  const pendingQuestions = messages.filter(
    (m) => (m.type === "agent_question" || m.type === "ask_user") && !m.is_answered && !m.answer
  );

  // Running tasks
  const inProgressTasks = tasks.filter(
    (t) => t.status === "in_progress" || t.status === "active"
  );
  const completedTasks = tasks
    .filter((t) => t.status === "done" || t.status === "completed")
    .slice(0, 5);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!objectiveInput.trim()) return;
    onStartObjective(objectiveInput.trim());
    setObjectiveInput("");
  };

  const handleStarterClick = (prompt: string) => {
    onStartObjective(prompt);
  };

  return (
    <div className={styles.homeContainer}>
      <div className={styles.scrollWrapper}>
        <div className={styles.content}>
          {/* Hero Welcome Banner */}
          <section className={styles.heroSection}>
            <div className={styles.heroBadge}>
              <Sparkles size={13} className={styles.sparkleIcon} />
              <span>Engineering Control Plane</span>
            </div>
            <h1 className={styles.heroTitle}>Resume work or state an objective</h1>
            <p className={styles.heroSubtitle}>
              Carole orchestrates multi-agent engineering teams with real tools, durable
              memory, live file diffs, and transparent human approval.
            </p>

            {/* Prominent Objective Composer */}
            <form onSubmit={handleSubmit} className={styles.composerCard}>
              <div className={styles.composerHeader}>
                <div className={styles.targetContext}>
                  <span className={styles.contextLabel}>Targeting:</span>
                  <span className={styles.contextPill}>
                    <FolderGit2 size={12} /> {currentProject?.name || "Project"}
                  </span>
                  <span className={styles.contextPill}>
                    <Users size={12} /> {currentTeam?.name || "Team"}
                  </span>
                </div>
                {agents.length > 0 && (
                  <div className={styles.teamAvatars}>
                    {agents.slice(0, 4).map((a) => (
                      <AgentAvatar
                        key={a.id}
                        name={a.name}
                        id={a.id}
                        role={a.role}
                        size={22}
                        hideBadge
                      />
                    ))}
                    {agents.length > 4 && (
                      <span className={styles.teamMore}>+{agents.length - 4}</span>
                    )}
                  </div>
                )}
              </div>

              <textarea
                className={styles.composerTextarea}
                aria-label="Describe your objective"
                placeholder="Describe an objective (e.g., 'Refactor the authentication flow with JWT refresh tokens and write unit tests')..."
                value={objectiveInput}
                onChange={(e) => setObjectiveInput(e.target.value)}
                rows={3}
                onKeyDown={(e) => {
                  if (!e.nativeEvent.isComposing && e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                    handleSubmit(e);
                  }
                }}
              />

              <div className={styles.composerFooter}>
                <div className={styles.keyboardHint}>Press Ctrl+Enter to dispatch</div>
                <button
                  type="submit"
                  className={`btn btn-primary ${styles.dispatchBtn}`}
                  disabled={!objectiveInput.trim()}
                >
                  <span>Dispatch Objective</span>
                  <ArrowRight size={14} />
                </button>
              </div>
            </form>

            {/* Quick Starter Templates */}
            <div className={styles.starterGrid}>
              {[
                {
                  icon: ShieldCheck,
                  label: "Audit security boundaries",
                  prompt:
                    "Perform a security audit across the codebase: check for SSRF vectors, exposed secrets, and unvalidated inputs.",
                },
                {
                  icon: Code2,
                  label: "Build API endpoint with tests",
                  prompt:
                    "Implement a robust API endpoint with request validation, database persistence, and comprehensive test coverage.",
                },
                {
                  icon: GitPullRequest,
                  label: "Inspect and review diffs",
                  prompt:
                    "Review all uncommitted git changes, analyze potential regression risks, and prepare a clean summary.",
                },
                {
                  icon: Zap,
                  label: "Triage & unblock Kanban tasks",
                  prompt:
                    "Review the current task board, inspect blocked items, and coordinate the team to complete pending goals.",
                },
              ].map((starter, i) => (
                <button
                  key={i}
                  className={styles.starterCard}
                  onClick={() => handleStarterClick(starter.prompt)}
                  type="button"
                >
                  <starter.icon size={16} className={styles.starterIcon} />
                  <span className={styles.starterLabel}>{starter.label}</span>
                  <ArrowRight size={12} className={styles.starterArrow} />
                </button>
              ))}
            </div>
          </section>

          {/* Attention Required (Approvals & Agent Questions) */}
          {(pendingApprovals.length > 0 || pendingQuestions.length > 0) && (
            <section className={styles.section}>
              <div className={styles.sectionHeader}>
                <div className={styles.sectionTitleGroup}>
                  <AlertTriangle size={16} style={{ color: "var(--color-warning)" }} />
                  <h3 className={styles.sectionTitle}>Requires Your Attention</h3>
                  <span className="state-badge state-waiting">
                    {pendingApprovals.length + pendingQuestions.length} item
                    {pendingApprovals.length + pendingQuestions.length > 1 ? "s" : ""}
                  </span>
                </div>
              </div>

              <div className={styles.attentionGrid}>
                {pendingApprovals.map((appr) => (
                  <div key={appr.id} className={styles.attentionCard}>
                    <div className={styles.attentionCardTop}>
                      <span className="state-badge state-waiting">Approval Required</span>
                      <span className={styles.attentionAgent}>
                        {appr.sender_name || "Agent"}
                      </span>
                    </div>
                    <div className={styles.attentionDesc}>
                      {appr.pending_approval?.tool_name
                        ? `Request to execute ${appr.pending_approval.tool_name}`
                        : appr.text || "Pending action approval"}
                    </div>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={onNavigateToChat}
                      style={{ alignSelf: "flex-start", marginTop: 8 }}
                    >
                      <span>Review in Chat</span>
                      <ArrowRight size={12} />
                    </button>
                  </div>
                ))}

                {pendingQuestions.map((q) => (
                  <div key={q.id} className={styles.attentionCard}>
                    <div className={styles.attentionCardTop}>
                      <span className="state-badge state-planning">Question</span>
                      <span className={styles.attentionAgent}>
                        {q.sender_name || "Agent"}
                      </span>
                    </div>
                    <div className={styles.attentionDesc}>
                      {q.question || q.text || "Agent asked a clarifying question"}
                    </div>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={onNavigateToChat}
                      style={{ alignSelf: "flex-start", marginTop: 8 }}
                    >
                      <span>Answer in Chat</span>
                      <ArrowRight size={12} />
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Active Work & Running Background Work */}
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <div className={styles.sectionTitleGroup}>
                <Clock size={16} style={{ color: "var(--color-primary-soft)" }} />
                <h3 className={styles.sectionTitle}>Active & Background Work</h3>
                {inProgressTasks.length > 0 && (
                  <span className="state-badge state-working">
                    {inProgressTasks.length} in progress
                  </span>
                )}
              </div>
              <button className="btn btn-ghost btn-sm" onClick={onNavigateToTasks}>
                <LayoutGrid size={13} /> View Board
              </button>
            </div>

            {inProgressTasks.length > 0 ? (
              <div className={styles.taskGrid}>
                {inProgressTasks.map((t) => (
                  <div key={t.id} className={styles.taskCard}>
                    <div className={styles.taskCardHeader}>
                      <span className="state-badge state-working">
                        <span className="state-indicator">●</span> In Progress
                      </span>
                      {t.priority && (
                        <span className={styles.priorityBadge}>{t.priority}</span>
                      )}
                    </div>
                    <h4 className={styles.taskTitle}>{t.title}</h4>
                    <p className={styles.taskDesc}>{t.description || "Active task"}</p>
                    <div className={styles.taskFooter}>
                      <span className={styles.taskAssignee}>
                        Assignee: {t.assigned_to || t.assigned_agent_id || "Unassigned"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className={styles.emptyCard}>
                <p>No active background tasks running right now. All agents are idle and ready.</p>
              </div>
            )}
          </section>

          {/* Recent Completed Work & Deliverables */}
          {completedTasks.length > 0 && (
            <section className={styles.section}>
              <div className={styles.sectionHeader}>
                <div className={styles.sectionTitleGroup}>
                  <CheckCircle2 size={16} style={{ color: "var(--color-success)" }} />
                  <h3 className={styles.sectionTitle}>Recent Deliverables</h3>
                </div>
              </div>

              <div className={styles.deliverablesList}>
                {completedTasks.map((t) => (
                  <div key={t.id} className={styles.deliverableRow}>
                    <CheckCircle2 size={15} style={{ color: "var(--color-success)" }} />
                    <span className={styles.deliverableTitle}>{t.title}</span>
                    <span className={styles.deliverableTime}>Completed</span>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
