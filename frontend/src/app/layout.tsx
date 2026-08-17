import type { Metadata } from "next";
import { ThemeProvider } from "../hooks/useTheme";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://carole.ai"),
  title: "Carole.ai — Multi-Agent Collaboration Platform",
  description: "Orchestrate AI agent teams with real-time chat, browser automation, task boards, and semantic memory.",
  keywords: ["AI agents", "multi-agent", "collaboration", "automation"],
  icons: {
    icon: [
      { url: "/branding/logo-mark.png", type: "image/png" },
      { url: "/favicon.ico" },
    ],
    shortcut: "/favicon.ico",
    apple: "/apple-touch-icon.png",
  },
  openGraph: {
    title: "Carole.ai — Multi-Agent Collaboration Platform",
    description: "AI Agents. Real Work.",
    images: [{ url: "/branding/logo-full.png", width: 1080, height: 1080 }],
  },
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
      <body>
        <ThemeProvider>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
