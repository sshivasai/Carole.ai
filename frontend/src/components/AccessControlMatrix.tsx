"use client";
import React, { useState, useCallback } from "react";
import {
  Shield, ShieldOff, Zap, Eye, FileEdit, FilePlus, Trash2,
  Terminal, GitBranch, Globe, Monitor, Users, Clock,
  ChevronDown, ChevronUp, Plus, X, Info, Cpu,
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
  autonomy:  { label: "Full Autonomy",  icon: "??", desc: "High trust, minimal friction",             judge: false, fallback: "allow",      cats: { view:"allow",edit:"allow",create:"allow",delete:"always_ask",execute:"allow",git:"allow",web:"allow",browser:"allow",subagents:"allow",scheduler:"allow" } },
  guarded:   { label: "Guarded",        icon: "???", desc: "Safe actions allowed, modifications judged", judge: true,  fallback: "always_ask", cats: { view:"allow",edit:"judge",create:"judge",delete:"always_ask",execute:"judge",git:"allow",web:"allow",browser:"allow",subagents:"allow",scheduler:"judge" } },
  readonly:  { label: "Read-Only",      icon: "??", desc: "Blocks execution, deletion, and file edits", judge: true,  fallback: "always_ask", cats: { view:"allow",edit:"block",create:"block",delete:"block",execute:"block",git:"allow",web:"allow",browser:"allow",subagents:"block",scheduler:"block" } },
  supervised:{ label: "Supervised",     icon: "??", desc: "Always asks before workspace changes",       judge: false, fallback: "always_ask", cats: { view:"allow",edit:"always_ask",create:"always_ask",delete:"always_ask",execute:"always_ask",git:"always_ask",web:"allow",browser:"allow",subagents:"always_ask",scheduler:"always_ask" } },
};

const CATEGORIES: { key: ActionCategory; label: string; desc: string; Icon: React.ElementType; tools: string }[] = [
  { key:"view",      label:"View / Read",     desc:"read_file, list_directory, grep_search, diff_files…",                 Icon:Eye,       tools:"read_file, list_directory, grep_search, glob_search, diff_files, workspace_tree" },
  { key:"edit",      label:"Edit Files",      desc:"edit_file, append_file",                                              Icon:FileEdit,  tools:"edit_file, append_file" },
  { key:"create",    label:"Create / Write",  desc:"write_file, create_directory, copy_file, move_file",                  Icon:FilePlus,  tools:"write_file, create_directory, copy_file, move_file" },
  { key:"delete",    label:"Delete",          desc:"delete_file, workspace deletions",                                    Icon:Trash2,    tools:"delete_file" },
  { key:"execute",   label:"Execute / Shell", desc:"execute_command, shell scripts",                                      Icon:Terminal,  tools:"execute_command" },
  { key:"git",       label:"Git Operations",  desc:"git_status, git_diff, git_log, git_commit, git_push…",                Icon:GitBranch, tools:"git_status, git_diff, git_log, git_add, git_commit, git_push, git_pull, git_branch" },
  { key:"web",       label:"Web & Search",    desc:"web_search, web_fetch, http_request",                                 Icon:Globe,     tools:"web_search, web_fetch, http_request" },
  { key:"browser",   label:"Browser",         desc:"browser_navigate, browser_click, browser_type, screenshots",          Icon:Monitor,   tools:"browser_navigate, browser_click, browser_type, browser_screenshot" },
  { key:"subagents", label:"Subagents",       desc:"spawn_agent, hire_subagent, send_message, team_broadcast",            Icon:Users,     tools:"spawn_agent, hire_subagent, send_message, team_broadcast" },
  { key:"scheduler", label:"Scheduler",       desc:"create_scheduled_task, update_scheduled_task, delete_scheduled_task", Icon:Clock,     tools:"create_scheduled_task, update_scheduled_task, delete_scheduled_task" },
];

const OVERRIDE_TOOLS = [
  "read_file","write_file","edit_file","append_file","delete_file",
  "execute_command","git_push","git_commit","git_clone",
  "web_search","web_fetch","http_request",
  "browser_navigate","browser_type","browser_click",
  "spawn_agent","hire_subagent",
  "create_scheduled_task","delete_scheduled_task",
];

const PERM_CFG: Record<PermissionLevel, { label:string; color:string; bg:string; border:string; emoji:string }> = {
  allow:      { label:"Allow",      color:"#00d992", bg:"rgba(0,217,146,0.15)",   border:"rgba(0,217,146,0.4)",   emoji:"??" },
  judge:      { label:"Judge",      color:"#a78bfa", bg:"rgba(167,139,250,0.15)", border:"rgba(167,139,250,0.4)", emoji:"??" },
  always_ask: { label:"Always Ask", color:"#fbbf24", bg:"rgba(251,191,36,0.15)",  border:"rgba(251,191,36,0.4)",  emoji:"??" },
  block:      { label:"Block",      color:"#f87171", bg:"rgba(248,113,113,0.15)", border:"rgba(248,113,113,0.4)", emoji:"??" },
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
        placeholder={chips.length===0 ? placeholder : "Add more…"}
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
  const [showOverrides, setShowOverrides] = useState(false);
  const [overrideSearch, setOverrideSearch] = useState("");
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
  const hasOverrides = Object.keys(value.overrides).length > 0;
  const filteredTools = OVERRIDE_TOOLS.filter(t => !overrideSearch || t.includes(overrideSearch));

  const addFP = (p: string) => { if (!value.custom_skip_judge.file_patterns.includes(p)) patch({ custom_skip_judge: { ...value.custom_skip_judge, file_patterns: [...value.custom_skip_judge.file_patterns, p] } }); };
  const delFP = (p: string) => patch({ custom_skip_judge: { ...value.custom_skip_judge, file_patterns: value.custom_skip_judge.file_patterns.filter((x: string) => x !== p) } });
  const addCP = (p: string) => { if (!value.custom_skip_judge.command_prefixes.includes(p)) patch({ custom_skip_judge: { ...value.custom_skip_judge, command_prefixes: [...value.custom_skip_judge.command_prefixes, p] } }); };
  const delCP = (p: string) => patch({ custom_skip_judge: { ...value.custom_skip_judge, command_prefixes: value.custom_skip_judge.command_prefixes.filter((x: string) => x !== p) } });

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:"var(--sp-xl)" }}>

      {/* 1 — Judge Toggle */}
      <div style={{
        padding:"var(--sp-lg)", borderRadius:"var(--radius-md)", transition:"all 0.3s ease",
        background: judgeOn ? "linear-gradient(135deg,rgba(167,139,250,0.08),rgba(0,217,146,0.05))" : "rgba(248,113,113,0.05)",
        border: `1.5px solid ${judgeOn ? "rgba(167,139,250,0.3)" : "rgba(248,113,113,0.2)"}`,
      }}>
        <div style={{ display:"flex", alignItems:"flex-start", gap:"var(--sp-lg)" }}>
          <div style={{ width:42, height:42, borderRadius:"50%", flexShrink:0, display:"flex", alignItems:"center", justifyContent:"center",
            background: judgeOn ? "rgba(167,139,250,0.15)" : "rgba(248,113,113,0.1)",
            border: `1.5px solid ${judgeOn ? "rgba(167,139,250,0.4)" : "rgba(248,113,113,0.3)"}` }}>
            {judgeOn ? <Shield size={20} color="#a78bfa" /> : <ShieldOff size={20} color="#f87171" />}
          </div>
          <div style={{ flex:1 }}>
            <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:4 }}>
              <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                <span className="body-sm-strong">AI Safety Judge</span>
                <span style={{ fontSize:10, padding:"2px 8px", borderRadius:10, fontWeight:700,
                  background: judgeOn ? "rgba(167,139,250,0.2)" : "rgba(248,113,113,0.15)",
                  color: judgeOn ? "#a78bfa" : "#f87171",
                  border: `1px solid ${judgeOn ? "rgba(167,139,250,0.4)" : "rgba(248,113,113,0.3)"}` }}>
                  {judgeOn ? "ACTIVE" : "DISABLED"}
                </span>
              </div>
              <button type="button" onClick={() => patch({ enable_judge: !judgeOn })}
                aria-label={judgeOn ? "Disable Judge" : "Enable Judge"}
                style={{ position:"relative", width:44, height:24, borderRadius:12, background: judgeOn ? "#a78bfa" : "var(--color-hairline)", border:"none", cursor:"pointer", transition:"background 0.2s", flexShrink:0 }}>
                <span style={{ position:"absolute", top:3, left: judgeOn ? 23 : 3, width:18, height:18, borderRadius:"50%", background:"white", transition:"left 0.2s", boxShadow:"0 1px 4px rgba(0,0,0,0.3)" }} />
              </button>
            </div>
            <p className="caption" style={{ margin:0 }}>
              {judgeOn
                ? "?? An AI model evaluates each action's safety. Safe operations execute instantly; risky ones escalate to you."
                : "? Judge LLM is offline — zero evaluation latency & token cost. Configure fallback for ?? Judge actions below."}
            </p>
            {!judgeOn && (
              <div style={{ marginTop:"var(--sp-md)" }}>
                <span className="caption" style={{ display:"block", marginBottom:6 }}>When Judge is OFF, treat <strong>?? Judge</strong> actions as:</span>
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
                        {fb==="allow" ? "?? Auto-Allow (Autonomy)" : "?? Always Ask (Strict)"}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 2 — Quick Presets */}
      <div>
        <div style={{ display:"flex", alignItems:"center", gap:6, marginBottom:"var(--sp-sm)" }}>
          <Zap size={13} color="var(--color-primary)" />
          <span className="body-sm-strong" style={{ fontSize:12 }}>Quick Presets</span>
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

      {/* 3 — Action Permissions Grid */}
      <div>
        <div style={{ display:"flex", alignItems:"center", gap:6, marginBottom:"var(--sp-md)" }}>
          <Cpu size={13} color="var(--color-primary)" />
          <span className="body-sm-strong" style={{ fontSize:12 }}>Action Permissions</span>
          {!judgeOn && <span style={{ fontSize:10, color:"var(--color-mute)" }}>(?? Judge option hidden)</span>}
        </div>
        <div style={{ display:"flex", flexDirection:"column", gap:"var(--sp-sm)" }}>
          {CATEGORIES.map(({ key, label, desc, Icon }) => (
            <div key={key} style={{ padding:"var(--sp-md) var(--sp-lg)", borderRadius:"var(--radius-sm)", background:"var(--color-canvas-raised)", border:"1px solid var(--color-hairline)", display:"flex", flexDirection:"column", gap:"var(--sp-xs)" }}>
              <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", gap:"var(--sp-sm)", flexWrap:"wrap" }}>
                <div style={{ display:"flex", alignItems:"center", gap:"var(--sp-sm)" }}>
                  <div style={{ width:28, height:28, borderRadius:6, flexShrink:0, background:"var(--color-canvas-sunken)", display:"flex", alignItems:"center", justifyContent:"center" }}>
                    <Icon size={13} color="var(--color-mute)" />
                  </div>
                  <div>
                    <div className="body-sm-strong" style={{ fontSize:12 }}>{label}</div>
                    <button type="button" onClick={() => setTooltipCat(tooltipCat===key ? null : key)}
                      style={{ background:"none", border:"none", padding:0, cursor:"pointer", display:"flex", alignItems:"center", gap:3, color:"var(--color-mute)", fontSize:10 }}>
                      <Info size={9} /><span style={{ fontFamily:"monospace" }}>{desc.length>45 ? desc.slice(0,45)+"…" : desc}</span>
                    </button>
                  </div>
                </div>
                <PillGroup value={value.categories[key] || "allow"} onChange={l => setCategory(key, l)} noJudge={!judgeOn} />
              </div>
              {tooltipCat===key && (
                <div style={{ padding:"var(--sp-sm) var(--sp-md)", background:"var(--color-canvas-sunken)", borderRadius:"var(--radius-xs)", border:"1px solid var(--color-hairline)", fontSize:11, color:"var(--color-mute)", fontFamily:"monospace" }}>
                  {CATEGORIES.find(c=>c.key===key)?.tools}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 4 — Skip-Judge Whitelist */}
      {judgeOn && (
        <div>
          <div style={{ display:"flex", alignItems:"center", gap:6, marginBottom:"var(--sp-sm)" }}>
            <Zap size={13} color="#fbbf24" />
            <span className="body-sm-strong" style={{ fontSize:12 }}>Skip-Judge Whitelist</span>
            <span className="caption" style={{ fontSize:10, color:"var(--color-mute)" }}>— matching paths/commands execute instantly</span>
          </div>
          <div style={{ display:"flex", flexDirection:"column", gap:"var(--sp-md)" }}>
            <div>
              <label className="caption" style={{ display:"block", marginBottom:4 }}>?? Safe File Patterns <span style={{ color:"var(--color-mute)", fontSize:10 }}>(glob, press Enter to add)</span></label>
              <ChipInput chips={value.custom_skip_judge.file_patterns} placeholder="*.md, docs/**, .carole/**" onAdd={addFP} onRemove={delFP} />
            </div>
            <div>
              <label className="caption" style={{ display:"block", marginBottom:4 }}>? Safe Command Prefixes <span style={{ color:"var(--color-mute)", fontSize:10 }}>(press Enter to add)</span></label>
              <ChipInput chips={value.custom_skip_judge.command_prefixes} placeholder="git status, npm test, pytest" onAdd={addCP} onRemove={delCP} />
            </div>
          </div>
        </div>
      )}

      {/* 5 — Granular Tool Overrides */}
      <div>
        <button type="button" onClick={() => setShowOverrides(v=>!v)}
          style={{ display:"flex", alignItems:"center", gap:"var(--sp-sm)", background:"none", border:"none", cursor:"pointer", color:"var(--color-body)", padding:0, width:"100%", textAlign:"left" }}>
          <div style={{ display:"flex", alignItems:"center", gap:6, flex:1 }}>
            {showOverrides ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            <span className="body-sm-strong" style={{ fontSize:12 }}>Granular Tool Overrides</span>
            {hasOverrides && (
              <span style={{ fontSize:10, padding:"1px 7px", borderRadius:10, fontWeight:700, background:"rgba(251,191,36,0.15)", color:"#fbbf24", border:"1px solid rgba(251,191,36,0.3)" }}>
                {Object.keys(value.overrides).length} active
              </span>
            )}
          </div>
          <span className="caption" style={{ fontSize:10 }}>Per-tool permissions override category settings</span>
        </button>
        {showOverrides && (
          <div style={{ marginTop:"var(--sp-md)", padding:"var(--sp-lg)", borderRadius:"var(--radius-sm)", border:"1px solid var(--color-hairline)", background:"var(--color-canvas-raised)" }}>
            <input className="input" style={{ marginBottom:"var(--sp-md)", fontSize:12 }} placeholder="Search tools…"
              value={overrideSearch} onChange={e => setOverrideSearch(e.target.value)} />
            <div style={{ display:"flex", flexDirection:"column", gap:"var(--sp-sm)", maxHeight:300, overflowY:"auto" }}>
              {filteredTools.map(tool => {
                const ov = value.overrides[tool] as PermissionLevel|undefined;
                return (
                  <div key={tool} style={{ display:"flex", alignItems:"center", justifyContent:"space-between", gap:"var(--sp-sm)", padding:"var(--sp-sm) var(--sp-md)", borderRadius:"var(--radius-xs)", background: ov ? "rgba(251,191,36,0.04)" : "transparent", border:`1px solid ${ov ? "rgba(251,191,36,0.2)" : "transparent"}` }}>
                    <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                      <code style={{ fontSize:11 }}>{tool}</code>
                      {ov && <span style={{ fontSize:10, color:"var(--color-mute)" }}>{PERM_CFG[ov].emoji} overriding</span>}
                    </div>
                    <div style={{ display:"flex", gap:4, alignItems:"center" }}>
                      {(["allow","judge","always_ask","block"] as PermissionLevel[]).map(l => {
                        if (l==="judge"&&!judgeOn) return null;
                        return <Pill key={l} level={l} active={ov===l} small onClick={() => setOverride(tool, ov===l ? null : l)} />;
                      })}
                      {ov && (
                        <button type="button" onClick={() => setOverride(tool,null)} title="Clear override"
                          style={{ padding:"2px 6px", fontSize:10, background:"none", border:"1px solid var(--color-hairline)", borderRadius:6, color:"var(--color-mute)", cursor:"pointer" }}>
                          <X size={9} />
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

