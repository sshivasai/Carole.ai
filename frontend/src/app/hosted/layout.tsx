import type { Metadata } from "next";

export const metadata: Metadata = {
  metadataBase: new URL("https://caroleai.com"),
  title: "Carole.ai — AI agents. Real work.",
  description:
    "A local AI agent workspace. Install Carole.ai from PyPI, then open your own local workspace to sign in and build.",
  alternates: { canonical: "/" },
  openGraph: {
    title: "Carole.ai — AI agents. Real work.",
    description: "Install Carole.ai and run your AI agent workspace locally.",
    images: [{ url: "/branding/logo-full-white-bg.png", width: 1080, height: 1080 }],
  },
};

export default function HostedLayout({ children }: { children: React.ReactNode }) {
  return children;
}
