"use client";

import React, { useState } from "react";
import { FileText, CheckCircle2, ArrowRight, Eye, Sparkles, AlertCircle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface InChatPlanCardProps {
  title?: string;
  summary?: string;
  planContent?: string;
  taskId?: string | null;
  status?: "awaiting_approval" | "approved" | "draft" | "executing";
  onProceed?: () => void;
  onReviewFull?: () => void;
}

export default function InChatPlanCard({
  title = "Implementation Plan",
  summary = "",
  planContent = "",
  taskId = null,
  status = "awaiting_approval",
  onProceed,
  onReviewFull
}: InChatPlanCardProps) {
  const [localProceeded, setLocalProceeded] = useState(status === "approved");

  // Extract key summary or "User Review Required" if available in markdown
  const previewText = React.useMemo(() => {
    if (summary) return summary;
    if (!planContent) return "Implementation plan proposed for user review and approval.";

    const reviewReqMatch = planContent.match(/## User Review Required([\s\S]*?)(?=##|$)/i);
    if (reviewReqMatch && reviewReqMatch[1].trim()) {
      return reviewReqMatch[1].trim().slice(0, 320);
    }
    const lines = planContent.split('\n').filter(l => l.trim() && !l.startsWith('#'));
    return lines.slice(0, 3).join('\n');
  }, [summary, planContent]);

  const handleProceedClick = () => {
    setLocalProceeded(true);
    if (onProceed) onProceed();
  };

  const isApproved = localProceeded || status === "approved";

  return (
    <div className="antigravity-artifact-card" style={{ maxWidth: 640 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              width: 30,
              height: 30,
              borderRadius: "8px",
              background: "rgba(99, 102, 241, 0.15)",
              border: "1px solid rgba(99, 102, 241, 0.3)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--color-primary-soft, #6366f1)"
            }}
          >
            <FileText size={16} />
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: "var(--color-ink, #ffffff)" }}>
                {title.startsWith("#") ? title.replace(/^#+\s*/, "") : title}
              </span>
              <span className="subagent-chip" style={{ fontSize: 9, padding: "1px 6px" }}>
                ARTIFACT
              </span>
            </div>
            <div style={{ fontSize: 11, color: "var(--color-mute, #94a3b8)", fontFamily: "var(--font-mono, monospace)" }}>
              implementation_plan.md
            </div>
          </div>
        </div>

        {/* Status Badge */}
        <div>
          {isApproved ? (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                padding: "2px 10px",
                borderRadius: 999,
                fontSize: 11,
                fontWeight: 600,
                background: "rgba(52, 211, 153, 0.15)",
                color: "#34d399",
                border: "1px solid rgba(52, 211, 153, 0.3)"
              }}
            >
              <CheckCircle2 size={12} /> Approved
            </span>
          ) : (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                padding: "2px 10px",
                borderRadius: 999,
                fontSize: 11,
                fontWeight: 600,
                background: "rgba(251, 191, 36, 0.15)",
                color: "#fbbf24",
                border: "1px solid rgba(251, 191, 36, 0.3)"
              }}
            >
              <Sparkles size={12} /> Needs Review
            </span>
          )}
        </div>
      </div>

      {/* Summary Box */}
      <div
        style={{
          background: "rgba(10, 10, 20, 0.6)",
          borderRadius: "8px",
          border: "1px solid rgba(255, 255, 255, 0.06)",
          padding: "10px 14px",
          marginBottom: 12,
          fontSize: 12,
          lineHeight: 1.5,
          color: "var(--color-body, #cbd5e1)"
        }}
        className="markdown-body"
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{previewText}</ReactMarkdown>
      </div>

      {/* Action Buttons */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        {onReviewFull && (
          <button
            onClick={onReviewFull}
            className="antigravity-pill-btn"
            style={{ padding: "6px 12px", fontSize: 12 }}
          >
            <Eye size={13} />
            <span>Review Full Plan</span>
          </button>
        )}

        <div style={{ display: "flex", gap: 8, marginLeft: "auto" }}>
          {!isApproved ? (
            <button
              onClick={handleProceedClick}
              style={{
                height: 32,
                borderRadius: 8,
                background: "linear-gradient(135deg, #4f46e5, #6366f1)",
                border: "none",
                color: "#ffffff",
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
                padding: "0 14px",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                boxShadow: "0 4px 14px rgba(79, 70, 229, 0.4)",
                transition: "all 0.15s ease"
              }}
            >
              <span>Proceed</span>
              <ArrowRight size={13} />
            </button>
          ) : (
            <div style={{ fontSize: 12, color: "#34d399", display: "flex", alignItems: "center", gap: 4 }}>
              <CheckCircle2 size={14} /> Plan approved — executing steps
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
