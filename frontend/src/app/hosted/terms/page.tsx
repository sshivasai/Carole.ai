import type { Metadata } from "next";
import LegalPage from "@/components/LegalPage";
import styles from "@/components/LegalPage.module.css";

export const metadata: Metadata = {
  title: "Terms of Service — Carole.ai",
  description: "Terms for downloading and using the Carole.ai local application.",
  alternates: { canonical: "/terms/" },
};

export default function TermsPage() {
  return (
    <LegalPage title="Terms of Service">
      <p>These terms govern your use of the Carole.ai website and locally installed software. By using Carole.ai, you agree to these terms.</p>

      <h2>Local software</h2>
      <p>Carole.ai runs on your device and acts on the projects, accounts, tools, and model providers you configure. You are responsible for safeguarding your device, reviewing requested permissions, and maintaining backups of important work.</p>

      <h2>Your accounts and content</h2>
      <p>You retain responsibility for your content and connected accounts. You must have permission to access and modify any data you provide to Carole.ai and must use the software in compliance with applicable law and third-party service terms.</p>

      <h2>Agent actions</h2>
      <p>AI output can be incomplete or incorrect. Review proposed actions before approval, especially messages, file changes, account changes, or other actions that affect external systems. You remain responsible for actions you approve or configure the software to perform.</p>

      <h2>Third-party services</h2>
      <p>Carole.ai can connect to services such as Google Workspace and independent AI providers. Those services are governed by their own terms, availability, quotas, and policies. Carole.ai does not control those services.</p>

      <h2>Availability and warranties</h2>
      <p className={styles.notice}>The website and software are provided on an “as is” and “as available” basis to the extent permitted by law. We do not promise uninterrupted or error-free operation, and AI-generated results should be independently reviewed before they are relied upon.</p>

      <h2>Changes</h2>
      <p>We may update these terms as Carole.ai evolves. The effective date at the top of this page identifies the current version.</p>

      <h2>Contact</h2>
      <p>Questions can be sent to <a href="mailto:support.carole.ai@gmail.com">support.carole.ai@gmail.com</a>.</p>
    </LegalPage>
  );
}
