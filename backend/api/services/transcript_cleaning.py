"""
Cleanup for STT output: collapse Whisper repetition-loop hallucinations.

On silence or noise Whisper can lock into a decoding loop and emit the same
token or short phrase hundreds of times ("Dr. Dr. Dr. ..."). Downstream
summarization then sees a corrupted transcript. This module collapses such
runs while leaving normal speech (which rarely repeats a phrase more than a
couple of times verbatim) untouched.
"""
from typing import Dict, List, Tuple

from loguru import logger

# Keep at most this many consecutive identical tokens/phrases/segments
MAX_REPEATS = 3
# Collapse repeated n-grams up to this length ("thank you thank you ...")
_MAX_NGRAM = 4


def collapse_repeats(text: str, max_repeats: int = MAX_REPEATS) -> str:
    """Collapse runs of identical tokens/phrases beyond max_repeats."""
    if not text:
        return text
    tokens = text.split()
    for n in range(1, _MAX_NGRAM + 1):
        tokens = _collapse_ngram_runs(tokens, n, max_repeats)
    return " ".join(tokens)


def _collapse_ngram_runs(tokens: List[str], n: int, max_repeats: int) -> List[str]:
    out: List[str] = []
    i = 0
    total = len(tokens)
    while i < total:
        if i + 2 * n <= total and tokens[i:i + n] == tokens[i + n:i + 2 * n]:
            reps = 2
            while tokens[i + reps * n: i + (reps + 1) * n] == tokens[i:i + n]:
                reps += 1
            out.extend(tokens[i:i + n] * min(reps, max_repeats))
            i += reps * n
        else:
            out.append(tokens[i])
            i += 1
    return out


def clean_transcription(text: str, segments: List[Dict]) -> Tuple[str, List[Dict]]:
    """Clean a transcription result: collapse repetition loops inside each
    segment, drop runs of identical segments, and rebuild the full text.

    Returns (cleaned_text, cleaned_segments)."""
    if not segments:
        return collapse_repeats((text or "").strip()), []

    cleaned_segments: List[Dict] = []
    prev_norm = None
    dup_run = 0
    for seg in segments:
        seg_text = collapse_repeats((seg.get("text") or "").strip())
        if not seg_text:
            continue
        norm = seg_text.lower()
        if norm == prev_norm:
            dup_run += 1
            if dup_run >= MAX_REPEATS:
                continue
        else:
            dup_run = 0
            prev_norm = norm
        cleaned_segments.append({**seg, "text": seg_text})

    cleaned_text = " ".join(s["text"] for s in cleaned_segments)
    if not cleaned_text.strip():
        cleaned_text = collapse_repeats((text or "").strip())

    orig_len = len(text or "")
    if orig_len and len(cleaned_text) < orig_len * 0.5:
        logger.warning(
            f"Repetition cleanup removed {orig_len - len(cleaned_text)} of {orig_len} chars "
            "— the recording likely contained an STT hallucination loop"
        )
    return cleaned_text, cleaned_segments
