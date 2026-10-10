"use client";

import LandingPage from "@/components/LandingPage";
import { useRef, useState } from "react";
import { ArrowUpRight, Check, Copy, Terminal, X } from "lucide-react";
import styles from "./page.module.css";

const localApp = "http://127.0.0.1:8000/";

export default function HostedLandingPage() {
  const dialog = useRef<HTMLDialogElement>(null);
  const [copyStatus, setCopyStatus] = useState("");
  const openLocalApp = () => {
    setCopyStatus("");
    dialog.current?.showModal();
  };
  const copyCommands = async () => {
    try {
      await navigator.clipboard.writeText("pip install carole.ai\ncaroleai");
      setCopyStatus("Commands copied");
    } catch {
      setCopyStatus("Select and copy the commands below.");
    }
  };

  return (
    <>
      <LandingPage
        hosted
        onLaunchApp={openLocalApp}
        onSignIn={openLocalApp}
        onSignUp={openLocalApp}
      />
      <dialog ref={dialog} className={styles.dialog} aria-labelledby="local-workspace-title">
        <div className={styles.body}>
        <button className={styles.close} onClick={() => dialog.current?.close()} aria-label="Close setup instructions" autoFocus><X size={18} /></button>
        <div className={styles.badge}><Terminal size={15} /> Local workspace</div>
        <h2 id="local-workspace-title">Your workspace starts here.</h2>
        <p className={styles.intro}>Run Carole.ai on your computer, then sign in to your own workspace.</p>
        <ol className={styles.steps}>
          <li><span className={styles.number}>01</span><div><strong>Install &amp; run</strong><p>In a terminal with Python and pip installed:</p>
            <div className={styles.terminal}>
              <div className={styles.terminalHeader}><span><Terminal size={13} /> Terminal</span><button className={styles.copy} onClick={copyCommands}>{copyStatus === "Commands copied" ? <Check size={14} /> : <Copy size={14} />}{copyStatus === "Commands copied" ? "Copied" : "Copy"}</button></div>
              <pre><code>{"pip install carole.ai\ncaroleai"}</code></pre>
            </div>
            <span className={styles.status} role="status">{copyStatus}</span></div>
          </li>
          <li><span className={styles.number}>02</span><div><strong>Make yourself at home</strong><p>Keep the terminal running. Once the app is ready, open your workspace to sign in or create an account.</p></div></li>
        </ol>
        <details className={styles.help}><summary>Workspace won’t open?</summary><p>Run <code>caroleai</code> on this same computer and try again. If you chose a different port, use the address printed in your terminal.</p></details>
        </div>
        <div className={styles.footer}>
          <a className={styles.launch} href={localApp} target="_blank" rel="noopener noreferrer">Open local workspace <ArrowUpRight size={17} /></a>
          <p>127.0.0.1:8000 <span>·</span> Opens in a new tab</p>
        </div>
      </dialog>
    </>
  );
}
