"""Extract readable text from raw HTML.

Uses BeautifulSoup to strip script/style/nav/footer/ads and collapse
whitespace, rather than passing full HTML markup to the LLM (which would
waste tokens and introduce noise/markup into synthesis).
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from app.retrieval.passage_extractor import extract_relevant_passages

_NOISE_TAGS = ("script", "style", "noscript", "nav", "footer", "header", "form", "svg", "iframe")


def extract_readable_text(html: str, max_chars: int = 20_000) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag_name in _NOISE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def top_passage(text: str, max_chars: int = 1200) -> str:
    """Return a leading excerpt suitable for use as an Evidence.passage."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_period = truncated.rfind(". ")
    if last_period > max_chars * 0.5:
        return truncated[: last_period + 1]
    return truncated + "..."


def extract_top_passage(text: str, query: str, max_chars: int = 1500) -> str:
    """Extract the most query-relevant passage from fetched text."""
    return extract_relevant_passages(text, query, max_chars=max_chars)
