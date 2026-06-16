"use client";

import React, { useState } from "react";
import { api } from "@/hooks/useApi";
import { Search, Loader2, File, ChevronRight, ChevronDown } from "lucide-react";

interface SearchPanelProps {
  projectId?: string;
  onFileSelect?: (path: string) => void;
}

export default function SearchPanel({ projectId, onFileSelect }: SearchPanelProps) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<{ file: string; line: string; content: string }[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Group by file
  const groupedResults = results.reduce((acc, curr) => {
    if (!acc[curr.file]) {
      acc[curr.file] = [];
    }
    acc[curr.file].push(curr);
    return acc;
  }, {} as Record<string, typeof results>);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    
    setLoading(true);
    setError(null);
    setHasSearched(true);
    
    try {
      const res = await api.searchFiles(query, projectId);
      if (res.status === "success") {
        setResults(res.results || []);
      } else {
        setError(res.message || "Search failed");
        setResults([]);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Error searching files";
      setError(msg);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "var(--color-canvas-soft)", color: "var(--color-body)" }}>
      {/* Search Input Area */}
      <div style={{ padding: "12px", borderBottom: "1px solid var(--color-hairline)" }}>
        <form onSubmit={handleSearch} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ position: "relative" }}>
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search in files..."
              style={{
                width: "100%",
                background: "var(--color-canvas)",
                border: "1px solid var(--color-hairline)",
                color: "var(--color-body)",
                padding: "6px 8px 6px 28px",
                borderRadius: "4px",
                outline: "none",
                fontSize: "13px"
              }}
            />
            <Search size={14} style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", color: "var(--color-mute)" }} />
          </div>
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="btn btn-primary btn-sm"
            style={{ display: "none" }} // Hidden but submit on enter
          >
            Search
          </button>
        </form>
      </div>

      {/* Results Area */}
      <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
        {loading && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "16px", color: "var(--color-mute)" }}>
            <Loader2 size={16} className="animate-spin mr-2" />
            <span className="body-sm">Searching...</span>
          </div>
        )}

        {!loading && error && (
          <div style={{ padding: "8px 16px", color: "var(--color-error)", fontSize: "13px" }}>
            {error}
          </div>
        )}

        {!loading && hasSearched && results.length === 0 && !error && (
          <div style={{ padding: "16px", color: "var(--color-mute)", fontSize: "13px", textAlign: "center", fontStyle: "italic" }}>
            No results found.
          </div>
        )}

        {!loading && results.length > 0 && (
          <div style={{ padding: "0 8px" }}>
            {Object.keys(groupedResults).map(file => (
              <FileResultGroup 
                key={file} 
                file={file} 
                matches={groupedResults[file]} 
                onFileSelect={onFileSelect} 
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function FileResultGroup({ file, matches, onFileSelect }: { 
  file: string; 
  matches: { line: string; content: string }[];
  onFileSelect?: (path: string) => void;
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div style={{ marginBottom: 4 }}>
      <div 
        onClick={() => setExpanded(!expanded)}
        style={{ 
          display: "flex", 
          alignItems: "center", 
          cursor: "pointer", 
          padding: "4px 0",
          userSelect: "none"
        }}
        className="hover:bg-gray-800 rounded transition-colors"
      >
        <span style={{ width: 16, display: "flex", justifyContent: "center", marginRight: 2 }}>
          {expanded ? <ChevronDown size={14} className="text-mute" /> : <ChevronRight size={14} className="text-mute" />}
        </span>
        <File size={14} className="text-gray-400 mr-2" />
        <span className="body-sm font-semibold truncate" style={{ fontSize: "13px" }} title={file}>
          {file}
        </span>
        <span className="ml-auto text-mute text-xs" style={{ background: "rgba(255,255,255,0.1)", padding: "1px 6px", borderRadius: "10px" }}>
          {matches.length}
        </span>
      </div>
      
      {expanded && (
        <div style={{ display: "flex", flexDirection: "column" }}>
          {matches.map((m, idx) => (
            <div 
              key={idx}
              onClick={() => onFileSelect && onFileSelect(file)}
              style={{ 
                display: "flex", 
                alignItems: "flex-start",
                padding: "2px 8px 2px 34px",
                cursor: "pointer",
                fontSize: "12px",
                fontFamily: "var(--font-mono, monospace)"
              }}
              className="hover:bg-gray-700 transition-colors"
              title={m.content}
            >
              <span style={{ color: "#569cd6", marginRight: 8, minWidth: "24px", textAlign: "right" }}>{m.line}</span>
              <span className="truncate" style={{ color: "#d4d4d4" }}>{m.content}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
