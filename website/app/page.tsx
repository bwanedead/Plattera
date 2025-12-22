import styles from "./page.module.css";

export default function Home() {
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
        <div className={styles.heroTitle}>
          <h1>
            Plattera<span className={styles.dot}>.</span>
          </h1>
          <a className={styles.primaryButton} href="/download">
            Get Plattera
          </a>
        </div>
      </main>
    </div>
  );
}
