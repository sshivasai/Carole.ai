/** Resolve a Markdown link within the current project, without escaping its root. */
export function resolveDocumentLink(href: string, documentPath: string): { path: string; hash: string } | null {
  if (!href || href.startsWith('#') || /^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(href)) return null;
  const [rawPath, fragment = ''] = href.split('#', 2);
  const pathOnly = rawPath.split('?')[0];
  let decoded: string;
  try { decoded = decodeURIComponent(pathOnly); } catch { return null; }
  const segments = decoded.startsWith('/') ? [] : documentPath.replace(/\\/g, '/').split('/').slice(0, -1);
  for (const segment of decoded.replace(/\\/g, '/').split('/')) {
    if (!segment || segment === '.') continue;
    if (segment === '..') { if (!segments.length) return null; segments.pop(); }
    else segments.push(segment);
  }
  return segments.length ? { path: segments.join('/'), hash: fragment } : null;
}

export function savedFileState<T extends { path: string; content: string; isDirty: boolean }>(files: T[], path: string, savedContent: string): T[] {
  return files.map(file => file.path === path && file.content === savedContent ? { ...file, isDirty: false } : file);
}
