"use client";

import LandingPage from "@/components/LandingPage";
import { useRef, useState } from "react";
import styles from "./page.module.css";

const localApp = "http://127.0.0.1:8000/";

export default function HostedLandingPage() {
  const dialog = useRef<HTMLDialogElement>(null);
  const [copyStatus, setCopyStatus] = useState("");
  const openLocalApp = () => {
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
        <button className={styles.close} onClick={() => dialog.current?.close()} aria-label="Close setup instructions" autoFocus>×</button>
        <span className={styles.eyebrow}>YOUR WORKSPACE, ON YOUR COMPUTER</span>
        <h2 id="local-workspace-title">Start Carole.ai to sign in</h2>
        <p>This website introduces Carole.ai. Your account and workspace live in the app running on your computer.</p>
        <ol className={styles.steps}>
          <li><strong>Install and start the app</strong><p>On your computer, open a terminal with Python and pip installed, then run:</p>
            <pre><code>{"pip install carole.ai\ncaroleai"}</code></pre>
            <button className={styles.copy} onClick={copyCommands}>Copy commands</button>
            <span className={styles.status} role="status">{copyStatus}</span>
          </li>
          <li><strong>Open your workspace</strong><p>Keep the terminal running. Once Carole.ai is ready, open your workspace to sign in or create a local account.</p></li>
        </ol>
        <a className={styles.launch} href={localApp} target="_blank" rel="noopener noreferrer">Open local workspace ↗</a>
        <p className={styles.hint}>Opens 127.0.0.1:8000 in a new tab. If it says “Unable to connect” or “Connection refused,” run <code>caroleai</code> on this same computer and try again. If you chose a different port, use the address printed in your terminal.</p>
      </dialog>
    </>
  );
}
