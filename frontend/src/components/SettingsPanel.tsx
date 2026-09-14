"use client";
import React, { useState, useMemo } from "react";
import {
  Settings,
  User,
  Key,
  Cpu,
  Shield,
  MessageSquare,
  Globe,
  DollarSign,
  Search,
  Trash2,
  AlertTriangle,
  Loader2,
  ChevronRight,
  Sliders,
  Sparkles,
  Activity,
} from "lucide-react";
import type { AgentConfig } from "@/lib/types";
import { api } from "@/hooks/useApi";
import Modal from "./Modal";
import styles from "./SettingsPanel.module.css";

// Sub-components
import GeneralSettings from "./settings/GeneralSettings";
import ProvidersSettings from "./settings/ProvidersSettings";
import ModelsSettings from "./settings/ModelsSettings";
import RuntimeSafetySettings from "./settings/RuntimeSafetySettings";
import BrowserSettings from "./settings/BrowserSettings";
import PromptsSettings from "./settings/PromptsSettings";
import ProjectCostSettings from "./settings/ProjectCostSettings";
import ObservabilitySettings from "./settings/ObservabilitySettings";

interface Props {
  teamId: string | null;
  projectId: string | null;
  agents: AgentConfig[];
  onToast: (msg: string, type: "success" | "error" | "info") => void;
  onTeamDeleted: () => void;
  onProjectDeleted: () => void;
}

type TabKey = "general" | "providers" | "models" | "observability" | "runtime" | "prompts" | "browser" | "project";

interface TabDefinition {
  id: TabKey;
  label: string;
  icon: React.ElementType;
  description: string;
  keywords: string[];
  group: "System & Access" | "AI & Capabilities" | "Workspace & Data";
}

const SETTINGS_TABS: TabDefinition[] = [
  {
    id: "general",
    label: "General & Health",
    icon: User,
    description: "Account profile, Google Workspace OAuth, and live backend health telemetry.",
    keywords: ["profile", "user", "email", "google", "calendar", "gmail", "meet", "health", "fastapi", "tools", "websocket"],
    group: "System & Access",
  },
  {
    id: "providers",
    label: "API Keys & Providers",
    icon: Key,
    description: "API keys for OpenAI, Anthropic, Gemini, OpenRouter, NVIDIA, Tavily, and Ollama.",
    keywords: ["api", "keys", "openai", "anthropic", "claude", "gemini", "google", "openrouter", "deepseek", "nvidia", "tavily", "ollama", "localhost"],
    group: "System & Access",
  },
  {
    id: "models",
    label: "Models & Catalog",
    icon: Cpu,
    description: "Global fallback models (Fast, Smart, Coder, Judge) and provider model catalog.",
    keywords: ["models", "defaults", "catalog", "fast", "smart", "coder", "judge", "gpt", "claude", "gemini", "llama", "temperature"],
    group: "AI & Capabilities",
  },
  {
    id: "observability",
    label: "OpenLLMetry Tracing",
    icon: Activity,
    description: "Native OpenTelemetry distributed traces, multi-agent swarm spans, latency, and token metrics.",
    keywords: ["openllmetry", "observability", "tracing", "spans", "telemetry", "opentelemetry", "tokens", "latency", "flamegraph", "metrics"],
    group: "AI & Capabilities",
  },
  {
    id: "runtime",
    label: "Safety & Runtime",
    icon: Shield,
    description: "Access control matrix, safety judge arbiter, loop limits, and memory compaction.",
    keywords: ["access", "safety", "judge", "security", "permissions", "matrix", "loops", "timeout", "dream", "memory", "compaction"],
    group: "AI & Capabilities",
  },
  {
    id: "prompts",
    label: "Prompts & Capabilities",
    icon: MessageSquare,
    description: "Agent persona roles and modular system capability instruction blocks.",
    keywords: ["prompts", "roles", "personas", "system", "capabilities", "blocks", "instructions", "orchestrator", "coder", "debugger", "personality"],
    group: "AI & Capabilities",
  },
  {
    id: "browser",
    label: "Browser Automation",
    icon: Globe,
    description: "3-tier browser engine, Browserbase cloud stealth, anti-bot proxies, and vision model.",
    keywords: ["browser", "web", "automation", "playwright", "browseruse", "browserbase", "cloud", "proxy", "scraperapi", "zenrows", "headless", "windowed", "captcha", "vision"],
    group: "Workspace & Data",
  },
  {
    id: "project",
    label: "Project, Cost & Danger",
    icon: DollarSign,
    description: "Token spend tracking, budget caps, knowledge base documents, and data deletion.",
    keywords: ["project", "cost", "spend", "tokens", "budget", "usage", "analytics", "knowledge", "upload", "pdf", "danger", "delete", "team"],
    group: "Workspace & Data",
  },
];

export default function SettingsPanel({
  teamId,
  projectId,
  agents,
  onToast,
  onTeamDeleted,
  onProjectDeleted,
}: Props) {
  const [activeTab, setActiveTab] = useState<TabKey>("general");
  const [searchQuery, setSearchQuery] = useState("");

  // Deletion modals state
  const [confirmDelete, setConfirmDelete] = useState<"team" | "project" | null>(null);
  const [deleting, setDeleting] = useState(false);

  const handleDeleteTeam = async (deleteContent: boolean) => {
    if (!teamId) return;
    setDeleting(true);
    try {
      await api.deleteTeam(teamId, deleteContent);
      onTeamDeleted();
      onToast("Team deleted successfully", "success");
    } catch {
      onToast("Failed to delete team", "error");
    } finally {
      setDeleting(false);
      setConfirmDelete(null);
    }
  };

  const handleDeleteProject = async (deleteContent: boolean) => {
    if (!projectId) return;
    setDeleting(true);
    try {
      await api.deleteProject(projectId, deleteContent);
      onProjectDeleted();
      onToast("Project deleted successfully", "success");
    } catch {
      onToast("Failed to delete project", "error");
    } finally {
      setDeleting(false);
      setConfirmDelete(null);
    }
  };

  // Filter tabs by search query
  const filteredTabs = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return SETTINGS_TABS;
    return SETTINGS_TABS.filter(
      t =>
        t.label.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.keywords.some(k => k.toLowerCase().includes(q))
    );
  }, [searchQuery]);

  // Group tabs by category
  const groupedTabs = useMemo(() => {
    const groups: Record<string, TabDefinition[]> = {};
    filteredTabs.forEach(t => {
      if (!groups[t.group]) groups[t.group] = [];
      groups[t.group].push(t);
    });
    return groups;
  }, [filteredTabs]);

  const activeTabDef = SETTINGS_TABS.find(t => t.id === activeTab) || SETTINGS_TABS[0];

  return (
    <div className={styles.settings}>
      {/* ── Top Header Bar ── */}
      <header className={styles.header}>
        <div className={styles.headerIdentity}>
          <div className={styles.headerIcon}>
            <Settings size={16} />
          </div>
          <div>
            <div className={styles.breadcrumb}>
              <span>Settings</span>
              <ChevronRight size={13} color="var(--color-mute)" />
              <span>{activeTabDef.label}</span>
            </div>
            <p>Configure the workspace, agent capabilities, and safety boundaries.</p>
          </div>
        </div>
        <div className={styles.agentStatus}><i />{agents.length} active {agents.length === 1 ? "agent" : "agents"}</div>
      </header>

      {/* ── Main Two-Column Master-Detail Layout ── */}
      <div className={styles.layout}>
        {/* ── Left Sidebar Navigation ── */}
        <aside className={styles.navigation}>
          {/* Search Bar */}
          <div className={styles.searchBox}>
            <div>
              <Search size={14} />
              <input
                type="text"
                placeholder="Search settings..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className={styles.searchInput}
              />
            </div>
          </div>

          {/* Grouped Navigation Links */}
          <div className={styles.navGroups}>
            {Object.entries(groupedTabs).map(([groupName, tabs]) => (
              <div key={groupName}>
                <div className={styles.groupLabel}>
                  {groupName}
                </div>
                <div className={styles.navList}>
                  {tabs.map(tab => {
                    const Icon = tab.icon;
                    const isActive = activeTab === tab.id;
                    return (
                      <button
                        key={tab.id}
                        type="button"
                        onClick={() => setActiveTab(tab.id)}
                        className={`${styles.navItem} ${isActive ? styles.navItemActive : ""}`}
                      >
                        <span className={styles.navIcon}><Icon size={15} /></span>
                        <span>{tab.label}</span>
                        {isActive && <i />}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}

            {filteredTabs.length === 0 && (
              <div className={styles.emptySearch}>
                No settings match &quot;{searchQuery}&quot;
              </div>
            )}
          </div>
        </aside>

        {/* ── Right Content Area ── */}
        <main className={styles.content}>
          {/* Active Tab Header */}
          <div className={styles.contentIntro}>
            <span>{activeTabDef.group}</span>
            <h1>{activeTabDef.label}</h1>
            <p>{activeTabDef.description}</p>
          </div>

          {/* Active Tab View */}
          <div className={styles.settingPage} key={activeTab}>
            {activeTab === "general" && <GeneralSettings teamId={teamId} onToast={onToast} />}
            {activeTab === "providers" && <ProvidersSettings onToast={onToast} />}
            {activeTab === "models" && <ModelsSettings onToast={onToast} />}
            {activeTab === "observability" && <ObservabilitySettings onToast={onToast} />}
            {activeTab === "runtime" && <RuntimeSafetySettings onToast={onToast} />}
            {activeTab === "prompts" && <PromptsSettings onToast={onToast} />}
            {activeTab === "browser" && <BrowserSettings onToast={onToast} />}
            {activeTab === "project" && (
              <ProjectCostSettings
                teamId={teamId}
                projectId={projectId}
                onToast={onToast}
                onRequestDelete={setConfirmDelete}
              />
            )}
          </div>
        </main>
      </div>

      {/* ── Deletion Confirmation Modal ── */}
      <Modal open={!!confirmDelete} onClose={() => setConfirmDelete(null)} title="Confirm Deletion" maxWidth={450}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-lg)" }}>
          <p className="body-sm">
            This action <strong>cannot be undone</strong>. You can choose to only delete the {confirmDelete} record from the database, or additionally delete all associated files and folders on disk.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-sm)", marginTop: "var(--sp-sm)" }}>
            <button
              className="btn btn-danger btn-sm"
              onClick={() => (confirmDelete === "team" ? handleDeleteTeam(false) : handleDeleteProject(false))}
              disabled={deleting}
              style={{ width: "100%", justifyContent: "center" }}
            >
              {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />} Delete {confirmDelete} Record Only
            </button>
            <button
              className="btn btn-danger btn-sm"
              onClick={() => (confirmDelete === "team" ? handleDeleteTeam(true) : handleDeleteProject(true))}
              disabled={deleting}
              style={{
                width: "100%",
                justifyContent: "center",
                background: "var(--color-danger)",
                borderColor: "var(--color-danger)",
                color: "#fff",
              }}
            >
              {deleting ? <Loader2 size={13} className="animate-spin" /> : <AlertTriangle size={13} />} Delete {confirmDelete} AND Content on Disk
            </button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setConfirmDelete(null)}
              disabled={deleting}
              style={{ width: "100%", justifyContent: "center", marginTop: "var(--sp-xs)" }}
            >
              Cancel
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
