import React, { useState, useEffect, useCallback, useRef } from "react";
import { Folder, ChevronRight, ChevronDown, RefreshCw, X, Terminal as TerminalIcon, Maximize2, Minimize2, Search, GitBranch, LayoutList, Activity, Eye, Pencil, RefreshCcwDot, Play, ChevronsUpDown, History, Filter, Plus } from "lucide-react";
import { PanelGroup, Panel, PanelResizeHandle } from "react-resizable-panels";
import { api } from "@/hooks/useApi";
import Editor from "@monaco-editor/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import TerminalPanel from "./TerminalPanel";
import GitPanel from "./GitPanel";
import SearchPanel from "./SearchPanel";
import ActivityLogPanel from "./ActivityLogPanel";
import Modal from "./Modal";
import { useToast } from "@/hooks/useToast";

function getLanguageFromPath(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase();
  const MAP: Record<string,string> = { ts:"typescript",tsx:"typescript",js:"javascript",jsx:"javascript",py:"python",json:"json",html:"html",css:"css",scss:"scss",sass:"scss",md:"markdown",yml:"yaml",yaml:"yaml",sh:"shell",bash:"shell",rs:"rust",go:"go",java:"java",c:"cpp",cpp:"cpp",h:"cpp",hpp:"cpp",sql:"sql",toml:"toml",xml:"xml" };
  return (ext && MAP[ext]) || "plaintext";
}

function getFileIcon(name: string, isDir = false): string {
  if (isDir) return "📁";
  const lower = name.toLowerCase(); const ext = lower.split(".").pop() || "";
  if (lower==="dockerfile") return "🐳";
  if (lower===".gitignore"||lower===".gitattributes") return "🙈";
  if (lower===".env"||lower.startsWith(".env.")) return "🔑";
  if (lower==="readme.md") return "📖";
  if (lower==="package.json"||lower==="package-lock.json") return "📦";
  if (lower==="tsconfig.json"||lower==="jsconfig.json") return "⚙️";
  if (lower==="requirements.txt") return "🐍";
  if (lower==="makefile") return "🔨";
  const M: Record<string,string> = { py:"🐍",ts:"📘",tsx:"⚛️",js:"📜",jsx:"⚛️",json:"📋",md:"📝",yml:"⚙️",yaml:"⚙️",sh:"🖥️",bash:"🖥️",css:"🎨",scss:"🎨",html:"🌐",rs:"🦀",go:"🔵",java:"☕",rb:"💎",php:"🐘",sql:"🗄️",toml:"⚙️",xml:"🔖",lock:"🔒",env:"🔑",png:"🖼️",jpg:"🖼️",jpeg:"🖼️",svg:"🖼️",pdf:"📕",txt:"📄",csv:"📊",zip:"📦",tar:"📦",gz:"📦",c:"⚙️",cpp:"⚙️",h:"⚙️",hpp:"⚙️" };
  return M[ext] || "📄";
}

const EXEC_EXTS = new Set(["py","js","ts","sh","bash","rb","php"]);
function isExecutable(path: string) { return EXEC_EXTS.has(path.split(".").pop()?.toLowerCase()||""); }
const isMarkdownPath = (p: string) => /\.(md|markdown|txt)$/i.test(p);

interface FileItem { name:string; is_dir:boolean; size:number; path:string; }
interface FileExplorerPanelProps { onClose?:()=>void; projectId?:string; teamId?:string; lastFileChange?:{path:string;after_content?:string;action?:string;sender_name?:string;_seq?:number}|null; pendingOpenFile?:string|null; onPendingOpenConsumed?:()=>void; }
interface ContextMenuState { x:number; y:number; path:string; isDir:boolean; }
interface OpenFile { path:string; content:string; isDirty:boolean; staleRemote?:{content:string;sender:string}|null; }
interface TerminalTab { id:string; label:string; cmd:{cmd:string;ts:number}|null; }

function Breadcrumb({ path }:{path:string}) {
  const parts = path.split("/").filter(Boolean);
  return (
    <div style={{display:"flex",alignItems:"center",gap:2,fontFamily:"var(--font-mono)",fontSize:11,color:"var(--color-mute)",overflow:"hidden",flexShrink:1,minWidth:0}}>
      {parts.map((part,i)=>{
        const isLast=i===parts.length-1;
        return (<React.Fragment key={i}>{i>0&&<span style={{opacity:0.4,flexShrink:0}}>/</span>}<span style={{color:isLast?"var(--color-body)":"var(--color-mute)",whiteSpace:"nowrap",flexShrink:isLast?1:0,overflow:"hidden",textOverflow:"ellipsis"}}>{part}</span></React.Fragment>);
      })}
    </div>
  );
}

function FileHistoryPanel({filePath,projectId,onRestored}:{filePath:string;projectId?:string;onRestored:()=>void}) {
  const [history,setHistory]=useState<any[]>([]); const [loading,setLoading]=useState(false); const [restoring,setRestoring]=useState<string|null>(null); const {addToast}=useToast();
  useEffect(()=>{ if(!filePath)return; setLoading(true); (api as any).getFileHistory?.(filePath,projectId).then((d:any[])=>setHistory(d)).catch(()=>setHistory([])).finally(()=>setLoading(false)); },[filePath,projectId]);
  const restore=async(id:string)=>{ setRestoring(id); try{ await (api as any).restoreFileBackup?.(id,projectId); addToast({type:"success",message:"Restored!"}); onRestored(); }catch(e){addToast({type:"error",message:`Restore failed: ${(e as Error).message}`});} finally{setRestoring(null);}};
  if(loading) return <div className="body-sm text-mute" style={{padding:16}}>Loading…</div>;
  if(!history.length) return <div className="body-sm" style={{color:"var(--color-mute)",padding:16,fontStyle:"italic"}}>No history.</div>;
  return (<div style={{flex:1,overflowY:"auto"}}>{history.map((e:any)=>(<div key={e.id} style={{padding:"8px 12px",borderBottom:"1px solid var(--color-hairline)",display:"flex",alignItems:"center",justifyContent:"space-between",gap:8}}><div style={{minWidth:0}}><div className="body-sm" style={{fontSize:12}}>{e.operation||"modified"}</div><div className="caption" style={{color:"var(--color-mute)",fontSize:11}}>{e.created_at?new Date(e.created_at).toLocaleString():"Unknown"}</div></div>{e.has_content&&<button className="btn btn-sm btn-ghost" style={{fontSize:11,padding:"2px 8px",flexShrink:0}} onClick={()=>restore(e.id)} disabled={restoring===e.id}>{restoring===e.id?"…":"↩ Restore"}</button>}</div>))}</div>);
}

function ContextMenuItem({children,onClick,style}:{children:React.ReactNode;onClick:()=>void;style?:React.CSSProperties}) {
  return <div onClick={onClick} style={{padding:"5px 14px",cursor:"pointer",fontSize:"12px",display:"flex",alignItems:"center",gap:6,...style}} className="hover:bg-gray-800 transition-colors">{children}</div>;
}

export default function FileExplorerPanel({onClose,projectId,teamId,lastFileChange,pendingOpenFile,onPendingOpenConsumed}:FileExplorerPanelProps) {
  const {addToast}=useToast();
  const [activeLeftTab,setActiveLeftTab]=useState<"explorer"|"search"|"git"|"activity"|"history">("explorer");
  const [isFullScreen,setIsFullScreen]=useState(false);
  const [openFiles,setOpenFiles]=useState<OpenFile[]>([]);
  const [activeFilePath,setActiveFilePath]=useState<string|null>(null);
  const [loadingContent,setLoadingContent]=useState(false);
  const [saving,setSaving]=useState(false);
  const [viewMode,setViewMode]=useState<"preview"|"edit">("preview");
  const [refreshKey,setRefreshKey]=useState(0);
  const [contextMenu,setContextMenu]=useState<ContextMenuState|null>(null);
  const [filterText,setFilterText]=useState("");
  const [collapseSignal,setCollapseSignal]=useState(0);
  const [showTerminal,setShowTerminal]=useState(false);
  const [terminalTabs,setTerminalTabs]=useState<TerminalTab[]>([{id:"t1",label:"Terminal 1",cmd:null}]);
  const [activeTerminalTabId,setActiveTerminalTabId]=useState("t1");
  const [projectName,setProjectName]=useState<string|null>(null);
  const dragRef=useRef<string|null>(null);
  const [dialog,setDialog]=useState<{visible:boolean;type:"delete"|"rename"|"new_file"|"new_folder";path:string;inputValue:string}>({visible:false,type:"delete",path:"",inputValue:""});

  useEffect(()=>{ if(projectId){api.getProject(projectId).then(r=>setProjectName(r.name)).catch(()=>setProjectName("project"));}else{setProjectName(null);} },[projectId]);
  useEffect(()=>{ const close=()=>setContextMenu(null); document.addEventListener("click",close); return()=>document.removeEventListener("click",close); },[]);
  useEffect(()=>{ if(!lastFileChange?.path)return; const rp=lastFileChange.path.replace(/\\/g,"/"); const nc=lastFileChange.after_content??""; const sender=lastFileChange.sender_name||"Agent"; setOpenFiles(prev=>prev.map(f=>{ if(f.path.replace(/\\/g,"/")!==rp)return f; if(f.isDirty)return{...f,staleRemote:{content:nc,sender}}; return{...f,content:nc,isDirty:false,staleRemote:null}; })); setRefreshKey(k=>k+1); },[lastFileChange]);
  useEffect(()=>{ if(!pendingOpenFile)return; void openFile(pendingOpenFile); onPendingOpenConsumed?.(); },[pendingOpenFile]);
  useEffect(()=>{ const h=(e:BeforeUnloadEvent)=>{if(openFiles.some(f=>f.isDirty)){e.preventDefault();e.returnValue="";}}; window.addEventListener("beforeunload",h); return()=>window.removeEventListener("beforeunload",h); },[openFiles]);
  useEffect(()=>{ const h=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key==="s"){e.preventDefault();handleSave();}}; window.addEventListener("keydown",h); return()=>window.removeEventListener("keydown",h); },[activeFilePath,openFiles,projectId]);

  const openFile=async(path:string)=>{ const ex=openFiles.find(f=>f.path===path); if(ex){setActiveFilePath(path);setViewMode(isMarkdownPath(path)?"preview":"edit");return;} setLoadingContent(true); try{ const res=await api.readFile(path,projectId); setOpenFiles(prev=>prev.some(f=>f.path===path)?prev:[...prev,{path,content:res.content,isDirty:false}]); setActiveFilePath(path); setViewMode(isMarkdownPath(path)?"preview":"edit"); }catch(e){addToast({type:"error",message:`Error: ${(e as Error).message}`});}finally{setLoadingContent(false);} };
  const applyStaleRemote=(path:string)=>{ setOpenFiles(prev=>prev.map(f=>f.path!==path||!f.staleRemote?f:{...f,content:f.staleRemote.content,isDirty:false,staleRemote:null})); };
  const closeFile=(path:string,e?:React.MouseEvent)=>{ if(e)e.stopPropagation(); setOpenFiles(prev=>{const f=prev.filter(x=>x.path!==path);if(activeFilePath===path)setActiveFilePath(f.length?f[f.length-1].path:null);return f;}); };
  const updateFileContent=(path:string,val:string)=>{ setOpenFiles(prev=>prev.map(f=>f.path===path?{...f,content:val,isDirty:true}:f)); };
  const handleSave=useCallback(async()=>{ if(!activeFilePath)return; const file=openFiles.find(f=>f.path===activeFilePath); if(!file||!file.isDirty)return; setSaving(true); try{await api.writeFile(file.path,file.content,projectId);setOpenFiles(prev=>prev.map(f=>f.path===activeFilePath?{...f,isDirty:false}:f));setRefreshKey(k=>k+1);}catch(e){addToast({type:"error",message:`Save failed: ${(e as Error).message}`});}finally{setSaving(false);} },[activeFilePath,openFiles,projectId]);

  const handleDelete=(p:string)=>setDialog({visible:true,type:"delete",path:p,inputValue:""});
  const handleRename=(p:string)=>setDialog({visible:true,type:"rename",path:p,inputValue:p});
  const handleCreateFile=(p:string)=>setDialog({visible:true,type:"new_file",path:p,inputValue:""});
  const handleCreateFolder=(p:string)=>setDialog({visible:true,type:"new_folder",path:p,inputValue:""});

  const submitDialog=async(e:React.FormEvent)=>{ e.preventDefault(); const{type,path,inputValue}=dialog; setDialog({...dialog,visible:false});
    if(type==="delete"){try{await api.deleteFile(path,projectId);setOpenFiles(prev=>prev.filter(f=>!(f.path===path||f.path.startsWith(path+"/"))));if(activeFilePath===path||activeFilePath?.startsWith(path+"/"))setActiveFilePath(null);setRefreshKey(k=>k+1);}catch(e){addToast({type:"error",message:`Delete failed: ${(e as Error).message}`});}}
    else if(type==="rename"&&inputValue&&inputValue!==path){try{await api.renameFile(path,inputValue,projectId);setOpenFiles(prev=>prev.map(f=>{if(f.path===path)return{...f,path:inputValue};if(f.path.startsWith(path+"/"))return{...f,path:f.path.replace(path,inputValue)};return f;}));if(activeFilePath===path)setActiveFilePath(inputValue);else if(activeFilePath?.startsWith(path+"/"))setActiveFilePath(activeFilePath.replace(path,inputValue));setRefreshKey(k=>k+1);}catch(e){addToast({type:"error",message:`Rename failed: ${(e as Error).message}`});}}
    else if(type==="new_file"&&inputValue){const fp=path==="."?inputValue:`${path}/${inputValue}`;try{await api.writeFile(fp,"",projectId);void openFile(fp);setRefreshKey(k=>k+1);}catch(e){addToast({type:"error",message:`Create failed: ${(e as Error).message}`});}}
    else if(type==="new_folder"&&inputValue){const fp=path==="."?inputValue:`${path}/${inputValue}`;try{await api.createFolder(fp,projectId);setRefreshKey(k=>k+1);}catch(e){addToast({type:"error",message:`Folder failed: ${(e as Error).message}`});}} };

  const handleExecuteFile=(path:string)=>{ const ext=path.split(".").pop()?.toLowerCase(); let cmd=""; if(ext==="js"||ext==="ts")cmd=`node ${path}`; else if(ext==="py")cmd=`python ${path}`; else if(ext==="sh"||ext==="bash")cmd=`bash ${path}`; else if(ext==="rb")cmd=`ruby ${path}`; else if(ext==="php")cmd=`php ${path}`; else{addToast({type:"warning",message:`Not executable: .${ext}`});return;} setShowTerminal(true); setTerminalTabs(prev=>prev.map(t=>t.id===activeTerminalTabId?{...t,cmd:{cmd,ts:Date.now()}}:t)); };
  const addTerminalTab=()=>{ const id=`t${Date.now()}`; setTerminalTabs(prev=>[...prev,{id,label:`Terminal ${prev.length+1}`,cmd:null}]); setActiveTerminalTabId(id); setShowTerminal(true); };
  const closeTerminalTab=(id:string,e:React.MouseEvent)=>{ e.stopPropagation(); setTerminalTabs(prev=>{const f=prev.filter(t=>t.id!==id);if(!f.length){setShowTerminal(false);return[{id:"t1",label:"Terminal 1",cmd:null}];}if(activeTerminalTabId===id)setActiveTerminalTabId(f[f.length-1].id);return f;}); };
  const handleContextMenu=(e:React.MouseEvent,path:string,isDir:boolean)=>{e.preventDefault();setContextMenu({x:e.clientX,y:e.clientY,path,isDir});};
  const copyRelPath=(path:string)=>{ navigator.clipboard.writeText(path).then(()=>addToast({type:"success",message:"Path copied!"})); };
  const openTerminalHere=(folder:string)=>{ setShowTerminal(true); setTerminalTabs(prev=>prev.map(t=>t.id===activeTerminalTabId?{...t,cmd:{cmd:`cd ${folder}`,ts:Date.now()}}:t)); };
  const handleDrop=async(targetDir:string)=>{ if(!dragRef.current||dragRef.current===targetDir)return; const src=dragRef.current; const fname=src.split("/").pop()||src; const dest=targetDir==="."?fname:`${targetDir}/${fname}`; if(dest===src)return; try{await api.renameFile(src,dest,projectId);setOpenFiles(prev=>prev.map(f=>f.path===src?{...f,path:dest}:f));if(activeFilePath===src)setActiveFilePath(dest);setRefreshKey(k=>k+1);addToast({type:"success",message:`Moved to ${dest}`});}catch(e){addToast({type:"error",message:`Move failed: ${(e as Error).message}`});}dragRef.current=null; };

  const activeFile=openFiles.find(f=>f.path===activeFilePath);
  const activeTermTab=terminalTabs.find(t=>t.id===activeTerminalTabId);
  const containerStyle:React.CSSProperties=isFullScreen?{position:"fixed",top:0,left:0,right:0,bottom:0,zIndex:9999,display:"flex",background:"var(--color-canvas)",width:"100%",maxWidth:"none"}:{display:"flex",height:"100%",borderLeft:"1px solid var(--border-subtle)",background:"var(--bg-app)",width:"100%",maxWidth:800};
  const TAB_BTNS=[{key:"explorer",icon:<LayoutList size={20}/>,title:"Explorer"},{key:"search",icon:<Search size={20}/>,title:"Search"},{key:"git",icon:<GitBranch size={20}/>,title:"Source Control"},{key:"activity",icon:<Activity size={20}/>,title:"Activity Log"},{key:"history",icon:<History size={20}/>,title:"File History"}];

  return (
    <div style={containerStyle}>
      <div style={{width:48,borderRight:"1px solid var(--color-hairline)",background:"var(--bg-glass-card)",display:"flex",flexDirection:"column",alignItems:"center",paddingTop:8,gap:8,flexShrink:0}}>
        {TAB_BTNS.map(({key,icon,title})=>(<button key={key} onClick={()=>setActiveLeftTab(key as any)} title={title} style={{padding:10,borderRadius:"var(--radius-sm)",color:activeLeftTab===key?"var(--color-primary)":"var(--color-body)",background:activeLeftTab===key?"var(--color-primary-glow-sm)":"transparent"}} className="hover:text-white transition-colors">{icon}</button>))}
      </div>
      <PanelGroup direction="horizontal" autoSaveId="fe-h">
        <Panel id="fe-left" order={1} defaultSize={25} minSize={15} maxSize={40} style={{display:"flex",flexDirection:"column",background:"var(--bg-surface)",borderRight:"1px solid var(--border-subtle)"}}>
          {activeLeftTab==="explorer"&&(<>
            <div style={{padding:"var(--sp-sm) var(--sp-md)",borderBottom:"1px solid var(--color-hairline)",display:"flex",justifyContent:"space-between",alignItems:"center"}}>
              <span className="body-sm-strong" style={{textTransform:"uppercase",fontSize:"11px",letterSpacing:"0.5px",color:"var(--color-mute)"}}>Explorer</span>
              <div style={{display:"flex",gap:"2px"}}>
                <button className="btn btn-ghost btn-icon btn-sm" onClick={()=>setCollapseSignal(s=>s+1)} title="Collapse All"><ChevronsUpDown size={13}/></button>
                <button className="btn btn-ghost btn-icon btn-sm" onClick={()=>setRefreshKey(k=>k+1)} title="Refresh"><RefreshCw size={13}/></button>
                <button className="btn btn-ghost btn-icon btn-sm" onClick={()=>setIsFullScreen(!isFullScreen)} title={isFullScreen?"Restore":"Full Screen"}>{isFullScreen?<Minimize2 size={13}/>:<Maximize2 size={13}/>}</button>
                {onClose&&<button className="btn btn-ghost btn-icon btn-sm" onClick={onClose} title="Close"><X size={13}/></button>}
              </div>
            </div>
            <div style={{padding:"4px 8px",borderBottom:"1px solid var(--color-hairline)"}}>
              <div style={{display:"flex",alignItems:"center",gap:6,background:"var(--bg-glass-panel)",borderRadius:4,padding:"2px 8px"}}>
                <Filter size={11} color="var(--color-mute)" style={{flexShrink:0}}/>
                <input placeholder="Filter files…" value={filterText} onChange={e=>setFilterText(e.target.value)} style={{flex:1,background:"transparent",border:"none",outline:"none",fontSize:12,color:"var(--color-body)"}}/>
                {filterText&&<button onClick={()=>setFilterText("")} style={{background:"none",border:"none",cursor:"pointer",color:"var(--color-mute)",padding:0}}><X size={10}/></button>}
              </div>
            </div>
            <div style={{flex:1,overflowY:"auto",padding:"4px 0"}}>
              {projectId?(<>
                <div style={{display:"flex",alignItems:"center",padding:"2px 8px",userSelect:"none"}}>
                  <span style={{width:16,display:"flex",justifyContent:"center",marginRight:2}}><ChevronDown size={14} color="var(--color-mute)"/></span>
                  <span style={{marginRight:6,fontSize:14}}>📁</span>
                  <span className="body-sm truncate" style={{fontSize:"13px",fontWeight:"bold"}}>workspaces</span>
                </div>
                <div style={{paddingLeft:12}}>
                  <TreeNode path="." name={projectName||"loading…"} isDir={true} onFileSelect={openFile} selectedPath={activeFilePath} defaultExpanded={true} projectId={projectId} refreshKey={refreshKey} onContextMenu={handleContextMenu} filterText={filterText} collapseSignal={collapseSignal} dragRef={dragRef} onDrop={handleDrop}/>
                </div>
              </>):(
                <div style={{display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",padding:"48px 16px",textAlign:"center",color:"var(--color-mute)"}}>
                  <Folder size={32} style={{marginBottom:12,opacity:0.4}}/>
                  <div className="body-sm-strong" style={{marginBottom:8,color:"var(--color-body)"}}>No Project Selected</div>
                  <div className="caption" style={{lineHeight:1.5}}>Please create or select a project from the left sidebar to view its workspace files.</div>
                </div>
              )}
            </div>
          </>)}
          {activeLeftTab==="search"&&<SearchPanel projectId={projectId} onFileSelect={openFile}/>}
          {activeLeftTab==="git"&&<GitPanel projectId={projectId}/>}
          {activeLeftTab==="activity"&&teamId&&<ActivityLogPanel teamId={teamId}/>}
          {activeLeftTab==="history"&&(<div style={{flex:1,display:"flex",flexDirection:"column"}}>
            <div style={{padding:"var(--sp-sm) var(--sp-md)",borderBottom:"1px solid var(--color-hairline)"}}><span className="body-sm-strong" style={{textTransform:"uppercase",fontSize:"11px",color:"var(--color-mute)"}}>File History</span></div>
            {activeFilePath?<FileHistoryPanel filePath={activeFilePath} projectId={projectId} onRestored={()=>{void openFile(activeFilePath);setRefreshKey(k=>k+1);}}/>:<div className="body-sm" style={{color:"var(--color-mute)",padding:16,fontStyle:"italic"}}>Open a file to see history.</div>}
          </div>)}
        </Panel>
        <PanelResizeHandle className="resize-handle" style={{width:"4px",cursor:"col-resize",background:"var(--border-subtle)",flexShrink:0}}/>
        <Panel id="fe-right" order={2} style={{display:"flex",flexDirection:"column",minWidth:0,background:"transparent"}}>
          {openFiles.length>0?(<>
            <div style={{display:"flex",background:"var(--bg-glass-card)",overflowX:"auto",overflowY:"hidden",height:35,flexShrink:0}} className="scrollbar-hide">
              {openFiles.map(file=>{
                const isActive=file.path===activeFilePath;
                const fname=file.path.split("/").pop()||file.path;
                return (<div key={file.path} onClick={()=>setActiveFilePath(file.path)} style={{display:"flex",alignItems:"center",padding:"0 8px 0 12px",gap:4,background:isActive?"var(--bg-glass-panel)":"transparent",color:isActive?"var(--color-primary)":"var(--color-mute)",borderRight:"1px solid var(--color-hairline)",borderTop:isActive?"1px solid var(--color-primary)":"1px solid transparent",cursor:"pointer",minWidth:100,maxWidth:180,height:"100%",userSelect:"none"}} className="hover:bg-[#2a2d2e] transition-colors">
                  <span style={{fontSize:12,flexShrink:0}}>{getFileIcon(fname)}</span>
                  <span className="truncate body-sm font-mono" style={{fontSize:"12px",flex:1}}>{fname}</span>
                  {file.isDirty&&<div style={{width:7,height:7,borderRadius:"50%",background:"#fff",flexShrink:0}}/>}
                  <button onClick={e=>closeFile(file.path,e)} style={{padding:2,borderRadius:3,flexShrink:0}} className="hover:bg-gray-600 text-transparent hover:text-white"><X size={11}/></button>
                </div>);
              })}
            </div>
            {activeFile&&(<div style={{padding:"3px 12px",borderBottom:"1px solid var(--color-hairline)",background:"var(--bg-glass-panel)",display:"flex",alignItems:"center",justifyContent:"space-between",flexShrink:0,gap:8}}>
              <div style={{display:"flex",alignItems:"center",gap:6,minWidth:0,flex:1}}>
                <Breadcrumb path={activeFile.path}/>
                {isMarkdownPath(activeFile.path)&&(<div style={{display:"flex",gap:2,background:"var(--color-surface)",borderRadius:4,padding:2,flexShrink:0}}>
                  <button className="btn btn-sm" onClick={()=>setViewMode("preview")} style={{padding:"1px 7px",fontSize:11,background:viewMode==="preview"?"var(--color-primary)":"transparent",color:viewMode==="preview"?"#fff":"var(--color-body)",border:"none"}}><Eye size={11} className="mr-1"/>Preview</button>
                  <button className="btn btn-sm" onClick={()=>setViewMode("edit")} style={{padding:"1px 7px",fontSize:11,background:viewMode==="edit"?"var(--color-primary)":"transparent",color:viewMode==="edit"?"#fff":"var(--color-body)",border:"none"}}><Pencil size={11} className="mr-1"/>Edit</button>
                </div>)}
              </div>
              <div style={{display:"flex",alignItems:"center",gap:6,flexShrink:0}}>
                {isExecutable(activeFile.path)&&(<button onClick={()=>handleExecuteFile(activeFile.path)} style={{padding:"2px 8px",fontSize:11,background:"rgba(34,197,94,0.15)",color:"#4ade80",border:"1px solid rgba(74,222,128,0.3)",borderRadius:4,cursor:"pointer",display:"flex",alignItems:"center",gap:4}} title="Run"><Play size={11}/>Run</button>)}
                <button className={`btn btn-sm ${showTerminal?"btn-secondary":"btn-ghost"}`} onClick={()=>setShowTerminal(s=>!s)} style={{padding:"2px 8px",fontSize:11}}><TerminalIcon size={11} className="mr-1"/>Terminal</button>
                <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving||!activeFile.isDirty} style={{padding:"2px 8px",fontSize:11}}>{saving?"Saving…":"Save"}</button>
              </div>
            </div>)}
            {activeFile?.staleRemote&&(<div style={{padding:"5px 16px",borderBottom:"1px solid var(--color-hairline)",background:"rgba(234,179,8,0.12)",display:"flex",alignItems:"center",justifyContent:"space-between",gap:8,flexShrink:0}}>
              <span className="caption" style={{color:"#eab308"}}>⚠ {activeFile.staleRemote.sender} updated this file remotely.</span>
              <button className="btn btn-sm btn-secondary" onClick={()=>applyStaleRemote(activeFile.path)} style={{padding:"2px 8px",fontSize:11}}><RefreshCcwDot size={11} className="mr-1"/>Reload</button>
            </div>)}
            <div style={{flex:1,overflow:"hidden",display:"flex",flexDirection:"column"}}>
              {loadingContent?<div className="text-mute body-sm p-4">Loading…</div>:(
                <div style={{flex:1,display:"flex",flexDirection:"column",minHeight:0}}>
                  <PanelGroup direction="vertical" autoSaveId="fe-v">
                    <Panel defaultSize={showTerminal?60:100} minSize={20} style={{display:"flex",flexDirection:"column",overflow:"hidden",paddingTop:4}}>
                      {activeFile?(
                        isMarkdownPath(activeFile.path)&&viewMode==="preview"?(
                          <div style={{height:"100%",overflowY:"auto",padding:"8px 24px 32px"}} className="markdown-body">
                            {activeFile.content.trim()?<ReactMarkdown remarkPlugins={[remarkGfm]} components={{a:({node,...p})=><a {...p} target="_blank" rel="noopener noreferrer"/>}}>{activeFile.content}</ReactMarkdown>:<div className="body-sm" style={{color:"var(--color-mute)",fontStyle:"italic"}}>Empty — switch to Edit.</div>}
                          </div>
                        ):(
                          <Editor height="100%" language={getLanguageFromPath(activeFile.path)} theme="vs-dark" value={activeFile.content} onChange={v=>updateFileContent(activeFile.path,v||"")} options={{minimap:{enabled:true,maxColumn:80,renderCharacters:false},fontSize:13,fontFamily:"'JetBrains Mono','Fira Code',Consolas,monospace",wordWrap:"on",padding:{top:8,bottom:16},scrollBeyondLastLine:false,quickSuggestions:true,suggestOnTriggerCharacters:true,hover:{enabled:true,delay:500},renderWhitespace:"boundary",smoothScrolling:true} as any}/>
                        )
                      ):<div style={{flex:1,display:"flex",alignItems:"center",justifyContent:"center",color:"var(--color-mute)"}} className="body-sm">Select a file to view</div>}
                    </Panel>
                    {showTerminal&&(<>
                      <PanelResizeHandle className="resize-handle"/>
                      <Panel defaultSize={40} minSize={20} style={{display:"flex",flexDirection:"column",borderTop:"1px solid var(--color-hairline)",overflow:"hidden"}}>
                        <div style={{display:"flex",alignItems:"center",background:"var(--bg-glass-card)",borderBottom:"1px solid var(--color-hairline)",height:30,flexShrink:0}}>
                          {terminalTabs.map(tab=>(<div key={tab.id} onClick={()=>setActiveTerminalTabId(tab.id)} style={{display:"flex",alignItems:"center",gap:4,padding:"0 10px",height:"100%",cursor:"pointer",borderRight:"1px solid var(--color-hairline)",background:activeTerminalTabId===tab.id?"var(--bg-glass-panel)":"transparent",color:activeTerminalTabId===tab.id?"var(--color-body)":"var(--color-mute)",fontSize:12,userSelect:"none"}} className="hover:bg-gray-800 transition-colors"><TerminalIcon size={11}/><span>{tab.label}</span>{terminalTabs.length>1&&<button onClick={e=>closeTerminalTab(tab.id,e)} style={{background:"none",border:"none",cursor:"pointer",padding:"0 2px",color:"var(--color-mute)"}} className="hover:text-white"><X size={10}/></button>}</div>))}
                          <button onClick={addTerminalTab} title="New Terminal" style={{padding:"0 10px",height:"100%",background:"none",border:"none",cursor:"pointer",color:"var(--color-mute)"}} className="hover:text-white"><Plus size={12}/></button>
                          <div style={{flex:1}}/>
                          <button onClick={()=>setShowTerminal(false)} style={{padding:"0 8px",height:"100%",background:"none",border:"none",cursor:"pointer",color:"var(--color-mute)"}} className="hover:text-white"><X size={12}/></button>
                        </div>
                        {terminalTabs.map(tab=>(<div key={tab.id} style={{flex:1,display:activeTerminalTabId===tab.id?"flex":"none",flexDirection:"column",overflow:"hidden"}}><TerminalPanel projectId={projectId} onClose={()=>setShowTerminal(false)} triggerCommand={tab.cmd}/></div>))}
                      </Panel>
                    </>)}
                  </PanelGroup>
                </div>
              )}
            </div>
          </>):(
            <div style={{flex:1,display:"flex",flexDirection:"column"}}>
              <div style={{padding:"8px 16px",borderBottom:"1px solid var(--color-hairline)",background:"var(--bg-glass-panel)",display:"flex",alignItems:"center",justifyContent:"flex-end"}}>
                <button className={`btn btn-sm ${showTerminal?"btn-secondary":"btn-ghost"}`} onClick={()=>setShowTerminal(s=>!s)}><TerminalIcon size={13} className="mr-1"/>Terminal</button>
              </div>
              <div style={{flex:1,display:"flex",flexDirection:"column",minHeight:0}}>
                {!showTerminal?<div style={{flex:1,display:"flex",alignItems:"center",justifyContent:"center",color:"var(--color-mute)"}} className="body-sm">Select a file from the explorer</div>:<TerminalPanel projectId={projectId} onClose={()=>setShowTerminal(false)} triggerCommand={activeTermTab?.cmd??null}/>}
              </div>
            </div>
          )}
        </Panel>
      </PanelGroup>

      {contextMenu&&(<div style={{position:"fixed",top:contextMenu.y,left:contextMenu.x,background:"var(--color-surface)",border:"1px solid var(--color-hairline)",borderRadius:"6px",boxShadow:"0 8px 24px rgba(0,0,0,0.4)",padding:"4px 0",zIndex:9999,minWidth:"185px",display:"flex",flexDirection:"column"}} onClick={e=>e.stopPropagation()}>
        {contextMenu.isDir&&(<>
          <ContextMenuItem onClick={()=>{handleCreateFile(contextMenu.path);setContextMenu(null);}}>📄 New File</ContextMenuItem>
          <ContextMenuItem onClick={()=>{handleCreateFolder(contextMenu.path);setContextMenu(null);}}>📁 New Folder</ContextMenuItem>
          <ContextMenuItem onClick={()=>{openTerminalHere(contextMenu.path);setContextMenu(null);}}>🖥️ Open Terminal Here</ContextMenuItem>
          <div style={{height:"1px",background:"var(--color-hairline)",margin:"4px 0"}}/>
        </>)}
        {!contextMenu.isDir&&(<>
          <ContextMenuItem onClick={()=>{handleExecuteFile(contextMenu.path);setContextMenu(null);}}>▶ Run File</ContextMenuItem>
          <div style={{height:"1px",background:"var(--color-hairline)",margin:"4px 0"}}/>
        </>)}
        <ContextMenuItem onClick={()=>{handleRename(contextMenu.path);setContextMenu(null);}}>✏️ Rename</ContextMenuItem>
        <ContextMenuItem onClick={()=>{copyRelPath(contextMenu.path);setContextMenu(null);}}>📋 Copy Path</ContextMenuItem>
        <div style={{height:"1px",background:"var(--color-hairline)",margin:"4px 0"}}/>
        <ContextMenuItem onClick={()=>{handleDelete(contextMenu.path);setContextMenu(null);}} style={{color:"var(--color-error)"}}>🗑️ Delete</ContextMenuItem>
      </div>)}
      {dialog.visible&&(<Modal open={dialog.visible} onClose={()=>setDialog({...dialog,visible:false})} title={dialog.type==="delete"?"Delete Item":dialog.type==="rename"?"Rename Item":dialog.type==="new_file"?"New File":"New Folder"} maxWidth={400}>
        <form onSubmit={submitDialog} style={{display:"flex",flexDirection:"column",gap:"var(--sp-md)"}}>
          <p className="body-sm">{dialog.type==="delete"?`Delete "${dialog.path}"?`:dialog.type==="rename"?`Rename to:`:dialog.type==="new_file"?`New file in ${dialog.path}:`:`New folder in ${dialog.path}:`}</p>
          {dialog.type!=="delete"&&<input className="input" autoFocus value={dialog.inputValue} onChange={e=>setDialog({...dialog,inputValue:e.target.value})}/>}
          <div style={{display:"flex",justifyContent:"flex-end",gap:"var(--sp-sm)",marginTop:"var(--sp-md)"}}>
            <button type="button" className="btn btn-ghost btn-sm" onClick={()=>setDialog({...dialog,visible:false})}>Cancel</button>
            <button type="submit" className={`btn btn-sm ${dialog.type==="delete"?"btn-danger":"btn-primary"}`} disabled={dialog.type!=="delete"&&!dialog.inputValue.trim()}>{dialog.type==="delete"?"Delete":"Confirm"}</button>
          </div>
        </form>
      </Modal>)}
    </div>
  );
}

function TreeNode({path,name,isDir,onFileSelect,selectedPath,defaultExpanded=false,projectId,refreshKey,onContextMenu,filterText,collapseSignal,dragRef,onDrop}:{path:string;name:string;isDir:boolean;onFileSelect:(p:string)=>void;selectedPath:string|null;defaultExpanded?:boolean;projectId?:string;refreshKey:number;onContextMenu:(e:React.MouseEvent,p:string,d:boolean)=>void;filterText?:string;collapseSignal?:number;dragRef:React.MutableRefObject<string|null>;onDrop:(dir:string)=>void;}) {
  const [expanded,setExpanded]=useState(defaultExpanded);
  const [children,setChildren]=useState<FileItem[]>([]);
  const [loading,setLoading]=useState(false);
  const [isEditing,setIsEditing]=useState(false);
  const [editName,setEditName]=useState(name);
  const [isDragOver,setIsDragOver]=useState(false);
  const editRef=useRef<HTMLInputElement>(null);
  const {addToast}=useToast();

  const loadChildren=async()=>{ if(!isDir)return; setLoading(true); try{const items=await api.listFiles(path,projectId);items.sort((a,b)=>a.is_dir===b.is_dir?a.name.localeCompare(b.name):a.is_dir?-1:1);setChildren(items);}catch(err:any){if(err.status===404){setExpanded(false);setChildren([]);}else console.warn(`Failed:${path}`,err);}finally{setLoading(false);} };
  const toggleExpand=()=>{ if(!isDir){onFileSelect(path);return;} if(!expanded){setExpanded(true);loadChildren();}else setExpanded(false); };

  useEffect(()=>{if(expanded&&isDir)void loadChildren();},[refreshKey]);
  useEffect(()=>{if(defaultExpanded&&expanded&&isDir&&children.length===0)void loadChildren();},[]);
  useEffect(()=>{if((collapseSignal||0)>0&&!defaultExpanded)setExpanded(false);},[collapseSignal]);

  const commitRename=async()=>{ setIsEditing(false); const n=editName.trim(); if(!n||n===name)return; const parent=path.includes("/")?path.substring(0,path.lastIndexOf("/")):"." ; const np=parent==="."?n:`${parent}/${n}`; try{await api.renameFile(path,np,projectId);}catch(e){addToast({type:"error",message:`Rename failed: ${(e as Error).message}`});setEditName(name);} };

  const lf=(filterText||"").toLowerCase();
  if(lf&&!name.toLowerCase().includes(lf)&&!isDir)return null;
  const isSelected=path===selectedPath&&!isDir;
  const folderIcon=isDir?(expanded?"📂":"📁"):getFileIcon(name);

  return (
    <div>
      <div style={{display:"flex",alignItems:"center",padding:"2px 8px",background:isDragOver?"rgba(99,102,241,0.2)":isSelected?"var(--color-primary-glow-sm)":"transparent",color:isSelected?"var(--color-primary)":"var(--color-body)",cursor:"pointer",userSelect:"none",borderLeft:isSelected?"2px solid var(--color-primary)":"2px solid transparent"}}
        className="hover:bg-gray-800 transition-colors"
        onClick={toggleExpand}
        onContextMenu={e=>onContextMenu(e,path,isDir)}
        onDoubleClick={e=>{if(!isDir){e.stopPropagation();setIsEditing(true);setEditName(name);setTimeout(()=>editRef.current?.select(),50);}}}
        draggable={!defaultExpanded}
        onDragStart={e=>{dragRef.current=path;e.dataTransfer.effectAllowed="move";}}
        onDragEnd={()=>{dragRef.current=null;setIsDragOver(false);}}
        onDragOver={e=>{if(isDir){e.preventDefault();setIsDragOver(true);}}}
        onDragLeave={()=>setIsDragOver(false)}
        onDrop={e=>{e.preventDefault();setIsDragOver(false);if(isDir)onDrop(path);}}>
        <span style={{width:16,display:"flex",justifyContent:"center",marginRight:2,flexShrink:0}}>
          {isDir?(expanded?<ChevronDown size={13} color="var(--color-mute)"/>:<ChevronRight size={13} color="var(--color-mute)"/>):<span/>}
        </span>
        <span style={{marginRight:6,fontSize:13,flexShrink:0}}>{folderIcon}</span>
        {isEditing?(
          <input ref={editRef} value={editName} onChange={e=>setEditName(e.target.value)} onBlur={commitRename}
            onKeyDown={e=>{if(e.key==="Enter"){e.preventDefault();commitRename();}if(e.key==="Escape"){setIsEditing(false);setEditName(name);}}}
            onClick={e=>e.stopPropagation()}
            style={{flex:1,background:"var(--bg-glass-panel)",border:"1px solid var(--color-primary)",borderRadius:3,padding:"0 4px",fontSize:13,color:"var(--color-body)",outline:"none"}}/>
        ):<span className="body-sm truncate" style={{fontSize:"13px",flex:1}}>{name}</span>}
        {loading&&<RefreshCw size={10} className="animate-spin ml-1" style={{color:"var(--color-mute)",flexShrink:0}}/>}
      </div>
      {expanded&&isDir&&(
        <div style={{paddingLeft:12}}>
          {children.filter(c=>!lf||c.name.toLowerCase().includes(lf)||c.is_dir).map(child=>(
            <TreeNode key={child.path} path={child.path} name={child.name} isDir={child.is_dir} onFileSelect={onFileSelect} selectedPath={selectedPath} projectId={projectId} refreshKey={refreshKey} onContextMenu={onContextMenu} filterText={filterText} collapseSignal={collapseSignal} dragRef={dragRef} onDrop={onDrop}/>
          ))}
          {!children.length&&!loading&&<div style={{padding:"4px 28px",color:"var(--color-mute)",fontSize:"12px",fontStyle:"italic"}}>Empty</div>}
        </div>
      )}
    </div>
  );
}
