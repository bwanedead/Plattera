from __future__ import annotations

from dataclasses import dataclass
import unicodedata


@dataclass(frozen=True)
class NormalizationResult:
    normalized: str
    map_norm_to_orig: list[int]


NORMALIZER_VERSION = "v0"

_REPLACEMENTS: dict[str, str] = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201B": "'",
    "\u2032": "'",
    "\u02BC": "'",
    "\u00B4": "'",
    "\u201C": '"',
    "\u201D": '"',
    "\u201F": '"',
    "\u2033": '"',
}


def normalize_text_v1(text: str) -> str:
    return normalize_text_with_mapping_v1(text).normalized


def normalize_text_with_mapping_v1(text: str) -> NormalizationResult:
    normalized_chars: list[str] = []
    map_norm_to_orig: list[int] = []

    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\r":
            if i + 1 < len(text) and text[i + 1] == "\n":
                normalized_chars.append("\n")
                map_norm_to_orig.append(i)
                i += 2
                continue
            normalized_chars.append("\n")
            map_norm_to_orig.append(i)
            i += 1
            continue

        norm_chunk = unicodedata.normalize("NFKC", ch)
        if not norm_chunk:
            i += 1
            continue

        for norm_ch in norm_chunk:
            repl = _REPLACEMENTS.get(norm_ch, norm_ch)
            for out_ch in repl:
                normalized_chars.append(out_ch)
                map_norm_to_orig.append(i)
        i += 1

    return NormalizationResult("".join(normalized_chars), map_norm_to_orig)
