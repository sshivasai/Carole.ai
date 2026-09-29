import styles from "./LegalPage.module.css";

type LegalPageProps = { children: React.ReactNode; title: string };

export default function LegalPage({ children, title }: LegalPageProps) {
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <a className={styles.brand} href="/">carole.ai</a>
        <a className={styles.back} href="/">Back to home</a>
      </header>
      <article className={styles.content}>
        <h1>{title}</h1>
        <p className={styles.updated}>Effective September 28, 2026</p>
        {children}
      </article>
    </main>
  );
}
