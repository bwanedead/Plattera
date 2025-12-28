import fs from "node:fs/promises";
import path from "node:path";
import styles from "./page.module.css";

const releaseUrl = "https://github.com/ORG/REPO/releases";
const latestFallbackUrl = "https://github.com/ORG/REPO/releases/latest";

type LatestRelease = {
  platforms?: {
    "windows-x86_64"?: {
      url?: string;
    };
  };
};

async function getLatestDownloadUrl() {
  try {
    const latestPath = path.resolve(process.cwd(), "..", "releases", "latest.json");
    const file = await fs.readFile(latestPath, "utf-8");
    const data = JSON.parse(file) as LatestRelease;
    return data.platforms?.["windows-x86_64"]?.url ?? latestFallbackUrl;
  } catch {
    return latestFallbackUrl;
  }
}

export default async function DownloadPage() {
  const latestDownloadUrl = await getLatestDownloadUrl();

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
