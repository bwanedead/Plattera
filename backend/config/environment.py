"""Canonical backend process-environment bootstrap.

Loads ``backend/.env`` relative to the source tree for API and harness
source-mode entrypoints. Existing process variables always win.
"""

from __future__ import annotations

from dotenv import load_dotenv

from config.paths import backend_root


def load_backend_environment() -> bool:
    """Load ``backend/.env`` into the process environment.

    - Resolves the file from the backend source tree, not the cwd.
    - Uses ``override=False`` so inherited/process variables win.
    - Missing file is a safe no-op (returns False).
    - Never reads, returns, logs, or embeds secret values.
    """
    env_path = backend_root() / ".env"
    if not env_path.is_file():
        return False
    return bool(load_dotenv(dotenv_path=env_path, override=False))
