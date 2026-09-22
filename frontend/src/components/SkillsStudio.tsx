"use client";
import React, { useState, useEffect, useRef } from "react";
import {
  BookOpen, Plus, Save, Trash2, Loader2, Sparkles, FolderCode, FileCode,
  CheckCircle2, XCircle, Upload, RefreshCw, Edit3, Eye, FileText, Check,
  AlertCircle, Copy, Layers, HardDrive
} from "lucide-react";
import { api } from "@/hooks/useApi";
import Modal from "./Modal";
import { useAuth } from "@/hooks/useAuth";

const POPULAR_TOOLS = [
  "run_command",
  "view_file",
  "replace_file_content",
  "write_to_file",
  "grep_search",
  "read_resource",
  "search_web",
  "browser_subagent"
];

const SKILL_TEMPLATES = [
  {
    id: "custom",
    title: "Blank / Custom",
    desc: "Clean starting template with YAML frontmatter",
    name: "my-custom-skill",
    description: "Executes specialized automation tasks with dedicated tools",
    tools: "run_command, view_file",
    author: "Carole AI",
    version: "1.0.0",
    instructions: `# Instructions

## Overview
Describe the purpose and objective of this skill package.

## Execution Guidelines
1. Inspect the relevant workspace files or command outputs.
2. Formulate a plan before applying modifications.
3. Validate results and communicate outcomes clearly.
`
  },
  {
    id: "code-review",
    title: "Code Reviewer & Quality",
    desc: "Security, maintainability, and regression checks",
    name: "code-reviewer",
    description: "Reviews code changes against architecture standards and security best practices",
    tools: "view_file, grep_search, run_command",
    author: "Carole AI",
    version: "1.0.0",
    instructions: `# Code Review Protocol

## Objectives
Ensure high code quality, security posture, and test coverage across modified files.

## Review Steps
1. Scan for potential security vulnerabilities (SQL injection, XSS, exposed secrets).
2. Verify error handling, boundary conditions, and resource cleanup.
3. Provide constructive diff recommendations and line-by-line feedback.
`
  },
  {
    id: "data-analyst",
    title: "Data Analyst & SQL",
    desc: "Data investigation, schema analysis, and query optimization",
    name: "data-analyst",
    description: "Analyzes datasets, builds performant SQL queries, and generates reports",
    tools: "run_command, read_resource",
    author: "Carole AI",
    version: "1.0.0",
    instructions: `# Data Analysis & SQL Guidelines

## Workflow
1. Inspect schemas and table partition layouts before issuing queries.
2. Filter on indexed columns and limit query scan volume.
3. Present findings with markdown tables and summary highlights.
`
  },
  {
    id: "browser-qa",
    title: "Browser Automation",
    desc: "Playwright UI automation, scraping, and visual testing",
    name: "browser-automation",
    description: "Automates web navigation, captures visual states, and performs E2E checks",
    tools: "browser_subagent, run_command, view_file",
    author: "Carole AI",
    version: "1.0.0",
    instructions: `# Browser Automation Protocol

## Workflow
1. Use \`browser_subagent\` or Playwright scripts in scratch directories.
2. Wait explicitly for DOM selectors and network stability.
3. Capture visual artifacts and assert interface consistency.
`
  }
];

function generateSkillMarkdown(
  name: string,
  description: string,
  toolsStr: string,
  author: string,
  version: string,
  isActive: boolean,
  instructions: string
): string {
  const toolsList = toolsStr
    .split(",")
    .map(t => t.trim())
    .filter(Boolean);

  const toolsYaml = toolsList.length > 0
    ? toolsList.map(t => `  - ${t}`).join("\n")
    : "  - run_command";

  const safeDesc = (description || "Custom skill package").replace(/"/g, '\\"');

  return `---
name: ${name.trim() || "unnamed-skill"}
description: "${safeDesc}"
tools:
${toolsYaml}
author: ${author.trim() || "Carole AI"}
version: ${version.trim() || "1.0.0"}
is_active: ${isActive}
---

${instructions.trim() || "# Instructions\n\nProvide agent directives here."}
`;
}

export default function SkillsStudio({
  teamId,
  onToast
}: {
  teamId: string | null;
  onToast: (msg: string, type: "success" | "error" | "info") => void;
}) {
  useAuth();
  const [activeTab, setActiveTab] = useState<"discovered" | "custom">("discovered");

  // ── Discovered Skills State ──
  const [discoveredSkills, setDiscoveredSkills] = useState<any[]>([]);
  const [loadingDiscovered, setLoadingDiscovered] = useState(false);
  const [togglingSkill, setTogglingSkill] = useState<string | null>(null);

  // Discovered Modals
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [deleteDiscoveredConfirmOpen, setDeleteDiscoveredConfirmOpen] = useState(false);
  const [skillToDelete, setSkillToDelete] = useState<string | null>(null);

  // Discovered Editor State
  const [discoveredEditorMode, setDiscoveredEditorMode] = useState<"create" | "edit">("create");
  const [editorTab, setEditorTab] = useState<"builder" | "raw">("builder");
  const [discoveredTargetLocation, setDiscoveredTargetLocation] = useState<"project" | "global">("project");
  const [savingDiscovered, setSavingDiscovered] = useState(false);

  // Discovered Form Builder Fields
  const [discName, setDiscName] = useState("");
  const [discDescription, setDiscDescription] = useState("");
  const [discTools, setDiscTools] = useState("");
  const [discAuthor, setDiscAuthor] = useState("Carole AI");
  const [discVersion, setDiscVersion] = useState("1.0.0");
  const [discIsActive, setDiscIsActive] = useState(true);
  const [discInstructions, setDiscInstructions] = useState("");

  // Raw SKILL.md Content
  const [rawSkillContent, setRawSkillContent] = useState("");

  // Upload State
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTargetLocation, setUploadTargetLocation] = useState<"project" | "global">("project");
  const [uploadSkillName, setUploadSkillName] = useState("");
  const [uploadPreviewContent, setUploadPreviewContent] = useState("");
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Custom Team Skills State ──
  const [skills, setSkills] = useState<any[]>([]);
  const [activeSkillId, setActiveSkillId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [tools, setTools] = useState("");
  const [mcpServers, setMcpServers] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    fetchDiscoveredSkills();
    if (teamId) {
      fetchSkills();
    }
  }, [teamId]);

  // ── Discovered Skills Operations ──
  const fetchDiscoveredSkills = async () => {
    setLoadingDiscovered(true);
    try {
      const data = await api.listDiscoveredSkills(undefined, teamId || undefined);
      setDiscoveredSkills(data);
    } catch (err) {
      console.error("Failed to load discovered skills", err);
    } finally {
      setLoadingDiscovered(false);
    }
  };

  const handleToggleDiscoveredSkill = async (skillName: string, currentActive: boolean) => {
    setTogglingSkill(skillName);
    try {
      await api.toggleSkillState(skillName, !currentActive, teamId || undefined);
      setDiscoveredSkills(prev =>
        prev.map(s => s.name === skillName ? { ...s, is_active: !currentActive } : s)
      );
      onToast(`Skill '${skillName}' ${!currentActive ? "enabled" : "disabled"}`, "info");
    } catch (err) {
      onToast(`Failed to toggle skill: ${err}`, "error");
    } finally {
      setTogglingSkill(null);
    }
  };

  const handleOpenCreateModal = (templateId = "custom") => {
    const tmpl = SKILL_TEMPLATES.find(t => t.id === templateId) || SKILL_TEMPLATES[0];
    setDiscoveredEditorMode("create");
    setDiscoveredTargetLocation("project");
    setDiscName(tmpl.name);
    setDiscDescription(tmpl.description);
    setDiscTools(tmpl.tools);
    setDiscAuthor(tmpl.author);
    setDiscVersion(tmpl.version);
    setDiscIsActive(true);
    setDiscInstructions(tmpl.instructions);

    const initialMd = generateSkillMarkdown(
      tmpl.name,
      tmpl.description,
      tmpl.tools,
      tmpl.author,
      tmpl.version,
      true,
      tmpl.instructions
    );
    setRawSkillContent(initialMd);
    setEditorTab("builder");
    setCreateModalOpen(true);
  };

  const handleApplyTemplate = (tmpl: typeof SKILL_TEMPLATES[0]) => {
    setDiscName(tmpl.name);
    setDiscDescription(tmpl.description);
    setDiscTools(tmpl.tools);
    setDiscAuthor(tmpl.author);
    setDiscVersion(tmpl.version);
    setDiscInstructions(tmpl.instructions);

    const md = generateSkillMarkdown(
      tmpl.name,
      tmpl.description,
      tmpl.tools,
      tmpl.author,
      tmpl.version,
      discIsActive,
      tmpl.instructions
    );
    setRawSkillContent(md);
  };

  const handleTogglePopularTool = (toolName: string) => {
    const current = discTools
      .split(",")
      .map(t => t.trim())
      .filter(Boolean);
    let next: string[];
    if (current.includes(toolName)) {
      next = current.filter(t => t !== toolName);
    } else {
      next = [...current, toolName];
    }
    const toolsStr = next.join(", ");
    setDiscTools(toolsStr);
    setRawSkillContent(generateSkillMarkdown(
      discName,
      discDescription,
      toolsStr,
      discAuthor,
      discVersion,
      discIsActive,
      discInstructions
    ));
  };

  const handleSwitchTab = (tab: "builder" | "raw") => {
    if (tab === "raw") {
      // Synchronize builder state to raw markdown
      const md = generateSkillMarkdown(
        discName,
        discDescription,
        discTools,
        discAuthor,
        discVersion,
        discIsActive,
        discInstructions
      );
      setRawSkillContent(md);
    } else {
      // Attempt to parse raw markdown back into builder
      const nameMatch = rawSkillContent.match(/name:\s*([a-zA-Z0-9_-]+)/);
      if (nameMatch) setDiscName(nameMatch[1]);
      const descMatch = rawSkillContent.match(/description:\s*["']?([^"\n\r]+)["']?/);
      if (descMatch) setDiscDescription(descMatch[1]);
      const authorMatch = rawSkillContent.match(/author:\s*([^\n\r]+)/);
      if (authorMatch) setDiscAuthor(authorMatch[1].trim());
      const verMatch = rawSkillContent.match(/version:\s*([^\n\r]+)/);
      if (verMatch) setDiscVersion(verMatch[1].trim());

      const parts = rawSkillContent.split(/---\s*[\r\n]+/);
      if (parts.length >= 3) {
        setDiscInstructions(parts.slice(2).join("---").trim());
      }
    }
    setEditorTab(tab);
  };

  const handleOpenEditDiscoveredSkill = async (skill: any) => {
    try {
      setSavingDiscovered(true);
      const info = await api.getDiscoveredSkillContent(skill.name, undefined, teamId || undefined);
      setDiscoveredEditorMode("edit");
      setDiscName(skill.name);
      setDiscoveredTargetLocation(skill.source === "global" ? "global" : "project");
      setRawSkillContent(info.content);
      setEditorTab("raw"); // Default to raw view for exact verification

      setDiscDescription(skill.description || "");
      setDiscTools((skill.tools || []).join(", "));
      setDiscAuthor(skill.author || "Carole AI");
      setDiscVersion(skill.version || "1.0.0");
      setDiscIsActive(skill.is_active ?? true);

      const parts = info.content.split(/---\s*[\r\n]+/);
      if (parts.length >= 3) {
        setDiscInstructions(parts.slice(2).join("---").trim());
      } else {
        setDiscInstructions(info.content);
      }

      setCreateModalOpen(true);
    } catch (err: any) {
      onToast(`Failed to load skill content: ${err.message || err}`, "error");
    } finally {
      setSavingDiscovered(false);
    }
  };

  const handleSaveDiscoveredSkill = async () => {
    setSavingDiscovered(true);
    try {
      let contentToSave = rawSkillContent;
      let nameToSave = discName.trim();

      if (editorTab === "builder") {
        contentToSave = generateSkillMarkdown(
          discName,
          discDescription,
          discTools,
          discAuthor,
          discVersion,
          discIsActive,
          discInstructions
        );
      } else {
        const nameMatch = contentToSave.match(/name:\s*([a-zA-Z0-9_-]+)/);
        if (nameMatch && nameMatch[1]) {
          nameToSave = nameMatch[1];
        }
      }

      if (!nameToSave) {
        onToast("Skill name is required (use letters, numbers, hyphens)", "error");
        setSavingDiscovered(false);
        return;
      }

      const slugRegex = /^[a-zA-Z0-9_-]+$/;
      if (!slugRegex.test(nameToSave)) {
        onToast("Skill name must be a slug (letters, numbers, hyphens, underscores)", "error");
        setSavingDiscovered(false);
        return;
      }

      await api.createDiscoveredSkill({
        name: nameToSave,
        content: contentToSave,
        target_location: discoveredTargetLocation,
        team_id: teamId || undefined,
      });

      const destPath = discoveredTargetLocation === "project" ? ".carole/skills/" : "~/.carole/skills/";
      onToast(`Skill '${nameToSave}' saved and hot-loaded into ${destPath}`, "success");
      setCreateModalOpen(false);
      await fetchDiscoveredSkills();
    } catch (err: any) {
      onToast(`Failed to save skill: ${err.message || err}`, "error");
    } finally {
      setSavingDiscovered(false);
    }
  };

  const handleDeleteDiscoveredSkill = async () => {
    if (!skillToDelete) return;
    try {
      await api.deleteDiscoveredSkill(skillToDelete, undefined, teamId || undefined);
      onToast(`Skill package '${skillToDelete}' deleted from disk`, "success");
      setDeleteDiscoveredConfirmOpen(false);
      setSkillToDelete(null);
      await fetchDiscoveredSkills();
    } catch (err: any) {
      onToast(`Failed to delete skill: ${err.message || err}`, "error");
    }
  };

  // ── Upload Operations ──
  const processUploadedFile = (file: File) => {
    if (!file.name.toLowerCase().endsWith(".md") && !file.name.toLowerCase().endsWith(".markdown") && !file.name.toLowerCase().endsWith(".txt")) {
      onToast("Only Markdown (.md) files are supported", "error");
      return;
    }
    setUploadFile(file);

    const reader = new FileReader();
    reader.onload = (e) => {
      const text = (e.target?.result as string) || "";
      setUploadPreviewContent(text);

      const nameMatch = text.match(/name:\s*([a-zA-Z0-9_-]+)/);
      if (nameMatch && nameMatch[1]) {
        setUploadSkillName(nameMatch[1]);
      } else {
        const stem = file.name.replace(/\.[^/.]+$/, "").replace(/[^a-zA-Z0-9_-]/g, "-").toLowerCase();
        if (stem && !["skill", "skills", "readme"].includes(stem)) {
          setUploadSkillName(stem);
        }
      }
    };
    reader.readAsText(file);
  };

  const handleUploadSubmit = async () => {
    if (!uploadFile) {
      onToast("Please select a .md file to upload", "error");
      return;
    }
    setUploading(true);
    try {
      await api.uploadDiscoveredSkill(
        uploadFile,
        uploadTargetLocation,
        uploadSkillName.trim() || undefined,
        undefined,
        teamId || undefined
      );
      const destPath = uploadTargetLocation === "project" ? ".carole/skills/" : "~/.carole/skills/";
      onToast(`Skill uploaded and hot-loaded into ${destPath}`, "success");
      setUploadModalOpen(false);
      setUploadFile(null);
      setUploadPreviewContent("");
      setUploadSkillName("");
      await fetchDiscoveredSkills();
    } catch (err: any) {
      onToast(`Upload failed: ${err.message || err}`, "error");
    } finally {
      setUploading(false);
    }
  };

  // ── Custom Skills Operations ──
  const fetchSkills = async () => {
    if (!teamId) return;
    setLoading(true);
    try {
      const data = await api.listSkills(teamId);
      setSkills(data);
      if (data.length > 0 && !activeSkillId) {
        selectSkill(data[0]);
      } else if (data.length === 0) {
        handleNew();
      }
    } catch (err) {
      console.error(err);
      onToast("Failed to load skills", "error");
    } finally {
      setLoading(false);
    }
  };

  const selectSkill = (skill: any) => {
    setActiveSkillId(skill.id);
    setName(skill.name || "");
    setDescription(skill.description || "");
    setSystemPrompt(skill.system_prompt_addendum || "");
    setTools((skill.tools || []).join(", "));
    setMcpServers((skill.mcp_servers || []).join(", "));
    setIsActive(skill.is_active ?? true);
  };

  const handleNew = () => {
    setActiveSkillId(null);
    setName("New Skill");
    setDescription("");
    setSystemPrompt("");
    setTools("");
    setMcpServers("");
    setIsActive(true);
  };

  const handleSave = async () => {
    if (!teamId) return;
    if (!name.trim()) {
      onToast("Skill name is required", "error");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        name,
        description,
        system_prompt_addendum: systemPrompt,
        tools: tools.split(",").map(t => t.trim()).filter(Boolean),
        mcp_servers: mcpServers.split(",").map(m => m.trim()).filter(Boolean),
        is_active: isActive
      };

      if (activeSkillId) {
        const updated = await api.updateSkill(activeSkillId, payload);
        setSkills(prev => prev.map(s => s.id === updated.id ? updated : s));
        onToast("Skill updated successfully", "success");
      } else {
        const created = await api.createSkill({ team_id: teamId, ...payload });
        setSkills([...skills, created]);
        setActiveSkillId(created.id);
        onToast("Skill created successfully", "success");
      }
    } catch (err: any) {
      onToast(`Save error: ${err.message || "Failed"}`, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!activeSkillId) return;
    setSaving(true);
    setConfirmOpen(false);
    try {
      await api.deleteSkill(activeSkillId);
      onToast("Skill deleted", "success");
      setSkills(prev => prev.filter(s => s.id !== activeSkillId));
      handleNew();
    } catch (err: any) {
      onToast(`Delete error: ${err.message || "Failed"}`, "error");
    } finally {
      setSaving(false);
    }
  };

  if (!teamId) {
    return (
      <div style={{ padding: "var(--sp-xl)", textAlign: "center", color: "var(--color-mute)" }}>
        Please select or create a team to manage skills.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", width: "100%", overflow: "hidden", background: "var(--color-canvas)" }}>
      {/* Top Header & Tabs */}
      <div style={{
        padding: "12px 24px",
        borderBottom: "1px solid var(--color-hairline)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        background: "var(--color-canvas-soft)",
        flexWrap: "wrap", gap: 12,
        backdropFilter: "blur(12px)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 32,
            height: 32,
            borderRadius: 8,
            background: "linear-gradient(135deg, rgba(79, 70, 229, 0.2), rgba(99, 102, 241, 0.35))",
            border: "1px solid rgba(99, 102, 241, 0.4)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#a5b4fc"
          }}>
            <Sparkles size={16} />
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--color-ink-strong)" }}>Skills Studio</div>
            <div style={{ fontSize: 11, color: "var(--color-mute)" }}>SKILL.md Packages & Hot Reloading</div>
          </div>
        </div>

        {/* Tab Controls */}
        <div style={{
          display: "flex",
          background: "var(--color-canvas-soft)",
          padding: 3,
          borderRadius: 10,
          border: "1px solid var(--color-hairline)"
        }}>
          <button
            onClick={() => setActiveTab("discovered")}
            style={{
              padding: "6px 14px",
              borderRadius: 7,
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
              border: "none",
              background: activeTab === "discovered" ? "var(--color-primary)" : "transparent",
              color: activeTab === "discovered" ? "#ffffff" : "var(--color-mute)",
              transition: "all 0.15s ease",
              display: "flex",
              alignItems: "center",
              gap: 6
            }}
          >
            <FolderCode size={14} />
            Discovered Packages
            <span style={{
              fontSize: 10,
              padding: "1px 6px",
              borderRadius: 10,
              background: activeTab === "discovered" ? "rgba(255,255,255,0.25)" : "rgba(255,255,255,0.06)",
              color: "#fff"
            }}>
              {discoveredSkills.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab("custom")}
            style={{
              padding: "6px 14px",
              borderRadius: 7,
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
              border: "none",
              background: activeTab === "custom" ? "var(--color-primary)" : "transparent",
              color: activeTab === "custom" ? "#ffffff" : "var(--color-mute)",
              transition: "all 0.15s ease",
              display: "flex",
              alignItems: "center",
              gap: 6
            }}
          >
            <BookOpen size={14} />
            Custom Team Skills
            <span style={{
              fontSize: 10,
              padding: "1px 6px",
              borderRadius: 10,
              background: activeTab === "custom" ? "rgba(255,255,255,0.25)" : "rgba(255,255,255,0.06)",
              color: "#fff"
            }}>
              {skills.length}
            </span>
          </button>
        </div>
      </div>

      {/* Tab Body */}
      {activeTab === "discovered" ? (
        <div style={{ flex: 1, overflowY: "auto", padding: 24 }}>
          <div style={{ maxWidth: 1150, margin: "0 auto" }}>
            {/* Header Actions */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 20, flexWrap: "wrap", gap: 12 }}>
              <div>
                <h3 style={{ fontSize: 16, fontWeight: 700, color: "var(--color-ink-strong)", margin: 0 }}>
                  Discovered SKILL.md Packages
                </h3>
                <p style={{ fontSize: 12, color: "var(--color-mute)", margin: "4px 0 0 0" }}>
                  Hot-loaded from <code style={{ color: "#a5b4fc" }}>.carole/skills/</code> and <code style={{ color: "#a5b4fc" }}>~/.carole/skills/</code>.
                </p>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <button
                  onClick={() => {
                    setUploadFile(null);
                    setUploadPreviewContent("");
                    setUploadSkillName("");
                    setUploadTargetLocation("project");
                    setUploadModalOpen(true);
                  }}
                  className="btn btn-secondary btn-sm"
                  style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}
                >
                  <Upload size={13} />
                  Upload .md
                </button>
                <button
                  onClick={() => handleOpenCreateModal("custom")}
                  className="btn btn-primary btn-sm"
                  style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}
                >
                  <Plus size={13} />
                  New SKILL.md
                </button>
                <button
                  onClick={fetchDiscoveredSkills}
                  className="btn btn-ghost btn-sm"
                  style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}
                  disabled={loadingDiscovered}
                  title="Reload from disk"
                >
                  {loadingDiscovered ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                  Refresh
                </button>
              </div>
            </div>

            {loadingDiscovered ? (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 60, color: "var(--color-mute)", gap: 8 }}>
                <Loader2 size={16} className="animate-spin" />
                <span>Scanning filesystem roots for SKILL.md definitions...</span>
              </div>
            ) : discoveredSkills.length === 0 ? (
              <div style={{
                background: "rgba(18, 18, 37, 0.4)",
                border: "1px dashed var(--color-hairline)",
                borderRadius: 12,
                padding: "48px 24px",
                textAlign: "center",
              }}>
                <FolderCode size={38} color="var(--color-mute)" style={{ margin: "0 auto 12px" }} />
                <h4 style={{ fontSize: 15, fontWeight: 600, color: "var(--color-ink-strong)", margin: 0 }}>No SKILL.md packages discovered</h4>
                <p style={{ fontSize: 12, color: "var(--color-mute)", maxWidth: 500, margin: "8px auto 20px", lineHeight: 1.5 }}>
                  Add capabilities by uploading an existing <code style={{ color: "#818cf8" }}>SKILL.md</code> or creating a formatted package directly in <code style={{ color: "#818cf8" }}>.carole/skills/</code> or <code style={{ color: "#818cf8" }}>~/.carole/skills/</code>.
                </p>

                <div style={{ display: "flex", justifyContent: "center", gap: 10, marginBottom: 24 }}>
                  <button
                    onClick={() => handleOpenCreateModal("custom")}
                    className="btn btn-primary btn-sm"
                    style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}
                  >
                    <Plus size={14} />
                    Create First SKILL.md
                  </button>
                  <button
                    onClick={() => setUploadModalOpen(true)}
                    className="btn btn-secondary btn-sm"
                    style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}
                  >
                    <Upload size={14} />
                    Upload Markdown File
                  </button>
                </div>

                <div style={{
                  background: "#080814",
                  border: "1px solid var(--color-hairline)",
                  borderRadius: 8,
                  padding: 14,
                  maxWidth: 440,
                  margin: "0 auto",
                  textAlign: "left",
                  fontSize: 11,
                  fontFamily: "var(--font-mono)",
                  color: "#94a3b8",
                  lineHeight: 1.5
                }}>
                  <span style={{ color: "#64748b" }}># Proper SKILL.md Format</span><br />
                  ---<br />
                  <span style={{ color: "#a5b4fc" }}>name:</span> code-reviewer<br />
                  <span style={{ color: "#a5b4fc" }}>description:</span> Audits code for correctness and security<br />
                  <span style={{ color: "#a5b4fc" }}>tools:</span> [view_file, grep_search, run_command]<br />
                  <span style={{ color: "#a5b4fc" }}>version:</span> 1.0.0<br />
                  ---<br />
                  <br />
                  <span style={{ color: "#e2e8f0" }}># Instructions</span><br />
                  Guidelines for the AI agent...
                </div>
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(350px, 100%), 1fr))", gap: 16 }}>
                {discoveredSkills.map(skill => {
                  const isToggling = togglingSkill === skill.name;
                  return (
                    <div
                      key={skill.name}
                      style={{
                        background: "var(--color-canvas-soft)",
                        border: skill.is_active ? "1px solid rgba(99, 102, 241, 0.35)" : "1px solid var(--color-hairline)",
                        borderRadius: 12,
                        padding: 18,
                        display: "flex",
                        flexDirection: "column",
                        gap: 12,
                        boxShadow: skill.is_active ? "0 4px 20px -8px rgba(99, 102, 241, 0.2)" : "none",
                        transition: "all 0.2s ease"
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                            <span style={{ fontSize: 14, fontWeight: 700, color: "var(--color-ink-strong)" }}>
                              {skill.name}
                            </span>
                            <span style={{
                              fontSize: 10,
                              fontWeight: 600,
                              padding: "2px 7px",
                              borderRadius: 6,
                              textTransform: "uppercase",
                              background: skill.source === "project" ? "rgba(99, 102, 241, 0.15)" : "rgba(168, 85, 247, 0.15)",
                              color: skill.source === "project" ? "#a5b4fc" : "#d8b4fe",
                              border: skill.source === "project" ? "1px solid rgba(99, 102, 241, 0.3)" : "1px solid rgba(168, 85, 247, 0.3)",
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 4
                            }}>
                              {skill.source === "project" ? <FolderCode size={10} /> : <HardDrive size={10} />}
                              {skill.source}
                            </span>
                          </div>
                          {skill.version && (
                            <span style={{ fontSize: 10, color: "var(--color-mute)" }}>
                              v{skill.version} {skill.author ? `• by ${skill.author}` : ""}
                            </span>
                          )}
                        </div>

                        {/* Toggle Button */}
                        <button
                          onClick={() => handleToggleDiscoveredSkill(skill.name, skill.is_active)}
                          disabled={isToggling}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 5,
                            padding: "4px 10px",
                            borderRadius: 20,
                            fontSize: 11,
                            fontWeight: 600,
                            cursor: "pointer",
                            border: "none",
                            background: skill.is_active ? "rgba(16, 185, 129, 0.15)" : "rgba(255, 255, 255, 0.05)",
                            color: skill.is_active ? "#10b981" : "var(--color-mute)",
                            transition: "all 0.15s ease"
                          }}
                        >
                          {isToggling ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : skill.is_active ? (
                            <CheckCircle2 size={12} />
                          ) : (
                            <XCircle size={12} />
                          )}
                          {skill.is_active ? "Active" : "Disabled"}
                        </button>
                      </div>

                      <p style={{ fontSize: 12, color: "var(--color-ink)", margin: 0, lineHeight: 1.4, flex: 1 }}>
                        {skill.description || "No description provided."}
                      </p>

                      {/* Tool Tags */}
                      {skill.tools && skill.tools.length > 0 && (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                          {skill.tools.map((tool: string) => (
                            <span
                              key={tool}
                              style={{
                                fontSize: 10,
                                fontFamily: "var(--font-mono)",
                                background: "rgba(255, 255, 255, 0.05)",
                                border: "1px solid rgba(255, 255, 255, 0.08)",
                                padding: "2px 6px",
                                borderRadius: 4,
                                color: "#cbd5e1"
                              }}
                            >
                              {tool}
                            </span>
                          ))}
                        </div>
                      )}

                      {/* Path and scripts info */}
                      {(skill.scripts?.length > 0 || skill.references?.length > 0 || skill.path) && (
                        <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11, color: "var(--color-mute)", borderTop: "1px solid var(--color-hairline)", paddingTop: 8 }}>
                          {skill.path && (
                            <div style={{ fontSize: 10, color: "var(--color-mute)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={skill.path}>
                              {skill.path}
                            </div>
                          )}
                          <div style={{ display: "flex", gap: 12 }}>
                            {skill.scripts?.length > 0 && (
                              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                                <FileCode size={12} /> {skill.scripts.length} script{skill.scripts.length > 1 ? "s" : ""}
                              </span>
                            )}
                            {skill.references?.length > 0 && (
                              <span>{skill.references.length} reference{skill.references.length > 1 ? "s" : ""}</span>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Card Action Buttons */}
                      <div style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        paddingTop: 8,
                        borderTop: "1px solid var(--color-hairline)",
                        marginTop: "auto"
                      }}>
                        <button
                          onClick={() => handleOpenEditDiscoveredSkill(skill)}
                          className="btn btn-ghost btn-sm"
                          style={{ fontSize: 11, padding: "4px 8px", display: "flex", alignItems: "center", gap: 5, color: "#a5b4fc" }}
                        >
                          <Edit3 size={12} />
                          View / Edit SKILL.md
                        </button>
                        <button
                          onClick={() => {
                            setSkillToDelete(skill.name);
                            setDeleteDiscoveredConfirmOpen(true);
                          }}
                          className="btn btn-ghost btn-sm text-danger"
                          style={{ fontSize: 11, padding: "4px 8px", display: "flex", alignItems: "center", gap: 4 }}
                          title="Delete skill folder from disk"
                        >
                          <Trash2 size={12} />
                          Delete
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      ) : (
        /* Custom Team Skills Tab */
        <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
          {/* Sidebar */}
          <div style={{ width: 250, borderRight: "1px solid var(--color-hairline)", display: "flex", flexDirection: "column", background: "var(--color-canvas-soft)" }}>
            <div style={{ padding: "var(--sp-md) var(--sp-lg)", borderBottom: "1px solid var(--color-hairline)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", fontWeight: 600 }}>
                <BookOpen size={16} color="var(--color-primary)" />
                <span>Team Skills</span>
              </div>
              <button className="btn btn-icon btn-ghost btn-sm" onClick={handleNew} title="New Skill">
                <Plus size={16} />
              </button>
            </div>

            <div style={{ flex: 1, overflowY: "auto", padding: "var(--sp-sm)" }}>
              {loading ? (
                <div style={{ padding: "var(--sp-md)", color: "var(--color-mute)", fontSize: 13 }}>Loading...</div>
              ) : skills.length === 0 ? (
                <div style={{ padding: "var(--sp-md)", color: "var(--color-mute)", fontSize: 13, textAlign: "center" }}>
                  No skills found.<br />Create one to extend agent capabilities.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  {skills.map(s => (
                    <button
                      key={s.id}
                      onClick={() => selectSkill(s)}
                      style={{
                        display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--sp-sm)",
                        padding: "8px 12px", width: "100%", textAlign: "left",
                        background: activeSkillId === s.id ? "var(--color-primary-glow)" : "transparent",
                        color: activeSkillId === s.id ? "var(--color-ink-strong)" : "var(--color-ink)",
                        border: activeSkillId === s.id ? "1px solid rgba(167, 139, 250, 0.35)" : "1px solid transparent",
                        borderRadius: "var(--radius-sm, 7px)", cursor: "pointer",
                        fontSize: 13, fontWeight: activeSkillId === s.id ? 700 : 500,
                        transition: "all var(--t-fast)",
                      }}
                    >
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</span>
                      {!s.is_active && <span style={{ fontSize: 10, color: "var(--color-danger)", background: "var(--color-danger-glow)", padding: "2px 6px", borderRadius: 4 }}>Off</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Editor Main */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, overflowY: "auto", padding: "var(--sp-xl)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "var(--sp-xl)" }}>
              <div>
                <h2 style={{ fontSize: 20, fontWeight: 600, margin: 0, color: "var(--color-ink)" }}>
                  {activeSkillId ? "Edit Skill" : "Create New Skill"}
                </h2>
                <p style={{ fontSize: 13, color: "var(--color-mute)", margin: "4px 0 0 0" }}>
                  Package prompts and tools together into reusable capabilities.
                </p>
              </div>
              <div style={{ display: "flex", gap: "var(--sp-sm)" }}>
                {activeSkillId && (
                  <button className="btn btn-ghost btn-sm text-danger" onClick={() => setConfirmOpen(true)} disabled={saving}>
                    <Trash2 size={14} /> Delete
                  </button>
                )}
                <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving || !name.trim()}>
                  {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                  {activeSkillId ? "Save Changes" : "Create Skill"}
                </button>
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-lg)", maxWidth: 800 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(230px, 100%), 1fr))", gap: "var(--sp-lg)" }}>
                <div>
                  <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: "var(--sp-xs)" }}>Skill Name</label>
                  <input className="input" style={{ width: "100%" }} value={name} onChange={e => setName(e.target.value)} placeholder="e.g., Python Expert" />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: "var(--sp-xs)" }}>Description</label>
                  <input className="input" style={{ width: "100%" }} value={description} onChange={e => setDescription(e.target.value)} placeholder="Short description of what this skill does" />
                </div>
              </div>

              <div>
                <label style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)", fontSize: 13, fontWeight: 500, cursor: "pointer" }}>
                  <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} />
                  Active (Agents can use this skill)
                </label>
              </div>

              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: "var(--sp-xs)" }}>
                  System Prompt Addendum
                  <span style={{ color: "var(--color-mute)", fontWeight: 400, marginLeft: 8 }}>(Appended to agent&apos;s system prompt)</span>
                </label>
                <textarea
                  className="input"
                  style={{ width: "100%", height: 150, fontFamily: "var(--font-mono)", fontSize: 13, resize: "vertical" }}
                  value={systemPrompt}
                  onChange={e => setSystemPrompt(e.target.value)}
                  placeholder="e.g., You are an expert Python developer. Always write type hints and use pytest for testing..."
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: "var(--sp-xs)" }}>
                  Associated Tools (Comma separated)
                </label>
                <input
                  className="input"
                  style={{ width: "100%" }}
                  value={tools}
                  onChange={e => setTools(e.target.value)}
                  placeholder="e.g., python_repl, write_file, read_file"
                />
                <p style={{ fontSize: 12, color: "var(--color-mute)", margin: "4px 0 0 0" }}>
                  If tools are listed here, the agent is explicitly told to use them when this skill is active.
                </p>
              </div>

              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: "var(--sp-xs)" }}>
                  Associated MCP Servers (Comma separated)
                </label>
                <input
                  className="input"
                  style={{ width: "100%" }}
                  value={mcpServers}
                  onChange={e => setMcpServers(e.target.value)}
                  placeholder="e.g., github-mcp, jira-mcp"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL: Create / Edit SKILL.md Package ── */}
      <Modal
        open={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        maxWidth={780}
        title={
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <FileCode size={18} color="#818cf8" />
            <span>{discoveredEditorMode === "create" ? "Create SKILL.md Package" : `Edit SKILL.md: ${discName}`}</span>
          </div>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Preset Template Selector (only during create) */}
          {discoveredEditorMode === "create" && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-mute)", textTransform: "uppercase", marginBottom: 6 }}>
                Choose Template
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(160px, 100%), 1fr))", gap: 8 }}>
                {SKILL_TEMPLATES.map(tmpl => {
                  const isSelected = discName === tmpl.name;
                  return (
                    <button
                      key={tmpl.id}
                      type="button"
                      onClick={() => handleApplyTemplate(tmpl)}
                      style={{
                        padding: "8px 12px",
                        textAlign: "left",
                        background: isSelected ? "rgba(99, 102, 241, 0.15)" : "rgba(255, 255, 255, 0.03)",
                        border: isSelected ? "1px solid rgba(99, 102, 241, 0.5)" : "1px solid var(--color-hairline)",
                        borderRadius: 8,
                        cursor: "pointer",
                        transition: "all 0.15s ease"
                      }}
                    >
                      <div style={{ fontSize: 12, fontWeight: 600, color: isSelected ? "#a5b4fc" : "var(--color-ink-strong)" }}>
                        {tmpl.title}
                      </div>
                      <div style={{ fontSize: 10, color: "var(--color-mute)", marginTop: 2, lineHeight: 1.3 }}>
                        {tmpl.desc}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Location & Editor Mode Switcher */}
          <div style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "8px 12px",
            background: "rgba(255, 255, 255, 0.03)",
            borderRadius: 8,
            border: "1px solid var(--color-hairline)",
            flexWrap: "wrap",
            gap: 8
          }}>
            {/* Target Location */}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: "var(--color-mute)" }}>Destination:</span>
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  type="button"
                  onClick={() => setDiscoveredTargetLocation("project")}
                  style={{
                    padding: "4px 8px",
                    borderRadius: 6,
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: "pointer",
                    border: "none",
                    background: discoveredTargetLocation === "project" ? "var(--color-primary)" : "rgba(255, 255, 255, 0.06)",
                    color: discoveredTargetLocation === "project" ? "#fff" : "var(--color-mute)"
                  }}
                >
                  Project (.carole/skills/)
                </button>
                <button
                  type="button"
                  onClick={() => setDiscoveredTargetLocation("global")}
                  style={{
                    padding: "4px 8px",
                    borderRadius: 6,
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: "pointer",
                    border: "none",
                    background: discoveredTargetLocation === "global" ? "var(--color-primary)" : "rgba(255, 255, 255, 0.06)",
                    color: discoveredTargetLocation === "global" ? "#fff" : "var(--color-mute)"
                  }}
                >
                  Global (~/.carole/skills/)
                </button>
              </div>
            </div>

            {/* Builder vs Raw Mode */}
            <div style={{ display: "flex", background: "rgba(0,0,0,0.3)", padding: 2, borderRadius: 6 }}>
              <button
                type="button"
                onClick={() => handleSwitchTab("builder")}
                style={{
                  padding: "4px 10px",
                  borderRadius: 5,
                  fontSize: 11,
                  fontWeight: 600,
                  cursor: "pointer",
                  border: "none",
                  background: editorTab === "builder" ? "rgba(99, 102, 241, 0.3)" : "transparent",
                  color: editorTab === "builder" ? "#a5b4fc" : "var(--color-mute)"
                }}
              >
                Form Builder
              </button>
              <button
                type="button"
                onClick={() => handleSwitchTab("raw")}
                style={{
                  padding: "4px 10px",
                  borderRadius: 5,
                  fontSize: 11,
                  fontWeight: 600,
                  cursor: "pointer",
                  border: "none",
                  background: editorTab === "raw" ? "rgba(99, 102, 241, 0.3)" : "transparent",
                  color: editorTab === "raw" ? "#a5b4fc" : "var(--color-mute)"
                }}
              >
                Raw SKILL.md
              </button>
            </div>
          </div>

          {/* Builder Mode Form */}
          {editorTab === "builder" ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(230px, 100%), 1fr))", gap: 12 }}>
                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
                    Skill Slug / Package Name <span style={{ color: "var(--color-danger)" }}>*</span>
                  </label>
                  <input
                    className="input"
                    style={{ width: "100%", fontSize: 12, fontFamily: "var(--font-mono)" }}
                    value={discName}
                    onChange={e => setDiscName(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, "-"))}
                    placeholder="e.g., code-reviewer"
                  />
                  <span style={{ fontSize: 10, color: "var(--color-mute)" }}>Folder: .carole/skills/{discName || "<slug>"}/SKILL.md</span>
                </div>
                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
                    Description
                  </label>
                  <input
                    className="input"
                    style={{ width: "100%", fontSize: 12 }}
                    value={discDescription}
                    onChange={e => setDiscDescription(e.target.value)}
                    placeholder="Short description of capabilities"
                  />
                </div>
              </div>

              {/* Tools Selection */}
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
                  Allowed Tools (Comma separated)
                </label>
                <input
                  className="input"
                  style={{ width: "100%", fontSize: 12, fontFamily: "var(--font-mono)", marginBottom: 6 }}
                  value={discTools}
                  onChange={e => setDiscTools(e.target.value)}
                  placeholder="e.g., run_command, view_file, grep_search"
                />
                {/* Popular tools chips */}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5, alignItems: "center" }}>
                  <span style={{ fontSize: 10, color: "var(--color-mute)", marginRight: 4 }}>Quick Add:</span>
                  {POPULAR_TOOLS.map(pt => {
                    const active = discTools.split(",").map(t => t.trim()).includes(pt);
                    return (
                      <button
                        key={pt}
                        type="button"
                        onClick={() => handleTogglePopularTool(pt)}
                        style={{
                          fontSize: 10,
                          fontFamily: "var(--font-mono)",
                          padding: "2px 7px",
                          borderRadius: 4,
                          cursor: "pointer",
                          border: active ? "1px solid rgba(99, 102, 241, 0.5)" : "1px solid rgba(255, 255, 255, 0.08)",
                          background: active ? "rgba(99, 102, 241, 0.2)" : "rgba(255, 255, 255, 0.03)",
                          color: active ? "#a5b4fc" : "#94a3b8"
                        }}
                      >
                        {active ? "✓ " : "+ "}{pt}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Author, Version, Active */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(160px, 100%), 1fr))", gap: 12 }}>
                <div>
                  <label style={{ display: "block", fontSize: 11, fontWeight: 600, marginBottom: 4 }}>Author</label>
                  <input
                    className="input"
                    style={{ width: "100%", fontSize: 12 }}
                    value={discAuthor}
                    onChange={e => setDiscAuthor(e.target.value)}
                    placeholder="Author name"
                  />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: 11, fontWeight: 600, marginBottom: 4 }}>Version</label>
                  <input
                    className="input"
                    style={{ width: "100%", fontSize: 12 }}
                    value={discVersion}
                    onChange={e => setDiscVersion(e.target.value)}
                    placeholder="1.0.0"
                  />
                </div>
                <div style={{ display: "flex", alignItems: "flex-end", paddingBottom: 6 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={discIsActive}
                      onChange={e => setDiscIsActive(e.target.checked)}
                    />
                    <span>Active on save</span>
                  </label>
                </div>
              </div>

              {/* Instructions Markdown Body */}
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
                  Instructions & Guidelines (Markdown)
                </label>
                <textarea
                  className="input"
                  style={{ width: "100%", height: 180, fontFamily: "var(--font-mono)", fontSize: 12, resize: "vertical" }}
                  value={discInstructions}
                  onChange={e => setDiscInstructions(e.target.value)}
                  placeholder="# Instructions&#10;&#10;Detailed directives and workflows for the agent..."
                />
              </div>
            </div>
          ) : (
            /* Raw Markdown Editor */
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 11, color: "var(--color-mute)" }}>
                  Directly edit the formatted <code style={{ color: "#a5b4fc" }}>SKILL.md</code> with YAML frontmatter.
                </span>
                <span style={{ fontSize: 10, color: "#94a3b8" }}>
                  {rawSkillContent.split("\n").length} lines
                </span>
              </div>
              <textarea
                className="input"
                style={{
                  width: "100%",
                  height: 320,
                  fontFamily: "var(--font-mono)",
                  fontSize: 12,
                  lineHeight: 1.5,
                  background: "#080814",
                  resize: "vertical"
                }}
                value={rawSkillContent}
                onChange={e => setRawSkillContent(e.target.value)}
                placeholder="---&#10;name: my-skill&#10;description: Overview&#10;tools:&#10;  - run_command&#10;---&#10;&#10;# Instructions..."
              />
            </div>
          )}

          {/* Modal Footer Actions */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid var(--color-hairline)", paddingTop: 12, marginTop: 4 }}>
            <div style={{ fontSize: 11, color: "var(--color-mute)" }}>
              Hot-reloaded into agent runtime immediately upon saving.
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setCreateModalOpen(false)}
                disabled={savingDiscovered}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleSaveDiscoveredSkill}
                disabled={savingDiscovered || (!discName.trim() && editorTab === "builder")}
                style={{ display: "flex", alignItems: "center", gap: 6 }}
              >
                {savingDiscovered ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                {discoveredEditorMode === "create" ? "Save & Hot-Load" : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      </Modal>

      {/* ── MODAL: Upload .md File ── */}
      <Modal
        open={uploadModalOpen}
        onClose={() => setUploadModalOpen(false)}
        maxWidth={540}
        title={
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Upload size={18} color="#818cf8" />
            <span>Upload SKILL.md Package</span>
          </div>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Drag & Drop Zone */}
          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => {
              e.preventDefault();
              setDragOver(false);
              if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                processUploadedFile(e.dataTransfer.files[0]);
              }
            }}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: dragOver ? "2px dashed #6366f1" : "2px dashed var(--color-hairline)",
              borderRadius: 12,
              padding: "28px 16px",
              textAlign: "center",
              background: dragOver ? "rgba(99, 102, 241, 0.08)" : "rgba(18, 18, 37, 0.5)",
              cursor: "pointer",
              transition: "all 0.15s ease"
            }}
          >
            <input
              type="file"
              ref={fileInputRef}
              accept=".md,.markdown,.txt"
              style={{ display: "none" }}
              onChange={e => {
                if (e.target.files && e.target.files[0]) {
                  processUploadedFile(e.target.files[0]);
                }
              }}
            />
            <FileCode size={36} color={uploadFile ? "#818cf8" : "var(--color-mute)"} style={{ margin: "0 auto 8px" }} />
            {uploadFile ? (
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#a5b4fc" }}>{uploadFile.name}</div>
                <div style={{ fontSize: 11, color: "var(--color-mute)", marginTop: 2 }}>
                  {(uploadFile.size / 1024).toFixed(1)} KB • Click to change file
                </div>
              </div>
            ) : (
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--color-ink-strong)" }}>
                  Click to select or drag & drop a .md file
                </div>
                <div style={{ fontSize: 11, color: "var(--color-mute)", marginTop: 4 }}>
                  Accepts SKILL.md or Markdown files with YAML frontmatter
                </div>
              </div>
            )}
          </div>

          {/* Destination Target */}
          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
              Target Destination
            </label>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(230px, 100%), 1fr))", gap: 8 }}>
              <button
                type="button"
                onClick={() => setUploadTargetLocation("project")}
                style={{
                  padding: "10px 12px",
                  borderRadius: 8,
                  fontSize: 11,
                  textAlign: "left",
                  cursor: "pointer",
                  border: uploadTargetLocation === "project" ? "1px solid rgba(99, 102, 241, 0.6)" : "1px solid var(--color-hairline)",
                  background: uploadTargetLocation === "project" ? "rgba(99, 102, 241, 0.15)" : "rgba(255, 255, 255, 0.03)",
                  color: uploadTargetLocation === "project" ? "#a5b4fc" : "var(--color-ink)"
                }}
              >
                <div style={{ fontWeight: 600 }}>Project Root</div>
                <div style={{ fontSize: 10, color: "var(--color-mute)", marginTop: 2 }}>.carole/skills/&lt;name&gt;/SKILL.md</div>
              </button>
              <button
                type="button"
                onClick={() => setUploadTargetLocation("global")}
                style={{
                  padding: "10px 12px",
                  borderRadius: 8,
                  fontSize: 11,
                  textAlign: "left",
                  cursor: "pointer",
                  border: uploadTargetLocation === "global" ? "1px solid rgba(99, 102, 241, 0.6)" : "1px solid var(--color-hairline)",
                  background: uploadTargetLocation === "global" ? "rgba(99, 102, 241, 0.15)" : "rgba(255, 255, 255, 0.03)",
                  color: uploadTargetLocation === "global" ? "#a5b4fc" : "var(--color-ink)"
                }}
              >
                <div style={{ fontWeight: 600 }}>Global Home</div>
                <div style={{ fontSize: 10, color: "var(--color-mute)", marginTop: 2 }}>~/.carole/skills/&lt;name&gt;/SKILL.md</div>
              </button>
            </div>
          </div>

          {/* Skill Slug Override */}
          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
              Skill Name / Slug (Optional override)
            </label>
            <input
              className="input"
              style={{ width: "100%", fontSize: 12, fontFamily: "var(--font-mono)" }}
              value={uploadSkillName}
              onChange={e => setUploadSkillName(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, "-"))}
              placeholder="Auto-inferred from YAML frontmatter or file name"
            />
          </div>

          {/* Preview Snippet */}
          {uploadPreviewContent && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-mute)", marginBottom: 4 }}>
                Preview Snippet
              </div>
              <div style={{
                maxHeight: 120,
                overflowY: "auto",
                background: "#080814",
                border: "1px solid var(--color-hairline)",
                borderRadius: 6,
                padding: 8,
                fontSize: 11,
                fontFamily: "var(--font-mono)",
                color: "#94a3b8",
                whiteSpace: "pre-wrap"
              }}>
                {uploadPreviewContent.slice(0, 500)}
                {uploadPreviewContent.length > 500 ? "..." : ""}
              </div>
            </div>
          )}

          {/* Footer Actions */}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, borderTop: "1px solid var(--color-hairline)", paddingTop: 12 }}>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setUploadModalOpen(false)}
              disabled={uploading}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleUploadSubmit}
              disabled={uploading || !uploadFile}
              style={{ display: "flex", alignItems: "center", gap: 6 }}
            >
              {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              Upload & Hot-Load
            </button>
          </div>
        </div>
      </Modal>

      {/* ── MODAL: Delete Discovered Skill Confirmation ── */}
      <Modal
        open={deleteDiscoveredConfirmOpen}
        onClose={() => setDeleteDiscoveredConfirmOpen(false)}
        title="Delete Discovered Skill Package"
        maxWidth={440}
      >
        <p className="body-sm" style={{ color: "var(--color-ink)", lineHeight: 1.5 }}>
          Are you sure you want to delete <strong style={{ color: "#ef4444" }}>{skillToDelete}</strong>?
        </p>
        <p style={{ fontSize: 12, color: "var(--color-mute)", marginTop: 6 }}>
          This will permanently delete the skill package directory and its <code style={{ color: "#a5b4fc" }}>SKILL.md</code> file from the filesystem.
        </p>
        <div style={{ display: "flex", gap: "var(--sp-sm)", justifyContent: "flex-end", marginTop: "var(--sp-xl)" }}>
          <button className="btn btn-ghost" onClick={() => setDeleteDiscoveredConfirmOpen(false)}>
            Cancel
          </button>
          <button className="btn btn-danger" onClick={handleDeleteDiscoveredSkill}>
            Delete Permanently
          </button>
        </div>
      </Modal>

      {/* ── MODAL: Delete Custom Skill Confirmation ── */}
      <Modal open={confirmOpen} onClose={() => setConfirmOpen(false)} title="Delete Skill">
        <p className="body-sm">Are you sure you want to delete this custom skill? This cannot be undone.</p>
        <div style={{ display: "flex", gap: "var(--sp-sm)", justifyContent: "flex-end", marginTop: "var(--sp-xl)" }}>
          <button className="btn btn-ghost" onClick={() => setConfirmOpen(false)}>Cancel</button>
          <button className="btn btn-danger" onClick={handleDelete}>Delete</button>
        </div>
      </Modal>
    </div>
  );
}
