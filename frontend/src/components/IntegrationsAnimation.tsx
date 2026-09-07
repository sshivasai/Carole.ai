"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
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
  DockerLogo,
  PuppeteerLogo,
  AWSLogo,
  AirtableLogo,
  FigmaLogo,
  HubSpotLogo,
  AsanaLogo,
  MongoDBLogo,
  BraveSearchLogo,
  PerplexityLogo,
} from "@/components/icons/IntegrationLogos";
import { Network } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";

interface IntegrationItem {
  id: string;
  name: string;
  glowColor: string;
  renderIcon: (size: number) => React.ReactNode;
}

const INTEGRATIONS: IntegrationItem[] = [
  {
    id: "github",
    name: "GitHub",
    glowColor: "rgba(255, 255, 255, 0.25)",
    renderIcon: (s) => <GitHubLogo size={s} />,
  },
  {
    id: "gitlab",
    name: "GitLab",
    glowColor: "rgba(252, 109, 38, 0.35)",
    renderIcon: (s) => <GitLabLogo size={s} />,
  },
  {
    id: "postgres",
    name: "PostgreSQL",
    glowColor: "rgba(51, 103, 145, 0.35)",
    renderIcon: (s) => <PostgresLogo size={s} />,
  },
  {
    id: "slack",
    name: "Slack",
    glowColor: "rgba(224, 30, 90, 0.35)",
    renderIcon: (s) => <SlackLogo size={s} />,
  },
  {
    id: "linear",
    name: "Linear",
    glowColor: "rgba(94, 106, 210, 0.35)",
    renderIcon: (s) => <LinearLogo size={s} />,
  },
  {
    id: "notion",
    name: "Notion",
    glowColor: "rgba(255, 255, 255, 0.2)",
    renderIcon: (s) => <NotionLogo size={s} />,
  },
  {
    id: "supabase",
    name: "Supabase",
    glowColor: "rgba(62, 207, 142, 0.35)",
    renderIcon: (s) => <SupabaseLogo size={s} />,
  },
  {
    id: "redis",
    name: "Redis",
    glowColor: "rgba(220, 56, 45, 0.35)",
    renderIcon: (s) => <RedisLogo size={s} />,
  },
  {
    id: "docker",
    name: "Docker",
    glowColor: "rgba(36, 150, 237, 0.35)",
    renderIcon: (s) => <DockerLogo size={s} />,
  },
  {
    id: "sentry",
    name: "Sentry",
    glowColor: "rgba(251, 66, 38, 0.35)",
    renderIcon: (s) => <SentryLogo size={s} />,
  },
  {
    id: "stripe",
    name: "Stripe",
    glowColor: "rgba(99, 91, 255, 0.35)",
    renderIcon: (s) => <StripeLogo size={s} />,
  },
  {
    id: "google-drive",
    name: "Google Drive",
    glowColor: "rgba(66, 133, 244, 0.35)",
    renderIcon: (s) => <GoogleDriveLogo size={s} />,
  },
  {
    id: "puppeteer",
    name: "Puppeteer",
    glowColor: "rgba(0, 216, 162, 0.35)",
    renderIcon: (s) => <PuppeteerLogo size={s} />,
  },
  {
    id: "discord",
    name: "Discord",
    glowColor: "rgba(88, 101, 242, 0.35)",
    renderIcon: (s) => <DiscordLogo size={s} />,
  },
  {
    id: "graphrag",
    name: "GraphRAG",
    glowColor: "rgba(168, 85, 247, 0.35)",
    renderIcon: (s) => <Network size={s} color="#a855f7" />,
  },
  {
    id: "jira",
    name: "Jira",
    glowColor: "rgba(0, 82, 204, 0.35)",
    renderIcon: (s) => <JiraLogo size={s} />,
  },
  {
    id: "figma",
    name: "Figma",
    glowColor: "rgba(242, 78, 30, 0.35)",
    renderIcon: (s) => <FigmaLogo size={s} />,
  },
  {
    id: "hubspot",
    name: "HubSpot",
    glowColor: "rgba(255, 122, 89, 0.35)",
    renderIcon: (s) => <HubSpotLogo size={s} />,
  },
  {
    id: "aws",
    name: "AWS",
    glowColor: "rgba(255, 153, 0, 0.35)",
    renderIcon: (s) => <AWSLogo size={s} />,
  },
  {
    id: "airtable",
    name: "Airtable",
    glowColor: "rgba(24, 191, 255, 0.35)",
    renderIcon: (s) => <AirtableLogo size={s} />,
  },
  {
    id: "mongodb",
    name: "MongoDB",
    glowColor: "rgba(0, 237, 100, 0.35)",
    renderIcon: (s) => <MongoDBLogo size={s} />,
  },
  {
    id: "brave",
    name: "Brave Search",
    glowColor: "rgba(251, 84, 43, 0.35)",
    renderIcon: (s) => <BraveSearchLogo size={s} />,
  },
  {
    id: "asana",
    name: "Asana",
    glowColor: "rgba(240, 106, 106, 0.35)",
    renderIcon: (s) => <AsanaLogo size={s} />,
  },
  {
    id: "perplexity",
    name: "Perplexity",
    glowColor: "rgba(34, 184, 205, 0.35)",
    renderIcon: (s) => <PerplexityLogo size={s} />,
  },
];

const WORKFLOWS = [
  {
    objective: "Triaged GitHub issue #402, migrated PostgreSQL schema, containerized microservice & updated Linear sprint.",
    activeTools: ["github", "postgres", "docker", "linear"],
  },
  {
    objective: "Captured production Sentry error trace, ran headless browser tests, and notified team on Slack.",
    activeTools: ["sentry", "gitlab", "slack", "puppeteer"],
  },
  {
    objective: "Synced Stripe invoice webhooks to Supabase database and exported quarterly financial summary to Google Docs.",
    activeTools: ["google-drive", "notion", "supabase", "stripe"],
  },
  {
    objective: "Queried LanceDB GraphRAG embeddings, purged Redis cache clusters, and published deployment logs to Discord.",
    activeTools: ["graphrag", "redis", "discord", "docker"],
  },
  {
    objective: "Extracted Figma design tokens, created Jira sprint epics, and synced product roadmap to Notion & Asana.",
    activeTools: ["figma", "jira", "asana", "notion"],
  },
  {
    objective: "Queried MongoDB user clusters, dispatched HubSpot lead workflows, and archived raw telemetry to AWS S3.",
    activeTools: ["mongodb", "hubspot", "aws", "airtable"],
  },
  {
    objective: "Ran live Brave Search & Perplexity research, executed Puppeteer browser scraping, and updated knowledge graphs.",
    activeTools: ["perplexity", "puppeteer", "brave", "github"],
  },
];

export default function IntegrationsAnimation() {
  const { theme } = useTheme();
  const isLight = theme === "light";
  const [workflowIdx, setWorkflowIdx] = useState(0);
  const [isBlinking, setIsBlinking] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setWorkflowIdx((idx) => (idx + 1) % WORKFLOWS.length);
    }, 4200);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const blink = () => {
      setIsBlinking(true);
      setTimeout(() => setIsBlinking(false), 150);
      const nextBlink = Math.random() * 4000 + 2000;
      setTimeout(blink, nextBlink);
    };

    const timeout = setTimeout(blink, 2000);
    return () => clearTimeout(timeout);
  }, []);

  const currentWorkflow = WORKFLOWS[workflowIdx];

  // Layout constants
  const CANVAS_W = 480;
  const CANVAS_H = 460;

  const AGENT_X = CANVAS_W / 2;
  const AGENT_Y = 50;

  const OBJECTIVE_X = CANVAS_W / 2;
  const OBJECTIVE_Y = 400;

  const TOOL_Y = 220;

  return (
    <div
      style={{
        position: "relative",
        width: CANVAS_W,
        height: CANVAS_H,
        margin: "0 auto",
        overflow: "visible",
        fontFamily: "'Google Sans Flex', -apple-system, BlinkMacSystemFont, sans-serif",
      }}
    >
      {/* SVG Background Lines */}
      <svg
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          zIndex: 0,
          overflow: "visible",
        }}
      >
        {[0, 1, 2, 3].map((i) => {
          const x = 96 + i * 96;
          const strokeColor = isLight ? "rgba(99, 102, 241, 0.22)" : "rgba(93, 111, 247, 0.35)";
          const strokeWidth = 1.5;

          return (
            <g key={`flow-${i}`}>
              {/* Agent -> Tool Cable */}
              <motion.path
                d={`M ${AGENT_X} ${AGENT_Y + 36} C ${AGENT_X} ${TOOL_Y - 60}, ${x} ${AGENT_Y + 60}, ${x} ${TOOL_Y - 36}`}
                fill="none"
                stroke={strokeColor}
                strokeWidth={strokeWidth}
                animate={{ stroke: strokeColor }}
                transition={{ duration: 0.5 }}
              />
              {/* Tool -> Objective Cable */}
              <motion.path
                d={`M ${x} ${TOOL_Y + 36} C ${x} ${TOOL_Y + 80}, ${OBJECTIVE_X} ${OBJECTIVE_Y - 80}, ${OBJECTIVE_X} ${OBJECTIVE_Y - 50}`}
                fill="none"
                stroke={strokeColor}
                strokeWidth={strokeWidth}
                animate={{ stroke: strokeColor }}
                transition={{ duration: 0.5 }}
              />

              {/* Glowing Pulse Packets in Brand Blue */}
              <motion.circle
                r={3}
                fill="#5d6ff7"
                initial={{ offsetDistance: "0%", opacity: 0 }}
                animate={{ offsetDistance: "100%", opacity: [0, 1, 1, 0] }}
                transition={{
                  duration: 1.6,
                  repeat: Infinity,
                  ease: "linear",
                  delay: i * 0.22,
                }}
                style={{
                  filter: "drop-shadow(0 0 6px #5d6ff7)",
                  offsetPath: `path('M ${AGENT_X} ${AGENT_Y + 36} C ${AGENT_X} ${TOOL_Y - 60}, ${x} ${AGENT_Y + 60}, ${x} ${TOOL_Y - 36}')`,
                } as any}
              />
              <motion.circle
                r={3}
                fill="#10b981"
                initial={{ offsetDistance: "0%", opacity: 0 }}
                animate={{ offsetDistance: "100%", opacity: [0, 1, 1, 0] }}
                transition={{
                  duration: 1.6,
                  repeat: Infinity,
                  ease: "linear",
                  delay: i * 0.22 + 0.8,
                }}
                style={{
                  filter: "drop-shadow(0 0 5px #10b981)",
                  offsetPath: `path('M ${x} ${TOOL_Y + 36} C ${x} ${TOOL_Y + 80}, ${OBJECTIVE_X} ${OBJECTIVE_Y - 80}, ${OBJECTIVE_X} ${OBJECTIVE_Y - 50}')`,
                } as any}
              />
            </g>
          );
        })}
      </svg>

      {/* Top Node: Agent Swarm Brain (Animated Face) - Blank & Circular */}
      <motion.div
        style={{
          position: "absolute",
          left: AGENT_X - 42,
          top: AGENT_Y - 42,
          width: 84,
          height: 84,
          borderRadius: "50%",
          background: "transparent",
          border: "none",
          boxShadow: "none",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 10,
          overflow: "hidden",
        }}
        animate={{
          y: [0, -4, 0],
        }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
      >
        <motion.div
          animate={{
            scale: [1, 1.04, 1],
          }}
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
          style={{ width: "100%", height: "100%", position: "relative", borderRadius: "50%", overflow: "hidden" }}
        >
          <img
            src={
              isBlinking
                ? "/branding/agent-eyes-closed.png"
                : "/branding/agent-eyes-open.png"
            }
            alt="Carole Agent"
            style={{
              width: "100%",
              height: "100%",
              objectFit: "contain",
              borderRadius: "50%",
            }}
          />
        </motion.div>
      </motion.div>

      {/* Middle Nodes: 4 Brand-Colored MCP Tools */}
      {[0, 1, 2, 3].map((i) => {
        const toolId = currentWorkflow.activeTools[i];
        const tool = INTEGRATIONS.find((t) => t.id === toolId) || INTEGRATIONS[0];
        const x = 96 + i * 96;
        const y = TOOL_Y;

        return (
          <div
            key={`slot-${i}`}
            style={{
              position: "absolute",
              left: x - 40,
              top: y - 40,
              width: 80,
              height: 94,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "flex-start",
              zIndex: 10,
            }}
          >
            {/* Unified AnimatePresence ensures Icon and Label transition together with 0 jump */}
            <AnimatePresence mode="wait">
              <motion.div
                key={tool.id}
                initial={{ scale: 0.88, opacity: 0, y: 4 }}
                animate={{ scale: 1, opacity: 1, y: 0 }}
                exit={{ scale: 0.88, opacity: 0, y: -4 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: "8px",
                  width: "100%",
                }}
              >
                {/* Icon Card */}
                <div
                  style={{
                    width: 60,
                    height: 60,
                    borderRadius: "14px",
                    background: isLight ? "rgba(255, 255, 255, 0.95)" : "rgba(18, 18, 35, 0.78)",
                    border: isLight ? "1px solid rgba(0, 0, 0, 0.08)" : "1px solid rgba(255, 255, 255, 0.12)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    boxShadow: isLight
                      ? `0 4px 16px rgba(0,0,0,0.06), 0 0 16px ${tool.glowColor}`
                      : `0 4px 16px rgba(0,0,0,0.2), 0 0 16px ${tool.glowColor}`,
                    backdropFilter: "blur(14px)",
                    WebkitBackdropFilter: "blur(14px)",
                    color: isLight ? "#0f172a" : "var(--color-ink-strong, #ffffff)",
                    flexShrink: 0,
                  }}
                >
                  {tool.renderIcon(28)}
                </div>

                {/* Light, Soft Label ALWAYS directly below card */}
                <span
                  style={{
                    fontSize: 11.5,
                    fontWeight: isLight ? 600 : 500,
                    color: isLight ? "#334155" : "var(--color-mute, #94a3b8)",
                    letterSpacing: "0.01em",
                    textAlign: "center",
                    whiteSpace: "nowrap",
                    lineHeight: "14px",
                  }}
                >
                  {tool.name}
                </span>
              </motion.div>
            </AnimatePresence>
          </div>
        );
      })}

      {/* Bottom Node: Live Team Objective Accomplishment */}
      <motion.div
        style={{
          position: "absolute",
          left: OBJECTIVE_X - 220,
          top: OBJECTIVE_Y - 50,
          background: isLight ? "rgba(255, 255, 255, 0.95)" : "rgba(14, 14, 26, 0.82)",
          border: isLight ? "1px solid rgba(0, 0, 0, 0.08)" : "1px solid rgba(255, 255, 255, 0.12)",
          borderRadius: 16,
          padding: "16px 20px",
          width: "440px",
          display: "flex",
          flexDirection: "column",
          gap: 8,
          zIndex: 10,
          backdropFilter: "blur(16px)",
          WebkitBackdropFilter: "blur(16px)",
          boxShadow: isLight
            ? "0 8px 30px rgba(0, 0, 0, 0.06), 0 0 16px rgba(99, 102, 241, 0.08)"
            : "0 8px 30px rgba(0, 0, 0, 0.25), 0 0 16px var(--color-primary-glow-sm)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: "#10b981",
              boxShadow: "0 0 8px #10b981",
            }}
          />
          <span
            style={{
              fontSize: 10.5,
              fontWeight: 700,
              letterSpacing: "0.08em",
              color: isLight ? "#059669" : "#10b981",
              textTransform: "uppercase",
            }}
          >
            Autonomous Swarm Active
          </span>
        </div>

        <div
          style={{
            minHeight: "38px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <AnimatePresence mode="wait">
            <motion.p
              key={workflowIdx}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.35 }}
              style={{
                margin: 0,
                fontSize: 12.5,
                lineHeight: "18px",
                fontWeight: isLight ? 550 : 450,
                color: isLight ? "#1e293b" : "var(--color-body, #94a3b8)",
                textAlign: "center",
              }}
            >
              {currentWorkflow.objective}
            </motion.p>
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
}
