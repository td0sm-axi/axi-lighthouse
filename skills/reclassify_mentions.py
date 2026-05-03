"""
skills/reclassify_mentions.py
Re-classify social mention rows using Claude.

Usage:
    from skills.reclassify_mentions import reclassify, classify_sentiment, classify_risk

    updated = reclassify(mention_dict)
    updated_list = reclassify_batch(list_of_mentions)
"""
import json
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Client (lazy-init — import does not require ANTHROPIC_API_KEY at load time)
# ---------------------------------------------------------------------------

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


# ---------------------------------------------------------------------------
# System prompt  ← cached; never put dynamic content here
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are a social media monitoring specialist for Axi, a global forex and CFD broker.
Your job is to classify social media mentions by sentiment and risk tier.

## Sentiment
- positive  — praise, recommendation, satisfaction, favourable comparison
- negative  — complaint, dissatisfaction, financial-loss claim, broker-switch intent
- neutral   — general discussion or informational post with no clear sentiment

## Risk Tiers
| Tier | Label     | Criteria |
|------|-----------|----------|
| L1   | Monitor   | Positive or neutral; engagement < 10; no risk signals |
| L2   | Complaint | Negative; engagement < 10; no viral or regulatory signals |
| L3   | Serious   | Negative AND (engagement ≥ 10 OR platform floor applies OR watch flag present) |
| L4   | Crisis    | Any of: engagement ≥ 50; client PII present; regulatory-body named; withdrawal/frozen account alleged; legal action threatened |

Platform floors — any negative mention is automatically ≥ L3:
  Reddit, TrustPilot, BrokersView

## Watch Flags
Return a comma-separated list of any matching keywords (or null if none apply):
  spread, leverage, withdrawal, FCA, ASIC, CySEC, SEC, regulator,
  frozen, scam, fraud, legal

## Client Info
Set has_client_info = true when the post contains account numbers, trade IDs,
specific P&L figures, case/ticket references, or other details that suggest
the author is an Axi client sharing private account information.
"""

# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class SentimentResult(BaseModel):
    sentiment: Literal["positive", "negative", "neutral"]
    sentiment_reasoning: str


class RiskResult(BaseModel):
    risk_level: Literal["L1", "L2", "L3", "L4"]
    risk_reasoning: str
    watch_flags: Optional[str] = None
    has_client_info: bool


class FullResult(BaseModel):
    sentiment: Literal["positive", "negative", "neutral"]
    sentiment_reasoning: str
    risk_level: Literal["L1", "L2", "L3", "L4"]
    risk_reasoning: str
    watch_flags: Optional[str] = None
    has_client_info: bool


def _build_schema(model: type[BaseModel]) -> dict:
    """JSON Schema from a Pydantic model, patched to pass API validation."""
    schema = model.model_json_schema()
    # Required by the structured-outputs API for every object
    schema.setdefault("additionalProperties", False)
    for defn in schema.get("$defs", {}).values():
        defn.setdefault("additionalProperties", False)
    return schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_mention(mention: dict) -> str:
    lines = []
    for label, key in [("Platform", "platform"), ("Author", "author"), ("Engagement", "engagement")]:
        if mention.get(key) is not None:
            lines.append(f"{label}: {mention[key]}")
    if mention.get("text"):
        lines.append(f"\n{mention['text']}")
    return "\n".join(lines)


def _call(user_prompt: str, schema: dict) -> dict:
    """Single API call: cached system prompt + structured JSON output."""
    client = _get_client()
    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=[{
            "type": "text",
            "text": _SYSTEM,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_prompt}],
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": schema},
        },
    )
    # Thinking blocks appear before the text block — find the text
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_sentiment(mention: dict) -> dict:
    """Return the mention dict with updated sentiment + sentiment_reasoning."""
    data = _call(
        f"Classify the sentiment of this mention:\n\n{_format_mention(mention)}",
        _build_schema(SentimentResult),
    )
    return {**mention, **data}


def classify_risk(mention: dict) -> dict:
    """Return the mention dict with updated risk_level, risk_reasoning, watch_flags, has_client_info."""
    data = _call(
        f"Classify the risk tier of this mention:\n\n{_format_mention(mention)}",
        _build_schema(RiskResult),
    )
    updated = {**mention, **data}
    if "tier" in mention:
        updated["tier"] = data["risk_level"]
    return updated


def reclassify(mention: dict) -> dict:
    """Re-classify both sentiment and risk tier in a single API call."""
    data = _call(
        f"Classify the sentiment and risk tier of this mention:\n\n{_format_mention(mention)}",
        _build_schema(FullResult),
    )
    updated = {**mention, **data}
    if "tier" in mention:
        updated["tier"] = data["risk_level"]
    return updated


def reclassify_batch(mentions: list[dict]) -> list[dict]:
    """Re-classify a list of mentions.
    The system prompt is cached after the first call, so subsequent
    requests pay only ~0.1× input cost for the cached portion.
    """
    return [reclassify(m) for m in mentions]
