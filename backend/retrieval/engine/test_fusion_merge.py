from __future__ import annotations

from corpus.types import CorpusEntryKind, CorpusEntryRef, CorpusView

from ..evidence.models import EvidenceCard, EvidenceSpan
from .merge import FusionConfig, fusion_merge


def _make_card(card_id: str, score: float, lane: str) -> EvidenceCard:
    """Helper to create a minimal evidence card for testing."""
    ref = CorpusEntryRef(
        view=CorpusView.FINALIZED,
        entry_id=card_id,
        kind=CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
        dossier_id=None,
    )
    span = EvidenceSpan(entry=ref, text="test")
    return EvidenceCard(id=card_id, spans=[span], score=score, lane=lane)


def test_fusion_merge_empty_input() -> None:
    """Empty lane results should return empty list."""
    result = fusion_merge({})
    assert result == []


def test_fusion_merge_single_lane() -> None:
    """Single lane should return its cards sorted by score."""
    cards = [
        _make_card("card1", 0.5, "lexical.raw"),
        _make_card("card2", 0.9, "lexical.raw"),
        _make_card("card3", 0.7, "lexical.raw"),
    ]
    result = fusion_merge({"lexical.raw": cards})

    assert len(result) == 3
    assert result[0].id == "card2"  # highest score
    assert result[1].id == "card3"
    assert result[2].id == "card1"  # lowest score


def test_fusion_merge_per_lane_cap() -> None:
    """Should respect per-lane cap and only take top-K from each lane."""
    raw_cards = [
        _make_card("raw1", 0.9, "lexical.raw"),
        _make_card("raw2", 0.8, "lexical.raw"),
        _make_card("raw3", 0.7, "lexical.raw"),
        _make_card("raw4", 0.6, "lexical.raw"),
    ]
    norm_cards = [
        _make_card("norm1", 0.95, "lexical.normalized"),
        _make_card("norm2", 0.85, "lexical.normalized"),
        _make_card("norm3", 0.75, "lexical.normalized"),
    ]

    config = FusionConfig(per_lane_cap=2)
    result = fusion_merge(
        {"lexical.raw": raw_cards, "lexical.normalized": norm_cards}, config=config
    )

    # Should only have 2 from each lane = 4 total
    assert len(result) == 4
    raw_ids = [c.id for c in result if c.lane == "lexical.raw"]
    norm_ids = [c.id for c in result if c.lane == "lexical.normalized"]
    assert len(raw_ids) == 2
    assert len(norm_ids) == 2
    # Should have taken first 2 from each lane (in input order before sorting)
    assert "raw1" in raw_ids
    assert "raw2" in raw_ids
    assert "norm1" in norm_ids
    assert "norm2" in norm_ids


def test_fusion_merge_dedupe_first_wins() -> None:
    """Duplicate card IDs should dedupe with first occurrence winning."""
    raw_cards = [
        _make_card("dup1", 0.5, "lexical.raw"),
    ]
    norm_cards = [
        _make_card("dup1", 0.9, "lexical.normalized"),  # Higher score but comes later
        _make_card("unique1", 0.8, "lexical.normalized"),
    ]

    # Default lane order: lexical.raw comes before lexical.normalized
    result = fusion_merge({"lexical.raw": raw_cards, "lexical.normalized": norm_cards})

    # Should have 2 cards (dup1 from raw, unique1 from norm)
    assert len(result) == 2
    ids = [c.id for c in result]
    assert "dup1" in ids
    assert "unique1" in ids

    # The dup1 card should be from lexical.raw (first occurrence)
    dup_card = next(c for c in result if c.id == "dup1")
    assert dup_card.lane == "lexical.raw"
    assert dup_card.score == 0.5


def test_fusion_merge_stable_ordering_by_score() -> None:
    """Cards should be sorted by score descending."""
    cards = [
        _make_card("card1", 0.3, "lexical.raw"),
        _make_card("card2", 0.9, "lexical.normalized"),
        _make_card("card3", 0.6, "semantic"),
    ]
    result = fusion_merge(
        {
            "lexical.raw": [cards[0]],
            "lexical.normalized": [cards[1]],
            "semantic": [cards[2]],
        }
    )

    assert len(result) == 3
    assert result[0].id == "card2"  # 0.9
    assert result[1].id == "card3"  # 0.6
    assert result[2].id == "card1"  # 0.3


def test_fusion_merge_stable_ordering_lane_tiebreaker() -> None:
    """When scores are equal, lane order should be used as tie-breaker."""
    cards = [
        _make_card("raw1", 0.5, "lexical.raw"),
        _make_card("norm1", 0.5, "lexical.normalized"),
        _make_card("sem1", 0.5, "semantic:local"),
    ]
    result = fusion_merge(
        {
            "semantic": [cards[2]],  # Order in dict doesn't matter
            "lexical.raw": [cards[0]],
            "lexical.normalized": [cards[1]],
        }
    )

    assert len(result) == 3
    # With equal scores, lane order (raw, normalized, semantic) determines order
    assert result[0].id == "raw1"
    assert result[1].id == "norm1"
    assert result[2].id == "sem1"


def test_fusion_merge_stable_ordering_id_tiebreaker() -> None:
    """When scores and lanes are equal, card.id should be final tie-breaker."""
    cards = [
        _make_card("card_c", 0.5, "lexical.raw"),
        _make_card("card_a", 0.5, "lexical.raw"),
        _make_card("card_b", 0.5, "lexical.raw"),
    ]
    result = fusion_merge({"lexical.raw": cards})

    assert len(result) == 3
    # With equal scores and same lane, alphabetical card.id determines order
    assert result[0].id == "card_a"
    assert result[1].id == "card_b"
    assert result[2].id == "card_c"


def test_fusion_merge_respects_lane_order() -> None:
    """Should process lanes in configured order."""
    config = FusionConfig(lane_order=["semantic", "lexical.normalized", "lexical.raw"])

    raw_cards = [_make_card("raw1", 0.5, "lexical.raw")]
    norm_cards = [_make_card("norm1", 0.5, "lexical.normalized")]
    sem_cards = [_make_card("sem1", 0.5, "semantic")]

    result = fusion_merge(
        {"lexical.raw": raw_cards, "lexical.normalized": norm_cards, "semantic": sem_cards},
        config=config,
    )

    # With equal scores, custom lane order should be respected
    assert result[0].id == "sem1"
    assert result[1].id == "norm1"
    assert result[2].id == "raw1"


def test_fusion_merge_tiebreaker_accepts_lane_prefix() -> None:
    """Lane order should apply to lanes with prefixes (e.g., semantic:local)."""
    cards = [
        _make_card("sem1", 0.5, "semantic:local"),
        _make_card("raw1", 0.5, "lexical.raw"),
    ]
    result = fusion_merge({"lexical.raw": [cards[1]], "semantic": [cards[0]]})

    assert result[0].id == "raw1"
    assert result[1].id == "sem1"


def test_fusion_merge_stable_key_fn_dedupes_across_lanes() -> None:
    """Stable key function enables cross-lane dedupe when provided."""
    raw_cards = [
        _make_card("doc1:raw", 0.6, "lexical.raw"),
    ]
    sem_cards = [
        _make_card("doc1:sem", 0.9, "semantic:local"),
    ]

    def stable_key(card: EvidenceCard) -> str:
        return card.id.split(":")[0]

    result = fusion_merge(
        {"lexical.raw": raw_cards, "semantic": sem_cards}, stable_key_fn=stable_key
    )

    assert len(result) == 1
    assert result[0].id == "doc1:raw"


def test_fusion_merge_missing_lanes_handled_gracefully() -> None:
    """Missing lanes in results should not cause errors."""
    config = FusionConfig(lane_order=["lexical.raw", "lexical.normalized", "semantic"])

    # Only provide one lane
    result = fusion_merge({"lexical.raw": [_make_card("card1", 0.5, "lexical.raw")]}, config=config)

    assert len(result) == 1
    assert result[0].id == "card1"


def test_fusion_merge_default_config() -> None:
    """Default config should use standard lane order and per-lane cap."""
    raw_cards = [_make_card(f"raw{i}", 0.5, "lexical.raw") for i in range(15)]
    norm_cards = [_make_card(f"norm{i}", 0.5, "lexical.normalized") for i in range(15)]

    result = fusion_merge({"lexical.raw": raw_cards, "lexical.normalized": norm_cards})

    # Default per_lane_cap is 10, so should have max 20 cards
    assert len(result) == 20
    raw_count = sum(1 for c in result if c.lane == "lexical.raw")
    norm_count = sum(1 for c in result if c.lane == "lexical.normalized")
    assert raw_count == 10
    assert norm_count == 10


def test_fusion_merge_complex_scenario() -> None:
    """Test a realistic multi-lane scenario with mixed scores and duplicates."""
    raw_cards = [
        _make_card("doc1", 0.95, "lexical.raw"),
        _make_card("doc2", 0.7, "lexical.raw"),
        _make_card("doc3", 0.5, "lexical.raw"),
    ]
    norm_cards = [
        _make_card("doc1", 0.6, "lexical.normalized"),  # Duplicate, lower score
        _make_card("doc4", 0.8, "lexical.normalized"),
        _make_card("doc5", 0.4, "lexical.normalized"),
    ]
    sem_cards = [
        _make_card("doc2", 0.9, "semantic"),  # Duplicate, higher score but later
        _make_card("doc6", 0.85, "semantic"),
    ]

    result = fusion_merge(
        {"lexical.raw": raw_cards, "lexical.normalized": norm_cards, "semantic": sem_cards}
    )

    # Should have 6 unique docs (doc1-doc6)
    assert len(result) == 6
    ids = [c.id for c in result]
    assert set(ids) == {"doc1", "doc2", "doc3", "doc4", "doc5", "doc6"}

    # doc1 should be from lexical.raw (first occurrence)
    doc1 = next(c for c in result if c.id == "doc1")
    assert doc1.lane == "lexical.raw"
    assert doc1.score == 0.95

    # doc2 should be from lexical.raw (first occurrence)
    doc2 = next(c for c in result if c.id == "doc2")
    assert doc2.lane == "lexical.raw"
    assert doc2.score == 0.7

    # Top result should be doc1 with highest score
    assert result[0].id == "doc1"
