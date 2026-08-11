"""Tests for provider-neutral backend environment bootstrap.

Uses temporary dotenv fixtures only — never the operator's real ``backend/.env``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config import environment as environment_module


DUMMY_ABSENT_KEY = "PLATTERA_TEST_ENV_ABSENT"
DUMMY_PRESENT_KEY = "PLATTERA_TEST_ENV_PRESENT"
DUMMY_HASH_KEY = "PLATTERA_TEST_ENV_HASH"
DUMMY_SPACE_KEY = "PLATTERA_TEST_ENV_SPACE"
DUMMY_QUOTED_KEY = "PLATTERA_TEST_ENV_QUOTED"


@pytest.fixture
def isolated_backend_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point dotenv resolution at a temp backend root (never the real repo .env)."""
    monkeypatch.setattr(environment_module, "backend_root", lambda: tmp_path)
    return tmp_path


def test_missing_dotenv_is_noop(isolated_backend_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DUMMY_ABSENT_KEY, raising=False)
    assert not (isolated_backend_root / ".env").exists()
    assert environment_module.load_backend_environment() is False
    assert DUMMY_ABSENT_KEY not in __import__("os").environ


def test_dotenv_path_is_source_tree_relative_not_cwd(
    isolated_backend_root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Resolution uses backend_root(), never the process cwd."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(DUMMY_ABSENT_KEY, raising=False)
    (tmp_path / ".env").write_text(f"{DUMMY_ABSENT_KEY}=from-cwd\n", encoding="utf-8")
    (isolated_backend_root / ".env").write_text(
        f"{DUMMY_ABSENT_KEY}=from-backend-root\n",
        encoding="utf-8",
    )
    assert environment_module.load_backend_environment() is True
    assert __import__("os").environ.get(DUMMY_ABSENT_KEY) == "from-backend-root"


def test_absent_process_var_loaded_from_file(
    isolated_backend_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(DUMMY_ABSENT_KEY, raising=False)
    (isolated_backend_root / ".env").write_text(
        f"{DUMMY_ABSENT_KEY}=from-dotenv-file\n",
        encoding="utf-8",
    )
    assert environment_module.load_backend_environment() is True
    assert __import__("os").environ.get(DUMMY_ABSENT_KEY) == "from-dotenv-file"


def test_existing_process_var_not_overwritten(
    isolated_backend_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(DUMMY_PRESENT_KEY, "from-process")
    (isolated_backend_root / ".env").write_text(
        f"{DUMMY_PRESENT_KEY}=from-dotenv-file\n",
        encoding="utf-8",
    )
    assert environment_module.load_backend_environment() is True
    assert __import__("os").environ.get(DUMMY_PRESENT_KEY) == "from-process"


def test_dotenv_parsing_hash_spaces_and_quotes(
    isolated_backend_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in (DUMMY_HASH_KEY, DUMMY_SPACE_KEY, DUMMY_QUOTED_KEY):
        monkeypatch.delenv(key, raising=False)
    (isolated_backend_root / ".env").write_text(
        "\n".join(
            [
                f"{DUMMY_HASH_KEY}=abc#not-a-comment",
                f'{DUMMY_SPACE_KEY}="value with spaces"',
                f"{DUMMY_QUOTED_KEY}='single-quoted'",
                "",
            ]
        ),
        encoding="utf-8",
    )
    assert environment_module.load_backend_environment() is True
    env = __import__("os").environ
    assert env.get(DUMMY_HASH_KEY) == "abc#not-a-comment"
    assert env.get(DUMMY_SPACE_KEY) == "value with spaces"
    assert env.get(DUMMY_QUOTED_KEY) == "single-quoted"


def test_environment_module_has_no_provider_specific_key_names() -> None:
    source = Path(environment_module.__file__).read_text(encoding="utf-8")
    forbidden = (
        "META_MODEL_API_KEY",
        "OPENAI_API_KEY",
        "MODEL_API_KEY",
        "anthropic",
        "openai",
        "meta",
        "muse",
    )
    lowered = source.lower()
    for token in forbidden:
        assert token.lower() not in lowered, f"provider-specific token leaked: {token}"
