import type { Metadata } from "next";
import { ThemeProvider } from "../hooks/useTheme";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://carole.ai"),
  title: "Carole.ai: Autonomous AI Engineering Teams & Multi-Agent Platform",
  description:
    "Deploy self-coordinating AI engineering teams with Actor-model message queues, AST dead-end pruning, Judge AI security, and persistent LanceDB GraphRAG memory.",
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
    title: "Carole.ai: Autonomous AI Engineering Teams Platform",
    description: "AI Engineering Teams. Real Work. 100% Free & Open Source.",
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
      <body>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
