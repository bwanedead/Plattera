import styles from "./page.module.css";

const releaseUrl = "https://github.com/ORG/REPO/releases";
const latestDownloadUrl = "https://github.com/ORG/REPO/releases/latest";

export default function DownloadPage() {
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
        </nav>
      </header>

      <main className={styles.hero}>
        <h1>Download Plattera</h1>
        <p className={styles.note}>Windows build.</p>
        <div className={styles.actions}>
          <a className={styles.primaryButton} href={latestDownloadUrl}>
            <span className={styles.buttonIcon} aria-hidden="true">
              <svg viewBox="0 0 24 24" focusable="false">
                <path d="M2.5 4.5 11 3v8H2.5V4.5ZM13 2.7 21.5 1v10H13V2.7ZM2.5 13H11v8l-8.5-1.5V13ZM13 13h8.5v10L13 21.3V13Z" />
              </svg>
            </span>
            Download for Windows
          </a>
        </div>
        <p className={styles.helper}>Download begins on click.</p>
      </main>
    </div>
  );
}
