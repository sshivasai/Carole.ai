"use client";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { MessageCircleQuestion, Check, Loader2, ArrowUpRight } from "lucide-react";
import "./chat-workspace.css";
export interface QuestionItem { id?: string; question: string; options?: string[]; is_multi_select?: boolean; }
interface Props {
  questionId: string; agentName: string; question?: string; options?: string[]; questions?: QuestionItem[];
  answered?: boolean; chosenAnswer?: string;
  onAnswer: (questionId: string, answer: string) => Promise<void> | void;
  onSkip?: (questionId: string) => Promise<void> | void;
}
export default function AskUserQuestionCard({ questionId, agentName, question = "", options, questions, answered = false, chosenAnswer = "", onAnswer, onSkip }: Props) {
  const list = useMemo(() => questions?.length ? questions : [{ id: questionId, question, options }], [questions, questionId, question, options]);
  const [drafts, setDrafts] = useState<Record<number, { selected: string[]; text: string }>>({});
  const [receipt, setReceipt] = useState<{ id: string; answer: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const currentId = useRef(questionId);
  useEffect(() => { currentId.current = questionId; }, [questionId]);
  useEffect(() => { setDrafts({}); setError(""); }, [questionId]);
  const resolved = answered || receipt?.id === questionId;
  const update = (index: number, patch: Partial<{ selected: string[]; text: string }>) => setDrafts(prev => ({ ...prev, [index]: { ...(prev[index] || { selected: [], text: "" }), ...patch } }));
  const valueAt = (index: number) => [...(drafts[index]?.selected || []), ...(drafts[index]?.text.trim() ? [drafts[index].text.trim()] : [])].join(", ");
  const complete = list.every((_, index) => valueAt(index));
  const submit = async (skip = false) => {
    if (lock.current || resolved || (!skip && !complete)) return;
    const answer = skip ? "Skipped by user" : list.length === 1 ? valueAt(0) : JSON.stringify(Object.fromEntries(list.map((q, index) => [q.id || (list.filter(other => other.question === q.question).length > 1 ? q.question + " (" + (index + 1) + ")" : q.question), valueAt(index)])));
    lock.current = true; setBusy(true); setError("");
    try {
      if (skip && onSkip) await onSkip(questionId); else await onAnswer(questionId, answer);
      if (currentId.current === questionId) setReceipt({ id: questionId, answer });
    } catch (e) { if (currentId.current === questionId) setError(e instanceof Error ? e.message : "Your answer was not sent. Please retry."); }
    finally { lock.current = false; setBusy(false); }
  };
  if (resolved) return <section className="cw-request cw-request-resolved" data-status="approved"><div className="cw-receipt"><Check size={16} /><strong>Response sent</strong><small>{agentName}</small></div><div className="cw-request-content"><p>{chosenAnswer || receipt?.answer}</p></div></section>;
  return <section className="cw-request cw-question" aria-label="Agent question" aria-busy={busy}>
    <div className="cw-request-heading"><span className="cw-request-icon"><MessageCircleQuestion size={21} /></span><div><span className="cw-eyebrow">Your input</span><h3>Let’s choose a direction</h3><p>{agentName} needs your input to continue.</p></div></div>
    <form className="cw-request-content" onSubmit={e => { e.preventDefault(); void submit(); }}>
      {list.map((q, index) => <fieldset key={q.id || index} disabled={busy}>
        <legend>{list.length > 1 ? (index + 1) + ". " : ""}{q.question}</legend>
        {q.is_multi_select && <p className="cw-muted">Select all that apply.</p>}
        <div className="cw-options">{(q.options || []).map(option => <label className="cw-option" key={option}><input type={q.is_multi_select ? "checkbox" : "radio"} name={questionId + "-" + index} checked={drafts[index]?.selected.includes(option) || false} onChange={() => {
          const selected = drafts[index]?.selected || [];
          update(index, { selected: q.is_multi_select ? selected.includes(option) ? selected.filter(v => v !== option) : [...selected, option] : [option], ...(!q.is_multi_select ? { text: "" } : {}) });
        }} /><span>{option}</span><Check size={15} className="cw-option-check" aria-hidden="true" /></label>)}</div>
        <label className="cw-detail-label" htmlFor={questionId + "-answer-" + index}>{q.options?.length ? "Or add your own answer" : "Your answer"}</label>
        <textarea id={questionId + "-answer-" + index} rows={2} value={drafts[index]?.text || ""} onChange={e => update(index, { text: e.target.value, ...(!q.is_multi_select && e.target.value.trim() ? { selected: [] } : {}) })} placeholder="Share your preference…" />
      </fieldset>)}
      {error && <p role="alert" className="cw-inline-error">{error}</p>}
      <div className="cw-request-actions">{onSkip && <button type="button" className="cw-text-button" disabled={busy} onClick={() => void submit(true)}>Skip for now</button>}<button className="cw-button cw-primary" type="submit" disabled={busy || !complete}>{busy ? <Loader2 size={14} className="cw-spin" /> : <ArrowUpRight size={14} />}{busy ? "Sending…" : "Send answer"}</button></div>
    </form>
  </section>;
}
