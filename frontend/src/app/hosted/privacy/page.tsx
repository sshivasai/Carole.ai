import type { Metadata } from "next";
import LegalPage from "@/components/LegalPage";

export const metadata: Metadata = {
  title: "Privacy Policy — Carole.ai",
  description: "How Carole.ai handles local workspace and Google account data.",
  alternates: { canonical: "/privacy/" },
};

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy">
      <p>Carole.ai is a local-first AI agent workspace. This policy explains what information the Carole.ai application processes when you install it and connect third-party services such as Google Workspace.</p>

      <h2>Local workspace data</h2>
      <p>Your projects, agent conversations, settings, and local application data are stored on your device. Carole.ai does not operate a hosted account database for the locally installed application.</p>

      <h2>Google account data</h2>
      <p>Google connection is optional. If you choose to connect an account, Carole.ai requests only the permissions shown on Google&apos;s consent screen to identify your account and work with Gmail messages, Calendar events, and Google Tasks. The app accesses this data only when you or an agent invokes the corresponding feature.</p>
      <ul>
        <li>OAuth access and refresh tokens remain on your device in its operating-system credential vault.</li>
        <li>The public Desktop OAuth client identity bundled with Carole.ai is not a user token and cannot access an account by itself.</li>
        <li>Carole.ai does not sell Google user data or use it for advertising.</li>
        <li>Email sending and other external changes require an in-app human approval before execution.</li>
      </ul>

      <h2>AI providers and other integrations</h2>
      <p>When you configure an AI model provider or another integration, the data needed for your request is sent directly from your device to that provider under its own privacy terms. Review the provider and model you select before sharing sensitive information.</p>

      <h2>Retention and control</h2>
      <p>You can disconnect Google from Carole.ai at any time. Disconnecting revokes the connection when possible and removes the locally stored token. You can also revoke access from your Google Account security settings and delete local Carole.ai data from your device.</p>

      <h2>Security</h2>
      <p>We use least-privilege OAuth scopes, local credential-vault storage, and approval gates for external mutations. No system is perfectly secure, so keep your operating system updated and protect your device account.</p>

      <h2>Contact</h2>
      <p>Questions or privacy requests can be sent to <a href="mailto:support.carole.ai@gmail.com">support.carole.ai@gmail.com</a>.</p>
    </LegalPage>
  );
}
