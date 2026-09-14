"use client";
import { useState } from "react";
import ChatInterface from "@/components/ChatInterface";
import AgentPermissionCard from "@/components/AgentPermissionCard";
import AskUserQuestionCard from "@/components/AskUserQuestionCard";
import FileChangeCard from "@/components/FileChangeCard";
import { AuthProvider } from "@/hooks/useAuth";
import type { ChatMessage } from "@/lib/types";

const messages: ChatMessage[] = [
  { id: "preview-user", sender_id: "human", sender_name: "You", type: "message", text: "Can you make our request flow easier to follow?" },
  { id: "preview-agent", sender_id: "archer", sender_name: "Archer", role: "assistant", type: "message", text: "The conversation should make three things clear: **what’s happening, what needs you, and what changed.**\n\nI’ve traced the request flow and found a good place to start. We can keep the conversation spacious while making every tool call inspectable.\n\n### A clearer flow\n\n- Group related tool calls into a compact activity ledger.\n- Keep decisions visible until they’re resolved.\n- Review changes without losing your place.", reasoning: "I’ll inspect the current request flow before proposing changes.\n🛠️ **read_file**\n```json\n{\"path\":\"src/components/ChatInterface.tsx\"}\n```\n📄 **Result:**\n```\nLoaded the conversation component.\n```\n" },
];
export default function ChatPreview() {
  const [view, setView] = useState("conversation");
  const [fail, setFail] = useState(false);
  const [light, setLight] = useState(false);
  const [reset, setReset] = useState(0);
  const respond = async () => { if (fail) throw new Error("Preview failure: your response was not sent. Turn off simulated failure and retry."); };
  return <div className={light ? "theme-light" : "theme-dark"} style={{ height: "100dvh", display: "flex", flexDirection: "column", background: "var(--color-canvas)", color: "var(--color-ink)" }}>
    <div style={{ padding: 10, display: "flex", alignItems: "center", flexWrap: "wrap", gap: 8, borderBottom: "1px solid var(--color-hairline)", fontSize: 12 }}>
      <strong>Local UI fixture</strong><span>No agent actions are sent.</span>
      <select aria-label="Preview state" value={view} onChange={e => setView(e.target.value)}><option value="conversation">Conversation</option><option value="empty">Empty conversation</option><option value="requests">Requests & changes</option></select>
      <label><input type="checkbox" checked={fail} onChange={e => setFail(e.target.checked)} /> Simulate failure</label>
      <button onClick={() => setReset(v => v + 1)}>Reset requests</button><button onClick={() => setLight(v => !v)}>Toggle preview theme</button>
    </div>
    {view === "requests" ? <div className="cw-workspace" style={{ flex: 1, overflow: "auto", padding: "24px 16px" }}><div style={{ maxWidth: 760, margin: "auto" }} key={reset}>
      <AgentPermissionCard msg={{ id: "fixture-approval", tx_id: "fixture-approval", sender_id: "archer", sender_name: "Archer", text: "Run the frontend checks to verify these changes.", type: "approval_request", tool_name: "execute_command", arguments: { command: "npm run lint", cwd: "frontend" } }} onDecide={respond} />
      <AskUserQuestionCard questionId="fixture-question" agentName="Archer" question="How should the activity timeline open?" options={["Collapsed until I open it", "Expanded while work is running"]} onAnswer={respond} onSkip={respond} />
      <FileChangeCard files={[{ path: "src/components/ChatInterface.tsx", action: "modified", diff: "--- a/src/components/ChatInterface.tsx\n+++ b/src/components/ChatInterface.tsx\n@@ -12,2 +12,2 @@\n-const title = 'Team chat';\n+const title = 'Conversation';\n return title;" }, { path: "src/features/chat/background.ts", action: "created" }]} />
    </div></div> : <AuthProvider><ChatInterface key={view} messages={view === "empty" ? [] : messages} agents={[{ id: "archer", name: "Archer", role: "Lead engineer", model: "Preview model" }]} teamId={null} onSendMessage={() => ({ success: false, error: "This is a UI fixture." })} /></AuthProvider>}
  </div>;
}
