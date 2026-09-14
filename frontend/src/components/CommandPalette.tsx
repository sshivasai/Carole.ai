"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Search,
  MessageSquare,
  LayoutGrid,
  GitBranch,
  Terminal,
  Globe,
  Settings,
  Brain,
  Zap,
  FileCode,
  Sparkles,
  ArrowRight,
  Command,
  X,
} from "lucide-react";
import styles from "./CommandPalette.module.css";
import type { TaskItem, AgentConfig } from "@/lib/types";

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigate: (view: string) => void;
  onSelectFile?: (path: string) => void;
  onNewObjective?: () => void;
  tasks?: TaskItem[];
  agents?: AgentConfig[];
}

interface PaletteItem {
  id: string;
  category: "Navigation" | "Actions" | "Tasks" | "Agents";
  title: string;
  subtitle?: string;
  icon: React.ComponentType<{ size?: number; className?: string; style?: React.CSSProperties }>;
  action: () => void;
}

export default function CommandPalette({
  isOpen,
  onClose,
  onNavigate,
  onSelectFile,
  onNewObjective,
  tasks = [],
  agents = [],
}: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setQuery("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  // Built-in navigation items
  const baseItems: PaletteItem[] = [
    {
      id: "nav-home",
      category: "Navigation",
      title: "Workspace Home",
      subtitle: "Resume work, start new objectives & view attention queue",
      icon: Sparkles,
      action: () => {
        onNavigate("home");
        onClose();
      },
    },
    {
      id: "nav-chat",
      category: "Navigation",
      title: "Team Chat Workspace",
      subtitle: "Core conversation control plane with live agents",
      icon: MessageSquare,
      action: () => {
        onNavigate("chat");
        onClose();
      },
    },
    {
      id: "nav-tasks",
      category: "Navigation",
      title: "Kanban Task Board",
      subtitle: "Manage agent task queues, priorities, and dependencies",
      icon: LayoutGrid,
      action: () => {
        onNavigate("tasks");
        onClose();
      },
    },
    {
      id: "nav-git",
      category: "Navigation",
      title: "Source Control & Git",
      subtitle: "Review staging, branches, and commit checkpoints",
      icon: GitBranch,
      action: () => {
        onNavigate("git");
        onClose();
      },
    },
    {
      id: "nav-terminal",
      category: "Navigation",
      title: "Terminal Sessions",
      subtitle: "Execute commands and view agent shell outputs",
      icon: Terminal,
      action: () => {
        onNavigate("terminal");
        onClose();
      },
    },
    {
      id: "nav-browser",
      category: "Navigation",
      title: "Browser Workspace",
      subtitle: "Inspect web automation sessions and checkpoints",
      icon: Globe,
      action: () => {
        onNavigate("browser");
        onClose();
      },
    },
    {
      id: "nav-memory",
      category: "Navigation",
      title: "Memory & Knowledge Base",
      subtitle: "Inspect learned preferences, entities, and project knowledge",
      icon: Brain,
      action: () => {
        onNavigate("memory");
        onClose();
      },
    },
    {
      id: "nav-settings",
      category: "Navigation",
      title: "Settings & Configuration",
      subtitle: "Models, providers, runtime safety, and cost policies",
      icon: Settings,
      action: () => {
        onNavigate("settings");
        onClose();
      },
    },
    {
      id: "act-new-objective",
      category: "Actions",
      title: "Start New Objective",
      subtitle: "State an engineering task for the agent team",
      icon: Sparkles,
      action: () => {
        if (onNewObjective) onNewObjective();
        else onNavigate("home");
        onClose();
      },
    },
  ];

  // Dynamic items from active tasks and agents
  const taskItems: PaletteItem[] = tasks.slice(0, 8).map((t) => ({
    id: `task-${t.id}`,
    category: "Tasks",
    title: t.title,
    subtitle: `Status: ${t.status} · ${t.priority || "normal"}`,
    icon: LayoutGrid,
    action: () => {
      onNavigate("tasks");
      onClose();
    },
  }));

  const agentItems: PaletteItem[] = agents.map((a) => ({
    id: `agent-${a.id}`,
    category: "Agents",
    title: a.name,
    subtitle: `${a.role} · ${a.model || "default"}`,
    icon: Zap,
    action: () => {
      onNavigate("chat");
      onClose();
    },
  }));

  const allItems = [...baseItems, ...taskItems, ...agentItems];

  const filteredItems = query.trim()
    ? allItems.filter(
        (item) =>
          item.title.toLowerCase().includes(query.toLowerCase()) ||
          item.subtitle?.toLowerCase().includes(query.toLowerCase()) ||
          item.category.toLowerCase().includes(query.toLowerCase())
      )
    : allItems;

  // Keyboard controls
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % Math.max(1, filteredItems.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) =>
        prev <= 0 ? filteredItems.length - 1 : prev - 1
      );
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (filteredItems[selectedIndex]) {
        filteredItems[selectedIndex].action();
      }
    } else if (e.key === "Escape") {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div
        className={styles.modal}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        {/* Search Input Bar */}
        <div className={styles.searchBar}>
          <Search size={16} className={styles.searchIcon} />
          <input
            ref={inputRef}
            className={styles.input}
            placeholder="Type a command or search workspace..."
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
          />
          <button className={styles.closeBtn} onClick={onClose} title="Close (Esc)">
            <X size={14} />
          </button>
        </div>

        {/* Results list */}
        <div className={styles.resultsList}>
          {filteredItems.map((item, idx) => {
            const isSelected = idx === selectedIndex;
            const IconComponent = item.icon;
            return (
              <div
                key={item.id}
                className={`${styles.item} ${isSelected ? styles.itemSelected : ""}`}
                onClick={item.action}
                onMouseEnter={() => setSelectedIndex(idx)}
              >
                <div className={styles.itemIconWrapper}>
                  <IconComponent size={15} />
                </div>
                <div className={styles.itemMeta}>
                  <div className={styles.itemTitleRow}>
                    <span className={styles.itemTitle}>{item.title}</span>
                    <span className={styles.itemCategory}>{item.category}</span>
                  </div>
                  {item.subtitle && (
                    <span className={styles.itemSubtitle}>{item.subtitle}</span>
                  )}
                </div>
                {isSelected && (
                  <ArrowRight size={13} className={styles.itemEnterArrow} />
                )}
              </div>
            );
          })}

          {filteredItems.length === 0 && (
            <div className={styles.emptyResults}>
              No matching commands, tasks, or navigation items.
            </div>
          )}
        </div>

        {/* Footer shortcuts */}
        <div className={styles.footer}>
          <div className={styles.shortcut}>
            <kbd className={styles.kbd}>↑</kbd>
            <kbd className={styles.kbd}>↓</kbd>
            <span>to navigate</span>
          </div>
          <div className={styles.shortcut}>
            <kbd className={styles.kbd}>↵</kbd>
            <span>to select</span>
          </div>
          <div className={styles.shortcut}>
            <kbd className={styles.kbd}>esc</kbd>
            <span>to close</span>
          </div>
        </div>
      </div>
    </div>
  );
}
