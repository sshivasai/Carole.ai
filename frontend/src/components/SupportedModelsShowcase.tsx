"use client";

import React, { useState } from "react";
import MagneticCard from "./MagneticCard";
import GravityText from "./GravityText";
import {
  Sparkles,
  Zap,
  CheckCircle2,
  Cpu,
  ShieldCheck,
  Code2,
  Terminal,
  Layers,
  ArrowUpRight,
} from "lucide-react";

import {
  ClaudeLogo,
  OpenAILogo,
  GeminiLogo,
  DeepSeekLogo,
  OllamaLogo,
} from "@/components/icons/IntegrationLogos";

/* --------------------------------------------------------------------------
   Provider Model Metadata & Realistic Real-Time Theming
   -------------------------------------------------------------------------- */

function renderProviderLogo(id: string, size = 18) {
  switch (id) {
    case "anthropic":
      return <ClaudeLogo size={size} />;
    case "openai":
      return <OpenAILogo size={size} />;
    case "google":
      return <GeminiLogo size={size} />;
    case "deepSeek":
    case "deepseek":
      return <DeepSeekLogo size={size} />;
    case "ollama":
    default:
      return <OllamaLogo size={size} />;
  }
}

interface ModelProvider {
  id: string;
  name: string;
  badge: string;
  color: string;
  gradient: string;
  bgGlow: string;
  cardBg: string;
  description: string;
  featuredModels: {
    name: string;
    tag: string;
    context: string;
    pricing: string;
    strengths: string[];
  }[];
}

const PROVIDERS: ModelProvider[] = [
  {
    id: "anthropic",
    name: "Anthropic Claude",
    badge: "Flagship Reasoning & Code Architecture",
    color: "#818cf8",
    gradient: "linear-gradient(135deg, #a78bfa 0%, #6366f1 100%)",
    bgGlow: "rgba(99, 102, 241, 0.16)",
    cardBg: "radial-gradient(ellipse at top left, rgba(99, 102, 241, 0.12), rgba(15, 17, 32, 0.95))",
    description: "Industry-leading hybrid thinking and coding precision with massive 200k context windows and AST-level refactoring.",
    featuredModels: [
      {
        name: "Claude 3.7 Sonnet",
        tag: "Hybrid Thinking / Coding",
        context: "200k Context",
        pricing: "Top Tier",
        strengths: ["AST Dead-End Pruning", "Subagent Lead Coordination", "Multi-file Architecture"],
      },
      {
        name: "Claude 3.5 Sonnet",
        tag: "Gold Standard Engineering",
        context: "200k Context",
        pricing: "Flagship",
        strengths: ["Deep Reasoning Traces", "Mathematical Logic", "Complex Git Rebasing"],
      },
      {
        name: "Claude 3.5 Haiku",
        tag: "Ultra-Fast Execution",
        context: "200k Context",
        pricing: "Low Latency",
        strengths: ["Sub-Second Tool Calls", "JSON Extraction", "Heartbeat Status Sync"],
      },
    ],
  },
  {
    id: "openai",
    name: "OpenAI",
    badge: "o-Series Reasoning & Function Calling",
    color: "#818cf8",
    gradient: "linear-gradient(135deg, #a78bfa 0%, #6366f1 100%)",
    bgGlow: "rgba(99, 102, 241, 0.16)",
    cardBg: "radial-gradient(ellipse at top left, rgba(99, 102, 241, 0.12), rgba(15, 17, 32, 0.95))",
    description: "Deep chain-of-thought reasoning models with strict typed schema adherence and high-throughput tool calling.",
    featuredModels: [
      {
        name: "o3-mini & o1",
        tag: "Chain-of-Thought Reasoning",
        context: "200k Context",
        pricing: "Reasoning Tier",
        strengths: ["Algorithmic Optimization", "Security Auditing", "Bug Hypothesis Testing"],
      },
      {
        name: "GPT-4o",
        tag: "High-Throughput Multimodal",
        context: "128k Context",
        pricing: "Flagship",
        strengths: ["Image & DOM Inspection", "Parallel Tool Calling", "Fast Context Retrieval"],
      },
      {
        name: "GPT-4o Mini",
        tag: "Cost-Efficient Workhorse",
        context: "128k Context",
        pricing: "Budget",
        strengths: ["Judge AI Policy Check", "File Parsing", "Continuous Code Linting"],
      },
    ],
  },
  {
    id: "google",
    name: "Google Gemini",
    badge: "2M+ Massive Context & Multimodal",
    color: "#818cf8",
    gradient: "linear-gradient(135deg, #a78bfa 0%, #6366f1 100%)",
    bgGlow: "rgba(99, 102, 241, 0.16)",
    cardBg: "radial-gradient(ellipse at top left, rgba(99, 102, 241, 0.12), rgba(15, 17, 32, 0.95))",
    description: "Unmatched 2,000,000+ token context capacity with native multi-modal image, audio, and large codebase ingestion.",
    featuredModels: [
      {
        name: "Gemini 2.5 Pro",
        tag: "2 Million Context Leader",
        context: "2M Context",
        pricing: "High Context",
        strengths: ["Repo-Wide Ingestion", "GraphRAG Grounding", "Full Documentation Synthesis"],
      },
      {
        name: "Gemini 2.5 Flash",
        tag: "Fast Thinking & Latency",
        context: "1M Context",
        pricing: "Balanced",
        strengths: ["Real-Time Chat Streaming", "DOM Scraping", "Playwright Log Parsing"],
      },
      {
        name: "Gemini 2.0 Flash Lite",
        tag: "High-Speed Micro-Agent",
        context: "1M Context",
        pricing: "$0.075 / M",
        strengths: ["Background Summaries", "Telemetry Compression", "AST Dead-End Pruning"],
      },
    ],
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    badge: "Open Weights & Code Architecture",
    color: "#818cf8",
    gradient: "linear-gradient(135deg, #a78bfa 0%, #6366f1 100%)",
    bgGlow: "rgba(99, 102, 241, 0.16)",
    cardBg: "radial-gradient(ellipse at top left, rgba(99, 102, 241, 0.12), rgba(15, 17, 32, 0.95))",
    description: "Highly specialized, open-weights reasoning and code generation models with full local self-hosting capability.",
    featuredModels: [
      {
        name: "DeepSeek R1",
        tag: "671B Open Reasoning Flagship",
        context: "64k Context",
        pricing: "Open Weights",
        strengths: ["Autonomous Planning", "AST Disambiguation", "Complex Math Verification"],
      },
      {
        name: "DeepSeek V3",
        tag: "High-Throughput MoE",
        context: "64k Context",
        pricing: "$0.14 / M",
        strengths: ["Full-Stack App Dev", "Code Refactoring", "Fast Test Generation"],
      },
      {
        name: "DeepSeek Coder V2",
        tag: "Code Synthesis Specialist",
        context: "128k Context",
        pricing: "Budget",
        strengths: ["Fill-In-The-Middle (FIM)", "Git Diff Synthesis", "Syntax Parsing"],
      },
    ],
  },
  {
    id: "ollama",
    name: "Local Ollama & Open Source",
    badge: "100% Private, Air-Gapped & Offline",
    color: "#818cf8",
    gradient: "linear-gradient(135deg, #a78bfa 0%, #6366f1 100%)",
    bgGlow: "rgba(99, 102, 241, 0.16)",
    cardBg: "radial-gradient(ellipse at top left, rgba(99, 102, 241, 0.12), rgba(15, 17, 32, 0.95))",
    description: "Execute completely offline on local GPUs via Ollama, vLLM, or LM Studio with zero external data transfer.",
    featuredModels: [
      {
        name: "Qwen 2.5 Coder 32B/7B",
        tag: "Top Local Coding Benchmark",
        context: "128k Context",
        pricing: "Local $0",
        strengths: ["Local AST Inspection", "Python/Rust/TS Output", "Zero Data Leakage"],
      },
      {
        name: "Llama 3.3 70B & 8B",
        tag: "Meta AI Open Core",
        context: "128k Context",
        pricing: "Local $0",
        strengths: ["Private Git CI/CD", "Local LanceDB Embeddings", "Air-Gapped Workspaces"],
      },
      {
        name: "Mistral Codestral 22B",
        tag: "European AI Code Base",
        context: "32k Context",
        pricing: "Local $0",
        strengths: ["Fast Fill-In-The-Middle", "Local Tool Parsing", "Private Memory Store"],
      },
    ],
  },
];

export default function SupportedModelsShowcase() {
  const [selectedProvider, setSelectedProvider] = useState<string>("anthropic");

  const currentProvider =
    PROVIDERS.find((p) => p.id === selectedProvider) || PROVIDERS[0];

  return (
    <div
      style={{
        width: "100%",
        position: "relative",
        paddingTop: 16,
        paddingBottom: 24,
      }}
    >
      {/* Section Header */}
      <div style={{ textAlign: "center", marginBottom: 28 }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "4px 14px",
            borderRadius: 9999,
            background: "rgba(167, 139, 250, 0.12)",
            border: "1px solid rgba(167, 139, 250, 0.25)",
            fontSize: 11,
            fontWeight: 800,
            color: "var(--color-primary, #7c3aed)",
            letterSpacing: "0.06em",
            marginBottom: 10,
            textTransform: "uppercase",
          }}
        >
          <Sparkles size={12} />
          <span>Universal LLM Foundation</span>
        </div>

        <h2
          style={{
            fontSize: "clamp(24px, 3.8vw, 36px)",
            fontWeight: 800,
            color: "var(--color-ink-strong, #0f172a)",
            letterSpacing: "-0.025em",
            marginBottom: 8,
          }}
        >
          <GravityText text="Supported Models & Providers" />
        </h2>

        <p
          style={{
            fontSize: 14.5,
            color: "var(--color-body, #475569)",
            maxWidth: 680,
            margin: "0 auto",
            lineHeight: 1.5,
          }}
        >
          Bring your own API keys or connect to local Ollama endpoints. Carole.ai standardizes tool-calling, token streaming, and subagent hiring across all leading models.
        </p>
      </div>

      {/* Provider Selector Tabs with Official Vector Logos */}
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          flexWrap: "wrap",
          gap: 10,
          marginBottom: 24,
        }}
      >
        {PROVIDERS.map((prov) => {
          const isSelected = prov.id === selectedProvider;
          return (
            <button
              key={prov.id}
              onClick={() => setSelectedProvider(prov.id)}
              style={{
                padding: "8px 16px",
                borderRadius: 9999,
                fontSize: 13,
                fontWeight: 700,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 8,
                background: isSelected
                  ? "var(--bg-glass-card, #ffffff)"
                  : "var(--color-canvas-raised, #f1f5f9)",
                border: isSelected
                  ? `2px solid ${prov.color}`
                  : "1px solid var(--color-hairline, #e2e8f0)",
                color: isSelected ? "var(--color-ink-strong, #0f172a)" : "var(--color-body, #475569)",
                boxShadow: isSelected ? `0 6px 20px ${prov.bgGlow}` : "none",
                transform: isSelected ? "translateY(-2px)" : "none",
                transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: prov.color,
                }}
              >
                {renderProviderLogo(prov.id, 18)}
              </div>
              <span>{prov.name}</span>
            </button>
          );
        })}
      </div>

      {/* Provider Details & Models Cards Grid */}
      <MagneticCard
        tiltMaxAngle={3}
        liftAmount={6}
        glowColor={currentProvider.bgGlow}
        style={{ borderRadius: 20 }}
      >
        <div
          style={{
            background: "var(--color-canvas-raised, #ffffff)",
            border: `1px solid var(--color-hairline, rgba(0,0,0,0.1))`,
            borderRadius: 20,
            padding: "28px 24px",
            boxShadow: `0 16px 48px rgba(0, 0, 0, 0.08), 0 0 32px ${currentProvider.bgGlow}`,
            backdropFilter: "blur(24px)",
            WebkitBackdropFilter: "blur(24px)",
            transition: "all 0.3s ease",
          }}
        >
          {/* Header row with authentic provider theme */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 16,
              marginBottom: 20,
              borderBottom: "1px solid var(--color-hairline, rgba(0, 0, 0, 0.08))",
              paddingBottom: 16,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 12,
                  background: "var(--color-canvas-soft, rgba(0, 0, 0, 0.04))",
                  border: `1px solid ${currentProvider.color}50`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  boxShadow: `0 4px 14px ${currentProvider.bgGlow}`,
                  color: currentProvider.color,
                }}
              >
                {renderProviderLogo(currentProvider.id, 24)}
              </div>

              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <h3
                    style={{
                      fontSize: 22,
                      fontWeight: 800,
                      color: "var(--color-ink-strong, #0f172a)",
                      margin: 0,
                    }}
                  >
                    {currentProvider.name}
                  </h3>
                  <span
                    style={{
                      fontSize: 10.5,
                      fontWeight: 700,
                      padding: "2px 9px",
                      borderRadius: 9999,
                      background: `${currentProvider.color}18`,
                      color: currentProvider.color,
                      border: `1px solid ${currentProvider.color}45`,
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                    }}
                  >
                    {currentProvider.badge}
                  </span>
                </div>
                <p style={{ fontSize: 13, color: "var(--color-body, #475569)", margin: "4px 0 0" }}>
                  {currentProvider.description}
                </p>
              </div>
            </div>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 7,
                fontFamily: "var(--font-mono, monospace)",
                fontSize: 11.5,
                fontWeight: 700,
                color: "#059669",
                padding: "5px 12px",
                borderRadius: 8,
                background: "rgba(16, 185, 129, 0.12)",
                border: "1px solid rgba(16, 185, 129, 0.3)",
              }}
            >
              <CheckCircle2 size={13} />
              <span>Full Token Streaming & Tool Scaffolding</span>
            </div>
          </div>

          {/* Model Cards Grid */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: 16,
            }}
          >
            {currentProvider.featuredModels.map((m, idx) => (
              <div
                key={idx}
                style={{
                  background: "var(--color-canvas-soft, #f8fafc)",
                  border: `1px solid var(--color-hairline, rgba(0, 0, 0, 0.08))`,
                  borderRadius: 14,
                  padding: "18px 16px",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  boxShadow: "0 4px 16px rgba(0, 0, 0, 0.04)",
                  transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
                }}
              >
                <div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      marginBottom: 6,
                    }}
                  >
                    <div style={{ fontSize: 15.5, fontWeight: 800, color: "var(--color-ink-strong, #0f172a)" }}>
                      {m.name}
                    </div>
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        fontFamily: "var(--font-mono, monospace)",
                        padding: "2px 7px",
                        borderRadius: 5,
                        background: `${currentProvider.color}18`,
                        color: currentProvider.color,
                        border: `1px solid ${currentProvider.color}35`,
                      }}
                    >
                      {m.context}
                    </span>
                  </div>

                  <div
                    style={{
                      fontSize: 12,
                      color: "var(--color-body, #475569)",
                      marginBottom: 14,
                    }}
                  >
                    {m.tag} •{" "}
                    <strong style={{ color: "var(--color-ink-strong, #0f172a)", fontWeight: 700 }}>
                      {m.pricing}
                    </strong>
                  </div>

                  {/* Strengths */}
                  <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 14 }}>
                    {m.strengths.map((s, sIdx) => (
                      <div
                        key={sIdx}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          fontSize: 12,
                          fontWeight: 600,
                          color: "var(--color-ink, #1e293b)",
                        }}
                      >
                        <Zap size={11} style={{ color: currentProvider.color, flexShrink: 0 }} />
                        <span>{s}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div
                  style={{
                    paddingTop: 10,
                    borderTop: "1px solid var(--color-hairline, rgba(0, 0, 0, 0.08))",
                    fontSize: 11,
                    fontFamily: "var(--font-mono, monospace)",
                    fontWeight: 600,
                    color: "var(--color-mute, #64748b)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <span>ReAct Loop Ready</span>
                  <span style={{ color: currentProvider.color, fontWeight: 700 }}>● Active</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </MagneticCard>
    </div>
  );
}
