import styles from "./page.module.css";

export default function Home() {
  return (
    <div className={styles.page}>
      <main className={styles.hero}>
        <div className={styles.brandRow}>
          <img
            className={styles.logo}
            src="/assets/images/app_logo.png"
            alt="Plattera logo"
          />
          <h1>
            Plattera<span className={styles.dot}>.</span>
          </h1>
        </div>
        <a className={styles.primaryButton} href="/download">
          Get Plattera
        </a>
      </main>
    </div>
  );
}
