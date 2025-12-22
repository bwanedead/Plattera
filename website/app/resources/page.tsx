import styles from "./page.module.css";

export default function ResourcesPage() {
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
        <h1>Resources</h1>
        <div className={styles.accordion}>
          <details className={styles.panel} open>
            <summary className={styles.summary}>Download &amp; Install</summary>
            <div className={styles.panelBody}>
              <p>Instructions will go here.</p>
            </div>
          </details>
          <details className={styles.panel}>
            <summary className={styles.summary}>API Key Setup</summary>
            <div className={styles.panelBody}>
              <p>Instructions will go here.</p>
            </div>
          </details>
          <details className={styles.panel}>
            <summary className={styles.summary}>Application Walkthrough</summary>
            <div className={styles.panelBody}>
              <p>Steps and usage details will go here.</p>
            </div>
          </details>
          <details className={styles.panel}>
            <summary className={styles.summary}>Full Tutorial Video</summary>
            <div className={styles.panelBody}>
              <p>Video embed placeholder.</p>
            </div>
          </details>
        </div>
      </main>
    </div>
  );
}
