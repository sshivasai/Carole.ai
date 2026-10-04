import styles from "./LegalPage.module.css";
import Image from "next/image";
import Link from "next/link";

type LegalPageProps = {
  children: React.ReactNode;
  title: string;
  summary: string;
  sections: { id: string; label: string }[];
};

export default function LegalPage({ children, title, summary, sections }: LegalPageProps) {
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/" aria-label="Carole.ai home"><Image src="/branding/logo-horizontal-dark.png" alt="Carole.ai" width={142} height={50} /></Link>
        <Link className={styles.back} href="/">← Back to home</Link>
      </header>
      <div className={styles.shell}>
        <div className={styles.hero}>
          <span className={styles.eyebrow}>Carole.ai · Legal</span>
          <h1>{title}</h1>
          <p className={styles.summary}>{summary}</p>
          <p className={styles.updated}>Effective October 4, 2026</p>
        </div>
        <div className={styles.body}>
          <nav className={styles.nav} aria-label={`${title} sections`}>
            <span>On this page</span>
            {sections.map(section => <a key={section.id} href={`#${section.id}`}>{section.label}</a>)}
          </nav>
          <article className={styles.content}>{children}</article>
        </div>
      </div>
      <footer className={styles.footer}><span>Carole.ai · Local-first by design</span><a href="/privacy/">Privacy</a><a href="/terms/">Terms</a></footer>
    </main>
  );
}
