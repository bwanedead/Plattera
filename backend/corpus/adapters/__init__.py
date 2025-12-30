"""
Corpus adapters
==============

Adapters are the only layer that should touch storage layout details (filesystem, etc).
They must read roots via `config.paths` so dev vs frozen layouts stay consistent.
"""


