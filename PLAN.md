# Lighthouse v1 — Technical Spec

## Context

Lighthouse v1 is a brand intelligence and social response service for Axi. It continuously monitors public platforms for mentions of Axi, classifies each mention by sentiment and risk severity, creates Jira tickets for tracking, auto-replies to low-risk mentions, and routes high-risk mentions to compliance for human review. Nothing from v0.01 is carried forward — this is a clean build.

---

## Architecture Overview

```
Scheduler (APScheduler)
    │
    ▼
[1] Crawler Layer          — platform-specific scrapers run in parallel
    │
    ▼
[2] Enrichment Layer       — screenshot, summary, store raw text + link
    │
    ▼
[3] Classification Layer   — Claude: sentiment → risk tier (L1–L4)
    │
    ├── L1 / L2 ──────────► [4a] Response Agent  — template + Claude personalisation → auto-post
    │
    └── L3 / L4 ──────────► [4b] Compliance Queue — Jira ticket flagged PENDING_HUMAN_REVIEW
    │
    ▼
[5] Jira Sync              — create ticket for every mention, update status on poll
    │
    ▼
[6] Dashboard (Flask)      — view all mentions, ticket status, compliance queue
```

---

## Component Breakdown

### 1. Crawler Layer

One scraper module per platform. All scrapers share a common output schema.

| Platform | Library / Method |
|---|---|
| Reddit | `praw` (official Reddit API) |
| TrustPilot | `playwright` headless scrape (no public API) |
| ForexPeaceArmy / BabyPips | `playwright` headless scrape |
| X (Twitter) | X API v2 — search recent tweets |
| Facebook / Instagram | Meta Graph API — page mentions + comments |
| TikTok | TikTok Research API |
| LinkedIn | LinkedIn API — brand mentions |
| Google Play | `google-play-scraper` Python library |
| Apple App Store | `app-store-scraper` Python library |
| News / Web | Google Custom Search API or SerpAPI |

Each scraper returns:
```python
{
  "platform": str,
  "url": str,
  "author": str,
  "posted_at": datetime,
  "raw_text": str,
  "title": str | None
}
```

### 2. Enrichment Layer

Runs after crawl, before classification.

- **Screenshot**: `playwright` captures full-page PNG, saved to `data/screenshots/<mention_id>.png`
- **Summary**: Claude call — 2–3 sentence summary of the mention in English
- **Storage**: All raw text, URL, screenshot path, and summary written to PostgreSQL before classification begins

### 3. Classification Layer

Two sequential Claude calls per mention:

**Stage 1 — Sentiment**
- Input: raw text + summary
- Output: `positive` | `negative` | `neutral`
- Simple binary with neutral catch-all

**Stage 2 — Risk Tier**
- Input: raw text + summary + sentiment
- Output: `L1` | `L2` | `L3` | `L4`
- Tier definitions: finalised during validation phase (see Open Questions)
- Prompt includes: chain-of-thought enforcement, prompt-injection defence preamble, mention delimiters

PII redaction (regex-based) runs on `raw_text` before either Claude call.

### 4a. Response Agent (L1 / L2)

- Selects the correct response template based on platform + sentiment + category
- Claude personalises the opening 1–2 sentences to the specific mention
- Posts reply via the platform's API / posting mechanism
- Logs: response text, posted_at, post URL

Template categories to define:
- Positive review → thank you + brand reinforcement
- General complaint (L1) → acknowledgement + support link
- Minor product complaint (L2) → acknowledgement + resolution path

### 4b. Compliance Queue (L3 / L4)

- Jira ticket created immediately with status `PENDING_HUMAN_REVIEW`
- Ticket body includes: mention URL, screenshot, summary, raw text, classification reasoning
- No automated response posted
- Dashboard shows compliance queue with approve / escalate / dismiss controls

### 5. Jira Sync

- Every mention gets a Jira ticket regardless of tier
- L1/L2: ticket created after auto-reply is posted; status set to `AUTO_RESPONDED`
- L3/L4: ticket created immediately; status `PENDING_HUMAN_REVIEW`
- Sync job polls Jira every hour and updates local DB with current ticket status
- Jira fields: summary, description, priority (maps to L1–L4), label (platform), custom field for mention URL

### 6. Flask Dashboard

| Route | Purpose |
|---|---|
| `/` | Overview — mention counts by tier, platform, status |
| `/mentions` | Full filterable mention list |
| `/mention/<id>` | Detail — screenshot, raw text, summary, classification, ticket |
| `/compliance` | L3/L4 queue — approve response / escalate / dismiss |
| `/tickets` | All Jira tickets and current status |
| `/runs` | Crawler run history |

HTTP basic auth on all routes. Credentials from `.env`.

---

## Data Model (PostgreSQL)

```
mentions
  id, platform, url, author, posted_at, raw_text, title,
  summary, screenshot_path,
  sentiment, risk_level, classification_reasoning,
  response_text, response_posted_at, response_url,
  jira_ticket_id, jira_status,
  created_at, updated_at

crawler_runs
  id, started_at, finished_at, platform, mentions_found, errors

response_templates
  id, platform, sentiment, category, template_text
```

---

## Build Phases

### Phase 1 — Foundation
- [ ] Repo structure, `.env.example`, `requirements.txt`
- [ ] PostgreSQL schema + SQLAlchemy models
- [ ] Base crawler interface (shared output schema)
- [ ] Playwright setup (screenshot + scraping)

### Phase 2 — Crawlers
- [ ] Reddit (`praw`)
- [ ] App stores (`google-play-scraper`, `app-store-scraper`)
- [ ] TrustPilot (Playwright scrape)
- [ ] X API v2
- [ ] Meta Graph API (Facebook / Instagram)
- [ ] TikTok Research API
- [ ] LinkedIn API
- [ ] News / web (Google Custom Search or SerpAPI)
- [ ] ForexPeaceArmy / BabyPips (Playwright scrape)

### Phase 3 — Classification Pipeline
- [ ] PII redactor
- [ ] Stage 1 sentiment prompt + Claude call
- [ ] Stage 2 risk tier prompt + Claude call (tiers TBD — see Open Questions)
- [ ] Enrichment: summary call + screenshot save

### Phase 4 — Response & Escalation
- [ ] Response template store + seeding
- [ ] Claude personalisation call
- [ ] Per-platform posting (Reddit reply, TrustPilot reply, X reply, etc.)
- [ ] Compliance queue — Jira ticket with `PENDING_HUMAN_REVIEW` status

### Phase 5 — Jira Integration
- [ ] Ticket creation for all tiers
- [ ] Hourly Jira status sync job

### Phase 6 — Dashboard
- [ ] Flask app, HTTP basic auth
- [ ] All routes listed above
- [ ] Compliance queue approval workflow

### Phase 7 — Scheduler + Hardening
- [ ] APScheduler: crawler runs (daily), Jira sync (hourly), digest (weekly)
- [ ] Prompt validation harness against real Axi mention export
- [ ] L1–L4 tier definitions finalised from validation results
- [ ] Credentials rotated, compliance PII sign-off

---

## Open Questions (Decide During Build)

1. **L1–L4 tier definitions** — finalised after running classifier against real Axi mention data in Phase 7
2. **Response templates** — need to be written per platform and category before Phase 4 can ship
3. **Which Jira project key** handles mentions? CX? Legal?
4. **Platform API credentials** — X, Meta, TikTok, LinkedIn all require app registration; confirm which accounts Axi has
5. **PII compliance sign-off** — required before live mode touches real customer text

---

## Verification

- Run crawler in isolation per platform, confirm output schema matches
- Run classification pipeline against 30-day Brandwatch export, review every label manually
- Test auto-reply end-to-end on a sandbox Reddit account before enabling on live accounts
- Confirm L3/L4 Jira tickets appear with correct fields and `PENDING_HUMAN_REVIEW` status
- Confirm Jira sync updates local DB correctly after manually moving a ticket in Jira
