## Plattera Desktop Version Update Checklist

This checklist covers everything that must be updated when cutting a **new desktop version** (for example, from `0.9.0` → `0.9.1`), so that:

- The **Tauri app** reports the new version (for the version badge and updater).
- The **updater manifest** (`releases/latest.json`) points to the correct ZIP and signature.
- The **GitHub Release** assets match what the updater expects.

Use `X.Y.Z` below as the placeholder for the new version (for example, `0.9.1`).

---

### 1) Decide the new version string

- **Version to release**: choose `X.Y.Z` (for example, `0.9.1`).

All subsequent steps must use this exact value:

- Tauri config (`tauri.conf.json`)
- Rust crate version (`Cargo.toml`)
- Frontend package version (`package.json`, optional but recommended)
- ZIP and `.sig` file names
- `releases/latest.json.version`
- GitHub Release tag and asset names

---

### 2) Update version numbers in the codebase

- **File**: `frontend/src-tauri/tauri.conf.json`
  - **Change**: set the `version` field to the new value.

  Example:

  ```4:5:frontend/src-tauri/tauri.conf.json
  "productName": "Plattera",
  "version": "0.9.1",
  ```

- **File**: `frontend/src-tauri/Cargo.toml`
  - **Change**: bump the `[package] version` to the same value.

  ```1:4:frontend/src-tauri/Cargo.toml
  [package]
  name = "app"
  version = "0.9.1"
  ```

- **File** (optional but recommended): `frontend/package.json`
  - **Change**: update the `"version"` field to keep JS tooling in sync.

  ```2:4:frontend/package.json
  "name": "plattera-frontend",
  "version": "0.9.1",
  ```

- **File** (optional but recommended): `frontend/package-lock.json`
  - **Change**: keep the lockfile’s root version in sync with `package.json`.
    In an npm v9 lockfile this appears in two places:
    - Top‑level `"version"` field
    - `packages[""].version` inside the `"packages"` map
  - Easiest way to keep this aligned is to bump `package.json` and then run
    `npm install` once so npm refreshes `package-lock.json` for you.

> **Note**: The desktop app’s runtime version (used by the **in‑app updater** and the bottom‑left **version badge**) ultimately comes from the Tauri app config / Rust crate, not `latest.json`. Bumping `tauri.conf.json` and `Cargo.toml` is mandatory for each release.

---

### 3) Build the backend sidecar (PyInstaller)

- **Directory**: `C:\projects\Plattera\backend`
- **Activate venv** (if not already):

  ```powershell
  cd C:\projects\Plattera
  .\.venv\scripts\activate.ps1
  ```

- **Build sidecar**:

  ```powershell
  cd C:\projects\Plattera\backend
  pyinstaller --noconfirm --onefile --name plattera-backend --hidden-import openai --hidden-import services.llm.openai --add-data "schema\plss_m_and_b.json;backend/schema" main.py
  ```

- **Expected output**:
  - `backend\dist\plattera-backend.exe`

---

### 4) Copy sidecar into Tauri `bin` directory

- **Still in** `C:\projects\Plattera\backend`:

  ```powershell
  Copy-Item ".\dist\plattera-backend.exe" "..\frontend\src-tauri\bin\plattera-backend-x86_64-pc-windows-msvc.exe" -Force
  Copy-Item ".\dist\plattera-backend.exe" "..\frontend\src-tauri\bin\plattera-backend.exe" -Force
  ```

- This ensures the Tauri bundler can find the correct sidecar binary for Windows x86_64.

---

### 5) Build the Tauri desktop app

- **Directory**: `C:\projects\Plattera\frontend`

```powershell
cd C:\projects\Plattera\frontend
npm run tauri:build
```

- **Expected output folder**:
  - `frontend\src-tauri\target\release\bundle\`
    - `nsis\Plattera_X.Y.Z_x64-setup.exe` (installer)
    - `Plattera_X.Y.Z_windows_x86_64.zip` (ZIP, once you create it)
    - `Plattera_X.Y.Z_windows_x86_64.zip.sig` (signature, after signing)
    - `latest.json` (intermediate manifest, if you generate it there)

---

### 6) Create the Windows ZIP for updater

- **Directory**: `C:\projects\Plattera\frontend`
- **Set a helper variable** (bundle root):

```powershell
cd C:\projects\Plattera\frontend

$rel = ".\src-tauri\target\release"
```

- **Create ZIP** (adjusting file list if your layout changes):

```powershell
Compress-Archive `
  -Path "$rel\app.exe","$rel\resources\*","$rel\plattera-backend.exe" `
  -DestinationPath "$rel\bundle\Plattera_X.Y.Z_windows_x86_64.zip" `
  -Force
```

For example, for `0.9.1`:

```powershell
Compress-Archive `
  -Path "$rel\app.exe","$rel\resources\*","$rel\plattera-backend.exe" `
  -DestinationPath "$rel\bundle\Plattera_0.9.1_windows_x86_64.zip" `
  -Force
```

> **Check** that the filenames (`app.exe`, `plattera-backend.exe`) match what `tauri build` actually produced. Update the paths if that ever changes.

---

### 7) Sign the ZIP with the Tauri updater key

- **Directory**: `C:\projects\Plattera\frontend`
- **Set your updater signing password in PowerShell** (do **not** commit this):

```powershell
$pw = "<your-tauri-signing-password>"
```

- **Generate `.sig`** for the new ZIP:

```powershell
npx tauri signer sign `
  --private-key-path C:\keys\plattera-updater.key `
  --password $pw `
  .\src-tauri\target\release\bundle\Plattera_0.9.1_windows_x86_64.zip
```

- This produces:
  - `Plattera_0.9.1_windows_x86_64.zip.sig` next to the ZIP.
  - The **public signature string** in the console (also contained in the `.sig` file).

---

### 8) Update `releases/latest.json` for the new version

The updater fetches:

- `https://raw.githubusercontent.com/bwanedead/Plattera/main/releases/latest.json`

So `releases/latest.json` at the repo root must describe the new version and point to the new ZIP.

- **Directory**: `C:\projects\Plattera\frontend`

```powershell
$bundle    = ".\src-tauri\target\release\bundle"
$signature = Get-Content "$bundle\Plattera_0.9.1_windows_x86_64.zip.sig" -Raw
$pub       = (Get-Date -Format s) + "Z"

@"
{
  "version": "0.9.1",
  "notes": "",
  "pub_date": "$pub",
  "platforms": {
    "windows-x86_64": {
      "signature": "$signature",
      "url": "https://github.com/bwanedead/Plattera/releases/download/v0.9.1/Plattera_0.9.1_windows_x86_64.zip"
    }
  }
}
"@ | Set-Content -Encoding UTF8 "$bundle\latest.json"
```

- Then copy that manifest over the tracked `releases\latest.json`:

```powershell
Copy-Item ".\src-tauri\target\release\bundle\latest.json" "..\releases\latest.json" -Force
```

> **Important fields**:
> - **`version`**: must match the Tauri app version (`0.9.1` in `tauri.conf.json`).
> - **`url`**: must match the GitHub Release asset URL you will publish.
> - **`signature`**: must be the exact base64 signature for that ZIP from the signer.

---

### 9) Publish / update the GitHub Release

- Create or update a GitHub Release tagged **`vX.Y.Z`** (e.g. `v0.9.1`).
- Upload these assets to the Release:
  - `Plattera_0.9.1_x64-setup.exe`
  - `Plattera_0.9.1_windows_x86_64.zip`
  - `Plattera_0.9.1_windows_x86_64.zip.sig`

You do **not** need to upload `latest.json` to the Release; it’s served from the repo root via `raw.githubusercontent.com`.

---

### 10) Sanity check: remote manifest & ZIP reachability

- **Check remote `latest.json`**:

```powershell
Invoke-WebRequest "https://raw.githubusercontent.com/bwanedead/Plattera/main/releases/latest.json" |
  Select-Object -ExpandProperty Content
```

Confirm:

- **`version`** is `0.9.1`.
- **`url`** points to `.../v0.9.1/Plattera_0.9.1_windows_x86_64.zip`.
- **`signature`** is non‑empty.

- **Check ZIP URL**:

```powershell
Invoke-WebRequest "https://github.com/bwanedead/Plattera/releases/download/v0.9.1/Plattera_0.9.1_windows_x86_64.zip" -Method Head
```

Expect `StatusCode` 200.

---

### 11) Test the in‑app updater path

- **Install the previous version** (for example, `0.9.0`):
  - Use the `Plattera_0.9.0_x64-setup.exe` you already released.

- **Run the app and use “Check for Updates”**:
  - In `frontend/pages/index.tsx` the “Check for Updates” button calls `@tauri-apps/plugin-updater`’s `check()` and shows a dialog if an update is available.
  - From 0.9.0, expect:
    - The updater sees `latest.json.version = 0.9.1` and reports an update.
    - `Update now` triggers `downloadAndInstall()` for the 0.9.1 ZIP.

- **Restart the app**:
  - The bottom-left `AppVersionBadge` (from `frontend/src/components/AppVersionBadge.tsx`) should now display `v0.9.1` (via `getVersion()` from Tauri).
  - “Check for Updates” should now report “You are up to date.”

---

### 12) Quick recap (minimal fields to bump per release)

- **Core version**:
  - `frontend/src-tauri/tauri.conf.json` → `"version": "X.Y.Z"`
  - `frontend/src-tauri/Cargo.toml` → `version = "X.Y.Z"`
- **Nice to keep in sync**:
  - `frontend/package.json` → `"version": "X.Y.Z"`
- **Updater manifest**:
  - `releases/latest.json`:
    - `"version": "X.Y.Z"`
    - `"url": ".../vX.Y.Z/Plattera_X.Y.Z_windows_x86_64.zip"`
    - `"signature": "<signature for that ZIP>"`

Once these are aligned and the GitHub Release assets are uploaded, the in‑app updater can reliably move users from `X.Y.(Z-1)` → `X.Y.Z` via the “Check for Updates” button. 

