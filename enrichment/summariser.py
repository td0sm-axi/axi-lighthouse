"""
Enrichment — generates a 2-3 sentence English summary of a mention's raw_text.

Uses Claude Haiku (fast, cheap — summary is low-complexity).
System prompt is cached so only the per-mention text incurs variable cost.
Returns None on failure so the mention is still persisted without a summary.
"""
import logging

import anthropic

log = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None

_SYSTEM = (
    "You are a social media analyst for Axi, a global forex and CFD broker. "
    "Summarise the following customer mention in 2-3 concise English sentences. "
    "Focus on: what the person is saying about Axi, the core issue or praise, "
    "and any specific products or actions mentioned. "
    "Do not editorialize or add context not in the text."
)


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def summarise(raw_text: str, platform: str) -> str | None:
    try:
        response = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=[{
                "type": "text",
                "text": _SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": f"Platform: {platform}\n\n{raw_text[:4000]}",
            }],
        )
        return response.content[0].text.strip()
    except Exception:
        log.exception("summarise() failed for platform=%s", platform)
        return None
