"use client";
import React, { useEffect, useRef, useState } from "react";
import { api } from "@/hooks/useApi";
import { Search, Loader2, FileText, ChevronRight } from "lucide-react";
import styles from "./SearchPanel.module.css";
interface Props { projectId?: string; onFileSelect?: (path: string) => void; }
interface Match { file: string; line: string; content: string; }
export default function SearchPanel(props: Props) { return <ProjectSearch key={props.projectId || 'none'} {...props} />; }
function ProjectSearch({ projectId, onFileSelect }: Props) {
  const [query, setQuery] = useState('');
  const [submitted, setSubmitted] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<Match[]>([]);
  const [error, setError] = useState('');
  const request = useRef(0);
  useEffect(() => () => { request.current++; }, []);
  const grouped = new Map<string, Match[]>();
  results.forEach(match => grouped.set(match.file, [...(grouped.get(match.file) || []), match]));
  const search = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!projectId || !query.trim()) return;
    const id = ++request.current;
    const term = query.trim();
    setLoading(true); setError(''); setSubmitted(term); setResults([]);
    try {
      const response = await api.searchFiles(term, projectId);
      if (request.current !== id) return;
      if (response.status !== 'success') throw new Error(response.message || 'Search failed. Try again.');
      setResults(response.results || []);
    } catch (error) { if (request.current === id) setError(error instanceof Error ? error.message : 'Could not search files.'); }
    finally { if (request.current === id) setLoading(false); }
  };
  return <section className={styles.panel} aria-label="Search workspace files">
    <form onSubmit={search} className={styles.form}>
      <label htmlFor="workspace-search">Search file contents</label>
      <div className={styles.search}><Search size={15} /><input id="workspace-search" type="search" placeholder="Search this project…" value={query} onChange={event => setQuery(event.target.value)} disabled={!projectId} /></div>
      <button className="btn btn-primary btn-sm" disabled={!projectId || !query.trim() || loading}>{loading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}{loading ? 'Searching…' : 'Search'}</button>
    </form>
    <div className={styles.results}>
      {error && <p className={styles.error} role="alert">{error}</p>}
      {!submitted && <div className={styles.empty}><Search size={26} /><strong>{projectId ? 'Find something in your code' : 'Choose a project to search'}</strong><p>{projectId ? 'Search for a symbol, phrase, or line of code. Open a result to inspect its file.' : 'Search is scoped to the selected workspace.'}</p></div>}
      {submitted && !loading && !error && <p className={styles.summary} role="status">{results.length ? `${results.length} matches in ${grouped.size} files` : `No matches for “${submitted}”`}</p>}
      {Array.from(grouped, ([file, matches]) => <details key={file} open className={styles.group}>
        <summary><ChevronRight size={14} /><FileText size={14} /><span title={file}>{file}</span><small>{matches.length}</small></summary>
        {matches.map((match, index) => <button key={`${match.line}-${index}`} className={styles.match} onClick={() => onFileSelect?.(file)} title={`Open ${file}:${match.line}`}><span>{match.line}</span><code>{match.content}</code></button>)}
      </details>)}
    </div>
  </section>;
}
