"""Shared pytest fixtures for harness CLI tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def isolated_harness_root(tmp_path, monkeypatch):
    root = tmp_path / "harness_art"
    root.mkdir()
    import config.paths as paths_mod

    monkeypatch.setattr(paths_mod, "harness_cli_artifacts_root", lambda: root)
    return root
