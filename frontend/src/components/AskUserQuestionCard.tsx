"use client";
/**
 * AskUserQuestionCard.tsx
 *
 * Interactive card rendered in the chat when an agent calls ask_user with
 * optional multiple-choice options. The user can:
 *   - Click a choice button (sends that text as the answer)
 *   - Type a free-form reply in the input and press Enter / Send
 *
 * Props:
 *  questionId  - UUID returned by the backend (required to route the answer)
 *  agentName   - Name of the asking agent
 *  question    - The question text
 *  options     - Optional list of choice strings
 *  answered    - Whether this question has already been answered (UI locks)
 *  onAnswer    - Callback with (questionId, answerText)
 */
import React, { useState, useRef, useEffect } from "react";
import { Send, CheckCircle2, HelpCircle } from "lucide-react";

interface Props {
  questionId: string;
  agentName: string;
  question: string;
  options?: string[];
  answered?: boolean;
  chosenAnswer?: string;
  onAnswer: (questionId: string, answer: string) => void;
}

export default function AskUserQuestionCard({
  questionId, agentName, question, options, answered, chosenAnswer, onAnswer,
}: Props) {
  const [freeText, setFreeText] = useState("");
  const [localAnswered, setLocalAnswered] = useState(answered ?? false);
  const [localChosen, setLocalChosen] = useState(chosenAnswer ?? "");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!localAnswered && !options?.length) inputRef.current?.focus();
  }, []);

  const submit = (text: string) => {
    if (!text.trim() || localAnswered) return;
    setLocalAnswered(true);
    setLocalChosen(text.trim());
    onAnswer(questionId, text.trim());
  };

  return (
    <div style={{
      background: "var(--color-canvas-raised, #1f2937)",
      border: "1px solid var(--color-accent, #6366f1)",
      borderRadius: "var(--radius-md, 10px)",
      padding: "var(--sp-md, 12px) var(--sp-lg, 16px)",
      maxWidth: 480,
      boxShadow: "0 4px 24px rgba(99,102,241,0.12)",
    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <HelpCircle size={15} style={{ color: "var(--color-accent, #6366f1)", flexShrink: 0 }} />
        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--color-accent, #6366f1)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
          {agentName} asks
        </span>
      </div>

      {/* Question */}
      <div style={{ fontSize: 14, color: "var(--color-ink, #f9fafb)", marginBottom: 14, lineHeight: 1.5, fontWeight: 500 }}>
        {question}
      </div>

      {/* Already answered */}
      {localAnswered ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#10b981", fontSize: 13 }}>
          <CheckCircle2 size={15} />
          <span>Answered: <strong>{localChosen}</strong></span>
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
                    textAlign: "left", background: "var(--color-canvas-soft, #111827)",
                    border: "1px solid var(--color-hairline, #374151)", borderRadius: "var(--radius-sm, 6px)",
                    padding: "8px 12px", fontSize: 13, color: "var(--color-ink, #f9fafb)",
                    cursor: "pointer", transition: "all 0.15s",
                  }}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLElement).style.background = "var(--color-accent, #6366f1)";
                    (e.currentTarget as HTMLElement).style.color = "#fff";
                    (e.currentTarget as HTMLElement).style.borderColor = "var(--color-accent, #6366f1)";
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLElement).style.background = "var(--color-canvas-soft, #111827)";
                    (e.currentTarget as HTMLElement).style.color = "var(--color-ink, #f9fafb)";
                    (e.currentTarget as HTMLElement).style.borderColor = "var(--color-hairline, #374151)";
                  }}
                >
                  <span style={{ color: "var(--color-mute, #9ca3af)", marginRight: 8, fontSize: 11 }}>
                    {String.fromCharCode(65 + i)}.
                  </span>
                  {opt}
                </button>
              ))}
            </div>
          )}

          {/* Free-form text input */}
          <div style={{ display: "flex", gap: 8 }}>
            <input
              ref={inputRef}
              className="input"
              style={{ flex: 1, fontSize: 13, height: 36 }}
              placeholder={options?.length ? "Or type a custom answer…" : "Type your answer…"}
              value={freeText}
              onChange={e => setFreeText(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(freeText); } }}
            />
            <button
              className="btn btn-primary"
              style={{ height: 36, padding: "0 14px" }}
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
