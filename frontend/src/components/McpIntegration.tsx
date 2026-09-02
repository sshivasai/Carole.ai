"use client";
import React, { useState, useEffect, useCallback, useMemo } from "react";
import { api } from "@/hooks/useApi";
import { AgentConfig } from "@/lib/types";
import {
  Plus,
  Loader2,
  Server,
  Trash2,
  Power,
  Search,
  CheckCircle2,
  ExternalLink,
  Sliders,
  Plug,
  X,
  Key,
  Eye,
  EyeOff,
  Sparkles,
} from "lucide-react";
import { MCP_TEMPLATES, McpTemplate } from "@/lib/mcpTemplates";
import {
  GitHubLogo,
  GitLabLogo,
  SlackLogo,
  DiscordLogo,
  LinearLogo,
  NotionLogo,
  JiraLogo,
  PostgresLogo,
  RedisLogo,
  SupabaseLogo,
  GoogleDriveLogo,
  SentryLogo,
  StripeLogo,
  AWSLogo,
  AirtableLogo,
  BraveSearchLogo,
  FigmaLogo,
  HubSpotLogo,
  AsanaLogo,
  PuppeteerLogo,
  DockerLogo,
  MongoDBLogo,
  PerplexityLogo,
  McpLogo,
  DatabaseLogo,
} from "@/components/icons/IntegrationLogos";

interface Props {
  teamId: string | null;
  agents: AgentConfig[];
  onToast?: (msg: string, type: "success" | "error") => void;
}

const CATEGORIES = [
  "All",
  "Developer",
  "Database",
  "Productivity",
  "Communication",
  "Finance & CRM",
  "Cloud & Search",
  "Active",
] as const;

export default function McpIntegration({ teamId, agents, onToast }: Props) {
  const [servers, setServers] = useState<any[]>([]);
  const [globalServers, setGlobalServers] = useState<any[]>([]);
  const [fetching, setFetching] = useState(false);
  const [toggling, setToggling] = useState<string | null>(null);

  // Filter & Search State
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("All");

  // Connect Modal State
  const [selectedTemplate, setSelectedTemplate] = useState<McpTemplate | null>(null);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [selectedAgentId, setSelectedAgentId] = useState<string>("");
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
  const [connecting, setConnecting] = useState(false);

  // Custom Raw Form State
  const [showCustomForm, setShowCustomForm] = useState(false);
  const [customServerName, setCustomServerName] = useState("");
  const [customCommand, setCustomCommand] = useState("");
  const [customArgs, setCustomArgs] = useState("");
  const [customEnvVars, setCustomEnvVars] = useState("");
  const [customAgentId, setCustomAgentId] = useState("");
  const [customLoading, setCustomLoading] = useState(false);

  const [templates, setTemplates] = useState<McpTemplate[]>(MCP_TEMPLATES);

  const loadServers = useCallback(async () => {
    if (!teamId) return;
    setFetching(true);
    try {
      const [teamMcps, globalMcps, dynamicTemplates] = await Promise.all([
        api.listMcpServers(teamId),
        api.listGlobalMcpServers(),
        api.getMcpTemplates().catch(() => MCP_TEMPLATES),
      ]);
      setServers(teamMcps || []);
      setGlobalServers(globalMcps || []);
      if (dynamicTemplates && dynamicTemplates.length > 0) {
        setTemplates(dynamicTemplates);
      }
    } catch {
      // ignore
    } finally {
      setFetching(false);
    }
  }, [teamId]);

  useEffect(() => {
    if (teamId) loadServers();
    else {
      setServers([]);
      setGlobalServers([]);
    }
  }, [teamId, loadServers]);

  const renderLogo = (logoKey: string, size = 26) => {
    const cleanKey = (logoKey || "").toLowerCase().trim();
    switch (cleanKey) {
      case "github": return <GitHubLogo size={size} />;
      case "gitlab": return <GitLabLogo size={size} />;
      case "slack": return <SlackLogo size={size} />;
      case "discord": return <DiscordLogo size={size} />;
      case "linear": return <LinearLogo size={size} />;
      case "notion": return <NotionLogo size={size} />;
      case "jira": return <JiraLogo size={size} />;
      case "postgres":
      case "postgresql": return <PostgresLogo size={size} />;
      case "redis": return <RedisLogo size={size} />;
      case "supabase": return <SupabaseLogo size={size} />;
      case "google-drive":
      case "googledrive": return <GoogleDriveLogo size={size} />;
      case "sentry": return <SentryLogo size={size} />;
      case "stripe": return <StripeLogo size={size} />;
      case "aws":
      case "amazons3": return <AWSLogo size={size} />;
      case "airtable": return <AirtableLogo size={size} />;
      case "brave-search":
      case "brave": return <BraveSearchLogo size={size} />;
      case "figma": return <FigmaLogo size={size} />;
      case "hubspot": return <HubSpotLogo size={size} />;
      case "asana": return <AsanaLogo size={size} />;
      case "puppeteer": return <PuppeteerLogo size={size} />;
      case "docker": return <DockerLogo size={size} />;
      case "mongodb": return <MongoDBLogo size={size} />;
      case "perplexity": return <PerplexityLogo size={size} />;
      case "mcp": return <McpLogo size={size} />;
      case "database": return <DatabaseLogo size={size} />;
      default:
        return (
          <img
            src={`/logos/${cleanKey}.svg`}
            alt={cleanKey}
            style={{ width: size, height: size, objectFit: "contain" }}
            onError={(e) => {
              (e.currentTarget as HTMLElement).style.display = "none";
            }}
          />
        );
    }
  };

  // Check if a template is already connected
  const isTemplateConnected = (templateId: string) => {
    const tid = templateId.toLowerCase();
    return servers.some((s) => {
      const name = (s.server_name || "").toLowerCase();
      const argsStr = (Array.isArray(s.args) ? s.args.join(" ") : String(s.args || "")).toLowerCase();
      return name === tid || argsStr.includes(tid);
    });
  };

  const getConnectedServer = (templateId: string) => {
    const tid = templateId.toLowerCase();
    return servers.find((s) => {
      const name = (s.server_name || "").toLowerCase();
      const argsStr = (Array.isArray(s.args) ? s.args.join(" ") : String(s.args || "")).toLowerCase();
      return name === tid || argsStr.includes(tid);
    });
  };

  // Open 1-Click Connect Modal
  const openConnectModal = (template: McpTemplate) => {
    setSelectedTemplate(template);
    const initialValues: Record<string, string> = {};
    template.fields.forEach((f) => {
      if (f.defaultValue) initialValues[f.key] = f.defaultValue;
    });
    setFieldValues(initialValues);
    setSelectedAgentId("");
    setShowSecrets({});
  };

  // Handle 1-Click Connect Submission
  const handleConnectTemplate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!teamId || !selectedTemplate) return;

    setConnecting(true);
    try {
      // Package the environment variables
      const env_vars: Record<string, string> = {};
      selectedTemplate.fields.forEach((field) => {
        const val = fieldValues[field.key]?.trim();
        if (val) {
          env_vars[field.key] = val;
        }
      });

      await api.createMcpServer({
        team_id: teamId,
        server_name: selectedTemplate.id,
        command: selectedTemplate.command,
        args: selectedTemplate.args,
        agent_id: selectedAgentId || undefined,
        env_vars: Object.keys(env_vars).length > 0 ? env_vars : undefined,
      });

      await loadServers();
      setSelectedTemplate(null);
      onToast?.(`Connected ${selectedTemplate.name} successfully!`, "success");
    } catch {
      onToast?.(`Failed to connect ${selectedTemplate.name}`, "error");
    } finally {
      setConnecting(false);
    }
  };

  // Disconnect an MCP server
  const handleDisconnect = async (serverId: string, serverName: string) => {
    try {
      await api.deleteMcpServer(serverId);
      await loadServers();
      onToast?.(`Disconnected ${serverName}`, "success");
    } catch {
      onToast?.(`Failed to disconnect ${serverName}`, "error");
    }
  };

  // Handle Custom Manual Server Submission
  const handleAddCustom = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!teamId || !customServerName || !customCommand) return;
    setCustomLoading(true);
    try {
      const parsedEnv: Record<string, string> = {};
      if (customEnvVars.trim()) {
        customEnvVars.split("\n").forEach((line) => {
          const idx = line.indexOf("=");
          if (idx > 0)
            parsedEnv[line.substring(0, idx).trim()] = line
              .substring(idx + 1)
              .trim();
        });
      }
      await api.createMcpServer({
        team_id: teamId,
        server_name: customServerName,
        command: customCommand,
        args: customArgs,
        agent_id: customAgentId || undefined,
        env_vars: Object.keys(parsedEnv).length > 0 ? parsedEnv : undefined,
      });
      await loadServers();
      setCustomServerName("");
      setCustomCommand("");
      setCustomArgs("");
      setCustomAgentId("");
      setCustomEnvVars("");
      setShowCustomForm(false);
      onToast?.("Custom MCP server added", "success");
    } catch {
      onToast?.("Failed to add custom server", "error");
    } finally {
      setCustomLoading(false);
    }
  };

  const handleToggleGlobal = async (server_name: string) => {
    setToggling(server_name);
    try {
      await api.toggleGlobalMcpServer(server_name);
      await loadServers();
      onToast?.(`Toggled global MCP ${server_name}`, "success");
    } catch {
      onToast?.(`Failed to toggle ${server_name}`, "error");
    } finally {
      setToggling(null);
    }
  };

  // Filter templates
  const filteredTemplates = useMemo(() => {
    const seen = new Set<string>();
    return templates.filter((tpl) => {
      if (seen.has(tpl.id)) return false;
      seen.add(tpl.id);

      const matchesSearch =
        tpl.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        tpl.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
        tpl.category.toLowerCase().includes(searchQuery.toLowerCase());

      if (!matchesSearch) return false;

      if (selectedCategory === "All") return true;
      if (selectedCategory === "Active") return isTemplateConnected(tpl.id);
      return tpl.category === selectedCategory;
    });
  }, [searchQuery, selectedCategory, servers, templates]);

  if (!teamId) {
    return (
      <p className="caption" style={{ padding: "var(--sp-md)", textAlign: "center" }}>
        Select a team to manage MCP servers & integrations.
      </p>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-xl)", height: "100%" }}>
      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "var(--sp-md)", flexWrap: "wrap" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", marginBottom: 4 }}>
            <Plug size={18} color="var(--color-primary)" />
            <h3 className="display-sm" style={{ margin: 0, color: "var(--color-fg)" }}>
              MCP & Integrations Marketplace
            </h3>
            <span className="badge badge-primary" style={{ fontSize: 10 }}>1-Click Connect</span>
          </div>
          <p className="body-sm text-mute" style={{ margin: 0 }}>
            Connect official Model Context Protocol servers to grant your agents autonomous superpowers.
          </p>
        </div>

        <button
          className={`btn btn-sm ${showCustomForm ? "btn-outline" : "btn-primary"}`}
          onClick={() => setShowCustomForm((v) => !v)}
          style={{ display: "flex", alignItems: "center", gap: 6 }}
        >
          {showCustomForm ? <X size={13} /> : <Plus size={13} />}
          {showCustomForm ? "Close Custom Form" : " Custom MCP Server"}
        </button>
      </div>

      {/* ── Custom Raw Form (Collapsible) ─────────────────────────────────── */}
      {showCustomForm && (
        <form
          onSubmit={handleAddCustom}
          style={{
            background: "var(--color-canvas-raised)",
            border: "1px solid var(--color-primary)",
            borderRadius: "var(--radius-md)",
            padding: "var(--sp-lg)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--sp-sm)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
            <Sliders size={14} color="var(--color-primary)" />
            <span className="body-sm-strong" style={{ color: "var(--color-fg)" }}>
              Add Custom Stdio / SSE Server
            </span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--sp-sm)" }}>
            <input
              className="input input-sm"
              placeholder="Server name (e.g. internal-db)"
              value={customServerName}
              onChange={(e) => setCustomServerName(e.target.value)}
            />
            <input
              className="input input-sm"
              placeholder="Command (e.g. npx or uvx)"
              value={customCommand}
              onChange={(e) => setCustomCommand(e.target.value)}
            />
          </div>
          <input
            className="input input-sm"
            placeholder="Arguments comma-separated (e.g. -y,@modelcontextprotocol/server-xyz)"
            value={customArgs}
            onChange={(e) => setCustomArgs(e.target.value)}
          />
          <textarea
            className="input"
            placeholder="Environment Variables (KEY=VALUE per line)&#10;e.g. API_SECRET=xyz"
            value={customEnvVars}
            onChange={(e) => setCustomEnvVars(e.target.value)}
            style={{ fontSize: 11, minHeight: 60, resize: "vertical" }}
          />
          <div style={{ display: "flex", gap: "var(--sp-sm)", justifyContent: "space-between", alignItems: "center" }}>
            <select
              className="input input-sm"
              value={customAgentId}
              onChange={(e) => setCustomAgentId(e.target.value)}
              style={{ maxWidth: 220 }}
            >
              <option value="">Global (all agents)</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.role})
                </option>
              ))}
            </select>
            <button
              type="submit"
              className="btn btn-primary btn-sm"
              disabled={customLoading || !customServerName || !customCommand}
            >
              {customLoading ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
              Save Custom Server
            </button>
          </div>
        </form>
      )}

      {/* ── Search & Filter Tabs ─────────────────────────────────────────── */}
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
        <div style={{ display: "flex", gap: "var(--sp-md)", alignItems: "center", flexWrap: "wrap" }}>
          {/* Search bar */}
          <div style={{ position: "relative", flex: 1, minWidth: 240 }}>
            <Search
              size={14}
              color="var(--color-mute)"
              style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)" }}
            />
            <input
              type="text"
              className="input input-sm"
              placeholder="Search MCP integrations (GitHub, Slack, Postgres, Linear...)"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ paddingLeft: 32 }}
            />
          </div>

          {/* Category tabs */}
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                className={`btn btn-sm ${selectedCategory === cat ? "btn-primary" : "btn-ghost"}`}
                onClick={() => setSelectedCategory(cat)}
                style={{ fontSize: 11, padding: "4px 10px" }}
              >
                {cat}
                {cat === "Active" && servers.length > 0 && (
                  <span
                    style={{
                      background: "rgba(34, 197, 94, 0.2)",
                      color: "#4ade80",
                      borderRadius: 10,
                      padding: "1px 6px",
                      marginLeft: 4,
                      fontSize: 10,
                    }}
                  >
                    {servers.length}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Marketplace Grid ──────────────────────────────────────────────── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: "var(--sp-md)",
          overflowY: "auto",
        }}
      >
        {filteredTemplates.map((template) => {
          const connected = isTemplateConnected(template.id);
          const activeServer = getConnectedServer(template.id);

          return (
            <div
              key={template.id}
              style={{
                background: "var(--color-canvas-raised)",
                border: `1px solid ${connected ? "rgba(34, 197, 94, 0.5)" : "var(--color-hairline)"}`,
                borderRadius: "var(--radius-md)",
                padding: "var(--sp-lg)",
                display: "flex",
                flexDirection: "column",
                gap: "var(--sp-md)",
                position: "relative",
                transition: "all var(--t-fast)",
                boxShadow: connected ? "0 0 12px rgba(34, 197, 94, 0.08)" : "none",
              }}
            >
              {/* Card Header: Logo & Badges */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)" }}>
                  <div
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: "var(--radius-sm)",
                      background: "var(--color-canvas-subtle, rgba(125, 125, 125, 0.08))",
                      border: "1px solid var(--color-hairline)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: "var(--color-ink-strong)",
                      flexShrink: 0,
                    }}
                  >
                    {renderLogo(template.logo, 26)}
                  </div>
                  <div>
                    <h4 className="body-sm-strong" style={{ margin: 0, fontSize: 14, color: "var(--color-ink-strong)" }}>
                      {template.name}
                    </h4>
                    <span className="caption text-mute">{template.category}</span>
                  </div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
                  {template.badge && (
                    <span
                      style={{
                        fontSize: 9,
                        fontWeight: 700,
                        textTransform: "uppercase",
                        letterSpacing: 0.5,
                        background: "rgba(99, 102, 241, 0.15)",
                        color: "#818cf8",
                        padding: "2px 6px",
                        borderRadius: 4,
                      }}
                    >
                      {template.badge}
                    </span>
                  )}
                  {connected && (
                    <span
                      style={{
                        fontSize: 10,
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                        color: "#4ade80",
                      }}
                    >
                      <div
                        style={{
                          width: 6,
                          height: 6,
                          borderRadius: "50%",
                          background: "#4ade80",
                          boxShadow: "0 0 6px #4ade80",
                        }}
                      />
                      Connected
                    </span>
                  )}
                </div>
              </div>

              {/* Card Description */}
              <p
                className="body-sm text-mute"
                style={{
                  margin: 0,
                  fontSize: 12,
                  lineHeight: 1.45,
                  minHeight: 36,
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}
              >
                {template.description}
              </p>

              {/* Card Footer: Action Button */}
              <div style={{ marginTop: "auto", display: "flex", gap: "var(--sp-sm)", alignItems: "center" }}>
                {connected ? (
                  <button
                    className="btn btn-outline btn-sm"
                    style={{
                      flex: 1,
                      borderColor: "rgba(239, 68, 68, 0.4)",
                      color: "#f87171",
                      fontSize: 11,
                    }}
                    onClick={() =>
                      activeServer && handleDisconnect(activeServer.id, template.name)
                    }
                  >
                    <Trash2 size={11} /> Disconnect
                  </button>
                ) : (
                  <button
                    className="btn btn-primary btn-sm"
                    style={{ flex: 1, fontSize: 11 }}
                    onClick={() => openConnectModal(template)}
                  >
                    <Key size={11} /> Connect
                  </button>
                )}

                <a
                  href={template.docsUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-icon-sm btn-ghost"
                  title="View Documentation & Token Settings"
                >
                  <ExternalLink size={12} />
                </a>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Active Global Built-in Servers List ───────────────────────────── */}
      {globalServers.length > 0 && (
        <div style={{ marginTop: "var(--sp-md)" }}>
          <h4 className="label" style={{ marginBottom: "var(--sp-sm)", color: "var(--color-fg)" }}>
            Global Studio MCP Servers
          </h4>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-sm)" }}>
            {globalServers.map((s) => (
              <div
                key={s.server_name}
                style={{
                  background: "var(--color-canvas-raised)",
                  border: "1px solid var(--color-hairline)",
                  borderRadius: "var(--radius-sm)",
                  padding: "var(--sp-md)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  opacity: s.is_disabled ? 0.6 : 1,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)" }}>
                  <Server
                    size={14}
                    color={s.is_connected ? "var(--color-primary)" : "var(--color-mute)"}
                  />
                  <div>
                    <span className="body-sm-strong" style={{ color: "var(--color-fg)" }}>
                      {s.server_name}
                    </span>
                    <span className="caption text-mute" style={{ marginLeft: 8 }}>
                      {s.command} {Array.isArray(s.args) ? s.args.join(" ") : String(s.args || "")}
                    </span>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
                  <button
                    className={`btn btn-icon-sm btn-ghost ${s.is_disabled ? "text-success" : "text-danger"
                      }`}
                    title={s.is_disabled ? "Enable Server" : "Disable Server"}
                    onClick={() => handleToggleGlobal(s.server_name)}
                    disabled={toggling === s.server_name}
                  >
                    {toggling === s.server_name ? (
                      <Loader2 size={13} className="animate-spin" />
                    ) : (
                      <Power size={13} />
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 1-Click Connect Credential Modal ───────────────────────────────── */}
      {selectedTemplate && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.75)",
            backdropFilter: "blur(6px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
            padding: "var(--sp-md)",
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setSelectedTemplate(null);
          }}
        >
          <div
            style={{
              background: "var(--color-canvas-raised, #0f172a)",
              border: "1px solid var(--color-hairline)",
              borderRadius: "var(--radius-lg, 12px)",
              maxWidth: 480,
              width: "100%",
              padding: "var(--sp-xl)",
              display: "flex",
              flexDirection: "column",
              gap: "var(--sp-lg)",
              boxShadow: "0 20px 40px rgba(0, 0, 0, 0.5)",
              animation: "fadeIn 0.15s ease-out",
              color: "var(--color-fg)",
            }}
          >
            {/* Modal Header */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)" }}>
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: "var(--radius-sm)",
                    background: "var(--color-canvas-subtle, rgba(125, 125, 125, 0.08))",
                    border: "1px solid var(--color-hairline)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "var(--color-fg)",
                  }}
                >
                  {renderLogo(selectedTemplate.logo, 24)}
                </div>
                <div>
                  <h3 className="body-md-strong" style={{ margin: 0, color: "var(--color-fg)" }}>
                    Connect {selectedTemplate.name}
                  </h3>
                  <span className="caption text-mute">{selectedTemplate.description}</span>
                </div>
              </div>
              <button
                className="btn btn-icon-sm btn-ghost"
                onClick={() => setSelectedTemplate(null)}
              >
                <X size={14} />
              </button>
            </div>

            {/* Modal Form */}
            <form onSubmit={handleConnectTemplate} style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
              {selectedTemplate.fields.map((field) => (
                <div key={field.key} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <label className="label" style={{ fontSize: 11, color: "var(--color-fg)" }}>
                      {field.label} {field.required && <span style={{ color: "var(--color-danger)" }}>*</span>}
                    </label>
                    {field.isSecret && (
                      <button
                        type="button"
                        onClick={() =>
                          setShowSecrets((prev) => ({ ...prev, [field.key]: !prev[field.key] }))
                        }
                        style={{
                          background: "none",
                          border: "none",
                          cursor: "pointer",
                          color: "var(--color-mute)",
                          display: "flex",
                          alignItems: "center",
                          gap: 3,
                          fontSize: 10,
                        }}
                      >
                        {showSecrets[field.key] ? <EyeOff size={10} /> : <Eye size={10} />}
                        {showSecrets[field.key] ? "Hide" : "Show"}
                      </button>
                    )}
                  </div>

                  {field.type === "textarea" ? (
                    <textarea
                      className="input"
                      placeholder={field.placeholder}
                      value={fieldValues[field.key] || ""}
                      onChange={(e) =>
                        setFieldValues((prev) => ({ ...prev, [field.key]: e.target.value }))
                      }
                      style={{ fontSize: 11, minHeight: 80, resize: "vertical" }}
                      required={field.required}
                    />
                  ) : (
                    <input
                      type={field.isSecret && !showSecrets[field.key] ? "password" : "text"}
                      className="input input-sm"
                      placeholder={field.placeholder}
                      value={fieldValues[field.key] || ""}
                      onChange={(e) =>
                        setFieldValues((prev) => ({ ...prev, [field.key]: e.target.value }))
                      }
                      required={field.required}
                    />
                  )}

                  {field.helpText && (
                    <span className="caption text-mute" style={{ fontSize: 10 }}>
                      {field.helpText}
                    </span>
                  )}
                </div>
              ))}

              {/* Scope to Agent (Optional) */}
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <label className="label" style={{ fontSize: 11, color: "var(--color-fg)" }}>
                  Scope Access
                </label>
                <select
                  className="input input-sm"
                  value={selectedAgentId}
                  onChange={(e) => setSelectedAgentId(e.target.value)}
                >
                  <option value="">Global (All agents in team)</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} ({a.role})
                    </option>
                  ))}
                </select>
              </div>

              {/* Docs Help Link */}
              <div
                style={{
                  background: "rgba(99, 102, 241, 0.08)",
                  borderRadius: "var(--radius-sm)",
                  padding: "8px 12px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  fontSize: 11,
                }}
              >
                <span className="text-mute">Need help creating your credentials?</span>
                <a
                  href={selectedTemplate.docsUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    color: "var(--color-primary)",
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    textDecoration: "none",
                    fontWeight: 600,
                  }}
                >
                  Get Key <ExternalLink size={10} />
                </a>
              </div>

              {/* Action Buttons */}
              <div style={{ display: "flex", gap: "var(--sp-sm)", justifyContent: "flex-end", marginTop: "var(--sp-sm)" }}>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setSelectedTemplate(null)}
                  disabled={connecting}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary btn-sm" disabled={connecting}>
                  {connecting ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <CheckCircle2 size={12} />
                  )}
                  {connecting ? "Connecting..." : "Save & Connect"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
