## Plattera Desktop Build Process (Windows, v0.9.0+)

This document describes the **end‑to‑end build flow** for the Plattera desktop app on Windows, including the **PyInstaller sidecar** and the **Tauri bundles**. It is meant as a repeatable template so future releases don’t have to rediscover the steps or flags.

---

### 1. Prerequisites

- **Repository root**: `C:\projects\Plattera`
- **Python venv**:

```powershell
cd C:\projects\Plattera
.\.venv\scripts\activate.ps1
```

- **Backend dependencies** installed via `pip install -r backend\requirements.txt`.
- **Frontend / Tauri toolchain** already set up (`npm install` under `frontend`, Rust toolchain installed, etc.).

---

### 2. Build the backend sidecar (PyInstaller)

From the `backend` directory, build the frozen backend executable that Tauri will treat as a **sidecar**.

- **Directory**: `C:\projects\Plattera\backend`
- **Command (single line, avoids PowerShell parsing issues)**:

```powershell
cd C:\projects\Plattera\backend
pyinstaller --noconfirm --onefile --name plattera-backend --hidden-import openai --hidden-import services.llm.openai --add-data "schema\plss_m_and_b.json;backend/schema" main.py
```

- **Key flags and why they matter**:
  - **`--onefile`**: produces a single EXE suitable for Tauri sidecar bundling.
  - **`--name plattera-backend`**: matches the logical sidecar name in `tauri.conf.json` and `src-tauri/src/lib.rs`.
  - **`--hidden-import openai`** and **`--hidden-import services.llm.openai`**:
    - Ensures the **OpenAI client library** and the **Plattera OpenAI LLM service module** are included in the frozen EXE.
    - Without these, the EXE can start but will “lose” the OpenAI service and models like `gpt-o4-mini`.
  - **`--add-data "schema\plss_m_and_b.json;backend/schema"`**:
    - Packages the PLSS schema file into the bundle.
    - The `;backend/schema` part defines the **target path inside the bundle**, which the code expects.

- **Expected output**:
  - PyInstaller creates `backend\dist\plattera-backend.exe` (the sidecar binary).

---

### 3. Copy the sidecar into the Tauri `bin` directory

Tauri expects platform‑specific sidecar filenames under `frontend\src-tauri\bin`. For Windows x86_64, we need:

- `plattera-backend-x86_64-pc-windows-msvc.exe` (required for Tauri to bundle and spawn).
- Optionally: `plattera-backend.exe` for manual debugging.

From the project root, run:

```powershell
cd C:\projects\Plattera

Copy-Item "backend\dist\plattera-backend.exe" "frontend\src-tauri\bin\plattera-backend-x86_64-pc-windows-msvc.exe" -Force
Copy-Item "backend\dist\plattera-backend.exe" "frontend\src-tauri\bin\plattera-backend.exe" -Force
```

- **Important**:
  - The logical sidecar name used in Rust (`sidecar("plattera-backend")`) and in `tauri.conf.json` (`"externalBin": ["bin/plattera-backend"]`) must align with this file.
  - The `-x86_64-pc-windows-msvc.exe` suffix is how Tauri’s bundler locates the correct binary for the platform.

---

### 4. Build the Tauri desktop bundles

With the sidecar copied into `src-tauri\bin`, build the actual desktop bundles (NSIS installer, ZIP, etc.).

- **Directory**: `C:\projects\Plattera\frontend`
- **Command**:

```powershell
cd C:\projects\Plattera\frontend
npm run tauri:build
```

- **Expected output directory**:
  - `frontend\src-tauri\target\release\bundle\`
    - `nsis\Plattera_\<version>_x64-setup.exe`
    - `msi\Plattera_\<version>_x64_en-US.msi` (if enabled)
    - `Plattera_\<version>_windows_x86_64.zip`
    - `Plattera_\<version>_windows_x86_64.zip.sig`
    - `latest.json`

For v0.9.0 we specifically cared about:

- **Installer**: `nsis\Plattera_0.9.0_x64-setup.exe`
- **Update assets**:
  - `Plattera_0.9.0_windows_x86_64.zip`
  - `Plattera_0.9.0_windows_x86_64.zip.sig`
  - `latest.json`

---

### 5. Create ZIP, updater signature, and `latest.json`

After `npm run tauri:build` completes, we prepare the **update payload** that the Tauri updater consumes:

- The **ZIP** that contains the app bundle.
- The **`.sig` signature** for that ZIP.
- The **`latest.json` manifest** in the `releases/` folder (fetched via `raw.githubusercontent.com`).

All of this happens under:

- `frontend\src-tauri\target\release\bundle\`
- `releases\latest.json` (at the repo root)

#### 5.1 Set the signing password variable

In PowerShell, we use a `$pw` variable for the **Tauri updater signing key password**. Do **not** commit the real password; set it only in your local session:

```powershell
# Example – set this per-session; do NOT commit your real password anywhere
$pw = "<your-tauri-signing-password>"
```

You can also use a more secure pattern (like `Read-Host -AsSecureString`) if you prefer, as long as the value ends up passed to the signer command.

#### 5.2 Create (or confirm) the ZIP bundle

Tauri already produces a ZIP at:

- `frontend\src-tauri\target\release\bundle\Plattera_<version>_windows_x86_64.zip`

For v0.9.0 this is:

- `frontend\src-tauri\target\release\bundle\Plattera_0.9.0_windows_x86_64.zip`

If you ever need to recreate it manually (for example from the NSIS/other artifacts), you can use:

```powershell
cd C:\projects\Plattera\frontend\src-tauri\target\release\bundle
Compress-Archive -Path "nsis\Plattera_0.9.0_x64-setup.exe" -DestinationPath "Plattera_0.9.0_windows_x86_64.zip" -Force
```

Most of the time the ZIP from `npm run tauri:build` is sufficient and does not need to be re-created.

#### 5.3 Generate the updater `.sig` for the ZIP

Use the Tauri signer to generate the **updater signature** for the ZIP. The exact private key location/flags may vary; the important pattern is:

```powershell
cd C:\projects\Plattera\frontend\src-tauri\target\release\bundle

# Template – adapt <...> placeholders to your local key setup
npx tauri signer sign "Plattera_0.9.0_windows_x86_64.zip" `
  --private-key "<path-or-env-for-your-tauri-private-key>" `
  --password $pw `
  --output "Plattera_0.9.0_windows_x86_64.zip.sig"
```

- This produces `Plattera_0.9.0_windows_x86_64.zip.sig` containing the base64 signature string.
- The same signature string is also what goes into `latest.json` as the `signature` field.

#### 5.4 Update `releases\latest.json`

The updater endpoint in `frontend\src-tauri\tauri.conf.json` points to:

- `https://raw.githubusercontent.com/bwanedead/Plattera/main/releases/latest.json`

So the repo’s `releases\latest.json` file is the **single source of truth** for updates. Its structure (for v0.9.0) looks like:

```json
{
  "version": "0.9.0",
  "notes": "",
  "pub_date": "2025-11-25T00:00:00Z",
  "platforms": {
    "windows-x86_64": {
      "signature": "BASE64_SIGNATURE_FROM_.SIG",
      "url": "https://github.com/bwanedead/Plattera/releases/download/v0.9.0/Plattera_0.9.0_windows_x86_64.zip"
    }
  }
}
```

- **`version`**: must match the app version you just built (e.g. `0.9.0`).
- **`pub_date`**: ISO‑8601 timestamp of the release.
- **`signature`**: paste the base64 string from `Plattera_0.9.0_windows_x86_64.zip.sig`.
- **`url`**: direct GitHub Releases asset URL for the ZIP you will upload.

Workflow:

1. Open `releases\latest.json`.
2. Bump `version`, `pub_date`, and the `url` (to the new versioned ZIP).
3. Generate the `.sig` file for that ZIP and paste its base64 contents into `signature`.
4. Commit and push `releases\latest.json` so `raw.githubusercontent.com` serves the new metadata.

#### 5.5 Sanity check (local artifacts are present)

Before touching GitHub, confirm **all required files exist on disk** for this version.

From the repo root:

```powershell
cd C:\projects\Plattera

$paths = @(
  "frontend\src-tauri\target\release\bundle\nsis\Plattera_0.9.0_x64-setup.exe",
  "frontend\src-tauri\target\release\bundle\Plattera_0.9.0_windows_x86_64.zip",
  "frontend\src-tauri\target\release\bundle\Plattera_0.9.0_windows_x86_64.zip.sig",
  "releases\latest.json"
)

$paths | ForEach-Object {
  "{0} : {1}" -f $_, (Test-Path $_)
}
```

You should see `True` for **all** of the above. If any are `False`, fix that step (rebuild, re‑zip, re‑sign, or update `releases\latest.json`) before continuing.

#### 5.6 Sanity check: verify `latest.json` and updater payload

Before shipping, validate that the remote `latest.json` matches what you expect:

```powershell
Invoke-WebRequest "https://raw.githubusercontent.com/bwanedead/Plattera/main/releases/latest.json" |
  Select-Object -ExpandProperty Content
```

Confirm:

- `version` is correct.
- `url` points to the new GitHub Releases ZIP.
- `signature` is populated (non‑empty).

You can also quickly validate the ZIP is reachable (after uploading it to the GitHub Release) with:

```powershell
Invoke-WebRequest "https://github.com/bwanedead/Plattera/releases/download/v0.9.0/Plattera_0.9.0_windows_x86_64.zip" -Method Head
```

Expect a `StatusCode` of `200`.

---

### 6. Publish / update the GitHub Release

For each released version (e.g., `v0.9.0`):

- Create or update a **GitHub Release** tagged with that version.
- Upload the following as release assets:
  - **NSIS installer**: `Plattera_0.9.0_x64-setup.exe`
  - **ZIP bundle**: `Plattera_0.9.0_windows_x86_64.zip`
  - **Signature**: `Plattera_0.9.0_windows_x86_64.zip.sig`

> Note: The **manifest** is `releases\latest.json` in the repo, served via `raw.githubusercontent.com`, so it does **not** need to be uploaded as a separate release asset.

---

### 7. Post‑install sanity checks

After installing the NSIS build on Windows:

- **Verify backend auto‑start**

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen
```

- Expect a listener on `127.0.0.1:8000` attributed to `plattera-backend.exe` **without** manually running the EXE.

- **Smoke‑test the app**
  - Run **Image → Text** using `gpt-o4-mini` and confirm a response.
  - Open **Dossier Manager** and verify it lists / loads dossiers.
  - Open the **Logs** panel in the UI and confirm it can load recent backend logs.

- **Updater check**
  - Use the in‑app **“Check for Updates”** button.
  - Expected behavior:
    - If current version matches `latest.json`: message like “You are up to date.”
    - If a newer version exists (and `latest.json` points to it): updater prompts to download/apply the update.

---

### 8. Notes for development vs. build

- **Development (no sidecar)**:
  - Start backend directly:

    ```powershell
    cd C:\projects\Plattera\backend
    python main.py
    ```

  - Then in another terminal:

    ```powershell
    cd C:\projects\Plattera\frontend
    npm run tauri:dev
    ```

  - Tauri detects the backend already listening on port 8000 and **does not spawn the sidecar**.

- **Release / installed build**:
  - Tauri **spawns the PyInstaller sidecar** (`plattera-backend`) on demand.
  - All OpenAI and PLSS behavior depends on the PyInstaller command above being kept in sync with the backend code (hidden imports, data files, etc.).

Keep this document updated whenever:

- The PyInstaller command changes (new hidden imports, added data files, etc.).
- The updater endpoint format changes.
- The sidecar naming or Tauri configuration changes.


