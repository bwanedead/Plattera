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
              <p className={styles.lead}>
                Download <a href="/download">here</a>. Click the
                <strong> Download for Windows </strong>
                button, then run the installer once it finishes downloading.
              </p>
              <div className={styles.divider} />
              <p className={styles.lead}>
                Windows may show a protection screen because Plattera is not
                signed by a recognized publisher yet. This is expected for now.
              </p>
              <div className={styles.stepGroup}>
                <h3>Windows protection prompt</h3>
                <p>
                  Click <strong>More info</strong>, then select{" "}
                  <strong>Run anyway</strong> to continue the installer.
                </p>
                <div className={styles.stepImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/installation/install_windows_protected_machine_screen_more_info_arrow_first.png"
                      alt="Windows protected your PC screen with More info highlighted"
                    />
                    <figcaption>Step 1: Click More info.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/installation/install_windows_protected_machine_run_anyway_arrow_second.png"
                      alt="Windows protected your PC screen with Run anyway highlighted"
                    />
                    <figcaption>Step 2: Click Run anyway.</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Installer flow</h3>
                <p>
                  Follow the standard installer steps. Screenshots are included
                  for reference.
                </p>
                <div className={styles.stepImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/installation/welcome_plattera_setup_arrow_third.png"
                      alt="Plattera setup welcome screen with Next highlighted"
                    />
                    <figcaption>Welcome screen.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/installation/install_choose_location_arrow_fourth.png"
                      alt="Choose install location screen with Next highlighted"
                    />
                    <figcaption>
                      Use the default path (`C:\Users\your profile\AppData\Local\Plattera`)
                      unless you need a custom location.
                    </figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/installation/install_completed_fifth.png"
                      alt="Installer completed screen"
                    />
                    <figcaption>
                      Let the installation complete, then click Next.
                    </figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/installation/install_finish_sixth.png"
                      alt="Finish setup screen with optional selections"
                    />
                    <figcaption>
                      Finish the installation and optionally choose to run
                      Plattera immediately and add a desktop shortcut.
                    </figcaption>
                  </figure>
                </div>
              </div>
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
