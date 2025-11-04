# Third‑Party Notices

This application includes open‑source software. The sections below list third‑party
licenses for the frontend (Node), desktop shell (Rust/Tauri), and backend (Python).

This file can be (re)generated before a public release using the commands shown.

## Frontend (Node / Next.js)

Generate summary of production dependencies:

```bash
# Run from repo root or ./frontend
cd frontend
npx license-checker --production --summary > ../THIRD_PARTY_NOTICES_frontend.txt
```

The generated file: `THIRD_PARTY_NOTICES_frontend.txt`.

## Desktop (Rust / Tauri)

Generate license list for Rust crates:

```bash
# One‑time install
cargo install cargo-about

# Initialize once (creates cargo-about config)
cargo about init

# Generate notices
cargo about generate > THIRD_PARTY_NOTICES_rust.txt
```

The generated file: `THIRD_PARTY_NOTICES_rust.txt` (repo root).

## Backend (Python)

Generate license list for Python packages:

```bash
# Ensure venv active
pip install pip-licenses
pip-licenses --from=mixed --format=markdown > THIRD_PARTY_NOTICES_python.md
```

The generated file: `THIRD_PARTY_NOTICES_python.md` (repo root).

## Notes
- Application license: MIT (see LICENSE).
- Do not commit private signing keys; see `.gitignore` rules.
- If you ship additional assets (icons/fonts), include their licenses or credits here.


