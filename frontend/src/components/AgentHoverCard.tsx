"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import type { AgentConfig } from "@/lib/types";
import AgentAvatar from "./AgentAvatar";
import { 
  Bot, Shield, Sparkles, Cpu, AtSign, Copy, Check, 
  Terminal, FileCode, Globe, Zap, CheckCircle2, ChevronRight
} from "lucide-react";

import { getAvatarTheme } from "./PrettyAvatar";

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
                <span style={{ color: "var(--color-ink)", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block" }}>
                  {agentModel.split("/").pop() || agentModel}
                </span>
              </div>
              <div>
                <span style={{ color: "var(--color-mute)", display: "block", fontSize: "9px", textTransform: "uppercase", fontWeight: 700 }}>
                  Personality
                </span>
                <span style={{ color: "var(--color-ink)", fontWeight: 600, textTransform: "capitalize" }}>
                  {agent?.personality || "Professional"}
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
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                <span className="pill" style={{ fontSize: "10px", padding: "2px 6px", background: "rgba(255, 255, 255, 0.04)" }}>
                  <FileCode size={10} color="#34d399" /> Code & Files
                </span>
                <span className="pill" style={{ fontSize: "10px", padding: "2px 6px", background: "rgba(255, 255, 255, 0.04)" }}>
                  <Terminal size={10} color="#60a5fa" /> Terminal
                </span>
                <span className="pill" style={{ fontSize: "10px", padding: "2px 6px", background: "rgba(255, 255, 255, 0.04)" }}>
                  <Globe size={10} color="#f59e0b" /> Web Search
                </span>
                <span className="pill" style={{ fontSize: "10px", padding: "2px 6px", background: "rgba(255, 255, 255, 0.04)" }}>
                  <Zap size={10} color="#a855f7" /> Subagent Spawning
                </span>
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
