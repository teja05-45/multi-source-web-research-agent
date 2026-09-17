"""Query-aware passage extraction from fetched page content.

Instead of using only the leading 1200 characters of a page (which may
contain navigation, headers, and irrelevant content), this module:
1. Splits the page into sentence-sized chunks
2. Scores each chunk against the query using token overlap
3. Returns the most relevant chunks (up to max_chars), preserving order
"""
from __future__ import annotations

import re


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{2,}", text.lower()))


def _split_sentences(text: str) -> list[str]:
    """Split text into sentence-like chunks."""
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    result = []
    for chunk in chunks:
        if len(chunk) > 500:
            sub = re.split(r";\s+|,\s+(?:and|but|or|however|therefore|moreover)\s+", chunk)
            result.extend(sub)
        else:
            result.append(chunk)
    return [c.strip() for c in result if c.strip()]


def extract_relevant_passages(
    text: str,
    query: str,
    max_chars: int = 1500,
    min_overlap: float = 0.05,
) -> str:
    """Extract the most query-relevant passages from fetched text.

    Returns up to max_chars of text, selecting the most relevant sentences
    and preserving their original order.
    """
    if not text or not query:
        return text[:max_chars] if text else ""

    query_tokens = _tokenize(query)
    if not query_tokens:
        return text[:max_chars]

    sentences = _split_sentences(text)
    if not sentences:
        return text[:max_chars]

    scored = []
    for sent in sentences:
        sent_tokens = _tokenize(sent)
        if not sent_tokens:
            continue
        overlap = len(query_tokens & sent_tokens) / len(query_tokens)
        if overlap >= min_overlap:
            scored.append((overlap, sent))

    if not scored:
        # Fallback: return leading text
        return text[:max_chars]

    # Sort by relevance (descending), then by original position
    scored.sort(key=lambda x: x[0], reverse=True)

    # Pick top sentences up to max_chars, preserving order
    selected: list[str] = []
    current_len = 0
    for _, sent in scored[:20]:  # limit to top 20 candidates
        if current_len + len(sent) + 1 > max_chars:
            break
        selected.append(sent)
        current_len += len(sent) + 1

    if not selected:
        return text[:max_chars]

    # Re-sort by original position for coherent reading
    sent_to_idx = {s: i for i, s in enumerate(sentences)}
    selected.sort(key=lambda s: sent_to_idx.get(s, 0))

    return " ".join(selected)