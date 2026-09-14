"use client";
import React, { useEffect, useCallback, useRef, useId } from "react";
import { X } from "lucide-react";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  children: React.ReactNode;
  maxWidth?: number;
  hideClose?: boolean;
}

export default function Modal({ open, onClose, title, children, maxWidth = 480, hideClose }: ModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);
  const titleId = useId();

  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; }, [onClose]);

  // Focus trap & escape key handler
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      closeRef.current();
      return;
    }

    if (e.key === "Tab" && modalRef.current) {
      const focusable = Array.from(modalRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )).filter(element => element.getClientRects().length > 0 && !element.closest("[inert]"));
      if (focusable.length === 0) {
        e.preventDefault();
        modalRef.current.focus();
        return;
      }

      const firstElement = focusable[0];
      const lastElement = focusable[focusable.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === firstElement || !focusable.includes(document.activeElement as HTMLElement)) {
          e.preventDefault();
          lastElement.focus();
        }
      } else {
        if (document.activeElement === lastElement || !focusable.includes(document.activeElement as HTMLElement)) {
          e.preventDefault();
          firstElement.focus();
        }
      }
    }
  }, []);

  useEffect(() => {
    if (!open) return;

    // Remember previously focused trigger
    previousActiveElement.current = document.activeElement as HTMLElement | null;

    document.addEventListener("keydown", handleKeyDown);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // Initial focus onto first interactive element or modal card
    const timer = setTimeout(() => {
      if (modalRef.current) {
        const first = modalRef.current.querySelector<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled])'
        );
        if (first) {
          first.focus();
        } else {
          modalRef.current.focus();
        }
      }
    }, 40);

    return () => {
      clearTimeout(timer);
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = prevOverflow;

      // Restore focus to trigger element
      if (previousActiveElement.current && typeof previousActiveElement.current.focus === "function") {
        previousActiveElement.current.focus();
      }
    };
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div
      className="modal-backdrop"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? titleId : undefined}
      aria-label={title ? undefined : "Dialog"}
    >
      <div
        ref={modalRef}
        className="modal-card animate-slide-up"
        style={{ maxWidth, outline: "none" }}
        tabIndex={-1}
      >
        {(title || !hideClose) && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--sp-2xl)", flexShrink: 0 }}>
            {title && <h2 id={titleId} className="display-md">{title}</h2>}
            {!hideClose && (
              <button
                className="btn btn-icon btn-ghost"
                onClick={onClose}
                style={{ marginLeft: "auto", color: "var(--color-mute)" }}
                aria-label="Close modal"
              >
                <X size={18} />
              </button>
            )}
          </div>
        )}
        <div style={{ overflowY: "auto", minHeight: 0, flex: "1 1 auto" }} className="modal-content">
          {children}
        </div>
      </div>
    </div>
  );
}
