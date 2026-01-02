from __future__ import annotations

from .normalize import normalize_text_with_mapping_v1


def test_normalize_folds_quotes() -> None:
    text = "don\u2019t \u201Cquote\u201D"
    result = normalize_text_with_mapping_v1(text)
    assert result.normalized == "don't \"quote\""


def test_normalize_mapping_length_matches() -> None:
    text = "A\u2019B"
    result = normalize_text_with_mapping_v1(text)
    assert len(result.normalized) == len(result.map_norm_to_orig)
