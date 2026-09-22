"use client";
import React, { useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy, FileText, List } from "lucide-react";
import { resolveDocumentLink } from "@/features/files/document";
import styles from "./MarkdownViewer.module.css";

interface Props {
  content: string;
  path?: string;
  onOpenFile?: (path: string) => void;
  resolveAsset?: (path: string) => string;
}
interface Heading { id: string; title: string; depth: number; }
interface MarkdownNode { type: string; value?: string; depth?: number; children?: MarkdownNode[]; data?: { hProperties?: Record<string, string> }; }
function nodeText(node: MarkdownNode): string { return node.value || node.children?.map(nodeText).join('') || ''; }
function CodeBlock({ children, ...props }: React.ComponentProps<'pre'>) {
  const ref = useRef<HTMLPreElement>(null);
  const [state, setState] = useState<'idle' | 'copied' | 'error'>('idle');
  return <div className={styles.codeBlock}><div className={styles.codeToolbar}><span>Code</span><button type="button" onClick={async () => {
    try { await navigator.clipboard.writeText(ref.current?.textContent || ''); setState('copied'); } catch { setState('error'); }
  }}>{state === 'copied' ? <Check size={13} /> : <Copy size={13} />}{state === 'copied' ? 'Copied' : state === 'error' ? 'Retry copy' : 'Copy'}</button></div><pre ref={ref} {...props}>{children}</pre>{state === 'error' && <span role="status" className={styles.copyError}>Clipboard unavailable. Select the code to copy it.</span>}</div>;
}

export default function MarkdownViewer({ content, path = 'README.md', onOpenFile, resolveAsset }: Props) {
  const article = useRef<HTMLElement>(null);
  const [outlineOpen, setOutlineOpen] = useState(false);
  const { headings, headingPlugin } = useMemo(() => {
    const headings: Heading[] = [];
    const headingPlugin = () => (tree: MarkdownNode) => {
      headings.length = 0;
      const used = new Map<string, number>();
      const walk = (node: MarkdownNode) => {
        if (node.type === 'heading') {
          const title = nodeText(node);
          const base = title.toLowerCase().replace(/[^\p{L}\p{N}\s-]/gu, '').trim().replace(/\s+/g, '-') || 'section';
          const count = used.get(base) || 0; used.set(base, count + 1);
          const id = count ? `${base}-${count}` : base;
          node.data = { ...node.data, hProperties: { ...node.data?.hProperties, id } };
          headings.push({ id, title, depth: node.depth || 1 });
        }
        node.children?.forEach(walk);
      }; walk(tree);
    };
    return { headings, headingPlugin };
  }, [content]);
  const jump = (hash: string) => {
    let decoded = hash;
    try { decoded = decodeURIComponent(hash); } catch { /* Use the literal fragment. */ }
    const heading = Array.from(article.current?.querySelectorAll<HTMLElement>('[id]') || []).find(item => item.id === decoded);
    heading?.scrollIntoView({ block: 'start', behavior: 'auto' });
    if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
  };
  const rendered = <ReactMarkdown remarkPlugins={[remarkGfm, headingPlugin]} components={{
    pre: ({ node: _node, ...props }) => <CodeBlock {...props} />,
    a: ({ href = '', children }) => {
      const local = resolveDocumentLink(href, path);
      if (href.startsWith('#')) return <a href={href} onClick={event => { event.preventDefault(); jump(href.slice(1)); }}>{children}</a>;
      if (local && onOpenFile) return <a href={href} onClick={event => { event.preventDefault(); onOpenFile(local.path); }}>{children}</a>;
      return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
    },
    img: ({ src, alt }) => { const local = typeof src === 'string' ? resolveDocumentLink(src, path) : null; return <img src={local && resolveAsset ? resolveAsset(local.path) : src} alt={alt || ''} loading="lazy" />; },
    table: ({ node: _node, ...props }) => <div className={styles.tableScroll} tabIndex={0} role="region" aria-label="Scrollable table"><table {...props} /></div>,
  }}>{content}</ReactMarkdown>;
  return <section className={styles.viewer} aria-label="Markdown preview">
    <header className={styles.toolbar}><span><FileText size={15} /><strong>{path.split('/').pop()}</strong><small>Markdown preview</small></span><button type="button" aria-expanded={outlineOpen} onClick={() => setOutlineOpen(value => !value)}><List size={15} />Contents</button></header>
    <div className={styles.layout}>
      <article ref={article} className={`${styles.document} markdown-body`}>
        {content.trim() ? rendered : <div className={styles.empty}><FileText size={28} /><h3>This document is empty</h3><p>Switch to Edit to start writing.</p></div>}
      </article>
      {outlineOpen && <nav className={styles.outline} aria-label="Document contents"><strong>On this page</strong><DocumentOutline headings={headings} onJump={jump} /></nav>}
    </div>
  </section>;
}
// ReactMarkdown builds the heading list while the preceding article is rendered.
function DocumentOutline({ headings, onJump }: { headings: Heading[]; onJump: (id: string) => void }) {
  return headings.length ? <>{headings.map(heading => <button key={heading.id} style={{ paddingLeft: 10 + Math.min(heading.depth - 1, 3) * 10 }} onClick={() => onJump(heading.id)}>{heading.title}</button>)}</> : <p>No headings in this document.</p>;
}
