import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Carole.ai — Multi-Agent Collaboration Platform",
  description: "Orchestrate AI agent teams with real-time chat, browser automation, task boards, and semantic memory.",
  keywords: ["AI agents", "multi-agent", "collaboration", "automation"],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="theme-color" content="#0A0A0A" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body>{children}</body>
    </html>
  );
}
