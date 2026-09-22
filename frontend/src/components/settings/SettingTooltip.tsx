"use client";
import React, { useState, useRef, useLayoutEffect, useId } from "react";
import { createPortal } from "react-dom";
import { HelpCircle } from "lucide-react";

interface SettingTooltipProps {
  title?: string;
  why: string;
  how: string;
  placement?: "top" | "bottom" | "right" | "left";
  iconSize?: number;
  children?: React.ReactNode;
}

export default function SettingTooltip({ title, why, how, placement = "top", iconSize = 13, children }: SettingTooltipProps) {
  const [visible, setVisible] = useState(false);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const id = useId();

  useLayoutEffect(() => {
    if (!visible) return;
    const position = () => {
      const trigger = triggerRef.current;
      const tooltip = tooltipRef.current;
      if (!trigger || !tooltip) return;
      const rect = trigger.getBoundingClientRect();
      const theme = getComputedStyle(trigger);
      tooltip.style.background = theme.getPropertyValue("--color-canvas-raised").trim();
      tooltip.style.color = theme.getPropertyValue("--color-ink").trim();
      tooltip.style.borderColor = theme.getPropertyValue("--color-hairline").trim();
      const { width, height } = tooltip.getBoundingClientRect();
      let left = rect.left + (rect.width - width) / 2;
      let top = placement === "bottom" ? rect.bottom + 10 : rect.top - height - 10;
      if (placement === "right") { left = rect.right + 10; top = rect.top + (rect.height - height) / 2; }
      if (placement === "left") { left = rect.left - width - 10; top = rect.top + (rect.height - height) / 2; }
      if (top < 12) top = rect.bottom + 10;
      tooltip.style.left = `${Math.max(12, Math.min(left, window.innerWidth - width - 12))}px`;
      tooltip.style.top = `${Math.max(12, Math.min(top, window.innerHeight - height - 12))}px`;
      tooltip.style.visibility = "visible";
    };
    position();
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);
    return () => { window.removeEventListener("resize", position); window.removeEventListener("scroll", position, true); };
  }, [visible, placement]);

  return <span ref={triggerRef} role="button" tabIndex={0} aria-label={title ? `About ${title}` : "About this setting"} aria-describedby={visible ? id : undefined}
    onMouseEnter={() => setVisible(true)} onMouseLeave={() => setVisible(false)} onFocus={() => setVisible(true)} onBlur={() => setVisible(false)}
    onClick={() => setVisible(true)} onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); setVisible(false); } if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setVisible(value => !value); } }}
    style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0, padding: 4, borderRadius: 5, cursor: "help", verticalAlign: "middle", color: "var(--color-mute)" }}>
    {children || <HelpCircle size={iconSize} />}
    {visible && createPortal(<div ref={tooltipRef} id={id} role="tooltip" style={{ position: "fixed", visibility: "hidden", zIndex: 99999, width: "min(320px, calc(100vw - 24px))", maxHeight: "calc(100dvh - 24px)", overflowY: "auto", border: "1px solid", borderRadius: 12, padding: 16, boxShadow: "0 12px 40px rgb(0 0 0 / 22%)", fontSize: 12, lineHeight: 1.6, pointerEvents: "none" }}>
      {title && <strong style={{ display: "block", fontSize: 13, marginBottom: 8 }}>{title}</strong>}
      <p style={{ margin: "0 0 8px" }}>{why}</p><p style={{ margin: 0, opacity: .8 }}>{how}</p>
    </div>, document.body)}
  </span>;
}
