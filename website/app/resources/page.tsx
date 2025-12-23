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
              <div className={styles.stepGroup}>
                <h3>Open the OpenAI API page</h3>
                <ol className={styles.steps}>
                  <li>
                    Go to{" "}
                    <a href="https://openai.com/api/" target="_blank" rel="noreferrer">
                      https://openai.com/api/
                    </a>
                    .
                  </li>
                  <li>Click Log in (top-right).</li>
                  <li>If prompted, choose API Platform.</li>
                </ol>
                <div className={styles.stepImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/api_key/open_ai_api_landing_page_click_login_first.png"
                      alt="OpenAI API landing page with Log in highlighted"
                    />
                    <figcaption>Open the API page and click Log in.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/api_key/click_api_platform_second.png"
                      alt="API Platform selector highlighted"
                    />
                    <figcaption>Select API Platform if prompted.</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Sign in or create an account</h3>
                <ol className={styles.steps} start={4}>
                  <li>Enter your email and click Continue, or choose Sign up.</li>
                  <li>Finish login with your provider (Google, Apple, Microsoft, etc.).</li>
                </ol>
                <div className={styles.stepImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/api_key/sign_up_or_login_third.png"
                      alt="OpenAI sign in or sign up screen"
                    />
                    <figcaption>Complete the sign-in or sign-up flow.</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Optional: Create a Plattera project</h3>
                <ol className={styles.steps} start={6}>
                  <li>In the API Platform, open Settings.</li>
                  <li>Under Organization, open Projects.</li>
                  <li>Click Create project and name it Plattera.</li>
                </ol>
                <p className={styles.note}>
                  If you skip this, you can still create a key without a project.
                </p>
              </div>

              <div className={styles.stepGroup}>
                <h3>Set up billing</h3>
                <ol className={styles.steps} start={9}>
                  <li>In Settings, open Billing.</li>
                  <li>Add a payment method or prepaid credits.</li>
                </ol>
                <p className={styles.note}>
                  If billing is not set up, API requests can fail until funding is active.
                </p>
                <div className={styles.stepImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/api_key/click_billing_fourth.png"
                      alt="OpenAI billing section highlighted"
                    />
                    <figcaption>Open Billing to add a payment method.</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Create the API key</h3>
                <ol className={styles.steps} start={11}>
                  <li>In Settings, open API keys.</li>
                  <li>Click Create new secret key.</li>
                  <li>
                    Name it (example: My Plattera key), select the Plattera project if
                    created, and keep permissions as All.
                  </li>
                  <li>Create the key, then copy and save it immediately.</li>
                </ol>
                <div className={styles.stepImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/api_key/click_api_keys_fifth.png"
                      alt="API keys menu highlighted"
                    />
                    <figcaption>Open the API keys page.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/api_key/create_new_secret_key_sixth.png"
                      alt="Create new secret key button highlighted"
                    />
                    <figcaption>Create a new secret key.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/api_key/name_and_create_secret_key_seventh.png"
                      alt="Name and create secret key dialog"
                    />
                    <figcaption>Name the key and create it.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/api_key/copy_api_key_eighth%20.png"
                      alt="Copy API key dialog"
                    />
                    <figcaption>Copy and save the key immediately.</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Use the key in Plattera</h3>
                <ol className={styles.steps} start={15}>
                  <li>Open Plattera and find the OpenAI API Key field.</li>
                  <li>Paste the key and save/apply.</li>
                </ol>
              </div>

              <div className={styles.stepGroup}>
                <h3>Safety notes</h3>
                <ul className={styles.steps}>
                  <li>Do not share your API key publicly.</li>
                  <li>Do not commit the key to GitHub.</li>
                  <li>
                    If Plattera reports quota or billing errors, return to Settings &gt;
                    Billing and confirm funding is active.
                  </li>
                </ul>
              </div>
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
