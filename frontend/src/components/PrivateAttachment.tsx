"use client";

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { getApiBase } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";

/** Fetch private media with an Authorization header, never a token in the URL. */
export default function PrivateAttachment({ url, image = false, alt, style, children }: {
  url: string; image?: boolean; alt?: string; style?: CSSProperties; children?: ReactNode;
}) {
  const { token } = useAuth();
  const [resolved, setResolved] = useState<{ source: string; token: string | null; blob: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | undefined;
    const base = new URL(getApiBase(), window.location.origin);
    let target: URL;
    try { target = new URL(url, base); } catch { return; }
    // Upload previews are already local blobs. Never send credentials elsewhere.
    if (target.protocol === "blob:") return;
    if (target.origin !== base.origin || !/^\/api\/(media|uploads)\//.test(target.pathname) || !token) return;
    fetch(target, { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error("Media unavailable"); return response.blob(); })
      .then(blob => {
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setResolved({ source: url, token, blob: objectUrl });
      }).catch(() => { /* Render the unavailable state; do not leak server errors. */ });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [url, token]);
  const source = url.startsWith("blob:") ? url : resolved?.source === url && resolved.token === token ? resolved.blob : undefined;
  if (!source) return <span style={style}>Attachment unavailable or loading</span>;
  if (image) return <img src={source} alt={alt || "attachment"} style={style} />;
  return <a href={source} download style={style}>{children || "Download attachment"}</a>;
}
