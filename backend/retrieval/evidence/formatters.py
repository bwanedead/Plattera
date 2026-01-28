from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import EvidenceCard


@dataclass
class EvidenceFormatter:
    """
    Small helper for rendering evidence consistently for LLM context or UI.

    v0: deliberately minimal.
    """

    max_chars_per_span: int = 800

    def format_card(self, card: EvidenceCard) -> str:
        parts = []
        title = card.title or card.id
        parts.append(f"[{card.lane}] {title} (score={card.score:.4f})")
        for i, span in enumerate(card.spans, start=1):
            txt = span.text or span.preview or ""
            if len(txt) > self.max_chars_per_span:
                txt = txt[: self.max_chars_per_span] + "…"
            entry_id = span.entry.entry_id
            dossier_id = span.entry.dossier_id or "unknown"
            similarity = span.metadata.get("similarity_score") if span.metadata else None
            sim_note = f" score={similarity:.4f}" if isinstance(similarity, (int, float)) else ""
            parts.append(f"  - span {i} ({dossier_id}:{entry_id}){sim_note}: {txt}")
        return "\n".join(parts)

    def format_cards(self, cards: list[EvidenceCard], limit: Optional[int] = None) -> str:
        use = cards[:limit] if limit else cards
        return "\n\n".join(self.format_card(c) for c in use)





