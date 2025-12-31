"""
Corpus package
==============

Defines what "in-corpus" means for Plattera and provides stable views/adapters over
file-backed dossier storage and artifacts.

This package is intentionally lightweight and import-safe (no heavy deps).
"""

from .types import (
    CorpusChunkRef,
    CorpusEntry,
    CorpusEntryKind,
    CorpusEntryRef,
    CorpusView,
)
from .virtual_provider import VirtualCorpusProvider

__all__ = [
    "CorpusEntryRef",
    "CorpusChunkRef",
    "CorpusView",
    "CorpusEntry",
    "CorpusEntryKind",
    "VirtualCorpusProvider",
]


