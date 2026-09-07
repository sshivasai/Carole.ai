"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, CheckCircle2, HelpCircle, CornerDownLeft, SkipForward } from "lucide-react";

interface Props {
  questionId: string;
  agentName: string;
  question: string;
  options?: string[];
  answered?: boolean;
  chosenAnswer?: string;
  onAnswer: (questionId: string, answer: string) => void;
  onSkip?: (questionId: string) => void;
}

export default function AskUserQuestionCard({
  questionId, agentName, question, options, answered, chosenAnswer, onAnswer, onSkip,
}: Props) {
  const [freeText, setFreeText] = useState("");
  const [localAnswered, setLocalAnswered] = useState(answered ?? false);
  const [localChosen, setLocalChosen] = useState(chosenAnswer ?? "");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!localAnswered && !options?.length) inputRef.current?.focus();
  }, [localAnswered, options]);

  const submit = (text: string) => {
    if (!text.trim() || localAnswered) return;
    setLocalAnswered(true);
    setLocalChosen(text.trim());
    onAnswer(questionId, text.trim());
  };

  const handleSkip = () => {
    if (localAnswered) return;
    setLocalAnswered(true);
    setLocalChosen("Skipped by user");
    if (onSkip) {
      onSkip(questionId);
    } else {
      onAnswer(questionId, "Skipped");
    }
  };

  return (
    <div
      style={{
        background: "linear-gradient(145deg, rgba(20, 20, 38, 0.9), rgba(12, 12, 24, 0.95))",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        border: "1px solid rgba(99, 102, 241, 0.35)",
        borderRadius: "14px",
        padding: "14px 18px",
        maxWidth: 520,
        boxShadow: "0 8px 32px rgba(0, 0, 0, 0.45), 0 0 20px rgba(99, 102, 241, 0.1)",
        margin: "8px 0"
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              width: 26,
              height: 26,
              borderRadius: "6px",
              background: "rgba(99, 102, 241, 0.15)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--color-primary-soft, #6366f1)"
            }}
          >
            <HelpCircle size={15} />
          </div>
          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--color-primary-soft, #6366f1)", letterSpacing: "0.04em", textTransform: "uppercase" }}>
            {agentName} asks
          </span>
        </div>
        {!localAnswered && (
          <button
            onClick={handleSkip}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--color-mute, #94a3b8)",
              fontSize: 11,
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: 4
            }}
            className="hover:text-white"
          >
            <SkipForward size={12} />
            <span>Skip</span>
          </button>
        )}
      </div>

      {/* Question */}
      <div style={{ fontSize: 13.5, color: "var(--color-ink, #ffffff)", marginBottom: 14, lineHeight: 1.55, fontWeight: 500 }}>
        {question}
      </div>

      {/* Already answered */}
      {localAnswered ? (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "8px 12px",
            borderRadius: "8px",
            background: "rgba(52, 211, 153, 0.08)",
            border: "1px solid rgba(52, 211, 153, 0.25)",
            color: "#34d399",
            fontSize: 12.5
          }}
        >
          <CheckCircle2 size={15} />
          <span>Response recorded: <strong>{localChosen}</strong></span>
        </div>
      ) : (
        <>
          {/* Multiple-choice buttons */}
          {options && options.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 12 }}>
              {options.map((opt, i) => (
                <button
                  key={i}
                  onClick={() => submit(opt)}
                  style={{
                    textAlign: "left",
                    background: "rgba(10, 10, 22, 0.7)",
                    border: "1px solid rgba(255, 255, 255, 0.08)",
                    borderRadius: "8px",
                    padding: "9px 12px",
                    fontSize: 12.5,
                    color: "var(--color-ink, #f1f5f9)",
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                    display: "flex",
                    alignItems: "center",
                    gap: 10
                  }}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLElement).style.background = "rgba(99, 102, 241, 0.2)";
                    (e.currentTarget as HTMLElement).style.borderColor = "rgba(99, 102, 241, 0.45)";
                    (e.currentTarget as HTMLElement).style.color = "#ffffff";
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLElement).style.background = "rgba(10, 10, 22, 0.7)";
                    (e.currentTarget as HTMLElement).style.borderColor = "rgba(255, 255, 255, 0.08)";
                    (e.currentTarget as HTMLElement).style.color = "var(--color-ink, #f1f5f9)";
                  }}
                >
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: 20,
                      height: 20,
                      borderRadius: "4px",
                      background: "rgba(255, 255, 255, 0.06)",
                      fontSize: 10.5,
                      fontWeight: 700,
                      color: "var(--color-mute, #94a3b8)"
                    }}
                  >
                    {String.fromCharCode(65 + i)}
                  </span>
                  <span>{opt}</span>
                </button>
              ))}
            </div>
          )}

          {/* Free-form text input */}
          <div style={{ display: "flex", gap: 8 }}>
            <input
              ref={inputRef}
              className="input"
              style={{
                flex: 1,
                fontSize: 12.5,
                height: 36,
                background: "rgba(10, 10, 22, 0.75)",
                borderColor: "rgba(255, 255, 255, 0.12)",
                borderRadius: "8px"
              }}
              placeholder={options?.length ? "Or type custom response…" : "Type your response…"}
              value={freeText}
              onChange={e => setFreeText(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit(freeText);
                }
              }}
            />
            <button
              className="btn btn-primary btn-sm"
              style={{
                height: 36,
                padding: "0 14px",
                borderRadius: "8px",
                background: "linear-gradient(135deg, #4f46e5, #6366f1)"
              }}
              onClick={() => submit(freeText)}
              disabled={!freeText.trim()}
            >
              <Send size={13} />
            </button>
          </div>
        </>
      )}
    </div>
  );
}
