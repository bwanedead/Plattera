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
          <details className={styles.panel}>
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
                <div className={styles.downloadImages}>
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
                <div className={styles.downloadImages}>
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
                      className={styles.tallImage}
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
                      src="/assets/images/screenshots/api_key/copy_api_key_eighth.png"
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
                <div className={styles.stepImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/api_key/in_app_set_api_key_button_nineth.png"
                      alt="Plattera API key button highlighted"
                    />
                    <figcaption>Open the API key entry dialog.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/api_key/paste_key_then_save_tenth.png"
                      alt="Paste API key and save"
                    />
                    <figcaption>Paste the key and save.</figcaption>
                  </figure>
                </div>
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
            <summary className={styles.summary}>Image to Text Workspace</summary>
            <div className={styles.panelBody}>
              <p className={styles.lead}>
                The Image to Text workspace turns uploaded imagery into editable
                draft text and ties each run to dossiers for review.
              </p>

              <div className={styles.stepGroup}>
                <h3>Entry point</h3>
                <p>Start from the Image to Text card on the home screen.</p>
                <div className={styles.stepImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/image_to_text/home_page_image_to_text_card_first.png"
                      alt="Home page Image to Text card"
                    />
                    <figcaption>Open the Image to Text workspace.</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Workspace layout</h3>
                <p>
                  The workspace is split into the Control Panel, Dossier Manager,
                  and Results Viewer.
                </p>
                <div className={styles.downloadImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/image_to_text/full_workspace_control_panel_circled_second.png"
                      alt="Control panel highlighted in Image to Text workspace"
                    />
                    <figcaption>Control Panel (left).</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/image_to_text/full_workspace_dossier_manager_circled_third.png"
                      alt="Dossier manager highlighted in Image to Text workspace"
                    />
                    <figcaption>Dossier Manager (middle).</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/image_to_text/full_workspace_results_viewer_circled_fourth.png"
                      alt="Results viewer highlighted in Image to Text workspace"
                    />
                    <figcaption>Results Viewer (right).</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Control Panel: import + model</h3>
                <ol className={styles.steps}>
                  <li>Import one or more image files.</li>
                  <li>Select an AI model for extraction.</li>
                  <li>Choose the extraction mode that matches the document type.</li>
                  <li>Add optional instructions if you need custom guidance.</li>
                </ol>
                <div className={styles.downloadImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/image_to_text/control_panel_import_files.png"
                      alt="Import files area in control panel"
                    />
                    <figcaption>Import files.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/image_to_text/control_panel_ai_model_selection.png"
                      alt="AI model selection in control panel"
                    />
                    <figcaption>Select the model.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/image_to_text/control_panel_extraction_mode.png"
                      alt="Extraction mode selection in control panel"
                    />
                    <figcaption>Choose the extraction mode.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/image_to_text/control_panel_add_instruction.png"
                      alt="Add instruction option in control panel"
                    />
                    <figcaption>Add an optional instruction.</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Control Panel: dossier association</h3>
                <p>
                  Attach the run to an existing dossier, or let Plattera create
                  a new one. You can also target a specific segment.
                </p>
                <div className={styles.stepImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/image_to_text/control_panel_dossier_association.png"
                      alt="Dossier association selection in control panel"
                    />
                    <figcaption>Associate with a dossier and segment.</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Control Panel: enhancement + redundancy</h3>
                <ol className={styles.steps}>
                  <li>Use Image Enhancement to improve contrast and clarity.</li>
                  <li>Enable Redundancy to run multiple drafts for comparison.</li>
                  <li>Enable LLM Consensus to generate a merged draft from redundancy.</li>
                </ol>
                <div className={styles.downloadImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/image_to_text/control_panel_image_enhancement.png"
                      alt="Image enhancement settings"
                    />
                    <figcaption>Image enhancement presets.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/image_to_text/control_panel_redundancy_selection.png"
                      alt="Redundancy filter controls"
                    />
                    <figcaption>Redundancy filter settings.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/image_to_text/control_panel_enable_llm_consensus.png"
                      alt="Enable LLM consensus toggle"
                    />
                    <figcaption>LLM consensus (requires redundancy &gt; 1).</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Dossier Manager</h3>
                <p>
                  Each run appears under its dossier. Expand a dossier to browse
                  segments, runs, and drafts.
                </p>
                <div className={styles.downloadImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/image_to_text/full_workspace_dossier_manager_circled_third.png"
                      alt="Dossier manager panel"
                    />
                    <figcaption>Dossier list and navigation.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/image_to_text/dossier_manager_expanded_dossier_draft_layer_circled.png"
                      alt="Expanded dossier with draft layers"
                    />
                    <figcaption>Expanded run with draft layers.</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Results Viewer</h3>
                <p>
                  Review extracted text, JSON, normalized sections, and metadata.
                  Use the tray to edit, align, and set the final draft.
                </p>
                <div className={styles.downloadImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/image_to_text/full_workspace_results_viewer_circled_fourth.png"
                      alt="Results viewer panel"
                    />
                    <figcaption>Text and metadata tabs.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/image_to_text/results_viewer_menu_tray.png"
                      alt="Results viewer tool tray"
                    />
                    <figcaption>Edit, align, and finalize from the tray.</figcaption>
                  </figure>
                </div>
                <ul className={styles.steps}>
                  <li>
                    Edit mode lets you make changes and save back into the draft.
                  </li>
                  <li>
                    Alignment is available when redundancy is enabled (2+ drafts).
                  </li>
                  <li>
                    Select Final marks the chosen draft for the active segment.
                  </li>
                </ul>
              </div>
            </div>
          </details>
          <details className={styles.panel}>
            <summary className={styles.summary}>Text to Schema Workspace</summary>
            <div className={styles.panelBody}>
              <p className={styles.lead}>
                This workspace converts finalized text into structured schema output and
                gives you tools to validate, edit, and map the result.
              </p>

              <div className={styles.stepGroup}>
                <h3>Entry point</h3>
                <div className={styles.stepImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/text_to_schema/home_page_text_to_schema_card_first.png"
                      alt="Home page Text to Schema card"
                    />
                    <figcaption>Open Text to Schema from the home screen.</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Workspace layout</h3>
                <p>
                  The workspace is split into the Control Panel, Schema Manager,
                  and Results Viewer.
                </p>
                <div className={styles.downloadImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/text_to_schema/full_workspace_control_panel_circled.png"
                      alt="Text to Schema control panel highlighted"
                    />
                    <figcaption>Control Panel (left).</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/text_to_schema/full_workspace_schema_manager_circled.png"
                      alt="Text to Schema schema manager highlighted"
                    />
                    <figcaption>Schema Manager (middle).</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/text_to_schema/full_workspace_results_viewer_circled.png"
                      alt="Text to Schema results viewer highlighted"
                    />
                    <figcaption>Results Viewer (right).</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Control Panel: input source</h3>
                <ol className={styles.steps}>
                  <li>Select whether you want to use a finalized dossier or direct text.</li>
                  <li>For finalized dossiers, choose a snapshot to load.</li>
                  <li>For direct input, paste or type the text.</li>
                </ol>
                <div className={styles.downloadImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/text_to_schema/control_panel_input_source_selection.png"
                      alt="Input source selection in control panel"
                    />
                    <figcaption>Choose finalized dossier or direct input.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/text_to_schema/control_panel_choose_finalized_dossier.png"
                      alt="Choose finalized dossier dropdown"
                    />
                    <figcaption>Select a finalized dossier snapshot.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/text_to_schema/control_panel_direct_text_input_view.png"
                      alt="Direct text input view"
                    />
                    <figcaption>Paste or type direct text.</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Schema Manager</h3>
                <p>
                  Use the Schema Manager to browse schema versions and switch between
                  saved outputs.
                </p>
                <div className={styles.stepImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/text_to_schema/schema_manager_version_pills_highlighted.png"
                      alt="Schema manager version pills highlighted"
                    />
                    <figcaption>Version pills show schema lineage.</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Results Viewer: Field View</h3>
                <p>
                  Field View organizes the schema into readable sections and flags
                  quality check advisories.
                </p>
                <div className={styles.downloadImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/text_to_schema/results_viewer_field_view_tab_edit_in_json_button.png"
                      alt="Field view edit in JSON button"
                    />
                    <figcaption>Edit in JSON when you need structured edits.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/text_to_schema/results_viewer_field_view_tab_draw_button.png"
                      alt="Field view draw button"
                    />
                    <figcaption>Open the draw tools from Field View.</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Draw viewer</h3>
                <p>
                  The draw viewer lets you map parcels and verify geometry against
                  the schema output.
                </p>
                <div className={styles.downloadImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/text_to_schema/draw_viewer_map_button_circled.png"
                      alt="Draw viewer map button highlighted"
                    />
                    <figcaption>Launch the draw viewer.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/text_to_schema/draw_viewer_window.png"
                      alt="Draw viewer window"
                    />
                    <figcaption>Review geometry in the draw viewer.</figcaption>
                  </figure>
                </div>
              </div>

              <div className={styles.stepGroup}>
                <h3>Results Viewer: JSON tab</h3>
                <p>
                  Use the JSON tab for detailed schema edits and save a v2 output.
                </p>
                <div className={styles.downloadImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/text_to_schema/results_viewer_json_tab_edit_button.png"
                      alt="JSON tab edit button"
                    />
                    <figcaption>Enter JSON edit mode.</figcaption>
                  </figure>
                  <figure>
                    <img
                      src="/assets/images/screenshots/text_to_schema/results_viewer_json_tab_edit_mode_savev2_button.png"
                      alt="JSON tab save v2 button"
                    />
                    <figcaption>Save v2 when edits are complete.</figcaption>
                  </figure>
                </div>
              </div>
            </div>
          </details>
          <details className={styles.panel}>
            <summary className={styles.summary}>Map Workspace</summary>
            <div className={styles.panelBody}>
              <p className={styles.lead}>
                The map workspace handles spatial overlays, measurements, and parcel context.
              </p>
              <div className={styles.stepGroup}>
                <h3>Entry point</h3>
                <div className={styles.stepImages}>
                  <figure>
                    <img
                      src="/assets/images/screenshots/mapping/home_page_mapping_card_first.png"
                      alt="Home page Map workspace card"
                    />
                    <figcaption>Open the map workspace from home.</figcaption>
                  </figure>
                </div>
              </div>
              <p className={styles.note}>More detailed guidance coming soon.</p>
            </div>
          </details>
          <details className={styles.panel}>
            <summary className={styles.summary}>PLSS Data Download</summary>
            <div className={styles.panelBody}>
              <p className={styles.lead}>
                Plattera will prompt you to download PLSS data when it is required.
              </p>
              <div className={styles.stepImages}>
                <figure>
                  <img
                    src="/assets/images/screenshots/plss_downloader/map_screen_plss_download_prompt.png"
                    alt="PLSS download prompt in map workspace"
                  />
                  <figcaption>Follow the prompt to start the PLSS download.</figcaption>
                </figure>
              </div>
              <p className={styles.note}>
                More detailed guidance coming soon.
              </p>
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
