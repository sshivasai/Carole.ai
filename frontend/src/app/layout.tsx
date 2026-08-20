import type { Metadata } from "next";
import { ThemeProvider } from "../hooks/useTheme";
import { Plus_Jakarta_Sans, Bricolage_Grotesque, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const plusJakartaSans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  weight: ["400", "500", "600", "700", "800"],
});

const bricolageGrotesque = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["500", "600", "700", "800"],
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  metadataBase: new URL("https://carole.ai"),
  title: "Carole.ai — Autonomous Multi-Agent Swarm Platform",
  description:
    "Deploy autonomous agent swarms with persistent Hybrid GraphRAG memory, visual browser automation, zero-cost meeting intelligence, and live task coordination.",
  keywords: [
    "AI agents",
    "multi-agent orchestration",
    "GraphRAG",
    "autonomous software engineering",
    "MCP server",
    "open source AI",
  ],
  icons: {
    icon: [
      { url: "/branding/logo-mark.png", type: "image/png" },
      { url: "/favicon.ico" },
    ],
    shortcut: "/favicon.ico",
    apple: "/apple-touch-icon.png",
  },
  openGraph: {
    title: "Carole.ai — Autonomous Multi-Agent Swarm Platform",
    description: "AI Agents. Real Work. 100% Free & Open Source.",
    images: [{ url: "/branding/logo-full.png", width: 1080, height: 1080 }],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="theme-color" content="#030315" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
      </head>
      <body
        className={`${plusJakartaSans.variable} ${bricolageGrotesque.variable} ${jetbrainsMono.variable}`}
      >
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
