"""
Corpus package
==============

Defines what "in-corpus" means for Plattera and provides stable views/adapters over
file-backed dossier storage and artifacts.

This package is intentionally lightweight and import-safe (no heavy deps).
"""

from .models import CorpusDocRef, CorpusChunkRef, CorpusView, CorpusDoc

__all__ = [
    "CorpusDocRef",
    "CorpusChunkRef",
    "CorpusView",
    "CorpusDoc",
]


