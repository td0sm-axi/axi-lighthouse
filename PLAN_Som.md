# Lighthouse v1 — Som: Crawler & Enrichment Layer

Owner: Som  
Depends on: nothing (this is the entry point of the pipeline)  
Feeds into: Julie's Classification Layer

> **STATUS: PLANNING PHASE ONLY**
> Do not begin implementation. The goal right now is to identify all edge cases, validate the logic, and surface any unknowns before a single line of code is written. Review each section critically and add questions or concerns inline.

---

## Context

Som owns the first two stages of the Lighthouse pipeline. The crawler layer collects raw mentions from all platforms. The enrichment layer takes each raw mention, takes a screenshot, generates a summary, and persists everything to PostgreSQL before passing to classification.

---

## Architecture Position

```
Scheduler (APScheduler)
    │
    ▼
[1] Crawler Layer          ← Som
    │
    ▼
[2] Enrichment Layer       ← Som
    │
    ▼
[3] Classification Layer   → Julie
```

---

## Component 1 — Crawler Layer

One scraper module per platform. All scrapers implement the same interface and return the same output schema so the rest of the pipeline never needs to know which platform produced a mention.

### Platforms & Methods

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

### Common Output Schema

Every scraper must return this exact structure:

```python
{
  "platform": str,        # e.g. "reddit", "trustpilot", "x"
  "url": str,             # direct link to the mention
  "author": str,          # username or display name
  "posted_at": datetime,  # UTC
  "raw_text": str,        # full unmodified text of the mention
  "title": str | None     # post title if applicable, else None
}
```

### File Structure

```
crawlers/
  __init__.py
  base.py               # BaseCrawler abstract class with common interface
  reddit.py
  trustpilot.py
  forex_forums.py       # ForexPeaceArmy + BabyPips
  x.py
  meta.py               # Facebook + Instagram
  tiktok.py
  linkedin.py
  app_stores.py         # Google Play + App Store combined
  web.py                # Google Custom Search / SerpAPI
```

---

## Component 2 — Enrichment Layer

Runs immediately after each mention is crawled. Three jobs per mention:

1. **Screenshot** — `playwright` captures a full-page PNG of the mention URL
   - Saved to `data/screenshots/<mention_id>.png`
   - If page requires login or blocks headless browsers, save a blank placeholder and log the failure

2. **Summary** — Claude API call
   - Input: `raw_text`
   - Output: 2–3 sentence summary in English
   - Model: `claude-haiku-4-5-20251001` (fast, cheap — summary is low complexity)

3. **Persist to PostgreSQL** — write the full record before classification begins
   - If enrichment fails partway, the raw mention is still saved so it can be retried

---

## Data Model (Som's tables)

```
mentions
  id                    UUID, primary key
  platform              str
  url                   str
  author                str
  posted_at             datetime (UTC)
  raw_text              str
  title                 str | None
  summary               str | None        ← set by enrichment
  screenshot_path       str | None        ← set by enrichment
  created_at            datetime (UTC)
  -- classification fields set by Julie, left NULL at this stage --

crawler_runs
  id                    UUID, primary key
  started_at            datetime (UTC)
  finished_at           datetime (UTC)
  platform              str
  mentions_found        int
  errors                str | None
```

---

## Planning Checklist

### Design Decisions to Confirm
- [ ] Confirm which subreddits and search terms to monitor on Reddit (not just "Axi" — consider "Axi broker", "Axi trading", "axitrader")
- [ ] Confirm exact TrustPilot page URL and whether Playwright can access it without login
- [ ] Confirm ForexPeaceArmy and BabyPips URLs — are there multiple pages per broker? How deep to crawl?
- [ ] Decide: Google Custom Search vs SerpAPI for web/news — what are the cost and rate limit implications?
- [ ] Confirm PostgreSQL vs SQLite — is PostgreSQL available in the deployment environment?
- [ ] Decide deduplication strategy: same mention crawled twice (e.g. daily runs) — deduplicate by URL? by URL + posted_at? by content hash?
- [ ] Decide crawl window: how far back does each run look? Last 24 hours? Last 7 days on first run?
- [ ] Confirm screenshot storage: local disk or cloud (S3/GCS)? What happens if disk fills up?

### Edge Cases to Resolve
- [ ] **Mention with no text** — e.g. an image-only post or a TikTok video. What do we store? How does classification handle it?
- [ ] **Deleted/removed post** — URL is valid at crawl time, screenshot taken, but post is deleted before next run. Do we re-crawl and update?
- [ ] **Rate limits** — every API (Reddit, X, Meta, TikTok) has rate limits. What happens when we hit one mid-crawl? Fail the whole run or continue with remaining platforms?
- [ ] **Platform blocks headless browser** — TrustPilot and forums may detect Playwright. What is the fallback?
- [ ] **Non-English mentions** — raw_text in Arabic, Spanish, Thai. Does enrichment summarise in English? Does classification handle non-English input reliably?
- [ ] **Very long posts** — a 10,000-word forum thread mentioning Axi once. Do we truncate before sending to Claude? What is the token limit?
- [ ] **Author is Axi itself** — Axi's own social posts appear in brand mention searches. Do we filter these out before storing or before classifying?
- [ ] **Duplicate mentions across platforms** — same complaint copy-pasted to Reddit and TrustPilot. Track as two separate mentions or deduplicate?
- [ ] **App store reviews without URLs** — Google Play and App Store reviews don't have stable deep-link URLs. How do we form a unique URL for the `url` field?
- [ ] **Crawler partial failure** — Reddit succeeds, X fails, Meta succeeds. Do we mark the run as failed or partial? How does retry work?
- [ ] **Screenshot of login wall** — some platforms redirect to login. Screenshot captures login page, not the mention. How do we detect and flag this?
- [ ] **Enrichment fails after crawl** — mention is stored with raw_text but screenshot or summary fails. Does classification still run on it? With what input?

### Logic to Validate
- [ ] Walk through the full data flow end-to-end on paper: crawl → enrich → what exactly lands in the DB before Julie's pipeline picks it up?
- [ ] Confirm the common output schema handles all platforms without nullable hacks — title=None is fine, but are there other fields that vary?
- [ ] Confirm `posted_at` timezone handling — all platforms return UTC? Or does each need conversion?
- [ ] Confirm the crawler run record captures enough to diagnose failures: which platform failed, what error, how many mentions were saved before failure?

---

## Environment Variables (Som's section)

```
# Reddit
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=

# X (Twitter)
X_BEARER_TOKEN=

# Meta (Facebook / Instagram)
META_ACCESS_TOKEN=
META_PAGE_ID=

# TikTok
TIKTOK_CLIENT_KEY=
TIKTOK_CLIENT_SECRET=

# LinkedIn
LINKEDIN_ACCESS_TOKEN=

# App Stores (no auth needed for read-only scraping)

# Web search
GOOGLE_CSE_API_KEY=
GOOGLE_CSE_ID=

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/lighthouse

# Anthropic (for enrichment summaries)
ANTHROPIC_API_KEY=
```

---

## Pre-Implementation Sign-Off

Before Som moves to implementation, the following must be resolved:

- [ ] All edge cases above have a documented answer (even if the answer is "out of scope for v1")
- [ ] Deduplication strategy agreed with Timur (impacts the DB schema he owns)
- [ ] Non-English handling agreed with Julie (impacts what her classification prompts must handle)
- [ ] Screenshot storage location agreed with Timur (impacts the dashboard and DB path field)
- [ ] Rate limit and retry strategy agreed — document what "a failed crawl run" looks like so the dashboard can surface it correctly
- [ ] All required API credentials confirmed as obtainable (X, Meta, TikTok, LinkedIn all require app registration approval)
