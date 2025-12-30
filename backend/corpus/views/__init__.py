"""
Corpus views
============

View modules define how to enumerate corpus documents for different "channels":
finalized-only, everything, artifacts, etc.

Views return lightweight `CorpusDocRef` streams; actual hydration happens via `hydrate.py`.
"""


