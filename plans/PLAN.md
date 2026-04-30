# Lighthouse v1 — Technical Spec

## Context

Lighthouse v1 is a brand intelligence and social response service for Axi. It continuously monitors public platforms for mentions of Axi, classifies each mention by sentiment and risk severity, creates Jira tickets for tracking, auto-replies to low-risk mentions, and routes high-risk mentions to compliance for human review. Nothing from v0.01 is carried forward — this is a clean build.

---

## Architecture Overview

### Phase 0 — Prototype (Unblocks Frontend Immediately)

```
BrandWatch API
    │
    ▼
[0] BrandWatch Connector   — fetches Axi mentions via BrandWatch API every 30 min
    │
    ▼
data/brandwatch_mentions.csv   — append-only, deduped on mention ID
    │
    ▼
prototype/dashboard.html       — reads CSV; gives frontend a working data source now
```

This layer exists only during the prototype phase. Once the production crawlers and PostgreSQL are live (Phase 2+), the CSV is retired and the dashboard reads from the DB.

### Phase 1+ — Production Pipeline

```
Scheduler (APScheduler)
    │
    ├── Every 30 min ──► [1] Crawler Layer     — platform-specific scrapers run in parallel
    │                         │
    │                         ▼
    │                    [2] Enrichment Layer  — screenshot, summary, store raw text + link
    │
    └── Every 60 sec ──► [3] Classification Layer  — continuous poll; classifies each new mention immediately
                              │                       Claude: translate → sentiment → risk tier (L1–L4)
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

### 0. BrandWatch Prototype Layer

Runs during the prototype phase only. Gives the frontend a real data source before any custom crawlers are built.

- **Connector** (`crawlers/brandwatch.py`): authenticates with the BrandWatch API using `BRANDWATCH_API_KEY` + `BRANDWATCH_PROJECT_ID`, queries for Axi mentions, and maps each result to the common mention schema
- **CSV writer** (`scripts/bw_to_csv.py`): appends new rows to `data/brandwatch_mentions.csv`; deduplicates on BrandWatch mention ID so repeated runs never create duplicates
- **Schedule**: APScheduler triggers the connector every 30 minutes — same cadence as the production crawlers
- **Dashboard**: `prototype/dashboard.html` reads directly from the CSV via a lightweight local Flask route (`/api/mentions`)
- **Migration path**: when Phase 2 production crawlers go live, `crawlers/brandwatch.py` is updated to write to PostgreSQL instead of CSV and the prototype dashboard is retired

CSV schema (maps to the common mention schema):

```
id, platform, url, author, posted_at, raw_text, title, sentiment, engagement_count
```

`sentiment` is sourced directly from BrandWatch's own classification — it is used only for prototype display and is replaced by Julie's classification pipeline once the production flow is live.

### 1. Crawler Layer

One scraper module per platform. All scrapers share a common output schema. The list below is the initial target set — the architecture is designed to be extended with additional platforms without changes to the core pipeline.

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
| *(extensible)* | Any additional platform can be added by implementing the base crawler interface |

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

Three sequential Claude calls per mention:

**Stage 1 — Language Detection & Translation**
- Input: raw text
- Output: `detected_language` (ISO 639-1 code) + `translated_text` (English)
- If the mention is already in English, `translated_text` = `raw_text` and no API call is made (fast path)
- Translation is stored alongside the original — the original is never overwritten
- All downstream classification runs on `translated_text`; the original is shown in the dashboard with a "Translated from [language]" label and a "Show original" toggle

**Stage 2 — Sentiment**
- Input: translated text + summary
- Output: `positive` | `negative` | `neutral`
- Applied specifically to review-style content (TrustPilot, App Store, Google Play, ForexPeaceArmy) where positive/negative classification drives the response template and reporting
- Non-review platforms (Reddit, X, news) also receive a sentiment label but it is used for filtering and reporting only, not response routing

**Platform Escalation Floor (deterministic — no Claude call, runs after Stage 2)**
- Business rule: negative sentiment on high-visibility platforms enforces a minimum risk tier of L3
- Broker review & complaint sites: TrustPilot, BrokersView, FastBull, ForexPeaceArmy, Forex Factory
- App stores: Google Play, Apple App Store
- Financial forums & communities: Reddit (r/Forex, r/Daytrading), Telegram groups, WhatsApp communities
- Claude may still return L4 (preserved); floor only prevents under-classification on these platforms
- Any floor override is annotated in `risk_reasoning` for auditability

**Stage 3 — Risk Tier**
- Input: translated text + summary + sentiment
- Output: `L1` | `L2` | `L3` | `L4` (platform floor applied after this call)
- Tier definitions: finalised during validation phase (see Open Questions)
- Prompt includes: chain-of-thought enforcement, prompt-injection defence preamble, mention delimiters

PII redaction (regex-based) runs on `raw_text` before any Claude call.

### 4a. Response Agent

Handles both `PENDING_AUTO_RESPOND` (auto-posts) and `PENDING_HUMAN_POST` (drafts for human approval).

- Selects the correct response template based on platform + sentiment + category
- Claude personalises the template and writes the full response in the **same language as the original mention** — `detected_language` from the classification layer is passed to the prompt. Templates are in English; Claude translates as part of personalisation. No exceptions.
- All responses enforce Axi brand voice: **polite, corporate, solution-oriented** — consistent with Axi's website tone. No defensive language, no fault admissions, no legal commitments in any auto-generated text.
- Auto-posts L1/L2 on standard platforms; queues draft for **Community Manager** approval on L4, forums, and client-identified mentions

Template categories:
- Positive review → thank you + brand reinforcement
- General complaint (L1) → acknowledgement + support link
- Minor product complaint (L2) → acknowledgement + resolution path
- L4 / client identified → empathetic acknowledgement + escalation to private support channel
- Forum mention → community acknowledgement + invite to contact support privately

### 4c. Immediate Notifications (L3 / L4)

Fires the moment classification writes L3 or L4 to the DB — before the Community Manager next opens the dashboard.

- **Telegram + email** to the Community Manager — fires immediately on L3/L4 classification
- **12-hour reminders** repeat until the mention is resolved or dismissed
- **24-hour SLA breach** triggers a final escalation alert if still unresolved
- Reminders are suppressed the moment the Community Manager sets any manual resolution: `not_relevant`, `wont_respond`, `escalated`, or `responded`
- All delivery attempts and resolution actions logged for audit

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
| `/mention/<id>` | Detail — screenshot, raw text (+ translated), summary, sentiment, classification, ticket |
| `/compliance` | L3/L4 queue — approve response / escalate / dismiss |
| `/tickets` | All Jira tickets and current status |
| `/runs` | Crawler run history |

Flask-Login with persistent remember-me cookie (30 days). Login once, stay logged in across browser sessions. Credentials from `.env`.

---

## Data Model (PostgreSQL)

```
mentions
  id, platform, url, author, posted_at, raw_text, title,
  detected_language, translated_text,
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

### Phase 0 — BrandWatch Prototype (Unblocks Frontend)
- [ ] `crawlers/brandwatch.py` — BrandWatch API connector; authenticate, query Axi mentions, map to common schema
- [ ] `scripts/bw_to_csv.py` — append new rows to `data/brandwatch_mentions.csv`; dedup on BrandWatch mention ID
- [ ] Flask route `/api/mentions` in a minimal `prototype_server.py` — serves CSV rows as JSON for `prototype/dashboard.html`
- [ ] APScheduler job (every 30 min) — keeps CSV current; runs alongside production scheduler once Phase 7 is live
- [ ] Add `BRANDWATCH_API_KEY` and `BRANDWATCH_PROJECT_ID` to `.env.example`

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
- [ ] Stage 1 language detection + translation (Claude call; English fast-path skips call)
- [ ] Stage 2 sentiment prompt + Claude call (positive / negative / neutral)
- [ ] Stage 3 risk tier prompt + Claude call (tiers TBD — see Open Questions)
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
- [ ] Credentials rotated before sharing dashboard access

---

## Open Questions (Decide During Build)

1. **L1–L4 tier definitions** — defined in PLAN_Julie.md; to be validated against real Axi mention data in Phase 7 and adjusted if needed
2. **Response templates** — need to be written per platform and category before Phase 4 can ship
3. **Which Jira project key** handles mentions? CX? Legal?
4. **Platform API credentials** — X, Meta, TikTok, LinkedIn all require app registration; confirm which accounts Axi has
5. **Anthropic API** — Axi corporate account; data stays within Axi's contracted environment. PII redactor runs before all Claude calls as good practice.

---

## Verification

- Run crawler in isolation per platform, confirm output schema matches
- Run classification pipeline against 30-day BrandWatch export — use the CSV produced by `scripts/bw_to_csv.py` as the source; review every label manually
- Test translation stage with non-English mentions (Arabic, Spanish, Portuguese, Thai — key Axi markets); confirm translated text is accurate before downstream classification runs on it
- Test sentiment classification on a sample of TrustPilot and App Store reviews; verify positive/negative accuracy matches human labels
- Test auto-reply end-to-end on a sandbox Reddit account before enabling on live accounts
- Confirm L3/L4 Jira tickets appear with correct fields and `PENDING_HUMAN_REVIEW` status
- Confirm Jira sync updates local DB correctly after manually moving a ticket in Jira
