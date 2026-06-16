"use client";

import React, { useState, useEffect } from "react";
import { api } from "@/hooks/useApi";
import { GitBranch, RefreshCw, Check, AlertCircle, X, ChevronLeft } from "lucide-react";
import { DiffEditor } from "@monaco-editor/react";

interface GitPanelProps {
  projectId?: string;
  onClose?: () => void;
}

export default function GitPanel({ projectId, onClose }: GitPanelProps) {
  const [changes, setChanges] = useState<{ file: string; status: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [commitMessage, setCommitMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  // Diff View State
  const [selectedDiffFile, setSelectedDiffFile] = useState<string | null>(null);
  const [diffOriginal, setDiffOriginal] = useState<string>("");
  const [diffModified, setDiffModified] = useState<string>("");
  const [loadingDiff, setLoadingDiff] = useState(false);

  const [projectName, setProjectName] = useState<string | null>(null);

  useEffect(() => {
    if (projectId) {
      api.getProject(projectId)
        .then(res => setProjectName(res.name))
        .catch(() => setProjectName("project"));
    } else {
      setProjectName(null);
    }
  }, [projectId]);

  const fetchStatus = async () => {
    if (!projectName) return;
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await api.getGitStatus(projectName);
      if (res.status === "success") {
        setChanges(res.changes || []);
        if (res.message && res.changes?.length === 0) {
           setError(res.message);
        }
      } else {
        setError(res.message || "Failed to fetch git status");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Error fetching git status";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (projectName) {
      void fetchStatus();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectName]);

  const handleInit = async () => {
    if (!projectName) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.initGit(projectName);
      if (res.status === "success") {
        setSuccess("Repository initialized!");
        await fetchStatus();
      } else {
        setError(res.message || "Init failed");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error initializing repository");
    } finally {
      setLoading(false);
    }
  };

  const handleCommit = async () => {
    if (!commitMessage.trim() || !projectName) return;
    
    setLoading(true);
    setError(null);
    setSuccess(null);
    
    try {
      const res = await api.commitChanges(commitMessage, projectName);
      if (res.status === "success") {
        setSuccess("Committed successfully!");
        setCommitMessage("");
        await fetchStatus();
      } else {
        setError(res.message || "Commit failed");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Error committing changes";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#1e1e1e", color: "#d4d4d4", fontFamily: "var(--font-mono, monospace)", fontSize: 13 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "4px 12px", background: "#2d2d2d", borderBottom: "1px solid #3c3c3c" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {selectedDiffFile ? (
            <button 
              onClick={() => setSelectedDiffFile(null)}
              className="text-gray-400 hover:text-white flex items-center justify-center p-1"
              title="Back to Changes"
            >
              <ChevronLeft size={16} />
            </button>
          ) : (
            <GitBranch size={14} className="text-gray-400" />
          )}
          <span style={{ fontWeight: 600, fontSize: 12 }}>
            {selectedDiffFile ? `Diff: ${selectedDiffFile.split('/').pop()}` : "Source Control"}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button 
            onClick={() => void fetchStatus()}
            className="text-gray-400 hover:text-white"
            title="Refresh"
            style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 4 }}
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
          {onClose && (
            <button 
              onClick={onClose}
              className="text-gray-400 hover:text-white"
              title="Close Panel"
              style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 4 }}
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Main Content */}
      {selectedDiffFile ? (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: 0 }}>
          {loadingDiff ? (
            <div style={{ padding: 16, color: "#888", textAlign: "center" }}>Loading diff...</div>
          ) : (
            <DiffEditor
              height="100%"
              original={diffOriginal}
              modified={diffModified}
              language="javascript" // A generic language or detected
              theme="vs-dark"
              options={{
                renderSideBySide: false,
                readOnly: true,
                minimap: { enabled: false },
                fontSize: 12,
                fontFamily: "var(--font-mono, monospace)"
              }}
            />
          )}
        </div>
      ) : (
        <div style={{ flex: 1, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 16 }}>
        
        {/* Commit Input Area */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <textarea 
            value={commitMessage}
            onChange={e => setCommitMessage(e.target.value)}
            placeholder="Message (Enter to commit All changes)"
            style={{
              width: "100%",
              minHeight: "60px",
              background: "#3c3c3c",
              border: "1px solid #555",
              color: "#d4d4d4",
              padding: "8px",
              borderRadius: "4px",
              resize: "vertical",
              outline: "none",
              fontFamily: "inherit",
              fontSize: "inherit"
            }}
            disabled={loading || changes.length === 0}
            onKeyDown={e => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                void handleCommit();
              }
            }}
          />
          <button
            onClick={() => void handleCommit()}
            disabled={loading || changes.length === 0 || !commitMessage.trim()}
            style={{
              background: changes.length === 0 || !commitMessage.trim() ? "#444" : "#0e639c",
              color: changes.length === 0 || !commitMessage.trim() ? "#888" : "#fff",
              border: "none",
              padding: "6px 12px",
              borderRadius: "4px",
              cursor: changes.length === 0 || !commitMessage.trim() ? "not-allowed" : "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              fontWeight: "bold"
            }}
          >
            <Check size={14} />
            Commit
          </button>
        </div>

        {/* Status Messages */}
        {error && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#f14c4c", background: "#3c1e1e", padding: "8px", borderRadius: "4px" }}>
              <AlertCircle size={14} />
              <span>{error}</span>
            </div>
            {error.includes("Not a git repository") && (
              <button
                onClick={() => void handleInit()}
                disabled={loading}
                style={{
                  background: "#0e639c", color: "#fff", border: "none", padding: "6px 12px",
                  borderRadius: "4px", cursor: "pointer", fontWeight: "bold"
                }}
              >
                Initialize Repository
              </button>
            )}
          </div>
        )}
        {success && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#89d185", background: "#1e3c1e", padding: "8px", borderRadius: "4px" }}>
            <Check size={14} />
            <span>{success}</span>
          </div>
        )}

        {/* Changes List */}
        <div>
          <div style={{ fontWeight: "bold", marginBottom: 8, color: "#cccccc", borderBottom: "1px solid #3c3c3c", paddingBottom: 4 }}>
            Changes ({changes.length})
          </div>
          {changes.length === 0 ? (
            <div style={{ color: "#6e7681", fontStyle: "italic", textAlign: "center", padding: "16px 0" }}>
              No changes found in the working directory.
            </div>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 4 }}>
              {changes.map((change, idx) => (
                <li 
                  key={idx} 
                  onClick={async () => {
                    if (!projectName) return;
                    setSelectedDiffFile(change.file);
                    setLoadingDiff(true);
                    try {
                       // Load modified content
                       const currentRes = await api.readFile(change.file, projectId);
                       setDiffModified(currentRes.content || "");
                       
                       // Load original content
                       if (change.status.includes('A') || change.status.includes('?')) {
                         setDiffOriginal(""); // New file
                       } else {
                         const origRes = await api.getGitFileContent(change.file, projectName);
                         setDiffOriginal(origRes.content || "");
                       }
                    } catch (err) {
                       console.error(err);
                       setDiffOriginal("Error loading original");
                       setDiffModified("Error loading modified");
                    } finally {
                       setLoadingDiff(false);
                    }
                  }}
                  style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 8px", background: "#2d2d2d", borderRadius: "4px", cursor: "pointer" }}
                  className="hover:bg-gray-700"
                >
                  <span style={{ 
                    color: change.status.includes('M') ? "#cca700" : 
                           change.status.includes('A') || change.status.includes('?') ? "#89d185" : 
                           change.status.includes('D') ? "#f14c4c" : "#cccccc",
                    fontWeight: "bold",
                    width: "20px",
                    textAlign: "center"
                  }}>
                    {change.status}
                  </span>
                  <span style={{ wordBreak: "break-all" }}>{change.file}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      )}
    </div>
  );
}
