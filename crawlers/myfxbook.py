"""
Myfxbook crawler — Playwright + residential proxy required (Cloudflare/WAF).

robots.txt confirms /reviews/ and /community/ are NOT disallowed.

Axi review page IDs (confirmed):
    21257   — Axi main broker reviews
    3303921 — Axi Select (prop trading) reviews

Pagination uses comma notation: /21257,1  /21257,2  /21257,3

Env vars:
    PROXY_SERVER, PROXY_USERNAME, PROXY_PASSWORD
"""
import os
from datetime import datetime

from crawlers.base import BaseCrawler, RawMention

AXI_REVIEW_IDS = [21257, 3303921]


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


class MyfxbookCrawler(BaseCrawler):
    async def fetch(self, since: datetime) -> list[RawMention]:
        raise NotImplementedError(
            "Myfxbook selector extraction not yet implemented — "
            "launch Playwright manually against https://www.myfxbook.com/reviews/brokers/axi/21257,1 "
            "to identify CSS selectors for review text, rating, author, and date."
        )
