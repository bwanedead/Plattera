"""
Test utilities for semantic lane tests.
"""

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


@contextmanager
def mock_semantic_index_root(tmpdir: str):
    """
    Redirect semantic index paths to a temporary assets root.
    """
    tmp_path = Path(tmpdir)
    with patch("retrieval.lanes.semantic.manifest.assets_root", return_value=tmp_path):
        yield tmp_path
