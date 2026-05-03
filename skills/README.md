# Lighthouse Skills

Claude-powered skills for enriching and re-processing social mention data.
Each skill is a standalone Python module that calls the Anthropic API and returns
an updated copy of the mention dict it receives — original fields are preserved,
classification fields are overwritten.

---

## Setup

```bash
pip install anthropic pydantic
export ANTHROPIC_API_KEY="sk-ant-..."
```

All skills share a single lazy-initialised Anthropic client.
The client is created on the first call, so importing a skill file does not
require `ANTHROPIC_API_KEY` to be set at import time.

---

## Available Skills

| Module | Purpose |
|--------|---------|
| [`reclassify_mentions.py`](#reclassify_mentionspy) | Re-classify sentiment and/or risk tier for a mention |
| [`review_classifier.py`](#review_classifierpy) | Stratified QA audit comparing Brandwatch labels against Claude |

---

## reclassify_mentions.py

Re-classifies the **sentiment** and **risk tier** of a social media mention using
`claude-opus-4-7` with adaptive thinking and structured JSON output.
The system prompt is prompt-cached, so batches of mentions pay the cache-write
cost once and ~0.1× thereafter.

### Functions

#### `reclassify(mention: dict) → dict`

Re-classifies **both** sentiment and risk tier in a single API call.
Most efficient option for full re-processing.

```python
from skills.reclassify_mentions import reclassify

mention = {
    "platform": "Reddit",
    "author": "trader_99",
    "engagement": 31,
    "text": "Axi widened spreads right during NFP — lost 3× what I should have. Thinking of switching.",
}

updated = reclassify(mention)
# updated["sentiment"]           → "negative"
# updated["sentiment_reasoning"] → "Post expresses financial loss and broker-switch intent..."
# updated["risk_level"]          → "L3"
# updated["risk_reasoning"]      → "Negative on Reddit (platform floor = L3) with engagement ≥ 10..."
# updated["watch_flags"]         → "spread"
# updated["has_client_info"]     → False
```

#### `classify_sentiment(mention: dict) → dict`

Updates only `sentiment` and `sentiment_reasoning`. Use when risk tier is
already correct and only the sentiment label needs fixing.

```python
from skills.reclassify_mentions import classify_sentiment

updated = classify_sentiment(mention)
# updated["sentiment"]           → "negative"
# updated["sentiment_reasoning"] → "..."
```

#### `classify_risk(mention: dict) → dict`

Updates only `risk_level`, `risk_reasoning`, `watch_flags`, and `has_client_info`.
If the mention dict already contains a `tier` key, it is kept in sync with
the new `risk_level`.

```python
from skills.reclassify_mentions import classify_risk

updated = classify_risk(mention)
# updated["risk_level"]    → "L3"
# updated["risk_reasoning"] → "..."
# updated["watch_flags"]   → "spread"
# updated["has_client_info"] → False
```

#### `reclassify_batch(mentions: list[dict]) → list[dict]`

Runs `reclassify` over a list of mentions sequentially.
The system prompt cache warms on the first call; all subsequent calls in the
batch read from cache at ~0.1× input cost.

```python
from skills.reclassify_mentions import reclassify_batch

updated_mentions = reclassify_batch(mentions)
```

---

### Classification Rules

**Sentiment**

| Label | Criteria |
|-------|----------|
| `positive` | Praise, recommendation, satisfaction, favourable comparison |
| `negative` | Complaint, financial-loss claim, dissatisfaction, broker-switch intent |
| `neutral` | General/informational post with no clear sentiment |

**Risk Tiers**

| Tier | Label | Criteria |
|------|-------|----------|
| L1 | Monitor | Positive or neutral; engagement < 10; no risk signals |
| L2 | Complaint | Negative; engagement < 10; no viral or regulatory signals |
| L3 | Serious | Negative AND (engagement ≥ 10 OR platform floor OR watch flag present) |
| L4 | Crisis | Engagement ≥ 50; client PII present; regulatory-body named; withdrawal/frozen account alleged; legal action threatened |

**Platform floors** (any negative = minimum L3): Reddit, TrustPilot, BrokersView

**Watch flags** (returned as comma-separated string or `null`):
`spread`, `leverage`, `withdrawal`, `FCA`, `ASIC`, `CySEC`, `SEC`, `regulator`, `frozen`, `scam`, `fraud`, `legal`

---

### Input / Output Schema

The mention dict can contain any fields. The skill reads:

| Field | Type | Used for |
|-------|------|----------|
| `text` | str | Mention content (required) |
| `platform` | str | Platform floor rules |
| `engagement` | int | Tier escalation thresholds |
| `author` | str | Context only |

The skill writes (overwrites if already present):

| Field | Type | Set by |
|-------|------|--------|
| `sentiment` | `"positive" \| "negative" \| "neutral"` | `classify_sentiment`, `reclassify` |
| `sentiment_reasoning` | str | `classify_sentiment`, `reclassify` |
| `risk_level` | `"L1" \| "L2" \| "L3" \| "L4"` | `classify_risk`, `reclassify` |
| `risk_reasoning` | str | `classify_risk`, `reclassify` |
| `watch_flags` | `str \| None` | `classify_risk`, `reclassify` |
| `has_client_info` | bool | `classify_risk`, `reclassify` |
| `tier` | str | Synced to `risk_level` if key already exists in input |

---

## Adding a New Skill

1. Create `skills/<name>.py`
2. Follow the same pattern: lazy client, cached `_SYSTEM` prompt, Pydantic output schema, public functions that accept and return a dict
3. Add an entry to the table at the top of this README
