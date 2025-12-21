import styles from "./page.module.css";

export default function Home() {
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
        <a className={styles.primaryButton} href="/download">
          Get Plattera
        </a>
      </header>

      <main className={styles.hero}>
        <h1>Plattera</h1>
        <p>Land intelligence, aligned and ready for action.</p>
      </main>
    </div>
  );
}
