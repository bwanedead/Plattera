"use client";

import { useState } from "react";
import styles from "./page.module.css";

export default function ContactPage() {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText("contact@plattera.net");
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <a className={styles.brand} href="/">
          <span className={styles.brandName}>
            Plattera<span className={styles.dot}>.</span>
          </span>
        </a>
        <nav className={styles.nav}>
          <a href="/download">Download</a>
          <a href="/resources">Resources</a>
          <a href="/contact">Contact</a>
        </nav>
      </header>

      <main className={styles.hero}>
        <h1>Contact</h1>
        <p className={styles.note}>
          Reach us directly for product questions, support, or partnerships.
        </p>
        <div className={styles.card}>
          <p className={styles.label}>Primary contact</p>
          <div className={styles.emailRow}>
            <a className={styles.email} href="mailto:contact@plattera.net">
              contact@plattera.net
            </a>
            <button
              className={styles.secondaryButton}
              type="button"
              onClick={handleCopy}
              aria-label="Copy email address"
              title="Copy email address"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M9 9a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-8a2 2 0 0 1-2-2V9Zm2-1a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V9a1 1 0 0 0-1-1h-8ZM4 5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1h-2V5a1 1 0 0 0-1-1H6a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h1v2H6a2 2 0 0 1-2-2V5Z" />
              </svg>
            </button>
          </div>
          <div className={styles.actions}>
            <a className={styles.primaryButton} href="mailto:contact@plattera.net">
              Email Plattera
            </a>
          </div>
        </div>
        <p className={styles.copyStatus} aria-live="polite">
          {copied ? "Email copied to clipboard." : ""}
        </p>
        <p className={styles.helper}>
          For support, use <span>help@plattera.net</span>.
        </p>
      </main>
    </div>
  );
}
