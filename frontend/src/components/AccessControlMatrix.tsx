"use client";
import React, { useState, useCallback } from "react";
import {
  Shield, ShieldOff, Zap, Eye, FileEdit, FilePlus, Trash2,
  Terminal, GitBranch, Globe, Monitor, Users, Clock,
  ChevronDown, ChevronUp, Plus, X, Info, Cpu, Sparkles,
} from "lucide-react";
import type { AccessControlConfig, ActionCategory, PermissionLevel } from "@/lib/types";

export const DEFAULT_ACCESS_CONTROL: AccessControlConfig = {
  enable_judge: true,
  judge_fallback: "always_ask",
  categories: {
    view: "allow", edit: "judge", create: "judge", delete: "always_ask",
    execute: "judge", git: "allow", web: "allow",
    browser: "allow", subagents: "allow", scheduler: "judge",
  },
  overrides: {},
  custom_skip_judge: { file_patterns: [], command_prefixes: [] },
};

const PRESETS: Record<string, { label: string; icon: string; desc: string; cats: Partial<Record<ActionCategory, PermissionLevel>>; judge: boolean; fallback: "allow" | "always_ask" }> = {
  autonomy:  { label: "Full Autonomy",  icon: "", desc: "High trust, minimal friction",             judge: false, fallback: "allow",      cats: { view:"allow",edit:"allow",create:"allow",delete:"always_ask",execute:"allow",git:"allow",web:"allow",browser:"allow",subagents:"allow",scheduler:"allow" } },
  guarded:   { label: "Guarded",        icon: "?", desc: "Safe actions allowed, modifications judged", judge: true,  fallback: "always_ask", cats: { view:"allow",edit:"judge",create:"judge",delete:"always_ask",execute:"judge",git:"allow",web:"allow",browser:"allow",subagents:"allow",scheduler:"judge" } },
  readonly:  { label: "Read-Only",      icon: "", desc: "Blocks execution, deletion, and file edits", judge: true,  fallback: "always_ask", cats: { view:"allow",edit:"block",create:"block",delete:"block",execute:"block",git:"allow",web:"allow",browser:"allow",subagents:"block",scheduler:"block" } },
  supervised:{ label: "Supervised",     icon: "", desc: "Always asks before workspace changes",       judge: false, fallback: "always_ask", cats: { view:"allow",edit:"always_ask",create:"always_ask",delete:"always_ask",execute:"always_ask",git:"always_ask",web:"allow",browser:"allow",subagents:"always_ask",scheduler:"always_ask" } },
};

const CATEGORIES: { key: ActionCategory; label: string; desc: string; icon: React.ElementType; tools: string }[] = [
  { key:"view",      label:"View / Read",     desc:"read_file, list_directory, grep_search, diff_files...",                 icon:Eye,       tools:"read_file, list_directory, grep_search, glob_search, diff_files, workspace_tree" },
  { key:"edit",      label:"Edit Files",      desc:"edit_file, append_file",                                              icon:FileEdit,  tools:"edit_file, append_file" },
  { key:"create",    label:"Create / Write",  desc:"write_file, create_directory, copy_file, move_file",                  icon:FilePlus,  tools:"write_file, create_directory, copy_file, move_file" },
  { key:"delete",    label:"Delete",          desc:"delete_file, workspace deletions",                                    icon:Trash2,    tools:"delete_file" },
  { key:"execute",   label:"Execute / Shell", desc:"execute_command, shell scripts",                                      icon:Terminal,  tools:"execute_command" },
  { key:"git",       label:"Git Operations",  desc:"git_status, git_diff, git_log, git_commit, git_push...",                icon:GitBranch, tools:"git_status, git_diff, git_log, git_add, git_commit, git_push, git_pull, git_branch" },
  { key:"web",       label:"Web & Search",    desc:"web_search, web_fetch, http_request",                                 icon:Globe,     tools:"web_search, web_fetch, http_request" },
  { key:"browser",   label:"Browser",         desc:"browser_navigate, browser_click, browser_type, screenshots",          icon:Monitor,   tools:"browser_navigate, browser_click, browser_type, browser_screenshot" },
  { key:"subagents", label:"Subagents",       desc:"spawn_agent, hire_subagent, send_message, team_broadcast",            icon:Users,     tools:"spawn_agent, hire_subagent, send_message, team_broadcast" },
  { key:"scheduler", label:"Scheduler",       desc:"create_scheduled_task, update_scheduled_task, delete_scheduled_task", icon:Clock,     tools:"create_scheduled_task, update_scheduled_task, delete_scheduled_task" },
];

export const TOOL_CATALOG: { category: string; label: string; icon: string; tools: { name: string; desc: string }[] }[] = [
  {
    category: "filesystem",
    label: "Filesystem & Workspace",
    icon: "📁",
    tools: [
      { name: "read_file", desc: "Read full file contents" },
      { name: "write_file", desc: "Create or overwrite a file" },
      { name: "edit_file", desc: "Targeted character-exact replacement" },
      { name: "append_file", desc: "Append text to end of file" },
      { name: "delete_file", desc: "Delete a workspace file" },
      { name: "list_directory", desc: "List files and folders at path" },
      { name: "copy_file", desc: "Copy file to destination" },
      { name: "move_file", desc: "Move or rename file" },
      { name: "create_directory", desc: "Create new directory folder" },
      { name: "diff_files", desc: "Unified diff comparison between files" },
    ]
  },
  {
    category: "search",
    label: "Search & Code Analysis",
    icon: "🔍",
    tools: [
      { name: "grep_search", desc: "Regex/text search in workspace files" },
      { name: "glob_search", desc: "Find files matching glob pattern" },
      { name: "find_function", desc: "Locate function or class definitions" },
      { name: "find_todos", desc: "Find TODO/FIXME comments in code" },
      { name: "count_lines", desc: "Count lines of code and comments" },
      { name: "analyze_imports", desc: "List all imports in a file" },
      { name: "check_syntax", desc: "Validate Python syntax without executing" },
      { name: "analyze_impact", desc: "Analyze file dependency impact" },
    ]
  },
  {
    category: "shell",
    label: "Shell & Terminal",
    icon: "💻",
    tools: [
      { name: "execute_command", desc: "Run shell commands, test runners & scripts" },
    ]
  },
  {
    category: "git",
    label: "Git Version Control",
    icon: "🌿",
    tools: [
      { name: "git_status", desc: "Show modified and staged files" },
      { name: "git_diff", desc: "View uncommitted git diffs" },
      { name: "git_add", desc: "Stage files for commit" },
      { name: "git_commit", desc: "Create git commit" },
      { name: "git_log", desc: "View recent commit history" },
      { name: "git_checkout", desc: "Switch or create branch" },
      { name: "git_push", desc: "Push commits to remote" },
      { name: "git_pull", desc: "Fetch and merge remote changes" },
      { name: "git_branch", desc: "List branches" },
      { name: "git_stash", desc: "Stash uncommitted changes" },
      { name: "git_clone", desc: "Clone remote repository" },
    ]
  },
  {
    category: "web",
    label: "Web & HTTP",
    icon: "🌐",
    tools: [
      { name: "web_search", desc: "Search web using Tavily" },
      { name: "web_fetch", desc: "Fetch plain text from web URL" },
      { name: "http_request", desc: "Make arbitrary HTTP REST calls" },
    ]
  },
  {
    category: "browser",
    label: "Browser Automation",
    icon: "🖥️",
    tools: [
      { name: "browser_navigate", desc: "Open URL in real Chromium browser" },
      { name: "browser_snapshot", desc: "Extract live DOM with Ref IDs" },
      { name: "browser_act", desc: "Perform click, type, hover, scroll via Ref IDs" },
      { name: "browser_screenshot", desc: "Capture full page or viewport screenshot" },
      { name: "browser_screenshot_element", desc: "Screenshot specific element" },
      { name: "browser_click", desc: "Click element by CSS selector" },
      { name: "browser_click_text", desc: "Click element by visible text" },
      { name: "browser_type", desc: "Type text into form input" },
      { name: "browser_press_key", desc: "Press keyboard key (Enter, Tab, Esc)" },
      { name: "browser_hover", desc: "Hover element to trigger menu" },
      { name: "browser_select_option", desc: "Select dropdown option" },
      { name: "browser_checkbox", desc: "Check or uncheck box" },
      { name: "browser_scroll", desc: "Scroll page pixels" },
      { name: "browser_scroll_to_element", desc: "Scroll element into view" },
      { name: "browser_extract_text", desc: "Extract text from selector" },
      { name: "browser_extract_html", desc: "Extract raw HTML from element" },
      { name: "browser_get_attribute", desc: "Get attribute (href, src)" },
      { name: "browser_find_elements", desc: "Find matching selectors" },
      { name: "browser_get_metadata", desc: "Get page title, URL, meta description" },
      { name: "browser_get_all_links", desc: "Extract all hyperlinks" },
      { name: "browser_eval_js", desc: "Execute custom JavaScript" },
      { name: "browser_wait_for_selector", desc: "Wait for element in DOM" },
      { name: "browser_wait_for_navigation", desc: "Wait for page load" },
      { name: "browser_wait_ms", desc: "Wait milliseconds" },
      { name: "browser_go_back", desc: "Navigate back in history" },
      { name: "browser_go_forward", desc: "Navigate forward in history" },
      { name: "browser_reload", desc: "Reload current page" },
      { name: "browser_get_url", desc: "Get active page URL" },
      { name: "browser_get_cookies", desc: "Get session cookies" },
      { name: "browser_clear_cookies", desc: "Clear cookies" },
      { name: "browser_open_tab", desc: "Open new tab" },
      { name: "browser_list_tabs", desc: "List open tabs" },
      { name: "browser_switch_tab", desc: "Switch focused tab" },
      { name: "browser_close_tab", desc: "Close tab by index" },
      { name: "browser_close_session", desc: "Close entire browser session" },
      { name: "browser_handle_dialog", desc: "Accept or dismiss alert/confirm dialog" },
      { name: "browser_task", desc: "Run autonomous multi-step browser task" },
      { name: "browser_use_task", desc: "Delegate to browser-use agent" },
      { name: "browser_human_takeover", desc: "Pause and request human CAPTCHA/2FA takeover" },
    ]
  },
  {
    category: "coordination",
    label: "Subagents & Team Coordination",
    icon: "👥",
    tools: [
      { name: "spawn_agent", desc: "Spawn teammate with a task" },
      { name: "hire_subagent", desc: "Hire temporary isolated subagent" },
      { name: "send_message", desc: "Send message in team chat" },
      { name: "create_team_agent", desc: "Create permanent team member" },
      { name: "update_team_agent", desc: "Update agent profile/skills" },
      { name: "delete_team_agent", desc: "Remove agent from roster" },
    ]
  },
  {
    category: "tasks",
    label: "Task Board & Plans",
    icon: "📋",
    tools: [
      { name: "create_task", desc: "Create task on Kanban board" },
      { name: "list_tasks", desc: "List Kanban board tasks" },
      { name: "update_task", desc: "Update task status and assignee" },
      { name: "comment_on_task", desc: "Add comment to task" },
      { name: "write_task_plan", desc: "Write implementation plan markdown" },
      { name: "request_plan_approval", desc: "Request plan review" },
      { name: "update_task_todos", desc: "Update interactive checklist on task card" },
    ]
  },
  {
    category: "scheduler",
    label: "Scheduled Tasks (Cron)",
    icon: "⏰",
    tools: [
      { name: "create_scheduled_task", desc: "Create recurring cron prompt" },
      { name: "list_scheduled_tasks", desc: "List active scheduled tasks" },
      { name: "update_scheduled_task", desc: "Pause/resume/edit scheduled task" },
      { name: "delete_scheduled_task", desc: "Delete scheduled task" },
    ]
  },
  {
    category: "interaction",
    label: "Human Interaction & HIL",
    icon: "💬",
    tools: [
      { name: "ask_user", desc: "Ask clarifying questions or request text data from user" },
      { name: "sleep", desc: "Pause execution for duration" },
    ]
  },
  {
    category: "meetings",
    label: "Voice & Meetings",
    icon: "🎙️",
    tools: [
      { name: "join_meeting", desc: "Join Google Meet or Zoom call" },
      { name: "join_google_meet", desc: "Join Google Meet with captions" },
      { name: "send_google_meet_chat", desc: "Send chat in Google Meet" },
    ]
  },
  {
    category: "memory",
    label: "Long-term Memory",
    icon: "🧠",
    tools: [
      { name: "add_memory", desc: "Save fact or lesson to long-term memory" },
      { name: "search_memory", desc: "Search long-term archival memory" },
      { name: "update_memory", desc: "Update memory entry" },
      { name: "forget_memory", desc: "Delete memory entry" },
    ]
  }
];

const PERM_CFG: Record<PermissionLevel, { label:string; color:string; bg:string; border:string; emoji:string }> = {
  allow:      { label:"Allow",      color:"#00d992", bg:"rgba(0,217,146,0.15)",   border:"rgba(0,217,146,0.4)",   emoji:"" },
  judge:      { label:"Judge",      color:"#a78bfa", bg:"rgba(167,139,250,0.15)", border:"rgba(167,139,250,0.4)", emoji:"" },
  always_ask: { label:"Always Ask", color:"#fbbf24", bg:"rgba(251,191,36,0.15)",  border:"rgba(251,191,36,0.4)",  emoji:"" },
  block:      { label:"Block",      color:"#f87171", bg:"rgba(248,113,113,0.15)", border:"rgba(248,113,113,0.4)", emoji:"" },
};

function Pill({ level, active, onClick, small }: { level:PermissionLevel; active:boolean; onClick?:()=>void; small?:boolean }) {
  const c = PERM_CFG[level];
  return (
    <button type="button" onClick={onClick} style={{
      padding: small ? "2px 7px" : "4px 10px", fontSize: small ? 11 : 12, fontWeight:600,
      borderRadius:20, border:`1.5px solid ${active ? c.border : "var(--color-hairline)"}`,
      background: active ? c.bg : "transparent", color: active ? c.color : "var(--color-mute)",
      cursor:"pointer", transition:"all 0.15s ease", whiteSpace:"nowrap",
      boxShadow: active ? `0 0 8px ${c.bg}` : "none",
    }}>
      {c.emoji} {c.label}
    </button>
  );
}

function PillGroup({ value, onChange, noJudge }: { value:PermissionLevel; onChange:(v:PermissionLevel)=>void; noJudge?:boolean }) {
  const levels: PermissionLevel[] = noJudge ? ["allow","always_ask","block"] : ["allow","judge","always_ask","block"];
  return (
    <div style={{ display:"flex", gap:4, flexWrap:"wrap" }}>
      {levels.map(l => <Pill key={l} level={l} active={value===l} onClick={() => onChange(l)} />)}
    </div>
  );
}

function ChipInput({ chips, placeholder, onAdd, onRemove }: { chips:string[]; placeholder:string; onAdd:(v:string)=>void; onRemove:(v:string)=>void }) {
  const [input, setInput] = useState("");
  const commit = () => { if (input.trim()) { onAdd(input.trim()); setInput(""); } };
  return (
    <div style={{ display:"flex", flexWrap:"wrap", gap:6, padding:"6px 10px", background:"var(--color-canvas-raised)", border:"1px solid var(--color-hairline)", borderRadius:"var(--radius-sm)", minHeight:38, alignItems:"center" }}>
      {chips.map(chip => (
        <span key={chip} style={{ display:"inline-flex", alignItems:"center", gap:4, padding:"2px 8px", borderRadius:12, background:"rgba(0,217,146,0.1)", border:"1px solid rgba(0,217,146,0.25)", color:"var(--color-primary)", fontSize:11, fontWeight:600, fontFamily:"monospace" }}>
          {chip}<button type="button" onClick={() => onRemove(chip)} style={{ background:"none", border:"none", cursor:"pointer", padding:0, color:"inherit", lineHeight:1 }}><X size={10} /></button>
        </span>
      ))}
      <input value={input} onChange={e => setInput(e.target.value)}
        onKeyDown={e => { if (e.key==="Enter"||e.key===",") { e.preventDefault(); commit(); } if (e.key==="Backspace"&&!input&&chips.length>0) onRemove(chips[chips.length-1]); }}
        placeholder={chips.length===0 ? placeholder : "Add more..."}
        style={{ background:"none", border:"none", outline:"none", color:"var(--color-body)", fontSize:12, flex:1, minWidth:80, padding:0 }} />
      {input.trim() && (
        <button type="button" onClick={commit} style={{ padding:"2px 8px", fontSize:11, background:"rgba(0,217,146,0.15)", border:"1px solid rgba(0,217,146,0.3)", borderRadius:8, color:"var(--color-primary)", cursor:"pointer" }}>
          <Plus size={10} />
        </button>
      )}
    </div>
  );
}

interface Props { value: AccessControlConfig; onChange: (c: AccessControlConfig) => void; }

export default function AccessControlMatrix({ value, onChange }: Props) {
  const [subView, setSubView] = useState<"categories" | "overrides">("categories");
  const [overrideSearch, setOverrideSearch] = useState("");
  const [selectedCat, setSelectedCat] = useState<string>("all");
  const [tooltipCat, setTooltipCat] = useState<string|null>(null);

  const patch = (p: Partial<AccessControlConfig>) => onChange({ ...value, ...p });
  const setCategory = (cat: ActionCategory, level: PermissionLevel) => onChange({ ...value, categories: { ...value.categories, [cat]: level } });
  const setOverride = (tool: string, level: PermissionLevel|null) => {
    const o = { ...value.overrides };
    if (level===null) delete o[tool]; else o[tool] = level;
    onChange({ ...value, overrides: o });
  };
  const applyPreset = (key: string) => {
    const p = PRESETS[key]; if (!p) return;
    onChange({ ...DEFAULT_ACCESS_CONTROL, ...value, enable_judge: p.judge, judge_fallback: p.fallback, categories: { ...DEFAULT_ACCESS_CONTROL.categories, ...p.cats } } as AccessControlConfig);
  };

  const judgeOn = value.enable_judge;
  const overrideCount = Object.keys(value.overrides).length;
  const hasOverrides = overrideCount > 0;

  const addFP = (p: string) => { if (!value.custom_skip_judge.file_patterns.includes(p)) patch({ custom_skip_judge: { ...value.custom_skip_judge, file_patterns: [...value.custom_skip_judge.file_patterns, p] } }); };
  const delFP = (p: string) => patch({ custom_skip_judge: { ...value.custom_skip_judge, file_patterns: value.custom_skip_judge.file_patterns.filter((x: string) => x !== p) } });
  const addCP = (p: string) => { if (!value.custom_skip_judge.command_prefixes.includes(p)) patch({ custom_skip_judge: { ...value.custom_skip_judge, command_prefixes: [...value.custom_skip_judge.command_prefixes, p] } }); };
  const delCP = (p: string) => patch({ custom_skip_judge: { ...value.custom_skip_judge, command_prefixes: value.custom_skip_judge.command_prefixes.filter((x: string) => x !== p) } });

  const query = overrideSearch.trim().toLowerCase();
  const filteredCatalog = TOOL_CATALOG.map(group => {
    if (selectedCat !== "all" && group.category !== selectedCat) return null;
    const matchingTools = group.tools.filter(t => !query || t.name.toLowerCase().includes(query) || t.desc.toLowerCase().includes(query));
    if (matchingTools.length === 0) return null;
    return { ...group, tools: matchingTools };
  }).filter(Boolean) as typeof TOOL_CATALOG;

  const totalFilteredCount = filteredCatalog.reduce((acc, g) => acc + g.tools.length, 0);

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:"var(--sp-lg)" }}>
      
      {/* Sub-navigation pills */}
      <div style={{ display:"flex", gap:6, padding:3, background:"var(--color-canvas-raised)", borderRadius:"var(--radius-sm)", border:"1px solid var(--color-hairline)" }}>
        <button
          type="button"
          onClick={() => setSubView("categories")}
          style={{
            flex: 1,
            padding: "8px 14px",
            borderRadius: "var(--radius-xs)",
            border: "none",
            cursor: "pointer",
            fontSize: 12,
            fontWeight: 600,
            transition: "all 0.15s",
            background: subView === "categories" ? "rgba(0, 217, 146, 0.15)" : "transparent",
            color: subView === "categories" ? "var(--color-primary)" : "var(--color-mute)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 6
          }}
        >
          <Shield size={13} />
          <span>Category Defaults & Presets</span>
        </button>

        <button
          type="button"
          onClick={() => setSubView("overrides")}
          style={{
            flex: 1,
            padding: "8px 14px",
            borderRadius: "var(--radius-xs)",
            border: "none",
            cursor: "pointer",
            fontSize: 12,
            fontWeight: 600,
            transition: "all 0.15s",
            background: subView === "overrides" ? "rgba(167, 139, 250, 0.15)" : "transparent",
            color: subView === "overrides" ? "#c084fc" : "var(--color-mute)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 6
          }}
        >
          <Zap size={13} />
          <span>Granular Tool Overrides</span>
          {hasOverrides && (
            <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 8, background: "#fbbf24", color: "#000", fontWeight: 700 }}>
              {overrideCount}
            </span>
          )}
        </button>
      </div>

      {subView === "categories" ? (
        <div style={{ display:"flex", flexDirection:"column", gap:"var(--sp-xl)" }}>
          {/* 1. Judge Toggle */}
          <div style={{
            padding:"var(--sp-lg)", borderRadius:"var(--radius-md)", transition:"all 0.3s ease",
            background: judgeOn ? "linear-gradient(135deg,rgba(167,139,250,0.08),rgba(0,217,146,0.05))" : "rgba(248,113,113,0.05)",
            border: `1.5px solid ${judgeOn ? "rgba(167,139,250,0.3)" : "rgba(248,113,113,0.2)"}`,
          }}>
            <div style={{ display:"flex", alignItems:"flex-start", gap:"var(--sp-lg)" }}>
              <div style={{ width:40, height:40, borderRadius:"50%", flexShrink:0, display:"flex", alignItems:"center", justifyContent:"center",
                background: judgeOn ? "rgba(167,139,250,0.15)" : "rgba(248,113,113,0.1)",
                border: `1.5px solid ${judgeOn ? "rgba(167,139,250,0.4)" : "rgba(248,113,113,0.3)"}` }}>
                {judgeOn ? <Shield size={18} color="#a78bfa" /> : <ShieldOff size={18} color="#f87171" />}
              </div>
              <div style={{ flex:1 }}>
                <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:4 }}>
                  <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                    <span className="body-strong" style={{ fontSize:13 }}>Judge AI Verification Gate</span>
                    <span style={{ fontSize:10, padding:"2px 8px", borderRadius:10, fontWeight:700,
                      background: judgeOn ? "rgba(167,139,250,0.2)" : "rgba(248,113,113,0.15)",
                      color: judgeOn ? "#a78bfa" : "#f87171",
                      border: `1px solid ${judgeOn ? "rgba(167,139,250,0.4)" : "rgba(248,113,113,0.3)"}` }}>
                      {judgeOn ? "ACTIVE" : "BYPASSED"}
                    </span>
                  </div>
                  <button type="button" onClick={() => patch({ enable_judge: !judgeOn })}
                    style={{ position:"relative", width:44, height:24, borderRadius:12, background: judgeOn ? "#a78bfa" : "var(--color-hairline)", border:"none", cursor:"pointer", transition:"background 0.2s", flexShrink:0 }}>
                    <span style={{ position:"absolute", top:3, left: judgeOn ? 23 : 3, width:18, height:18, borderRadius:"50%", background:"white", transition:"left 0.2s", boxShadow:"0 1px 4px rgba(0,0,0,0.3)" }} />
                  </button>
                </div>
                <p className="caption" style={{ margin:0, color:"var(--color-mute)", fontSize:11 }}>
                  {judgeOn
                    ? "Actions marked 'Judge' are reviewed in real-time by a secondary safety evaluator before executing."
                    : "Judge AI is bypassed — 'Judge' actions will fall back to your default policy."}
                </p>
                {!judgeOn && (
                  <div style={{ marginTop:"var(--sp-md)" }}>
                    <span className="caption" style={{ display:"block", marginBottom:6 }}>When Judge is OFF, treat <strong>Judge</strong> actions as:</span>
                    <div style={{ display:"flex", gap:"var(--sp-sm)" }}>
                      {(["allow","always_ask"] as const).map(fb => {
                        const a = value.judge_fallback===fb;
                        return (
                          <button key={fb} type="button" onClick={() => patch({ judge_fallback: fb })} style={{
                            padding:"5px 14px", borderRadius:8, fontSize:12, fontWeight:600, cursor:"pointer", transition:"all 0.15s",
                            border:`1.5px solid ${a ? (fb==="allow" ? "rgba(0,217,146,0.5)" : "rgba(251,191,36,0.5)") : "var(--color-hairline)"}`,
                            background: a ? (fb==="allow" ? "rgba(0,217,146,0.12)" : "rgba(251,191,36,0.12)") : "transparent",
                            color: a ? (fb==="allow" ? "#00d992" : "#fbbf24") : "var(--color-mute)",
                          }}>
                            {fb==="allow" ? " Auto-Allow (Autonomy)" : " Always Ask (Strict)"}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* 2. Quick Presets */}
          <div>
            <div style={{ display:"flex", alignItems:"center", gap:6, marginBottom:"var(--sp-sm)" }}>
              <Sparkles size={13} color="var(--color-primary)" />
              <span className="body-sm-strong" style={{ fontSize:12 }}>Security Presets</span>
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"repeat(2,1fr)", gap:"var(--sp-sm)" }}>
              {Object.entries(PRESETS).map(([key, p]) => (
                <button key={key} type="button" onClick={() => applyPreset(key)}
                  style={{ padding:"var(--sp-md)", borderRadius:"var(--radius-sm)", border:"1px solid var(--color-hairline)", background:"var(--color-canvas-raised)", cursor:"pointer", textAlign:"left", transition:"all 0.15s" }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.border="1px solid rgba(0,217,146,0.4)"; (e.currentTarget as HTMLElement).style.background="rgba(0,217,146,0.05)"; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.border="1px solid var(--color-hairline)"; (e.currentTarget as HTMLElement).style.background="var(--color-canvas-raised)"; }}>
                  <div style={{ fontSize:16, marginBottom:2 }}>{p.icon}</div>
                  <div className="body-sm-strong" style={{ fontSize:12 }}>{p.label}</div>
                  <div className="caption" style={{ fontSize:10 }}>{p.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* 3. Action Permissions Grid */}
          <div>
            <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:"var(--sp-sm)" }}>
              <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                <Eye size={13} color="var(--color-primary)" />
                <span className="body-sm-strong" style={{ fontSize:12 }}>Action Category Permissions</span>
              </div>
              <span className="caption" style={{ fontSize:10 }}>Sets baseline policy for each tool group</span>
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(360px, 1fr))", gap:"var(--sp-sm)" }}>
              {CATEGORIES.map(({ key, label, desc, icon: Icon }) => (
                <div key={key} style={{
                  padding:"10px 14px", borderRadius:"var(--radius-xs)", border:"1px solid var(--color-hairline)",
                  background:"var(--color-canvas-raised)", display:"flex", flexDirection:"column", gap:"var(--sp-xs)"
                }}>
                  <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", gap:"var(--sp-sm)" }}>
                    <div style={{ display:"flex", alignItems:"center", gap:"var(--sp-sm)" }}>
                      <div style={{ width:26, height:26, borderRadius:6, flexShrink:0, background:"var(--color-canvas-sunken)", display:"flex", alignItems:"center", justifyContent:"center" }}>
                        <Icon size={13} color="var(--color-mute)" />
                      </div>
                      <div>
                        <div className="body-sm-strong" style={{ fontSize:12 }}>{label}</div>
                        <span style={{ fontSize:10, color:"var(--color-mute)" }}>{desc}</span>
                      </div>
                    </div>
                    <PillGroup value={value.categories[key] || "allow"} onChange={l => setCategory(key, l)} noJudge={!judgeOn} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 4. Skip-Judge Whitelist */}
          {judgeOn && (
            <div>
              <div style={{ display:"flex", alignItems:"center", gap:6, marginBottom:"var(--sp-sm)" }}>
                <Zap size={13} color="#fbbf24" />
                <span className="body-sm-strong" style={{ fontSize:12 }}>Skip-Judge Whitelist</span>
                <span className="caption" style={{ fontSize:10, color:"var(--color-mute)" }}>— matching paths/commands execute instantly</span>
              </div>
              <div style={{ display:"flex", flexDirection:"column", gap:"var(--sp-md)" }}>
                <div>
                  <label className="caption" style={{ display:"block", marginBottom:4 }}> Safe File Patterns <span style={{ color:"var(--color-mute)", fontSize:10 }}>(glob, press Enter to add)</span></label>
                  <ChipInput chips={value.custom_skip_judge.file_patterns} placeholder="*.md, docs/**, .carole/**" onAdd={addFP} onRemove={delFP} />
                </div>
                <div>
                  <label className="caption" style={{ display:"block", marginBottom:4 }}> Safe Command Prefixes <span style={{ color:"var(--color-mute)", fontSize:10 }}>(press Enter to add)</span></label>
                  <ChipInput chips={value.custom_skip_judge.command_prefixes} placeholder="git status, npm test, pytest" onAdd={addCP} onRemove={delCP} />
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        /* Granular Tool Overrides Subview */
        <div style={{ display:"flex", flexDirection:"column", gap:"var(--sp-md)" }}>
          {/* Header controls: Search & Category Filter Pills */}
          <div style={{ display:"flex", gap:8, alignItems:"center", flexWrap:"wrap" }}>
            <input
              className="input"
              style={{ flex: 1, minWidth: 220, fontSize: 12, padding: "8px 12px" }}
              placeholder="Search tools by name (e.g. browser_navigate, git_diff, write_file)..."
              value={overrideSearch}
              onChange={e => setOverrideSearch(e.target.value)}
            />
            {hasOverrides && (
              <button
                type="button"
                onClick={() => onChange({ ...value, overrides: {} })}
                className="btn btn-ghost btn-sm"
                style={{ fontSize: 11, color: "var(--color-danger)", padding: "6px 10px" }}
                title="Reset all custom overrides to category defaults"
              >
                Clear All ({overrideCount}) Overrides
              </button>
            )}
          </div>

          {/* Horizontal Category Filter Pills */}
          <div style={{ display:"flex", gap:4, overflowX:"auto", paddingBottom:4, scrollbarWidth:"none" }}>
            <button
              type="button"
              onClick={() => setSelectedCat("all")}
              style={{
                padding: "4px 10px",
                borderRadius: 14,
                fontSize: 11,
                fontWeight: 600,
                cursor: "pointer",
                border: "1px solid",
                borderColor: selectedCat === "all" ? "var(--color-primary)" : "var(--color-hairline)",
                background: selectedCat === "all" ? "rgba(0, 217, 146, 0.15)" : "var(--color-canvas-raised)",
                color: selectedCat === "all" ? "var(--color-primary)" : "var(--color-mute)",
                whiteSpace: "nowrap"
              }}
            >
              All Tools
            </button>
            {TOOL_CATALOG.map(g => {
              const active = selectedCat === g.category;
              return (
                <button
                  key={g.category}
                  type="button"
                  onClick={() => setSelectedCat(g.category)}
                  style={{
                    padding: "4px 10px",
                    borderRadius: 14,
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: "pointer",
                    border: "1px solid",
                    borderColor: active ? "#c084fc" : "var(--color-hairline)",
                    background: active ? "rgba(167, 139, 250, 0.15)" : "var(--color-canvas-raised)",
                    color: active ? "#c084fc" : "var(--color-mute)",
                    whiteSpace: "nowrap",
                    display: "flex",
                    alignItems: "center",
                    gap: 4
                  }}
                >
                  <span>{g.icon}</span>
                  <span>{g.label}</span>
                  <span style={{ fontSize: 9.5, opacity: 0.7 }}>({g.tools.length})</span>
                </button>
              );
            })}
          </div>

          {/* Clean tool list */}
          <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
            {filteredCatalog.length === 0 ? (
              <div style={{ padding:"var(--sp-2xl)", textAlign:"center", color:"var(--color-mute)", fontSize:12, background:"var(--color-canvas-raised)", borderRadius:"var(--radius-sm)" }}>
                No tools found matching &ldquo;{overrideSearch}&rdquo;
              </div>
            ) : (
              filteredCatalog.map(group => {
                const catDefault = value.categories[group.category as ActionCategory] || "allow";
                return (
                  <div key={group.category} style={{ display:"flex", flexDirection:"column", gap:4 }}>
                    <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"4px 6px", marginTop:4 }}>
                      <span style={{ fontSize:11, fontWeight:700, color:"var(--color-body)", display:"flex", alignItems:"center", gap:6 }}>
                        <span>{group.icon}</span> {group.label}
                        <span style={{ fontSize:10, color:"var(--color-mute)", fontWeight:400 }}>({group.tools.length})</span>
                      </span>
                      <span style={{ fontSize:10, color:"var(--color-mute)" }}>
                        Category Default: <strong style={{ color:"var(--color-body)", textTransform:"capitalize" }}>{catDefault}</strong>
                      </span>
                    </div>

                    <div style={{ display:"flex", flexDirection:"column", gap:3 }}>
                      {group.tools.map(tool => {
                        const ov = value.overrides[tool.name] as PermissionLevel | undefined;
                        const isOverridden = !!ov;
                        return (
                          <div
                            key={tool.name}
                            style={{
                              display:"flex",
                              alignItems:"center",
                              justifyContent:"space-between",
                              gap:"var(--sp-md)",
                              padding:"8px 12px",
                              borderRadius:"var(--radius-xs)",
                              border: isOverridden ? "1px solid rgba(251, 191, 36, 0.4)" : "1px solid var(--color-hairline)",
                              background: isOverridden ? "rgba(251, 191, 36, 0.05)" : "var(--color-canvas-raised)",
                              transition: "all 0.15s ease"
                            }}
                          >
                            <div style={{ display:"flex", flexDirection:"column", gap:2, minWidth:0, flex:1 }}>
                              <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                                <code style={{ fontSize:12, fontWeight:600, color: isOverridden ? "#fbbf24" : "var(--color-primary-soft)" }}>
                                  {tool.name}
                                </code>
                                {isOverridden && (
                                  <span style={{ fontSize:9, padding:"1px 5px", borderRadius:4, background:"rgba(251,191,36,0.18)", color:"#fbbf24", border:"1px solid rgba(251,191,36,0.4)", fontWeight:700 }}>
                                    OVERRIDE
                                  </span>
                                )}
                              </div>
                              <span style={{ fontSize:11, color:"var(--color-mute)", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                                {tool.desc}
                              </span>
                            </div>

                            <div style={{ display:"flex", gap:4, alignItems:"center", flexShrink:0 }}>
                              {(["allow","judge","always_ask","block"] as PermissionLevel[]).map(l => {
                                if (l==="judge" && !judgeOn) return null;
                                const isActive = isOverridden ? ov === l : catDefault === l;
                                return (
                                  <Pill
                                    key={l}
                                    level={l}
                                    active={isActive}
                                    small
                                    onClick={() => setOverride(tool.name, ov === l ? null : l)}
                                  />
                                );
                              })}
                              {isOverridden && (
                                <button
                                  type="button"
                                  onClick={() => setOverride(tool.name, null)}
                                  title="Reset to category default"
                                  style={{
                                    padding:"3px 6px",
                                    fontSize:10,
                                    background:"none",
                                    border:"1px solid var(--color-hairline)",
                                    borderRadius:4,
                                    color:"var(--color-mute)",
                                    cursor:"pointer"
                                  }}
                                >
                                  <X size={10} />
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })
            )}
          </div>
          <div style={{ fontSize:11, color:"var(--color-mute)", textAlign:"right", padding:"4px 0" }}>
            Showing {totalFilteredCount} tools
          </div>
        </div>
      )}
    </div>
  );
}
