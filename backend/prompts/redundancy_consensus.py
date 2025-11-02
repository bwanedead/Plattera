"""
Prompt builder for LLM-based consensus over multiple transcription drafts.

Output format (text-only):
- First line: "Title: <short descriptive title>" (optional)
- Then a blank line
- Then the consensus transcription body only (no explanations)
"""
from typing import List


def build_consensus_prompt(drafts: List[str]) -> str:
    """Construct a prompt to produce a best-guess consensus transcription.

    Guidance to the assistant:
    - Compare the drafts, resolve conflicts, and output a single clean transcription.
    - Prefer readings supported by multiple drafts and legalistic consistency.
    - Fix obvious OCR errors; preserve meaning and structure; do not summarize.
    - Do NOT include explanations or commentary.

    Output format STRICT:
    Title: <short descriptive title>

    <final consensus transcription only>
    """

    header = (
        "You are given multiple independent OCR/LLM transcription drafts of the same legal document.\n"
        "Your task is to produce the single best consensus transcription that most likely reflects the original text.\n\n"
        "Rules:\n"
        "- Prefer readings supported by multiple drafts.\n"
        "- If drafts disagree, choose the most plausible/legalistically consistent wording.\n"
        "- Correct obvious OCR errors (broken words, random punctuation, spacing).\n"
        "- Preserve original meaning and structure; do not summarize.\n"
        "- Do NOT add commentary or explanations.\n\n"
        "Output format STRICT:\n"
        "Title: <short descriptive title>\n\n"
        "<final consensus transcription only>\n"
    )

    parts = [header, "Drafts:\n"]
    for i, d in enumerate(drafts, start=1):
        parts.append(f"--- DRAFT {i} START ---\n{d.strip()}\n--- DRAFT {i} END ---\n")

    parts.append("\nNow produce the output in the exact required format.")
    return "".join(parts)


