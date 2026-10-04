import type { Metadata } from "next";
import LegalPage from "@/components/LegalPage";
import styles from "@/components/LegalPage.module.css";

export const metadata: Metadata = {
  title: "Privacy Policy — Carole.ai",
  description: "How the local Carole.ai workspace handles account data, Google connections, and AI providers.",
  alternates: { canonical: "/privacy/" },
};

const sections = [
  { id: "local-data", label: "What stays on your device" },
  { id: "google", label: "Google account connection" },
  { id: "providers", label: "AI providers and integrations" },
  { id: "controls", label: "Your controls" },
  { id: "security", label: "Security and contact" },
];

export default function PrivacyPage() {
  return <LegalPage title="Privacy Policy" summary="Your workspace is local by default. This page explains the limited cases where data leaves your device." sections={sections}>
    <section id="local-data">
      <h2>What stays on your device</h2>
      <p>Carole.ai runs its web interface and backend on your computer. Projects, conversations, settings, and local account records are stored in a database on your device by default—not in a Carole.ai-hosted account database. Local account passwords are hashed before storage; we do not store their plaintext versions.</p>
      <p className={styles.notice}>“Local-first” does not mean no data ever leaves your device. Google OAuth exchanges, the Google APIs you choose to use, and model or tool providers you configure involve those services as described below.</p>
    </section>

    <section id="google">
      <h2>Google account connection</h2>
      <p>Connecting Google is optional. With your consent, Carole.ai can use the permissions shown on Google’s consent screen for Gmail, Calendar, and Tasks. The local app makes Google API calls directly from your device when you use those features.</p>
      <ul>
        <li>Google access and refresh tokens are saved locally in your operating system’s credential vault.</li>
        <li>The built-in connection uses a Cloudflare-hosted token exchange service to exchange and refresh Google credentials. Authorization codes, PKCE verifiers, and tokens pass through that service in memory. The service does not persist them in a cloud database or application logs.</li>
        <li>The public OAuth client ID included with Carole.ai cannot access your account on its own.</li>
        <li>Carole.ai does not sell Google user data or use it for advertising.</li>
      </ul>
      <p>Agent actions that send, edit, trash, or delete data are designed to request in-app approval before execution. Review the requested action and its scope before approving.</p>
    </section>

    <section id="providers">
      <h2>AI providers and integrations</h2>
      <p>When you configure an AI model, MCP tool, or another integration, the information needed for that request may be sent from your device to that provider. This can include content you ask an agent to work with, including Google content. Those services have their own privacy practices; review the provider you select before sharing sensitive material.</p>
    </section>

    <section id="controls">
      <h2>Your controls</h2>
      <p>You can disconnect Google in Carole.ai, revoke its access in your Google Account, and remove locally stored workspace data from your device. Uninstalling the app alone may not remove your local workspace database or credentials from the operating-system vault.</p>
    </section>

    <section id="security">
      <h2>Security and contact</h2>
      <p>Carole.ai uses local storage, credential-vault token storage, and approval gates to reduce risk. No system is perfectly secure. Keep your device account and operating system protected.</p>
      <p>Questions or privacy requests: <a href="mailto:support.carole.ai@gmail.com">support.carole.ai@gmail.com</a>.</p>
    </section>
  </LegalPage>;
}
