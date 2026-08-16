"use client";
import React from "react";
import { Sun, Moon } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";

interface Props {
  className?: string;
}

export default function ThemeToggle({ className }: Props) {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      id="theme-toggle-btn"
      className={`btn btn-icon btn-ghost ${className ?? ""}`}
      onClick={toggleTheme}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      aria-label="Toggle theme"
      style={{ transition: "color 0.2s" }}
    >
      {theme === "dark" ? (
        <Sun size={17} style={{ color: "#fbbf24" }} />
      ) : (
        <Moon size={17} style={{ color: "#6366f1" }} />
      )}
    </button>
  );
}
