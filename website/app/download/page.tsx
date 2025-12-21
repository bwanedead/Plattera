import styles from "./page.module.css";

const releaseUrl = "https://github.com/ORG/REPO/releases";
const latestDownloadUrl = "https://github.com/ORG/REPO/releases/latest";

export default function DownloadPage() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <img
            className={styles.logo}
            src="/assets/images/logo.png"
            alt="Plattera logo"
          />
          <span className={styles.brandName}>Plattera</span>
        </div>
        <a className={styles.secondaryButton} href="/">
          Back to Home
        </a>
      </header>

      <main className={styles.hero}>
        <h1>Download Plattera</h1>
        <p>Grab the latest build or review previous releases on GitHub.</p>
        <div className={styles.actions}>
          <a className={styles.primaryButton} href={latestDownloadUrl}>
            Download Latest
          </a>
          <a className={styles.secondaryButton} href={releaseUrl}>
            View All Releases
          </a>
        </div>
      </main>
    </div>
  );
}
