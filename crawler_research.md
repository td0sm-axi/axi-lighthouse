# Lighthouse — Task B: Custom Crawler Research
**Date:** 2026-04-30
**Author:** Som (research document for Lighthouse v1 crawler build)

---

## Scope of Task B

Task B covers platforms that BrandWatch does not reach: **trading platform review sites, forex community forums, app stores, and open trading communities**. Social media (X/Twitter, Facebook, Instagram, TikTok, LinkedIn) is handled separately through official APIs and is **not** in scope here.

Platforms in scope:

| Platform | Category |
|----------|----------|
| Trustpilot | Broker review site |
| ForexPeaceArmy | Broker review + forex forum |
| BabyPips | Forex community forum |
| ForexFactory | Forex community forum |
| Myfxbook | Trading analytics + broker reviews |
| MQL5 | MetaTrader community forum |
| TradingView | Trading community + ideas |
| Trade2Win | Trading community forum |
| FXBlue | Trading analytics platform |
| Google Play Store | App store reviews |
| Apple App Store | App store reviews |
| Reddit | Forex community (r/Forex, r/algotrading, etc.) |

---

## Platform-by-Platform Breakdown

---

### 1. Trustpilot

**Why it matters:** The primary public review destination for retail traders. Highly indexed by Google — it is often the first result when someone searches "Axi review."

**Does it have an official API?** Yes.

Trustpilot's developer API (`developers.trustpilot.com`) has public endpoints that require no login:

```
GET https://api.trustpilot.com/v1/business-units/find?name=axi.com
→ Returns Axi's internal business unit ID

GET https://api.trustpilot.com/v1/business-units/{businessUnitId}/reviews
→ Returns paginated public reviews (up to 100,000 records)
```

Using the official API is the recommended approach — it is clean, stable, and legally defensible.

**Scraping fallback (if API is unavailable):**

Trustpilot embeds all review data in a `<script id="__NEXT_DATA__">` tag on every review page. A simple HTTP request (no browser needed) retrieves it:

```python
import httpx, json
from bs4 import BeautifulSoup

async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0..."}) as client:
    resp = await client.get("https://www.trustpilot.com/review/axi.com")
    soup = BeautifulSoup(resp.text, "html.parser")
    data = json.loads(soup.find("script", id="__NEXT_DATA__").string)
    reviews = data["props"]["pageProps"]["reviews"]
    total_pages = data["props"]["pageProps"]["totalPages"]
```

Paginate using the internal Next.js data endpoint:
```
https://www.trustpilot.com/_next/data/{buildId}/review/axi.com.json?sort=recency&page=2
```
The `buildId` is found inside the initial `__NEXT_DATA__` JSON. Iterate page 1 through `totalPages`.

**Anti-bot:** Rate limiting on rapid requests. Add 1–2 second delays. Plain `httpx` handles most Trustpilot pages without a browser.

**Axi's Trustpilot URL:** `trustpilot.com/review/axi.com`

**Difficulty:** Low–Medium. Official API is the easy path. Scraping is a solid fallback.

---

### 2. ForexPeaceArmy

**Why it matters:** The most prominent dedicated forex broker review site. Negative reviews here rank highly on Google and are read by traders comparing brokers.

**Technology:** Custom proprietary PHP review system + XenForo-based community forum.

**No official API exists.**

**Anti-bot:** Direct HTTP requests return **HTTP 403**. Full Cloudflare protection is in place. A headless browser (Playwright) with stealth mode and a residential proxy is required.

**Crawling broker reviews:**

```python
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def scrape_fpa_reviews():
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            proxy={"server": "http://gate.decodo.com:7000",
                   "username": "USER", "password": "PASS"}
        )
        page = await context.new_page()
        await page.goto("https://www.forexpeacearmy.com/forex-reviews/axi")
        # Extract reviews via CSS selectors — verify selectors on first build
        reviews = await page.query_selector_all(".review-item")
```

**Crawling the XenForo forum** (community broker discussion threads):

XenForo supports JSON responses when sent the right headers:
```
GET /community/search/?q=axi&o=date
Header: X-Requested-With: XMLHttpRequest
```
Pagination via `&page=N`. Still requires browser cookies due to Cloudflare session checks.

**Difficulty:** Hard. Requires Playwright + playwright-stealth + residential proxy. CSS selectors need maintenance when the site redesigns.

---

### 3. ForexFactory

**Why it matters:** One of the largest and most influential forex communities globally. Forum 74 ("Broker Discussion") contains multiple confirmed Axi threads with high engagement. Any mention here carries significant weight in the retail trader community.

**Technology:** Custom PHP application. Full Cloudflare stack (confirmed — HTTP 403 on direct requests).

**No official API for forum data.** (A public calendar JSON endpoint exists but is irrelevant for brand monitoring.)

**Known Axi thread IDs** (confirmed via research): `1294965`, `1291074`, `1244370`, `927514`, `744650`, `242612`

**Thread URL format:**
```
https://www.forexfactory.com/thread/{id}-{slug}?page={n}
```

**Broker Discussion forum index:**
```
https://www.forexfactory.com/forum/74-broker-discussion
```

**Crawling approach:**

Full Playwright + playwright-stealth + residential proxy required. `undetected-chromedriver` (Selenium-based) has been used by the community but was deprecated February 2025 — Playwright with stealth is the current recommended approach.

```python
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def scrape_ff_thread(thread_id: int, max_pages: int = 10):
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            proxy={"server": "http://gate.decodo.com:7000",
                   "username": "USER", "password": "PASS"}
        )
        page = await context.new_page()
        for p_num in range(1, max_pages + 1):
            url = f"https://www.forexfactory.com/thread/{thread_id}?page={p_num}"
            await page.goto(url)
            # Extract posts via CSS selectors
            posts = await page.query_selector_all(".thread-post")
            if not posts:
                break  # No more pages
```

**Strategy for finding new Axi threads:** Periodically scrape the Forum 74 index page, extract thread titles, and flag any containing "axi" (case-insensitive). Add newly found thread IDs to the crawl list.

**Difficulty:** Hard. Same Cloudflare challenge as ForexPeaceArmy. High Axi signal justifies the engineering effort.

---

### 4. BabyPips Forum

**Why it matters:** The largest English-language forex learning community. Widely read by new and intermediate retail traders. Trusted peer opinions shared here carry weight.

**Technology:** Discourse forum (`forums.babypips.com`).

**Discourse has a native JSON API** — no browser scraping needed. Append `.json` to any Discourse URL:

```python
import httpx

async with httpx.AsyncClient() as client:
    # Search all forum posts for Axi mentions
    resp = await client.get(
        "https://forums.babypips.com/search.json",
        params={"q": "axi broker", "order": "latest"}
    )
    posts = resp.json()["posts"]
    # Each post: {id, blurb, username, created_at, topic_id, url}

    # Fetch a full thread
    resp2 = await client.get("https://forums.babypips.com/t/{topic-id}.json")
    thread = resp2.json()
```

Pagination: `?page=N` in search URL. Add an `Api-Key` header from a registered account for higher rate limits.

**Rate limit:** Keep requests to ≤1/second without an API key.

**ToS note:** BabyPips explicitly prohibits automated scraping. Using the Discourse JSON API at low volume (a published platform feature, not circumventing access controls) is significantly lower risk than browser scraping. Full assessment in the Legal section.

**Difficulty:** Easy. Discourse's native JSON API does the hard work.

---

### 5. Myfxbook

**Why it matters:** Myfxbook is the most widely used third-party trading account analytics platform. It has a confirmed, dedicated Axi broker review page with community ratings, and a community forum. Highly trusted by active traders.

**Axi broker review page:** `https://www.myfxbook.com/reviews/brokers/axi/21257,1`
**Axi prop trading review page:** `https://www.myfxbook.com/reviews/brokers/axi/3303921,1` (Axi Select)

**Official API:** Myfxbook has a documented REST API (`myfxbook.com/api`) — but it only exposes data for the **authenticated user's own accounts**. It does not provide access to broker reviews or forum content. The community outlook endpoint (aggregate retail sentiment by currency pair) is available but unrelated to brand monitoring.

**Scraping broker reviews and forum:**

Direct HTTP requests return HTTP 403 — Cloudflare or similar WAF is in place. Playwright + residential proxy required.

```python
async def scrape_myfxbook_reviews(page_num: int = 1):
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            proxy={"server": "http://gate.decodo.com:7000",
                   "username": "USER", "password": "PASS"}
        )
        page = await context.new_page()
        # Pagination uses comma notation: /21257,1  /21257,2  /21257,3
        url = f"https://www.myfxbook.com/reviews/brokers/axi/21257,{page_num}"
        await page.goto(url)
        # Extract review text, rating, author, date via CSS selectors
```

**Community forum search:** No documented search URL parameter found. Use Google `site:myfxbook.com/community "axi"` to locate specific threads, then scrape those thread URLs directly.

**`robots.txt`:** `/reviews/` and `/community/` are **not disallowed** — these sections are robots.txt-safe to crawl.

**Difficulty:** Low for the official API (sentiment data). Medium–High for broker review HTML scraping (anti-bot present).

---

### 6. MQL5

**Why it matters:** MQL5.com is the official MetaQuotes community platform for MetaTrader 4 and MetaTrader 5 users. Given that Axi's trading platforms include MT4 and MT5, this is a direct-use community. Confirmed Axi mentions found in forum threads, blog posts, and trading signal listings.

**Technology:** Custom application running on Angie (Nginx fork). Hosted on MetaQuotes' own infrastructure. **No Cloudflare** — the absence of Cloudflare is significant; plain HTTP requests work.

**No official REST API for community content.**

**Content types to monitor:**
- Forum threads: `https://www.mql5.com/en/forum/{thread-id}`
- Blog posts: `https://www.mql5.com/en/blogs/`
- Trading signals: `https://www.mql5.com/en/signals/mt5/list/`
- Market products: `https://www.mql5.com/en/market/`

**Scraping approach:**

Plain `requests` + `BeautifulSoup` works. No Cloudflare to bypass:

```python
import httpx
from bs4 import BeautifulSoup

async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0..."}) as client:
    # Forum thread pagination: append -2, -3, etc. to thread ID
    resp = await client.get("https://www.mql5.com/en/forum/475583")
    soup = BeautifulSoup(resp.text, "html.parser")
    posts = soup.select(".post-content")

    # Signals list pagination: /list/page{N}
    resp2 = await client.get("https://www.mql5.com/en/signals/mt5/list/page2")
```

**robots.txt:** Forum and blog content are **not disallowed**. `/en/search` is disallowed — use direct section browsing and pagination instead of the site's search. Use Google `site:mql5.com "axi"` to identify specific thread IDs and blog post URLs, then crawl those directly.

**Known bot blocks:** Mail.RU_Bot, SemrushBot, AhrefsBot are blocked. Standard browser User-Agent works fine.

**Difficulty:** Low–Medium. No Cloudflare, no browser required. Pagination is straightforward.

---

### 7. TradingView

**Why it matters:** TradingView is used by millions of traders worldwide for charting and market analysis. Its community section (ideas, scripts, Minds posts) and news feed reference brokers. Note: **Axi is not in TradingView's broker directory** — it does not have a TradingView broker review page. However, Axi appears in TradingView news articles (e.g., "Axi Select Marks One Year") and may be mentioned in community ideas and Minds posts.

**Technology:** AWS CloudFront (not Cloudflare). Moderate anti-bot protection.

**No public API for community content.** A Broker Integration API exists but requires a formal broker partnership and is for order execution, not data access.

**Available Python library:** `tradingview-scraper` (PyPI, v0.4.20, December 2025, actively maintained).

```python
from tradingview_scraper.ideas import Ideas
from tradingview_scraper.news import News

# Scrape ideas mentioning "axi"
ideas = Ideas()
results = ideas.get_ideas(symbol="AXI", language="en", sort="recent")

# Scrape news
news = News()
articles = news.get_news(symbol="AXI", country="au")
```

For community Minds posts and general text search, use Playwright + residential proxy against CloudFront-protected pages.

**robots.txt:** `/search/` is disallowed. Ideas and news pages are accessible. Specific AI bots (ClaudeBot, PerplexityBot) are blocked from certain sections — use a standard browser User-Agent.

**Difficulty:** Medium. CloudFront WAF + rate limiting, but the `tradingview-scraper` library handles most of the complexity.

---

### 8. Trade2Win

**Why it matters:** An established UK-based trading community forum. **However, Axi has very minimal presence on Trade2Win** — only one confirmed result from research. Included for completeness but is the lowest priority platform in scope.

**Technology:** XenForo 2.x + full Cloudflare stack.

**Search URL:** `https://www.trade2win.com/search/?q=axi&o=date`

**robots.txt:** `/search/` is explicitly disallowed for crawlers.

**Scraping approach:**

Playwright + playwright-stealth + residential proxy (same pattern as ForexFactory/ForexPeaceArmy). XenForo-specific Python scrapers exist (`forumscraper` on PyPI, `TUVIMEN/xenforo-scraper` on GitHub) but require proxy wrapping to get past Cloudflare.

**Realistic assessment:** Given the near-zero Axi presence, the high scraping complexity (full Cloudflare), and the engineering effort required, Trade2Win should be **deprioritized** or excluded from the initial build. Revisit if Axi's presence grows on the platform.

**Difficulty:** High. Low value-to-effort ratio for Axi specifically.

---

### 9. FXBlue

**Why it matters:** FXBlue is a trading analytics platform used by individual traders to track and publish performance. **Important clarification: FXBlue is not a community forum and does not have broker reviews or discussion boards.** Its relevance to Axi is indirect — Axi runs trading competitions hosted via FXBlue infrastructure.

**Technology:** Next.js on AWS. **No Cloudflare** — directly on AWS with open `robots.txt` (`Allow: /` with no restrictions).

**What FXBlue does have:**
- Public trader performance profiles (`fxblue.com/users/{username}/`)
- RSS feeds, CSV exports, and stats pages for public accounts
- Trading competition leaderboards

**What FXBlue does NOT have:**
- Broker reviews
- Community discussion forums
- Searchable content about brokers

**Recommendation:** **Exclude FXBlue from the crawler.** There is no community content to mine for brand mentions. If Axi competition data is needed (leaderboards, participant counts), that lives on Axi's own site, not on FXBlue's community.

---

### 10. Google Play Store Reviews

**Library:** `google-play-scraper` by JoMingyu
**Version:** 1.2.7 (released June 2024, actively maintained)
**Install:** `pip install google-play-scraper`

**Confirmed app package names:**
- Axi Trading Platform: `com.lagom` (100K+ installs, 2.5★ from ~1,220 reviews)
- Axi Copy Trading: `com.axi.pelican` (separate app)

Reverse-engineers Google Play's internal RPC endpoints — no API key required.

```python
from google_play_scraper import reviews, Sort

result, continuation_token = reviews(
    'com.lagom',            # Axi Trading Platform (confirmed package name)
    lang='en',
    country='au',           # Query per country: au, gb, us, sg, za, ae
    sort=Sort.NEWEST,
    count=200
)

# Next page
result2, token2 = reviews('com.lagom', continuation_token=continuation_token)

# Axi Copy Trading app (separate app, separate package)
# result_ct, _ = reviews('com.axi.pelican', lang='en', country='au', sort=Sort.NEWEST, count=200)
```

**Safe rate pattern:** 200 reviews per call, 2–3 second delay between calls. Never use `reviews_all()` in production.

**Country coverage:** Query key markets separately: `au`, `gb`, `us`, `sg`, `za`, `ae`.

**Difficulty:** Medium. Well-maintained library, straightforward integration.

---

### 11. Apple App Store Reviews

**App IDs (confirmed):**
- Axi Trading Platform: `1537332269`
- Axi Copy Trading: `1589937901`

**Primary method:** Apple's **App Store Connect API** (`/v1/apps/{id}/customerReviews`) provides full access with stable IDs and **only works for apps you own** — which is the case here. This is the preferred method.

**Fallback library:** `app-store-web-scraper` (v0.2.0, June 2024) — uses the undocumented iTunes Customer Reviews API. Prefer over `app-store-reviews-reader`, which has a 47/100 health score on Snyk and is effectively dormant (last meaningful commit before its Aug 2025 v1.3 release was months prior, no PR activity). Both `app-store-reviews-reader` and the older `app-store-scraper` (abandoned 2020) should be avoided for new builds.

Apple's public RSS feed endpoint (used by both fallback libraries):
```
https://itunes.apple.com/{country}/rss/customerreviews/page={page}/sortBy=mostRecent/id={app_id}/json
```

```python
from app_store_web_scraper import AppStoreEntry, AppStoreReview

entry = AppStoreEntry(app_id=1537332269, country="au")
for review in entry.reviews():
    print(review.rating, review.title, review.content, review.date)
```

**Critical limitations (RSS fallback):**
- Max ~500 reviews per country per call via the RSS endpoint (50/page, ~10 pages)
- Apple does not provide stable review IDs in the RSS feed — use SHA-256 hash of `(author + date + first 100 chars)` for deduplication
- Rate limiting: HTTP 403 on rapid requests — add 2–3 second delays

**Country coverage:** `au`, `gb`, `us`, `sg`, `za`, `ae`

**Difficulty:** Medium. App Store Connect API is cleanest; fallback scraper is straightforward.

---

### 12. Reddit

**Library:** `praw`
**Install:** `pip install praw`

Register at `reddit.com/prefs/apps` (script type) to get credentials.

```python
import praw

reddit = praw.Reddit(
    client_id="CLIENT_ID",
    client_secret="CLIENT_SECRET",
    user_agent="AXI-BrandMonitor/1.0 by u/your_username"
)

# Search all of Reddit
for submission in reddit.subreddit("all").search("axi broker forex", sort="new", limit=100):
    print(submission.title, submission.url, submission.created_utc)

# Target key forex subreddits directly for higher signal-to-noise
for sub in ["Forex", "algotrading", "investing", "CFD", "forextrading"]:
    for post in reddit.subreddit(sub).search("axi", sort="new", limit=50):
        print(post.title)
```

**Rate limit:** 100 requests/minute on the free OAuth tier — more than sufficient.

**Hard ceiling:** Reddit returns at most ~1,000 posts per search query. Cannot paginate beyond this.

**Cost:** Free OAuth tier is adequate for brand monitoring volume.

**Difficulty:** Easy. Best-documented API of all platforms in scope.

---

## Anti-Bot Protection: The Central Challenge

### How Websites Detect Bots (Plain English)

1. **IP reputation** — Is this IP address from a datacenter? Has it been flagged before? Checked before the page even loads. A Python script on a cloud server will be flagged immediately.

2. **TLS fingerprinting** — The cryptographic "handshake" your HTTP client performs has a fingerprint. Python's standard libraries have a distinctive fingerprint that says "I am not Chrome." Invisible to you, readable by the server.

3. **Browser JavaScript checks** — `navigator.webdriver` is `true` in automated browsers. Basic bot scripts check for this.

4. **Behavioural analysis** — Advanced systems (DataDome, PerimeterX) track mouse movements, scroll timing, and navigation patterns. Statistical differences between human and bot behaviour are detectable.

5. **CAPTCHA challenges** — Cloudflare Turnstile and hCaptcha present interactive puzzles requiring real browser execution.

### What Defeats Each Level

| Protection Level | What It Does | What Defeats It |
|-----------------|-------------|-----------------|
| Level 1 — Basic JS check | `navigator.webdriver` flag | `playwright-stealth` |
| Level 2 — TLS fingerprint | JA3/JA4 hash of connection | `curl_cffi` or Playwright (real browser TLS) |
| Level 3 — Cloudflare Turnstile | Interactive CAPTCHA | SeleniumBase UC Mode or CapSolver (~$2/1,000) |
| Level 4 — Enterprise WAF | Multi-signal ML analysis | Managed browser service (Bright Data) + residential proxy |

**Decision tree:**
```
Is JavaScript rendering required?
├─ No, no anti-bot → httpx
├─ No, TLS fingerprinting only → curl_cffi
├─ Yes, basic anti-bot → playwright + playwright-stealth
└─ Yes, Cloudflare/CAPTCHA → playwright + residential proxy + CAPTCHA solver
```

**Do not use `cloudscraper`** — only handles old Cloudflare JS challenge versions, ineffective in 2025.
**Do not use `undetected-chromedriver`** — deprecated February 2025, Cloudflare detects it.

### Setting Up playwright-stealth

```bash
pip install playwright playwright-stealth
playwright install chromium
```

```python
from playwright_stealth import Stealth
from playwright.async_api import async_playwright

async def scrape(url: str):
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url)
        return await page.content()
```

`playwright-stealth` v2.0.3 (April 2026) patches ~17 fingerprint vectors: `navigator.webdriver`, plugins list, language/platform/vendor, Chrome-specific APIs, WebGL vendor strings, and more.

---

## Rotating Proxies

### What They Are (Plain English)

Every request your crawler makes arrives at the target server with your IP address attached. If the same IP makes many requests quickly, it gets banned. A **rotating residential proxy** routes each request through a different IP address assigned to a real home internet connection — much harder to detect and block than datacenter IPs.

### Provider Comparison

| Provider | Network Size | Entry Price | Notes |
|----------|-------------|-------------|-------|
| **Decodo** (ex-Smartproxy) | 115M+ residential IPs | $11.25/month (3 GB); popular plan $81.25/month (25 GB) | Good value; rebranded April 2025 |
| **Bright Data** | 72M+ residential IPs | ~$300+/month | Most features; enterprise-focused |
| **Oxylabs** | 100M+ residential IPs | ~$15/GB | Strong at scale |

**Decodo pricing tiers (2026):** 3 GB @ $11.25 · 10 GB @ $35 · 25 GB @ $81.25 (popular) · 50 GB @ $150 · 100 GB @ $275. Pay-as-you-go available at $4/GB with no commitment.

**For Axi:** The 10 GB plan ($35/month) is likely sufficient for brand monitoring volume. The 3 GB plan ($11.25/month) is enough for a low-frequency crawl schedule.

### Integration

**With httpx:**
```python
import httpx
proxies = {"https://": "http://user:pass@gate.decodo.com:7000"}
async with httpx.AsyncClient(proxies=proxies) as client:
    resp = await client.get("https://target.com")
```

**With Playwright (set at context level, not page level):**
```python
context = await browser.new_context(
    proxy={"server": "http://gate.decodo.com:7000",
           "username": "USER", "password": "PASS"}
)
```
Create a new browser context per domain to rotate the proxy.

---

## Scheduling

**Recommended tool:** APScheduler v4 (no external dependencies, full async support, in-process)

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job("cron", minute="*/30")
async def job_reddit():
    await scrape_reddit()

@scheduler.scheduled_job("cron", hour="6,12,18,23")
async def job_trustpilot():
    await scrape_trustpilot()

@scheduler.scheduled_job("cron", hour="7,19")
async def job_app_stores():
    await scrape_google_play()
    await scrape_app_store()

@scheduler.scheduled_job("cron", hour="8,20")
async def job_forex_forums():  # FPA, ForexFactory, Myfxbook — stagger to avoid overlap
    await scrape_forexpeacearmy()
    await scrape_forexfactory()
    await scrape_myfxbook()

@scheduler.scheduled_job("cron", hour="9,21")
async def job_light_forums():  # BabyPips, MQL5, TradingView — no proxy needed
    await scrape_babypips()
    await scrape_mql5()
    await scrape_tradingview()

scheduler.start()
```

**Why not Celery?** Celery is for distributed systems across multiple servers. APScheduler is zero infrastructure overhead and fully capable for a single-server brand monitor.

---

## Deduplication

### Strategy 1 — Platform ID (Primary)

Most platforms provide stable unique IDs. Use a PostgreSQL unique constraint:

```sql
CREATE TABLE mentions (
    id          SERIAL PRIMARY KEY,
    platform    TEXT NOT NULL,
    review_id   TEXT NOT NULL,
    raw_text    TEXT,
    posted_at   TIMESTAMPTZ,
    UNIQUE (platform, review_id)
);
```

```python
await conn.execute("""
    INSERT INTO mentions (platform, review_id, raw_text, posted_at)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (platform, review_id) DO NOTHING
""", "trustpilot", review["id"], review["text"], review["date"])
```

### Strategy 2 — Content Hash (Apple App Store)

Apple's RSS feed does not provide stable review IDs:

```python
import hashlib

def content_hash(author: str, date: str, text: str) -> str:
    return hashlib.sha256(f"{author}|{date}|{text[:100]}".encode()).hexdigest()
```

Store as a unique constraint in the database. Insert only when hash is new.

---

## Error Handling and Monitoring

### The Silent Failure Problem

The most dangerous failure mode: the scraper runs, no exception fires, but returns **0 results** because the site changed its HTML structure. Data stops flowing silently for days.

### Layer 1 — Zero-Results Alert

```python
async def run_crawler(name: str, scrape_fn):
    results = await scrape_fn()
    if len(results) == 0:
        await alert_slack(f"CRITICAL: {name} crawler returned 0 results — selector may be broken.")
    return results
```

### Layer 2 — Sentry Exception Capture

```python
import sentry_sdk
sentry_sdk.init(dsn="YOUR_SENTRY_DSN")

try:
    await run_crawler("ForexFactory", scrape_forexfactory)
except Exception as e:
    sentry_sdk.capture_exception(e)
```

Sentry sends email/Slack alerts with full stack traces. Free tier is sufficient.

### Layer 3 — Retry with Exponential Backoff

```python
from functools import wraps
import asyncio

def retry(max_attempts=3, base_delay=10):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception:
                    if attempt == max_attempts - 1:
                        raise
                    await asyncio.sleep(delay)
                    delay *= 2  # 10s → 20s → 40s
        return wrapper
    return decorator
```

### Layer 4 — Slack Alerting

```python
import httpx

async def alert_slack(message: str):
    await httpx.AsyncClient().post(
        SLACK_WEBHOOK_URL,
        json={"text": f":rotating_light: Brand Monitor: {message}"}
    )
```

---

## Legal Considerations

> **Disclaimer:** Practical risk assessment only — not legal advice. Consult Axi's legal team before deployment.

### GDPR

GDPR applies to personal data (usernames, review text) even when publicly visible. The applicable lawful basis is **legitimate interest** (Article 6(1)(f)).

**Safe practices:**
1. Store review text and ratings. Do not store reviewer email addresses or profile URLs beyond deduplication needs.
2. Respect `robots.txt` — French regulator CNIL now treats it as a signal in legitimate interest assessments.
3. Log all scraping activity with timestamps for audit trail.
4. Do not re-sell or share scraped data with third parties.

### Platform Risk Assessment

| Platform | Risk Level | Rationale |
|----------|-----------|-----------|
| Trustpilot | **Low** | Official API available. Public review monitoring is widely practiced and clearly legitimate interest. |
| Google Play | **Low** | Public data, widely-used library, own-brand monitoring. |
| App Store | **Low** | App Store Connect API available for Axi's own app. |
| Reddit | **Low** | Using official PRAW with OAuth, within published rate limits. |
| BabyPips | **Medium** | ToS prohibits automated access. Low-volume Discourse JSON API at ≤1 req/s is materially lower risk than screen-scraping. |
| MQL5 | **Medium** | No robots.txt restriction on forum/blog content; no explicit ToS prohibition found. Low volume. |
| Myfxbook | **Medium** | robots.txt does not restrict review pages. Anti-bot bypass required. |
| TradingView | **Medium** | CloudFront WAF bypass needed. `tradingview-scraper` library uses documented approaches. |
| ForexPeaceArmy | **Medium–High** | Cloudflare bypass required. No official API alternative. |
| ForexFactory | **Medium–High** | Cloudflare bypass required. High Axi signal justifies the complexity. |
| Trade2Win | **Medium–High** | Cloudflare bypass required. Very low Axi signal — deprioritise. |

### Key Legal Precedents

- **Meta v. Bright Data (2024):** Scraping publicly accessible data without bypassing authentication is not automatically a CFAA violation.
- **LinkedIn v. hiQ:** Scraping publicly visible, non-password-protected content is likely lawful under US federal computer fraud law.
- **KASPR fine (December 2024):** €240,000 for scraping 160M LinkedIn profiles at massive scale. Axi's brand monitor collects a few hundred mentions per day — orders of magnitude below enforcement-level activity.

---

## Constraints, Roadblocks, and Honest Difficulties

### 1. ForexFactory and ForexPeaceArmy Are the Hardest Targets

Both return HTTP 403 on direct requests. Both require Playwright + stealth + residential proxy. Cloudflare can update its detection algorithms at any time. If either site upgrades to Cloudflare Turnstile (active CAPTCHA), a solving service (CapSolver, ~$2/1,000 CAPTCHAs) will need to be integrated.

**Mitigation:** Start with Playwright + stealth. Add CapSolver if CAPTCHA appears. Both platforms have high Axi signal — the engineering investment is warranted.

### 2. All Playwright Scrapers Break Without Warning

When a website redesigns its HTML, CSS selectors stop matching. The scraper runs silently and returns zero results. The zero-results alert is the primary defence.

**Estimate:** 2–4 hours/month of Som's time for selector maintenance across all Playwright-based scrapers under normal conditions.

### 3. ForexFactory Thread Discovery

ForexFactory has no searchable API. The strategy is: (a) seed with known Axi thread IDs, and (b) periodically scrape the Forum 74 index to find new threads mentioning "Axi." This index scrape itself requires Playwright + proxy and is a two-step process.

### 4. MQL5 Search Is Disallowed by robots.txt

The site's own search endpoint (`/en/search`) is blocked in robots.txt. Use Google `site:mql5.com "axi"` to identify thread IDs and blog post URLs, then crawl those specific pages. This means the thread discovery process is semi-manual initially.

### 5. TradingView — Axi Has No Broker Listing

Axi does not appear in TradingView's broker directory despite using TradingView's charting technology. Community mentions of Axi on TradingView are limited to news articles and occasional ideas/Minds posts. Signal volume will be low; monitor but do not over-invest in this scraper.

### 6. Trade2Win Has Near-Zero Axi Presence

Only one confirmed Axi-related result was found during research. Given the high scraping complexity (full Cloudflare) and the near-zero signal, Trade2Win should be **excluded from the initial build** and revisited only if Axi's presence grows on the platform.

### 7. FXBlue Has No Community Content to Crawl

FXBlue is a trading analytics tool, not a forum or review platform. There is nothing to mine. **Exclude from the crawler entirely.**

---

## Tool Stack Summary

| Platform | Tool | Proxy Needed | Est. Monthly Cost |
|----------|------|-------------|-------------------|
| Trustpilot | Official Trustpilot API or `httpx` + `__NEXT_DATA__` | No | Free |
| ForexPeaceArmy | `playwright` + `playwright-stealth` | Yes | Proxy cost below |
| ForexFactory | `playwright` + `playwright-stealth` | Yes | Proxy cost below |
| BabyPips | `httpx` against Discourse JSON API | No | Free |
| Myfxbook | `playwright` + `playwright-stealth` (reviews) | Yes | Proxy cost below |
| MQL5 | `httpx` + `BeautifulSoup` | No | Free |
| TradingView | `tradingview-scraper` (PyPI) | Occasionally | Free |
| Trade2Win | **Deprioritised — exclude from initial build** | — | — |
| FXBlue | **Not a community platform — exclude** | — | — |
| Google Play | `google-play-scraper` v1.2.7 (packages: `com.lagom`, `com.axi.pelican`) | No | Free |
| App Store | App Store Connect API (official, App ID: `1537332269`) | No | Free |
| Reddit | `praw` v7.8.1 (free OAuth tier) | No | Free |
| Residential proxies | Decodo (ex-Smartproxy) | — | $11.25–$150/month |
| Anti-bot (TLS) | `curl_cffi` | — | Free |
| Anti-bot (JS/Cloudflare) | `playwright-stealth` v2.0.3 | — | Free |
| Anti-bot (CAPTCHA, if needed) | CapSolver | — | ~$2/1,000 CAPTCHAs |
| Scheduling | APScheduler v4 | — | Free |
| Dedup | PostgreSQL unique constraints + SHA-256 | — | Free |
| Monitoring | Sentry (free tier) + Slack webhook | — | Free |

**Estimated total monthly recurring cost: $35–$150/month** (proxies only — 10 GB plan likely sufficient; no social API cost in scope)

---

## Implementation Order

| Priority | Platform | Reason |
|----------|----------|--------|
| 1 | **Reddit** | Free, easy, high signal for retail trader sentiment |
| 2 | **Google Play + App Store** | Free libraries, high value, own-brand data |
| 3 | **Trustpilot** | Official API, simplest and most legally clean |
| 4 | **BabyPips** | Discourse JSON API, minimal setup |
| 5 | **MQL5** | No Cloudflare, plain requests, direct MT4/MT5 community |
| 6 | **Myfxbook** | Confirmed Axi review page; Playwright + proxy |
| 7 | **TradingView** | `tradingview-scraper` library handles complexity |
| 8 | **ForexPeaceArmy** | Hard (Cloudflare), but high-value broker review site |
| 9 | **ForexFactory** | Hard (Cloudflare), but confirmed high Axi thread volume |
| — | **Trade2Win** | Deprioritised — near-zero Axi presence |
| — | **FXBlue** | Excluded — not a community/review platform |

---

*Sources: Scrapfly Blog, Trustpilot Developer Docs, PyPI (google-play-scraper v1.2.7, app-store-reviews-reader, playwright-stealth v2.0.2, praw, tradingview-scraper v0.4.20, forumscraper), W3Techs Technology Profiles (forexfactory.com, trade2win.com, mql5.com, tradingview.com, fxblue.com), Myfxbook Official API Docs (v1.38), Decodo Residential Proxy Pricing (2025), ForexFactory Forum 74 (Broker Discussion), MQL5 robots.txt, Trade2Win robots.txt, FXBlue Live Trader Profiles, Scraperly TradingView Guide (2026), Meta v. Bright Data (2024), KASPR CNIL Decision (December 2024), Apple App Store Connect API Docs*
