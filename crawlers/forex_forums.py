"""
Forex forum crawlers:
  - ForexPeaceArmyCrawler  — Cloudflare-protected; requires Playwright + residential proxy
  - BabyPipsCrawler        — Discourse JSON API; plain httpx
  - ForexFactoryCrawler    — Cloudflare-protected; requires Playwright + residential proxy

Proxy env vars (Decodo / Smartproxy):
    PROXY_SERVER    e.g. http://gate.decodo.com:7000
    PROXY_USERNAME
    PROXY_PASSWORD
"""
import os
from datetime import datetime, timezone

import httpx

from crawlers.base import BaseCrawler, RawMention

# ForexFactory thread IDs confirmed to contain Axi discussions (from research)
FF_KNOWN_THREAD_IDS = [1294965, 1291074, 1244370, 927514, 744650, 242612]
FF_BROKER_FORUM_URL = "https://www.forexfactory.com/forum/74-broker-discussion"


def _proxy_kwargs() -> dict:
    server = os.environ.get("PROXY_SERVER")
    if not server:
        return {}
    return {
        "proxy": {
            "server": server,
            "username": os.environ.get("PROXY_USERNAME", ""),
            "password": os.environ.get("PROXY_PASSWORD", ""),
        }
    }


# ---------------------------------------------------------------------------
# ForexPeaceArmy
# ---------------------------------------------------------------------------

class ForexPeaceArmyCrawler(BaseCrawler):
    async def fetch(self, since: datetime) -> list[RawMention]:
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth

        mentions: list[RawMention] = []
        async with Stealth().use_async(async_playwright()) as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(**_proxy_kwargs())
            page = await context.new_page()

            await page.goto("https://www.forexpeacearmy.com/forex-reviews/axi", timeout=60_000)
            # TODO: extract reviews using CSS selectors — verify on first build
            # review_items = await page.query_selector_all(".review-item")
            # for item in review_items: ...
            raise NotImplementedError("ForexPeaceArmy selector extraction not yet implemented")

        return mentions


# ---------------------------------------------------------------------------
# BabyPips (Discourse JSON API — no browser needed)
# ---------------------------------------------------------------------------

class BabyPipsCrawler(BaseCrawler):
    BASE = "https://forums.babypips.com"

    async def fetch(self, since: datetime) -> list[RawMention]:
        mentions: list[RawMention] = []
        headers: dict[str, str] = {}
        api_key = os.environ.get("BABYPIPS_API_KEY")
        if api_key:
            headers["Api-Key"] = api_key
            headers["Api-Username"] = os.environ.get("BABYPIPS_API_USERNAME", "system")

        async with httpx.AsyncClient(headers=headers, timeout=30) as client:
            page = 1
            while True:
                resp = await client.get(
                    f"{self.BASE}/search.json",
                    params={"q": "axi broker", "order": "latest", "page": page},
                )
                resp.raise_for_status()
                data = resp.json()
                posts = data.get("posts", [])
                if not posts:
                    break

                for post in posts:
                    created_str = post.get("created_at", "")
                    if not created_str:
                        continue
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    if created < since:
                        return mentions
                    mentions.append(RawMention(
                        platform="babypips",
                        url=f"{self.BASE}/t/{post.get('topic_id')}/{post.get('post_number', 1)}",
                        author=post.get("username", "unknown"),
                        posted_at=created,
                        raw_text=post.get("blurb", ""),
                        review_id=str(post["id"]),
                    ))

                page += 1
                if page > 10:  # safety cap
                    break

        return mentions


# ---------------------------------------------------------------------------
# ForexFactory
# ---------------------------------------------------------------------------

class ForexFactoryCrawler(BaseCrawler):
    async def fetch(self, since: datetime) -> list[RawMention]:
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth

        mentions: list[RawMention] = []
        async with Stealth().use_async(async_playwright()) as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(**_proxy_kwargs())
            page = await context.new_page()

            for thread_id in FF_KNOWN_THREAD_IDS:
                p_num = 1
                while True:
                    url = f"https://www.forexfactory.com/thread/{thread_id}?page={p_num}"
                    await page.goto(url, timeout=60_000)
                    # TODO: extract posts using CSS selectors — verify on first build
                    # posts = await page.query_selector_all(".thread-post")
                    raise NotImplementedError("ForexFactory selector extraction not yet implemented")

        return mentions
