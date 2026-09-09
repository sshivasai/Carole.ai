"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import {
  Send,
  CheckCircle2,
  HelpCircle,
  SkipForward,
  Check,
  ListChecks,
  Sparkles,
  Layers,
} from "lucide-react";

export interface QuestionItem {
  id?: string;
  question: string;
  options?: string[];
  is_multi_select?: boolean;
}

interface Props {
  questionId: string;
  agentName: string;
  question?: string;
  options?: string[];
  questions?: QuestionItem[];
  answered?: boolean;
  chosenAnswer?: string;
  onAnswer: (questionId: string, answer: string) => Promise<void> | void;
  onSkip?: (questionId: string) => Promise<void> | void;
}

export default function AskUserQuestionCard({
  questionId,
  agentName,
  question = "",
  options = [],
  questions,
  answered = false,
  chosenAnswer = "",
  onAnswer,
  onSkip,
}: Props) {
  // Normalize into questions array
  const questionList: QuestionItem[] = useMemo(() => {
    if (questions && Array.isArray(questions) && questions.length > 0) {
      return questions;
    }
    if (question && question.trim()) {
      return [
        {
          id: questionId || "q_0",
          question: question.trim(),
          options: options || [],
          is_multi_select: false,
        },
      ];
    }
    return [];
  }, [questions, question, options, questionId]);

  const isMultiQuestion = questionList.length > 1;

  // Answers state for multi-question mode:
  // Map of questionIndex -> { selected: string[], custom: string }
  const [answersState, setAnswersState] = useState<
    Record<number, { selected: string[]; custom: string }>
  >(() => {
    const init: Record<number, { selected: string[]; custom: string }> = {};
    questionList.forEach((_, idx) => {
      init[idx] = { selected: [], custom: "" };
    });
    return init;
  });

  // Single-question free-text input state
  const [singleFreeText, setSingleFreeText] = useState("");
  const [localAnswered, setLocalAnswered] = useState(answered);
  const [localChosen, setLocalChosen] = useState(chosenAnswer);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const singleInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setLocalAnswered(answered);
    if (chosenAnswer) setLocalChosen(chosenAnswer);
    setErrorMessage(null);
  }, [answered, chosenAnswer]);

  useEffect(() => {
    if (!localAnswered && !isMultiQuestion && (!options || options.length === 0)) {
      singleInputRef.current?.focus();
    }
  }, [localAnswered, isMultiQuestion, options]);

  // Handle single question submission
  const submitSingle = async (text: string) => {
    if (!text.trim() || localAnswered || isSubmitting) return;
    const finalAnswer = text.trim();
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      await onAnswer(questionId, finalAnswer);
      setLocalAnswered(true);
      setLocalChosen(finalAnswer);
    } catch (err: any) {
      setErrorMessage(err?.message || "Failed to submit answer. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle multi-question submission
  const submitMulti = async () => {
    if (localAnswered || isSubmitting) return;
    const resultMap: Record<string, string> = {};
    questionList.forEach((q, idx) => {
      const state = answersState[idx] || { selected: [], custom: "" };
      const combinedParts: string[] = [...state.selected];
      if (state.custom.trim()) {
        combinedParts.push(state.custom.trim());
      }
      const ansString = combinedParts.join(", ") || "No response provided";
      const qKey = q.question.replace(/^[0-9]+\.\s*/, "").trim();
      resultMap[qKey] = ansString;
    });

    const serialized = JSON.stringify(resultMap);
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      await onAnswer(questionId, serialized);
      setLocalAnswered(true);
      setLocalChosen(serialized);
    } catch (err: any) {
      setErrorMessage(err?.message || "Failed to submit answer. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSkip = async () => {
    if (localAnswered || isSubmitting) return;
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      if (onSkip) {
        await onSkip(questionId);
      } else {
        await onAnswer(questionId, "Skipped by user");
      }
      setLocalAnswered(true);
      setLocalChosen("Skipped by user");
    } catch (err: any) {
      setErrorMessage(err?.message || "Failed to skip question.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const toggleOption = (qIdx: number, opt: string, isMultiSelect?: boolean) => {
    setAnswersState((prev) => {
      const current = prev[qIdx] || { selected: [], custom: "" };
      let newSelected: string[];
      if (isMultiSelect) {
        if (current.selected.includes(opt)) {
          newSelected = current.selected.filter((s) => s !== opt);
        } else {
          newSelected = [...current.selected, opt];
        }
      } else {
        newSelected = current.selected.includes(opt) ? [] : [opt];
      }
      return {
        ...prev,
        [qIdx]: { ...current, selected: newSelected },
      };
    });
  };

  const setCustomText = (qIdx: number, text: string) => {
    setAnswersState((prev) => {
      const current = prev[qIdx] || { selected: [], custom: "" };
      return {
        ...prev,
        [qIdx]: { ...current, custom: text },
      };
    });
  };

  // Parse chosen answer for resolved view
  const parsedResolvedMap = useMemo<Array<{ question: string; answer: string }>>(() => {
    if (!localChosen) {
      if (questionList.length > 0) {
        return questionList.map((q) => ({
          question: q.question,
          answer: "Response recorded",
        }));
      }
      return [{ question: question || "Inquiry", answer: "Response recorded" }];
    }

    const trimmed = localChosen.trim();

    // 1. Check if JSON format
    if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
      try {
        const obj = JSON.parse(trimmed);
        if (typeof obj === "object" && obj !== null) {
          return Object.entries(obj).map(([k, v]) => ({
            question: k,
            answer: String(v),
          }));
        }
      } catch {}
    }

    // 2. Check if markdown bullets: - **Question**: Answer
    const bulletLines = trimmed.split("\n").filter((l) => l.trim().startsWith("- **") || l.trim().startsWith("* **"));
    if (bulletLines.length > 0) {
      const items: Array<{ question: string; answer: string }> = [];
      for (const line of bulletLines) {
        const match = line.match(/^[-*]\s+\*\*([^*]+)\*\*:\s*(.+)$/);
        if (match) {
          items.push({ question: match[1].trim(), answer: match[2].trim() });
        }
      }
      if (items.length > 0) return items;
    }

    // 3. Fallback: align with questionList if multi-question or single item
    if (questionList.length === 1) {
      return [{ question: questionList[0].question, answer: trimmed }];
    }

    return [{ question: question || "Inquiry", answer: trimmed }];
  }, [localChosen, questionList, question]);

  // Count answered questions for multi-mode button
  const multiAnsweredCount = useMemo(() => {
    let count = 0;
    questionList.forEach((_, idx) => {
      const s = answersState[idx];
      if (s && (s.selected.length > 0 || s.custom.trim().length > 0)) {
        count++;
      }
    });
    return count;
  }, [questionList, answersState]);

  // ==========================================
  // RESOLVED STATE (ELEGANT EMERALD GLASS CARD)
  // ==========================================
  if (localAnswered) {
    return (
      <div
        className="animate-fade-in"
        style={{
          background: "linear-gradient(145deg, rgba(16, 26, 36, 0.92), rgba(10, 16, 25, 0.98))",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          border: "1px solid rgba(52, 211, 153, 0.3)",
          borderRadius: "14px",
          padding: "16px 20px",
          maxWidth: 580,
          boxShadow: "0 8px 32px rgba(0, 0, 0, 0.45), 0 0 24px rgba(52, 211, 153, 0.12)",
          margin: "8px 0",
        }}
      >
        {/* Resolved Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            paddingBottom: "12px",
            borderBottom: "1px solid rgba(52, 211, 153, 0.18)",
            marginBottom: "14px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 5,
                padding: "3px 9px",
                borderRadius: "999px",
                background: "rgba(52, 211, 153, 0.16)",
                border: "1px solid rgba(52, 211, 153, 0.35)",
                color: "#34d399",
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: "0.05em",
                textTransform: "uppercase",
              }}
            >
              <CheckCircle2 size={13} />
              <span>Resolved</span>
            </div>
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "var(--color-mute, #94a3b8)",
              }}
            >
              Inquiry by <strong style={{ color: "#f8fafc" }}>{agentName}</strong>
            </span>
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              fontSize: 11,
              color: "rgba(52, 211, 153, 0.8)",
              fontWeight: 500,
            }}
          >
            <Sparkles size={12} />
            <span>Response Confirmed</span>
          </div>
        </div>

        {/* Resolved Question & Answer Breakdown */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {parsedResolvedMap.map((item, i) => (
            <div
              key={i}
              style={{
                background: "rgba(0, 0, 0, 0.25)",
                border: "1px solid rgba(255, 255, 255, 0.06)",
                borderRadius: "10px",
                padding: "10px 14px",
              }}
            >
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: "var(--color-mute, #94a3b8)",
                  marginBottom: 6,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <HelpCircle size={13} color="#818cf8" />
                <span>{item.question}</span>
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 8,
                  fontSize: 13,
                  lineHeight: 1.5,
                  color: "#f8fafc",
                  fontWeight: 500,
                }}
              >
                <div
                  style={{
                    width: 18,
                    height: 18,
                    borderRadius: "50%",
                    background: "rgba(52, 211, 153, 0.2)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                    marginTop: 2,
                  }}
                >
                  <Check size={11} color="#34d399" />
                </div>
                <div style={{ flex: 1 }}>
                  <span
                    style={{
                      display: "inline-block",
                      background: "rgba(52, 211, 153, 0.12)",
                      border: "1px solid rgba(52, 211, 153, 0.25)",
                      borderRadius: "6px",
                      padding: "3px 10px",
                      color: "#6ee7b7",
                      fontWeight: 600,
                    }}
                  >
                    {item.answer}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ==========================================
  // UNANSWERED STATE: MULTI-QUESTION BATCH CARD
  // ==========================================
  if (isMultiQuestion) {
    return (
      <div
        className="animate-fade-in"
        style={{
          background: "linear-gradient(145deg, rgba(20, 20, 38, 0.95), rgba(12, 12, 24, 0.98))",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          border: "1px solid rgba(99, 102, 241, 0.35)",
          borderRadius: "14px",
          padding: "16px 20px",
          maxWidth: 600,
          boxShadow: "0 8px 32px rgba(0, 0, 0, 0.5), 0 0 24px rgba(99, 102, 241, 0.15)",
          margin: "8px 0",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            paddingBottom: 10,
            borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
            marginBottom: 14,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: "8px",
                background: "rgba(99, 102, 241, 0.2)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--color-primary-soft, #6366f1)",
              }}
            >
              <Layers size={16} />
            </div>
            <div>
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 700,
                  color: "var(--color-primary-soft, #6366f1)",
                  letterSpacing: "0.04em",
                  textTransform: "uppercase",
                }}
              >
                {agentName} asks {questionList.length} Questions
              </div>
              <div style={{ fontSize: 11, color: "var(--color-mute, #94a3b8)" }}>
                Batch response saves tokens & keeps execution fast
              </div>
            </div>
          </div>
          <button
            onClick={handleSkip}
            disabled={isSubmitting}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--color-mute, #94a3b8)",
              fontSize: 11,
              cursor: isSubmitting ? "not-allowed" : "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              padding: "4px 8px",
              borderRadius: "6px",
            }}
            className="hover:text-white hover:bg-white/5 transition"
          >
            <SkipForward size={12} />
            <span>Skip All</span>
          </button>
        </div>

        {errorMessage && (
          <div
            style={{
              padding: "8px 12px",
              marginBottom: 12,
              borderRadius: 6,
              background: "rgba(239, 68, 68, 0.15)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              color: "#fca5a5",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span>{errorMessage}</span>
            <button
              onClick={() => setErrorMessage(null)}
              style={{ background: "none", border: "none", color: "#fca5a5", cursor: "pointer", fontSize: 11 }}
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Questions List */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16, marginBottom: 18 }}>
          {questionList.map((q, idx) => {
            const state = answersState[idx] || { selected: [], custom: "" };
            const qOptions = q.options || [];
            return (
              <div
                key={idx}
                style={{
                  background: "rgba(10, 10, 24, 0.6)",
                  border: "1px solid rgba(255, 255, 255, 0.08)",
                  borderRadius: "10px",
                  padding: "12px 14px",
                }}
              >
                {/* Question Title */}
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: "var(--color-ink, #ffffff)",
                    marginBottom: 10,
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 8,
                  }}
                >
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: 20,
                      height: 20,
                      borderRadius: "6px",
                      background: "rgba(99, 102, 241, 0.25)",
                      color: "#a5b4fc",
                      fontSize: 11,
                      fontWeight: 700,
                      flexShrink: 0,
                    }}
                  >
                    {idx + 1}
                  </span>
                  <span>{q.question}</span>
                </div>

                {/* Options (chips/buttons) */}
                {qOptions.length > 0 && (
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: 6,
                      marginBottom: 8,
                    }}
                  >
                    {qOptions.map((opt, optIdx) => {
                      const isSelected = state.selected.includes(opt);
                      return (
                        <button
                          key={optIdx}
                          type="button"
                          onClick={() => toggleOption(idx, opt, q.is_multi_select)}
                          style={{
                            textAlign: "left",
                            background: isSelected
                              ? "rgba(99, 102, 241, 0.35)"
                              : "rgba(255, 255, 255, 0.04)",
                            border: `1px solid ${
                              isSelected
                                ? "rgba(129, 140, 248, 0.6)"
                                : "rgba(255, 255, 255, 0.1)"
                            }`,
                            borderRadius: "8px",
                            padding: "6px 12px",
                            fontSize: 12,
                            color: isSelected ? "#ffffff" : "var(--color-ink, #cbd5e1)",
                            cursor: "pointer",
                            transition: "all 0.15s ease",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 6,
                          }}
                          className="hover:border-indigo-400 hover:text-white"
                        >
                          <div
                            style={{
                              width: 14,
                              height: 14,
                              borderRadius: q.is_multi_select ? "3px" : "50%",
                              border: `1px solid ${
                                isSelected ? "#818cf8" : "rgba(255,255,255,0.3)"
                              }`,
                              background: isSelected ? "#4f46e5" : "transparent",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              flexShrink: 0,
                            }}
                          >
                            {isSelected && <Check size={10} color="#ffffff" />}
                          </div>
                          <span>{opt}</span>
                        </button>
                      );
                    })}
                  </div>
                )}

                {/* Custom write-in input */}
                <input
                  className="input"
                  style={{
                    width: "100%",
                    fontSize: 12,
                    height: 32,
                    background: "rgba(0, 0, 0, 0.4)",
                    borderColor: "rgba(255, 255, 255, 0.1)",
                    borderRadius: "6px",
                    padding: "0 10px",
                  }}
                  placeholder={
                    qOptions.length > 0
                      ? "Or write in custom response..."
                      : "Type your answer..."
                  }
                  value={state.custom}
                  onChange={(e) => setCustomText(idx, e.target.value)}
                />
              </div>
            );
          })}
        </div>

        {/* Submit Actions */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ fontSize: 11.5, color: "var(--color-mute, #94a3b8)" }}>
            {multiAnsweredCount} of {questionList.length} answered
          </div>
          <button
            type="button"
            onClick={submitMulti}
            disabled={multiAnsweredCount === 0}
            className="btn btn-primary"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              padding: "8px 18px",
              borderRadius: "8px",
              fontSize: 12.5,
              fontWeight: 600,
              background:
                multiAnsweredCount > 0
                  ? "linear-gradient(135deg, #4f46e5, #6366f1)"
                  : "rgba(255, 255, 255, 0.1)",
              opacity: multiAnsweredCount === 0 ? 0.5 : 1,
              cursor: multiAnsweredCount === 0 ? "not-allowed" : "pointer",
            }}
          >
            <ListChecks size={15} />
            <span>Submit All Responses</span>
          </button>
        </div>
      </div>
    );
  }

  // ==========================================
  // UNANSWERED STATE: SINGLE-QUESTION CARD
  // ==========================================
  return (
    <div
      className="animate-fade-in"
      style={{
        background: "linear-gradient(145deg, rgba(20, 20, 38, 0.95), rgba(12, 12, 24, 0.98))",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        border: "1px solid rgba(99, 102, 241, 0.35)",
        borderRadius: "14px",
        padding: "16px 20px",
        maxWidth: 540,
        boxShadow: "0 8px 32px rgba(0, 0, 0, 0.45), 0 0 20px rgba(99, 102, 241, 0.12)",
        margin: "8px 0",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              width: 26,
              height: 26,
              borderRadius: "6px",
              background: "rgba(99, 102, 241, 0.2)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--color-primary-soft, #6366f1)",
            }}
          >
            <HelpCircle size={15} />
          </div>
          <span
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: "var(--color-primary-soft, #6366f1)",
              letterSpacing: "0.04em",
              textTransform: "uppercase",
            }}
          >
            {agentName} asks
          </span>
        </div>
        <button
          onClick={handleSkip}
          disabled={isSubmitting}
          style={{
            background: "transparent",
            border: "none",
            color: "var(--color-mute, #94a3b8)",
            fontSize: 11,
            cursor: isSubmitting ? "not-allowed" : "pointer",
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
          }}
          className="hover:text-white"
        >
          <SkipForward size={12} />
          <span>Skip</span>
        </button>
      </div>

      {errorMessage && (
        <div
          style={{
            padding: "8px 12px",
            marginBottom: 12,
            borderRadius: 6,
            background: "rgba(239, 68, 68, 0.15)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            color: "#fca5a5",
            fontSize: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span>{errorMessage}</span>
          <button
            onClick={() => setErrorMessage(null)}
            style={{ background: "none", border: "none", color: "#fca5a5", cursor: "pointer", fontSize: 11 }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Question */}
      <div
        style={{
          fontSize: 13.5,
          color: "var(--color-ink, #ffffff)",
          marginBottom: 14,
          lineHeight: 1.55,
          fontWeight: 500,
        }}
      >
        {question}
      </div>

      {/* Multiple-choice buttons */}
      {options && options.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 7, marginBottom: 12 }}>
          {options.map((opt, i) => (
            <button
              key={i}
              type="button"
              onClick={() => submitSingle(opt)}
              style={{
                textAlign: "left",
                background: "rgba(10, 10, 24, 0.7)",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                borderRadius: "8px",
                padding: "9px 12px",
                fontSize: 12.5,
                color: "var(--color-ink, #f1f5f9)",
                cursor: "pointer",
                transition: "all 0.15s ease",
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.background = "rgba(99, 102, 241, 0.25)";
                (e.currentTarget as HTMLElement).style.borderColor = "rgba(99, 102, 241, 0.5)";
                (e.currentTarget as HTMLElement).style.color = "#ffffff";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.background = "rgba(10, 10, 24, 0.7)";
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
                  background: "rgba(255, 255, 255, 0.08)",
                  fontSize: 10.5,
                  fontWeight: 700,
                  color: "#a5b4fc",
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
          ref={singleInputRef}
          className="input"
          style={{
            flex: 1,
            fontSize: 12.5,
            height: 36,
            background: "rgba(10, 10, 24, 0.8)",
            borderColor: "rgba(255, 255, 255, 0.12)",
            borderRadius: "8px",
          }}
          placeholder={options?.length ? "Or write custom response…" : "Type your response…"}
          value={singleFreeText}
          onChange={(e) => setSingleFreeText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submitSingle(singleFreeText);
            }
          }}
        />
        <button
          className="btn btn-primary btn-sm"
          style={{
            height: 36,
            padding: "0 14px",
            borderRadius: "8px",
            background: "linear-gradient(135deg, #4f46e5, #6366f1)",
          }}
          onClick={() => submitSingle(singleFreeText)}
          disabled={!singleFreeText.trim()}
        >
          <Send size={13} />
        </button>
      </div>
    </div>
  );
}
