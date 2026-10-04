import type { Metadata } from "next";
import LegalPage from "@/components/LegalPage";
import styles from "@/components/LegalPage.module.css";

export const metadata: Metadata = {
  title: "Terms of Service — Carole.ai",
  description: "Terms for the Carole.ai website and locally installed AI workspace.",
  alternates: { canonical: "/terms/" },
};

const sections = [
  { id: "using-carole", label: "Using Carole.ai" },
  { id: "your-content", label: "Your accounts and content" },
  { id: "agent-actions", label: "Agent actions" },
  { id: "third-parties", label: "Third-party services" },
  { id: "availability", label: "Availability" },
  { id: "changes", label: "Changes and contact" },
];

export default function TermsPage() {
  return <LegalPage title="Terms of Service" summary="Carole.ai is software you run locally. These terms explain your responsibilities when using the app, its agents, and connected services." sections={sections}>
    <section id="using-carole">
      <h2>Using Carole.ai</h2>
      <p>These terms govern your use of the Carole.ai website and locally installed software. By using Carole.ai, you agree to them. The application runs on your device and uses the projects, accounts, tools, and model providers you configure.</p>
      <p>You are responsible for securing your device, controlling who can access your local workspace, and backing up important work.</p>
    </section>

    <section id="your-content">
      <h2>Your accounts and content</h2>
      <p>You retain responsibility for your content and connected accounts. Only provide data you have permission to access or modify, and use Carole.ai in accordance with applicable law and the terms of connected services.</p>
    </section>

    <section id="agent-actions">
      <h2>Agent actions</h2>
      <p>AI output can be incomplete or incorrect. Review proposed actions before approval—especially messages, file changes, account changes, and actions affecting external systems. You remain responsible for actions you approve or configure the software to perform.</p>
    </section>

    <section id="third-parties">
      <h2>Third-party services</h2>
      <p>Carole.ai can connect to Google Workspace, independent AI providers, and other integrations. Those services have their own terms, privacy practices, availability, and quotas. Some requests send data to those services; our <a href="/privacy/">Privacy Policy</a> explains the main data flows.</p>
    </section>

    <section id="availability">
      <h2>Availability and warranties</h2>
      <p className={styles.notice}>The website and software are provided on an “as is” and “as available” basis to the extent permitted by law. We do not promise uninterrupted or error-free operation. Independently review AI-generated results before relying on them.</p>
    </section>

    <section id="changes">
      <h2>Changes and contact</h2>
      <p>We may update these terms as Carole.ai evolves. The effective date above identifies the current version. Questions can be sent to <a href="mailto:support.carole.ai@gmail.com">support.carole.ai@gmail.com</a>.</p>
    </section>
  </LegalPage>;
}
