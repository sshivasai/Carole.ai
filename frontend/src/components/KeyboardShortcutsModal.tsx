import React, { useEffect, useState } from "react";
import Modal from "./Modal";
import { Keyboard, Command, ArrowUp, ArrowDown } from "lucide-react";

export default function KeyboardShortcutsModal() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd+/ or Ctrl+/ toggles this modal
      if ((e.ctrlKey || e.metaKey) && e.key === "/") {
        e.preventDefault();
        setOpen(o => !o);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  if (!open) return null;

  return (
    <Modal open={open} onClose={() => setOpen(false)} title={
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <Keyboard size={18} />
        <span>Keyboard Shortcuts</span>
      </div>
    } maxWidth={500}>
      <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px", background: "var(--bg-glass-panel)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-subtle)" }}>
            <span style={{ fontSize: "13px" }}>Toggle Shortcuts</span>
            <kbd style={{ fontSize: "11px", padding: "2px 6px", background: "var(--bg-surface-raised)", border: "1px solid var(--border-subtle)", borderRadius: "4px" }}>Ctrl + /</kbd>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px", background: "var(--bg-glass-panel)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-subtle)" }}>
            <span style={{ fontSize: "13px" }}>Toggle File Explorer</span>
            <kbd style={{ fontSize: "11px", padding: "2px 6px", background: "var(--bg-surface-raised)", border: "1px solid var(--border-subtle)", borderRadius: "4px" }}>Ctrl + B</kbd>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px", background: "var(--bg-glass-panel)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-subtle)" }}>
            <span style={{ fontSize: "13px" }}>Save File</span>
            <kbd style={{ fontSize: "11px", padding: "2px 6px", background: "var(--bg-surface-raised)", border: "1px solid var(--border-subtle)", borderRadius: "4px" }}>Ctrl + S</kbd>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px", background: "var(--bg-glass-panel)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-subtle)" }}>
            <span style={{ fontSize: "13px" }}>New Line (Chat)</span>
            <kbd style={{ fontSize: "11px", padding: "2px 6px", background: "var(--bg-surface-raised)", border: "1px solid var(--border-subtle)", borderRadius: "4px" }}>Shift + Enter</kbd>
          </div>
        </div>
        <div style={{ marginTop: "8px", textAlign: "right" }}>
          <button className="btn btn-primary btn-sm" onClick={() => setOpen(false)}>Done</button>
        </div>
      </div>
    </Modal>
  );
}
