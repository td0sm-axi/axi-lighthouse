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
[Phase 0 — Prototype]
BrandWatch API  ──► crawlers/brandwatch.py  ──► data/brandwatch_mentions.csv  ──► prototype/dashboard.html

[Phase 1+ — Production]
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

| Platform | Library / Method | Phase |
|---|---|---|
| **BrandWatch** | **BrandWatch API v2 — Axi brand query** | **Phase 0 — Prototype** |
| Reddit | `praw` (official Reddit API) | Phase 2 |
| TrustPilot | `playwright` headless scrape (no public API) | Phase 2 |
| ForexPeaceArmy / BabyPips | `playwright` headless scrape | Phase 2 |
| X (Twitter) | X API v2 — search recent tweets | Phase 2 |
| Facebook / Instagram | Meta Graph API — page mentions + comments | Phase 2 |
| TikTok | TikTok Research API | Phase 2 |
| LinkedIn | LinkedIn API — brand mentions | Phase 2 |
| Google Play | `google-play-scraper` Python library | Phase 2 |
| Apple App Store | `app-store-scraper` Python library | Phase 2 |
| News / Web | Google Custom Search API or SerpAPI | Phase 2 |

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

### Parallel Execution Strategy

All crawlers run simultaneously — one thread per crawler. A mention crawled from any platform is written to the DB immediately and picked up by the classification pipeline within 60 seconds, without waiting for other crawlers to finish.

**Two crawler groups with different concurrency models:**

**Group A — API-based crawlers (ThreadPoolExecutor)**
Each runs in its own thread with independent rate limiting. One slow or rate-limited API does not block the others.

| Crawler | Rate limit | Strategy |
|---|---|---|
| Reddit (`praw`) | 60 req/min | Built-in praw throttling |
| X API v2 | 15 req/15min (search) | Token bucket, back off on 429 |
| Meta Graph API | 200 calls/hour | Per-call delay, back off on 429 |
| TikTok Research API | Varies | Back off on 429 |
| LinkedIn API | Varies | Back off on 429 |
| Google Play scraper | No limit (library) | No throttle needed |
| App Store scraper | No limit (library) | No throttle needed |
| Google Custom Search | 100/day free, 10k/day paid | Daily quota tracker |

**Group B — Playwright scrapers (Browser pool, max 3 concurrent)**
Headless browser instances are memory-heavy. Max 3 run at the same time; the rest queue. Each scraper adds a 1–2 second polite delay between page requests.

| Crawler | Polite delay |
|---|---|
| TrustPilot | 1.5s between pages |
| ForexPeaceArmy | 1.5s between pages |
| BabyPips | 1.5s between pages |
| Forex Factory | 1.5s between pages |
| BrokersView | 1.5s between pages |
| FastBull | 1.5s between pages |

**Enrichment parallelism:**
Screenshot and summary run concurrently per mention using `asyncio`. Screenshot (Playwright) and Claude summary call fire at the same time; both results are written before the mention is marked ready for classification.

```python
# crawler/runner.py — simplified
with ThreadPoolExecutor(max_workers=len(API_CRAWLERS)) as pool:
    api_futures = [pool.submit(crawler.run) for crawler in API_CRAWLERS]

with BrowserPool(max_concurrent=3) as pool:
    playwright_futures = [pool.submit(crawler.run) for crawler in PLAYWRIGHT_CRAWLERS]

# Results written to DB as each future completes — no waiting for all
```

### File Structure

```
crawlers/
  __init__.py
  base.py               # BaseCrawler abstract class with common interface
  brandwatch.py         # Phase 0 — BrandWatch API connector; writes to CSV (prototype) or DB (production)
  runner.py             # parallel executor — ThreadPoolExecutor + BrowserPool
  reddit.py
  trustpilot.py
  forex_forums.py       # ForexPeaceArmy + BabyPips + Forex Factory + BrokersView + FastBull
  x.py
  meta.py               # Facebook + Instagram
  tiktok.py
  linkedin.py
  app_stores.py         # Google Play + App Store combined
  web.py                # Google Custom Search / SerpAPI

scripts/
  bw_to_csv.py          # Phase 0 — maps BrandWatch response to CSV schema; dedupes on mention ID

data/
  brandwatch_mentions.csv   # Phase 0 output; retired once PostgreSQL pipeline is live
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
   - Runs concurrently with screenshot using `asyncio` — both fire at the same time, saving the sequential wait

3. **Persist to PostgreSQL** — write the full record before classification begins
   - Raw mention is written immediately on crawl so classification can start as soon as enrichment completes
   - If enrichment fails partway, the raw mention is still saved and retried on the next enrichment pass
   - **No deduplication** — if the same URL is picked up by multiple crawlers (e.g. a tweet captured by both X API and Google Custom Search), each is stored and classified as a separate mention. URL is not a unique constraint. Each crawler source is an independent signal.

**Design note:** counting the same content twice from different sources is intentional — it reflects the reach of that mention across discovery channels and increases its weight in the engagement and trending calculations.

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
  -- classification fields (including pending_axi_reply) set by Julie, left NULL at this stage --

crawler_runs
  id                    UUID, primary key
  started_at            datetime (UTC)
  finished_at           datetime (UTC)
  platform              str
  mentions_found        int
  errors                str | None
```

---

## Build Checklist

### Phase 0 — BrandWatch Prototype
- [ ] `crawlers/brandwatch.py` — authenticate with BrandWatch API (`BRANDWATCH_API_KEY`, `BRANDWATCH_PROJECT_ID`); query for Axi mentions; map each result to common mention schema
- [ ] `scripts/bw_to_csv.py` — write mapped mentions to `data/brandwatch_mentions.csv`; skip rows where BrandWatch mention ID already exists in CSV
- [ ] `prototype_server.py` — minimal Flask app with `/api/mentions` route that reads CSV and serves rows as JSON for `prototype/dashboard.html`
- [ ] APScheduler job (every 30 min) in `prototype_server.py` — re-runs `bw_to_csv.py` to keep CSV current
- [ ] Test in isolation: run `python -m crawlers.brandwatch` and confirm CSV is populated with correct schema
- [ ] Confirm deduplication: run connector twice in a row, confirm row count does not increase on second run

### Phase 1 — Foundation
- [ ] Create `crawlers/` directory with `base.py` abstract class
- [ ] `crawlers/runner.py` — `ThreadPoolExecutor` for API crawlers + `BrowserPool` (max 3) for Playwright crawlers; writes results to DB as each future completes
- [ ] Set up PostgreSQL connection (`db/connection.py`) and SQLAlchemy models (`db/schema.py`)
- [ ] Install and configure Playwright (headless Chromium)
- [ ] Create `.env.example` with all required credential keys
- [ ] Create `requirements.txt`

### Phase 2 — Crawlers (build + test each in isolation)
- [ ] `crawlers/reddit.py` — `praw`, search for "Axi" in r/Forex and related subs
- [ ] `crawlers/app_stores.py` — `google-play-scraper` + `app-store-scraper`
- [ ] `crawlers/trustpilot.py` — Playwright scrape of Axi TrustPilot page
- [ ] `crawlers/x.py` — X API v2 recent search
- [ ] `crawlers/meta.py` — Meta Graph API page mentions + comments
- [ ] `crawlers/tiktok.py` — TikTok Research API
- [ ] `crawlers/linkedin.py` — LinkedIn brand mentions
- [ ] `crawlers/web.py` — Google Custom Search or SerpAPI
- [ ] `crawlers/forex_forums.py` — Playwright scrape of ForexPeaceArmy + BabyPips

### Phase 3 — Enrichment
- [ ] `enrichment/screenshot.py` — Playwright full-page PNG capture
- [ ] `enrichment/summarise.py` — Claude Haiku call, 2–3 sentence summary
- [ ] `enrichment/pipeline.py` — orchestrates screenshot + summarise + persist for each mention
- [ ] Retry logic: if screenshot fails, log and continue; don't block persist

---

## Environment Variables (Som's section)

```
# BrandWatch (Phase 0 — Prototype)
BRANDWATCH_API_KEY=
BRANDWATCH_PROJECT_ID=

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

## Verification

- Run BrandWatch connector in isolation: `python -m crawlers.brandwatch` — confirm `data/brandwatch_mentions.csv` is created and rows match the CSV schema
- Run connector twice — confirm duplicate rows are not created (dedup on BrandWatch mention ID)
- Start `prototype_server.py` and open `prototype/dashboard.html` — confirm mentions from CSV appear in the UI
- Run each crawler in isolation: `python -m crawlers.reddit` — confirm output matches the common schema
- Run enrichment on a single hardcoded mention — confirm screenshot saved and summary generated
- Check PostgreSQL: `SELECT platform, COUNT(*) FROM mentions GROUP BY platform;`
- Confirm `crawler_runs` table updated after each run with correct mention count and any errors
