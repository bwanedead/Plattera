"""
Pytest configuration for semantic lane tests.

Defines markers for test isolation:
- hnsw: Tests that require hnswlib and numpy (HNSW integration tests)
"""

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "hnsw: marks tests as requiring hnswlib/numpy dependencies (HNSW integration tests)",
    )
