"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import type { AgentConfig } from "@/lib/types";
import AgentAvatar from "./AgentAvatar";
import { 
  Bot, Shield, Sparkles, Cpu, AtSign, Copy, Check, 
  Terminal, FileCode, Globe, Zap, CheckCircle2, ChevronRight,
  Search, Bug, FileText, Layers, ShieldAlert
} from "lucide-react";

import { getAvatarTheme } from "./PrettyAvatar";

export function formatModelName(rawModel: string): string {
  if (!rawModel) return "Default LLM";
  const m = rawModel.toLowerCase();
  if (m === "free" || m.includes("openrouter/free") || m === "openrouter/auto") return "OpenRouter Free";
  if (m.includes("claude-3-5-sonnet") || m.includes("claude-3.5-sonnet")) return "Claude 3.5 Sonnet";
  if (m.includes("claude-3-7-sonnet") || m.includes("claude-3.7-sonnet")) return "Claude 3.7 Sonnet";
  if (m.includes("claude-3-opus")) return "Claude 3 Opus";
  if (m.includes("claude-3-haiku")) return "Claude 3 Haiku";
  if (m.includes("gpt-4o-mini")) return "GPT-4o Mini";
  if (m.includes("gpt-4o")) return "GPT-4o";
  if (m.includes("o1-mini") || m.includes("o3-mini")) return "o3-mini";
  if (m.includes("o1")) return "o1 Preview";
  if (m.includes("gemini-3.6-flash") || m.includes("gemini-3-6-flash")) return "Gemini 3.6 Flash";
  if (m.includes("gemini-1.5-pro")) return "Gemini 1.5 Pro";
  if (m.includes("gemini-1.5-flash")) return "Gemini 1.5 Flash";
  if (m.includes("deepseek-reasoner") || m.includes("deepseek-r1")) return "DeepSeek R1";
  if (m.includes("deepseek-chat") || m.includes("deepseek-v3")) return "DeepSeek V3";
  if (m.includes("llama-3.3") || m.includes("llama-3-3")) return "Llama 3.3 70B";
  if (m.includes("llama-3.1") || m.includes("llama-3-1")) return "Llama 3.1 70B";
  if (m.includes("mistral-large")) return "Mistral Large";
  if (m.includes("codestral")) return "Codestral";

  const parts = rawModel.split("/");
  const last = parts[parts.length - 1];
  if (last === "free") return "OpenRouter Free";
  return last.replace(/[-_]/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

export function resolvePersonality(agent?: AgentConfig | null, role?: string, name?: string): string {
  const raw = agent?.personality?.trim();
  if (raw) {
    const lower = raw.toLowerCase();
    if (lower === "casual") return "Casual & Direct";
    if (lower === "professional") return "Professional & Methodical";
    if (lower === "witty") return "Witty & Pragmatic";
    if (lower === "analytical") return "Analytical & Rigorous";
    if (lower === "curious") return "Curious & Inquisitive";
    if (lower === "direct") return "Direct & Concise";
    return raw.charAt(0).toUpperCase() + raw.slice(1);
  }

  const r = (role || agent?.role || "").toLowerCase();
  const n = (name || agent?.name || "").toLowerCase();

  if (r.includes("orchestrat") || r.includes("coordinator") || n === "archer" || n === "captain") {
    return "Strategic & Directive";
  }
  if (r.includes("inspect") || r.includes("debug") || n === "sherlock" || n === "probe") {
    return "Analytical & Methodical";
  }
  if (r.includes("coder") || r.includes("engineer") || r.includes("developer") || n === "nova" || n === "pixel") {
    return "Pragmatic & Fast";
  }
  if (r.includes("architect") || n === "blueprint" || n === "keystone") {
    return "Systemic & Thorough";
  }
  if (r.includes("review") || r.includes("critic") || r.includes("audit")) {
    return "Skeptical & Precise";
  }
  if (r.includes("test") || r.includes("qa")) {
    return "Meticulous & Defensive";
  }
  if (r.includes("research") || r.includes("scout")) {
    return "Curious & Inquisitive";
  }
  return "Professional & Focused";
}

interface CapabilityBadge {
  key: string;
  label: string;
  Icon: React.ComponentType<{ size?: number; color?: string }>;
  color: string;
}

export function resolveCapabilities(agent?: AgentConfig | null, role?: string, name?: string): CapabilityBadge[] {
  const list: CapabilityBadge[] = [];
  const r = (role || agent?.role || "").toLowerCase();
  const n = (name || agent?.name || "").toLowerCase();
  const skills = agent?.skills || [];
  const permissions = (agent?.tool_permissions || {}) as any;
  const overrides = permissions.overrides || (typeof permissions === "object" ? permissions : {});
  const categories = permissions.categories || {};

  const isBlocked = (toolName: string, catName?: string) => {
    if (overrides[toolName] === "block") return true;
    if (catName && categories[catName] === "block") return true;
    return false;
  };

  const isAllowed = (toolName: string, catName?: string) => {
    if (overrides[toolName] === "allow" || overrides[toolName] === "safe" || overrides[toolName] === "judge") return true;
    if (catName && (categories[catName] === "allow" || categories[catName] === "safe" || categories[catName] === "judge")) return true;
    return false;
  };

  // 1. Subagent Spawning & Delegation
  const canSpawn = (r.includes("orchestrat") || r.includes("coordinator") || n === "archer" || isAllowed("spawn_agent", "subagents")) && !isBlocked("spawn_agent", "subagents");
  if (canSpawn) {
    list.push({
      key: "subagents",
      label: "Subagent Spawning",
      Icon: Zap,
      color: "#a855f7",
    });
  }

  // 2. Code Implementation & File Editing vs Code Inspection vs Architecture
  const isCoder = r.includes("coder") || r.includes("engineer") || r.includes("developer") || n === "nova";
  const canEdit = !isBlocked("write_file", "edit") && !isBlocked("edit_file", "edit");
  if (isCoder && canEdit) {
    list.push({
      key: "code",
      label: "Code Implementation",
      Icon: FileCode,
      color: "#34d399",
    });
  } else if (r.includes("inspect") || r.includes("debug") || n === "sherlock") {
    list.push({
      key: "inspect",
      label: "Code Inspection",
      Icon: Search,
      color: "#38bdf8",
    });
  } else if (r.includes("architect") || n === "blueprint") {
    list.push({
      key: "arch",
      label: "Architecture Specs",
      Icon: FileText,
      color: "#818cf8",
    });
  }

  // 3. Root Cause Analysis / Diagnostics
  if (r.includes("debug") || r.includes("inspect") || n === "sherlock" || skills.some(s => s.toLowerCase().includes("root cause") || s.toLowerCase().includes("diagnos"))) {
    list.push({
      key: "rca",
      label: "Root Cause Analysis",
      Icon: Bug,
      color: "#f43f5e",
    });
  }

  // 4. Terminal Execution
  const canTerminal = !isBlocked("execute_command", "execute") && !r.includes("architect") && !r.includes("coordinator") && n !== "archer";
  if (canTerminal) {
    list.push({
      key: "terminal",
      label: "Terminal Execution",
      Icon: Terminal,
      color: "#60a5fa",
    });
  }

  // 5. Web Search
  const canWeb = !isBlocked("web_search", "web") && !isBlocked("web_fetch", "web");
  if (canWeb && (r.includes("research") || r.includes("orchestrat") || r.includes("inspect") || r.includes("debug") || r.includes("coder") || n === "archer" || n === "sherlock")) {
    list.push({
      key: "web",
      label: "Web Search",
      Icon: Globe,
      color: "#f59e0b",
    });
  }

  // 6. Regression Testing
  if (r.includes("test") || r.includes("qa") || skills.some(s => s.toLowerCase().includes("test") || s.toLowerCase().includes("regression"))) {
    list.push({
      key: "test",
      label: "Regression Testing",
      Icon: CheckCircle2,
      color: "#10b981",
    });
  }

  // 7. System Design & Modeling
  if (r.includes("architect") || skills.some(s => s.toLowerCase().includes("diagram") || s.toLowerCase().includes("system architecture"))) {
    list.push({
      key: "design",
      label: "Mermaid & Systems",
      Icon: Layers,
      color: "#c084fc",
    });
  }

  // 8. Custom configured skills from agent.skills
  for (const s of skills) {
    if (list.length >= 5) break;
    const clean = s.trim();
    if (clean && !list.some(item => item.label.toLowerCase() === clean.toLowerCase())) {
      list.push({
        key: `skill-${clean}`,
        label: clean.length > 24 ? clean.slice(0, 22) + "…" : clean,
        Icon: Sparkles,
        color: "#38bdf8",
      });
    }
  }

  if (list.length === 0) {
    list.push({ key: "task", label: "Task Execution", Icon: Cpu, color: "#38bdf8" });
  }

  return list.slice(0, 5);
}

interface AgentHoverCardProps {
  agent?: AgentConfig | null;
  name?: string;
  id?: string;
  role?: string;
  model?: string;
  isThinking?: boolean;
  isStreaming?: boolean;
  onMention?: (name: string) => void;
  children: React.ReactNode;
  align?: "left" | "right" | "center" | "auto";
  side?: "top" | "bottom" | "auto";
}

export default function AgentHoverCard({
  agent,
  name: explicitName,
  id: explicitId,
  role: explicitRole,
  model: explicitModel,
  isThinking = false,
  isStreaming = false,
  onMention,
  children,
  align = "auto",
  side = "auto",
}: AgentHoverCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const [copied, setCopied] = useState(false);
  const [mounted, setMounted] = useState(false);

  const triggerRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const openTimer = useRef<NodeJS.Timeout | null>(null);
  const closeTimer = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    setMounted(true);
    return () => {
      if (openTimer.current) clearTimeout(openTimer.current);
      if (closeTimer.current) clearTimeout(closeTimer.current);
    };
  }, []);

  const agentName = agent?.name || explicitName || "Agent";
  const agentId = agent?.id || explicitId || "";
  const agentRole = agent?.role || explicitRole || "Active Agent";
  const agentModel = agent?.model || explicitModel || "openrouter/free";
  const isSubagent = agentName.startsWith("Sub-") || agentName.startsWith("Subagent-") || agentRole.toLowerCase().includes("subagent");
  const isActive = isStreaming || isThinking;
  const avatarTheme = getAvatarTheme(agentName, agentRole, agentId);
  const formattedModel = formatModelName(agentModel);
  const resolvedPersonality = resolvePersonality(agent, agentRole, agentName);
  const resolvedCaps = resolveCapabilities(agent, agentRole, agentName);

  const calculatePosition = useCallback(() => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const cardWidth = 320;
    const cardHeight = 360;
    const padding = 10;

    let top = rect.bottom + 8;
    let left = rect.left;

    // Check if card goes off bottom edge
    if (side === "top" || (side === "auto" && rect.bottom + cardHeight > window.innerHeight - padding)) {
      top = Math.max(padding, rect.top - cardHeight - 8);
    }

    // Check horizontal alignment
    if (align === "right" || (align === "auto" && rect.left + cardWidth > window.innerWidth - padding)) {
      left = Math.max(padding, rect.right - cardWidth);
    } else if (align === "center") {
      left = Math.max(padding, rect.left + (rect.width / 2) - (cardWidth / 2));
    }

    // Ensure within bounds
    left = Math.min(left, window.innerWidth - cardWidth - padding);
    left = Math.max(padding, left);

    setCoords({ top, left });
  }, [align, side]);

  const handleMouseEnter = () => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
    openTimer.current = setTimeout(() => {
      calculatePosition();
      setIsOpen(true);
    }, 180);
  };

  const handleMouseLeave = () => {
    if (openTimer.current) {
      clearTimeout(openTimer.current);
      openTimer.current = null;
    }
    closeTimer.current = setTimeout(() => {
      setIsOpen(false);
    }, 220);
  };

  const handleCopyId = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (agentId) {
      navigator.clipboard.writeText(agentId);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  const handleMentionClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onMention) {
      onMention(agentName);
      setIsOpen(false);
    }
  };

  return (
    <>
      <div
        ref={triggerRef}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        style={{ display: "inline-flex", alignItems: "center" }}
      >
        {children}
      </div>

      {mounted && isOpen && createPortal(
        <div
          ref={cardRef}
          onMouseEnter={() => {
            if (closeTimer.current) clearTimeout(closeTimer.current);
          }}
          onMouseLeave={handleMouseLeave}
          style={{
            position: "fixed",
            top: coords.top,
            left: coords.left,
            width: "320px",
            zIndex: 99999,
            background: "rgba(14, 14, 28, 0.94)",
            backdropFilter: "blur(20px)",
            WebkitBackdropFilter: "blur(20px)",
            border: `1px solid ${avatarTheme.bgGrad[0]}44`,
            borderRadius: "16px",
            boxShadow: `0 24px 54px -8px rgba(0, 0, 0, 0.75), 0 0 28px -4px ${avatarTheme.bgGrad[0]}33`,
            overflow: "hidden",
            color: "var(--color-ink)",
            animation: "agentCardFadeIn 0.18s cubic-bezier(0.16, 1, 0.3, 1) forwards",
            pointerEvents: "auto",
          }}
        >
          {/* Top Banner Accent */}
          <div
            style={{
              height: "48px",
              background: `linear-gradient(135deg, ${avatarTheme.bgGrad[0]} 0%, ${avatarTheme.bgGrad[1]} 100%)`,
              position: "relative",
              display: "flex",
              alignItems: "center",
              justifyContent: "flex-end",
              padding: "0 12px",
            }}
          >
            <span
              style={{
                fontSize: "9px",
                fontWeight: 700,
                letterSpacing: "0.8px",
                textTransform: "uppercase",
                padding: "2px 8px",
                borderRadius: "10px",
                background: "rgba(0, 0, 0, 0.35)",
                color: "#ffffff",
                backdropFilter: "blur(4px)",
                border: `1px solid ${avatarTheme.accentColor}33`,
              }}
            >
              {isSubagent ? "⚡ Micro-Agent" : "👑 Core Teammate"}
            </span>
          </div>

          {/* Profile Header */}
          <div style={{ padding: "0 16px 14px 16px", marginTop: "-26px" }}>
            <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
              <div style={{ position: "relative" }}>
                <div
                  style={{
                    borderRadius: "50%",
                    border: "3px solid #0e0e1c",
                    boxShadow: "0 4px 12px rgba(0, 0, 0, 0.5)",
                  }}
                >
                  <AgentAvatar
                    name={agentName}
                    id={agentId}
                    role={agentRole}
                    size={52}
                    isThinking={isThinking}
                    isStreaming={isStreaming}
                    hideBadge
                  />
                </div>
                {/* Live Status indicator */}
                <span
                  title={isActive ? "Working on task" : "Online & Available"}
                  style={{
                    position: "absolute",
                    bottom: 2,
                    right: 2,
                    width: 12,
                    height: 12,
                    borderRadius: "50%",
                    background: isActive ? "#a855f7" : "#10b981",
                    border: "2px solid #0e0e1c",
                    boxShadow: isActive ? "0 0 8px #a855f7" : "0 0 6px #10b981",
                  }}
                />
              </div>

              {/* Action Buttons */}
              <div style={{ display: "flex", gap: "6px" }}>
                {onMention && (
                  <button
                    onClick={handleMentionClick}
                    className="btn btn-sm"
                    style={{
                      background: "rgba(255, 255, 255, 0.08)",
                      border: `1px solid ${avatarTheme.accentColor}44`,
                      color: "var(--color-ink)",
                      fontSize: "11px",
                      padding: "4px 8px",
                      height: "28px",
                      borderRadius: "6px",
                      display: "flex",
                      alignItems: "center",
                      gap: "4px",
                    }}
                    title="Mention this agent in chat"
                  >
                    <AtSign size={12} color={avatarTheme.accentColor} />
                    Mention
                  </button>
                )}
                {agentId && (
                  <button
                    onClick={handleCopyId}
                    className="btn btn-sm"
                    style={{
                      background: "rgba(255, 255, 255, 0.04)",
                      border: "1px solid rgba(255, 255, 255, 0.1)",
                      color: "var(--color-mute)",
                      padding: "4px 6px",
                      height: "28px",
                      borderRadius: "6px",
                    }}
                    title="Copy Agent ID"
                  >
                    {copied ? <Check size={12} color="#10b981" /> : <Copy size={12} />}
                  </button>
                )}
              </div>
            </div>

            {/* Name & Role */}
            <div style={{ marginTop: "10px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <h4 style={{ margin: 0, fontSize: "15px", fontWeight: 700, color: "var(--color-ink)" }}>
                  {agentName}
                </h4>
                <span style={{ fontSize: "11px", color: avatarTheme.accentColor, fontWeight: 600 }}>
                  @{agentName.toLowerCase()}
                </span>
              </div>
              <p style={{ margin: "2px 0 0 0", fontSize: "12px", color: "var(--color-body)", fontWeight: 500 }}>
                {agentRole}
              </p>
            </div>

            {/* AI Specs Grid */}
            <div
              style={{
                marginTop: "12px",
                padding: "8px 10px",
                borderRadius: "8px",
                background: "rgba(255, 255, 255, 0.03)",
                border: "1px solid rgba(255, 255, 255, 0.06)",
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "8px",
                fontSize: "11px",
              }}
            >
              <div>
                <span style={{ color: "var(--color-mute)", display: "block", fontSize: "9px", textTransform: "uppercase", fontWeight: 700 }}>
                  Model
                </span>
                <span style={{ color: "var(--color-ink)", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block" }} title={agentModel}>
                  {formattedModel}
                </span>
              </div>
              <div>
                <span style={{ color: "var(--color-mute)", display: "block", fontSize: "9px", textTransform: "uppercase", fontWeight: 700 }}>
                  Personality
                </span>
                <span style={{ color: "var(--color-ink)", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block" }}>
                  {resolvedPersonality}
                </span>
              </div>
            </div>

            {/* Custom Specialization / Instructions */}
            {agent?.custom_instructions && (
              <div
                style={{
                  marginTop: "10px",
                  padding: "8px 10px",
                  borderRadius: "8px",
                  background: `${avatarTheme.bgGrad[0]}15`,
                  border: `1px solid ${avatarTheme.bgGrad[0]}33`,
                }}
              >
                <span style={{ color: avatarTheme.accentColor, display: "block", fontSize: "9px", textTransform: "uppercase", fontWeight: 700, marginBottom: "3px" }}>
                  🎯 Expertise & Focus
                </span>
                <p style={{ margin: 0, fontSize: "11px", color: "var(--color-body)", lineHeight: "1.4", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                  {agent.custom_instructions}
                </p>
              </div>
            )}

            {/* Capability Badges */}
            <div style={{ marginTop: "12px" }}>
              <span style={{ color: "var(--color-mute)", display: "block", fontSize: "9px", textTransform: "uppercase", fontWeight: 700, marginBottom: "6px" }}>
                Capabilities & Access
              </span>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "5px" }}>
                {resolvedCaps.map(cap => {
                  const Icon = cap.Icon;
                  return (
                    <span
                      key={cap.key}
                      className="pill"
                      style={{
                        fontSize: "10px",
                        padding: "3px 7px",
                        background: "rgba(255, 255, 255, 0.04)",
                        border: `1px solid ${cap.color}33`,
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "5px",
                        color: "#f1f5f9",
                        fontWeight: 500,
                      }}
                    >
                      <Icon size={11} color={cap.color} />
                      {cap.label}
                    </span>
                  );
                })}
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}

      <style jsx global>{`
        @keyframes agentCardFadeIn {
          from {
            opacity: 0;
            transform: translateY(4px) scale(0.98);
          }
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }
      `}</style>
    </>
  );
}
