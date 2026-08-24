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

/* --------------------------------------------------------------------------
   Official Vector Brand Logos
   -------------------------------------------------------------------------- */

function ClaudeLogo({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M13.8 2.5L15.3 8.8L21.5 10.3L15.3 11.8L13.8 18.1L12.3 11.8L6.1 10.3L12.3 8.8L13.8 2.5Z"
        fill="#D97706"
      />
      <path
        d="M5.5 15.5L6.5 18.5L9.5 19.5L6.5 20.5L5.5 23.5L4.5 20.5L1.5 19.5L4.5 18.5L5.5 15.5Z"
        fill="#F59E0B"
      />
      <circle cx="13.8" cy="10.3" r="1.6" fill="#FFFBEB" />
    </svg>
  );
}

function OpenAILogo({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
      <path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.259 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7466-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.6667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813v6.7227zm1.1458-1.9775l3.0544-1.7607 3.0544 1.7607v3.5214l-3.0544 1.7607-3.0544-1.7607z" />
    </svg>
  );
}

function GeminiLogo({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="geminiGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#4285F4" />
          <stop offset="50%" stopColor="#9B72CF" />
          <stop offset="100%" stopColor="#D96570" />
        </linearGradient>
      </defs>
      <path
        d="M12 2C12 7.523 7.523 12 2 12C7.523 12 12 16.477 12 22C12 16.477 16.477 12 22 12C16.477 12 12 7.523 12 2Z"
        fill="url(#geminiGrad)"
      />
      <circle cx="12" cy="12" r="2.5" fill="#ffffff" />
    </svg>
  );
}

function DeepSeekLogo({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="dsGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="50%" stopColor="#0284c7" />
          <stop offset="100%" stopColor="#1d4ed8" />
        </linearGradient>
      </defs>
      <path
        d="M3 13.5C5 7.5 11 5.5 16 7.5C18.5 8.5 21 7 21 7C21 7 19.5 11 17 13C14 15.5 8.5 17 4.5 15.5C3.5 15.1 3 14.3 3 13.5Z"
        fill="url(#dsGrad)"
      />
      <circle cx="8" cy="11.5" r="1.5" fill="#ffffff" />
      <path
        d="M17 13C18.5 14.5 21 15.5 21 15.5C21 15.5 19 16.5 17 16"
        stroke="#38bdf8"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function OllamaLogo({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 2C8.5 2 7 4.5 7 7.5C7 8.5 7.3 9.5 7.8 10.3C6.5 11.2 5.5 12.8 5.5 15C5.5 18.5 8.5 21.5 12 21.5C15.5 21.5 18.5 18.5 18.5 15C18.5 12.8 17.5 11.2 16.2 10.3C16.7 9.5 17 8.5 17 7.5C17 4.5 15.5 2 12 2ZM10 7.5C10 6.9 10.4 6.5 11 6.5C11.6 6.5 12 6.9 12 7.5C12 8.1 11.6 8.5 11 8.5C10.4 8.5 10 8.1 10 7.5ZM13 7.5C13 6.9 13.4 6.5 14 6.5C14.6 6.5 15 6.9 15 7.5C15 8.1 14.6 8.5 14 8.5C13.4 8.5 13 8.1 13 7.5ZM10 14C10 13.4 10.9 13 12 13C13.1 13 14 13.4 14 14C14 14.6 13.1 15.5 12 15.5C10.9 15.5 10 14.6 10 14Z" />
    </svg>
  );
}

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
    color: "#d97706",
    gradient: "linear-gradient(135deg, #d97706 0%, #b45309 100%)",
    bgGlow: "rgba(217, 119, 6, 0.18)",
    cardBg: "radial-gradient(ellipse at top left, rgba(217, 119, 6, 0.15), rgba(15, 17, 32, 0.95))",
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
    color: "#10a37f",
    gradient: "linear-gradient(135deg, #10a37f 0%, #059669 100%)",
    bgGlow: "rgba(16, 163, 127, 0.18)",
    cardBg: "radial-gradient(ellipse at top left, rgba(16, 163, 127, 0.15), rgba(15, 17, 32, 0.95))",
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
    color: "#4285f4",
    gradient: "linear-gradient(135deg, #4285f4 0%, #9b72cf 50%, #d96570 100%)",
    bgGlow: "rgba(66, 133, 244, 0.2)",
    cardBg: "radial-gradient(ellipse at top left, rgba(66, 133, 244, 0.16), rgba(155, 114, 207, 0.1), rgba(15, 17, 32, 0.95))",
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
    color: "#0284c7",
    gradient: "linear-gradient(135deg, #0284c7 0%, #2563eb 100%)",
    bgGlow: "rgba(2, 132, 199, 0.2)",
    cardBg: "radial-gradient(ellipse at top left, rgba(2, 132, 199, 0.18), rgba(15, 17, 32, 0.95))",
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
    color: "#a855f7",
    gradient: "linear-gradient(135deg, #a855f7 0%, #ec4899 100%)",
    bgGlow: "rgba(168, 85, 247, 0.2)",
    cardBg: "radial-gradient(ellipse at top left, rgba(168, 85, 247, 0.18), rgba(15, 17, 32, 0.95))",
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
            background: currentProvider.cardBg,
            border: `1px solid ${currentProvider.color}45`,
            borderRadius: 20,
            padding: "28px 24px",
            boxShadow: `0 16px 48px rgba(0, 0, 0, 0.12), 0 0 32px ${currentProvider.bgGlow}`,
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
              borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
              paddingBottom: 16,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 12,
                  background: "rgba(255, 255, 255, 0.06)",
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
                      color: "var(--color-ink-strong, #ffffff)",
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
                      background: `${currentProvider.color}20`,
                      color: currentProvider.color,
                      border: `1px solid ${currentProvider.color}45`,
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                    }}
                  >
                    {currentProvider.badge}
                  </span>
                </div>
                <p style={{ fontSize: 13, color: "var(--color-body, #94a3b8)", margin: "4px 0 0" }}>
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
                fontWeight: 600,
                color: "#10b981",
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
                  background: "var(--bg-glass-card, rgba(13, 14, 32, 0.75))",
                  border: `1px solid ${currentProvider.color}25`,
                  borderRadius: 14,
                  padding: "18px 16px",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  boxShadow: "0 4px 16px rgba(0, 0, 0, 0.08)",
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
                    <div style={{ fontSize: 15.5, fontWeight: 800, color: "var(--color-ink-strong, #ffffff)" }}>
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
                      color: "var(--color-body, #94a3b8)",
                      marginBottom: 14,
                    }}
                  >
                    {m.tag} •{" "}
                    <strong style={{ color: "var(--color-ink-strong, #ffffff)", fontWeight: 700 }}>
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
                          color: "var(--color-ink, #cbd5e1)",
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
                    borderTop: "1px solid rgba(255, 255, 255, 0.08)",
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
