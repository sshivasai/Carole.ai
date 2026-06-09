"use client";
import React from "react";
import type { LearningItem } from "@/lib/types";
import { BrainCircuit, Database } from "lucide-react";

interface Props {
  learnings: LearningItem[];
}

export default function MemoryView({ learnings }: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "var(--sp-2xl)", overflowY: "auto" }}>
      <header style={{ marginBottom: "var(--sp-3xl)" }}>
        <h2 className="display-lg" style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)" }}>
          <BrainCircuit color="var(--color-primary)" /> Long-Term Memory
        </h2>
        <p className="body-md" style={{ color: "var(--color-mute)", marginTop: "var(--sp-sm)" }}>
          Rules and facts automatically extracted by the AutoDream worker and stored in LanceDB vector storage.
        </p>
      </header>

      {learnings.length === 0 ? (
        <div style={{ textAlign: "center", padding: "var(--sp-6xl) 0", color: "var(--color-mute)" }}>
          <Database size={48} style={{ margin: "0 auto var(--sp-md)", opacity: 0.5 }} />
          <h3 className="display-sm">Memory Bank Empty</h3>
          <p className="body-sm">The AutoDream worker has not consolidated any memories for this project yet.</p>
        </div>
      ) : (
        <div style={{ display: "grid", gap: "var(--sp-lg)", gridTemplateColumns: "repeat(auto-fill, minmax(400px, 1fr))" }}>
          {learnings.map(l => (
            <div key={l.id} className="card" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <span className="eyebrow" style={{ color: "var(--color-primary-soft)" }}>Lesson Extracted</span>
                <span className="caption">{new Date(l.created_at || "").toLocaleDateString()}</span>
              </div>
              <div>
                <h4 className="body-sm-strong" style={{ color: "var(--color-mute)", marginBottom: "var(--sp-xs)" }}>Context:</h4>
                <p className="body-md">{l.task_summary}</p>
              </div>
              <div className="green-divider" style={{ opacity: 0.3 }} />
              <div>
                <h4 className="body-sm-strong" style={{ color: "var(--color-primary)", marginBottom: "var(--sp-xs)" }}>Rule applied to System Prompt:</h4>
                <div className="code-block" style={{ borderLeft: "3px solid var(--color-primary)", background: "rgba(0,217,146,0.05)" }}>
                  {l.lesson_rule}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
