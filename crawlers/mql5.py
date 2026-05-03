"""
MQL5 crawler — plain httpx + BeautifulSoup (no Cloudflare, no browser needed).

Monitors forum threads, blog posts, and signals pages for Axi mentions.
MQL5's /en/search is disallowed by robots.txt — use direct section pagination instead.

Known Axi thread IDs should be seeded here as they are discovered via
Google site:mql5.com "axi" searches.
"""
import asyncio
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler, RawMention

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Seed with known Axi thread IDs — add more as discovered
KNOWN_THREAD_IDS: list[int] = [475583]

SIGNALS_URL = "https://www.mql5.com/en/signals/mt5/list/page{page}"
BLOGS_URL = "https://www.mql5.com/en/blogs/page{page}"


class MQL5Crawler(BaseCrawler):
    async def fetch(self, since: datetime) -> list[RawMention]:
        raise NotImplementedError(
            "MQL5 selector extraction not yet implemented — "
            "run `python -c 'import httpx; r=httpx.get(\"https://www.mql5.com/en/forum/475583\"); print(r.text[:2000])'` "
            "to inspect the HTML and confirm CSS selectors."
        )
