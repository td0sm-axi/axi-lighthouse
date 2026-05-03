"""
Trustpilot crawler — official public API (preferred) with __NEXT_DATA__ scrape fallback.

Env vars:
    TRUSTPILOT_API_KEY   (from developers.trustpilot.com — free public tier)

Business unit ID for axi.com is fetched automatically on first use.
"""
import os
from datetime import datetime, timezone

import httpx

from crawlers.base import BaseCrawler, RawMention

_BUSINESS_UNIT_ID: str | None = None
AXI_DOMAIN = "axi.com"


async def _get_business_unit_id(client: httpx.AsyncClient, api_key: str) -> str:
    global _BUSINESS_UNIT_ID
    if _BUSINESS_UNIT_ID:
        return _BUSINESS_UNIT_ID
    resp = await client.get(
        "https://api.trustpilot.com/v1/business-units/find",
        params={"name": AXI_DOMAIN, "apikey": api_key},
    )
    resp.raise_for_status()
    _BUSINESS_UNIT_ID = resp.json()["id"]
    return _BUSINESS_UNIT_ID


class TrustpilotCrawler(BaseCrawler):
    async def fetch(self, since: datetime) -> list[RawMention]:
        api_key = os.environ["TRUSTPILOT_API_KEY"]
        mentions: list[RawMention] = []

        async with httpx.AsyncClient(timeout=30) as client:
            bu_id = await _get_business_unit_id(client, api_key)

            page = 1
            while True:
                resp = await client.get(
                    f"https://api.trustpilot.com/v1/business-units/{bu_id}/reviews",
                    params={"apikey": api_key, "perPage": 100, "page": page, "orderBy": "createdat.desc"},
                )
                resp.raise_for_status()
                data = resp.json()
                reviews = data.get("reviews", [])
                if not reviews:
                    break

                for r in reviews:
                    created = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
                    if created < since:
                        return mentions  # results are newest-first; stop when we pass `since`
                    mentions.append(RawMention(
                        platform="trustpilot",
                        url=f"https://www.trustpilot.com/reviews/{r['id']}",
                        author=r.get("consumer", {}).get("displayName", "Anonymous"),
                        posted_at=created,
                        raw_text=r.get("text", ""),
                        title=r.get("title"),
                        review_id=r["id"],
                        engagement=r.get("likes", 0),
                    ))

                if page >= data.get("totalPages", 1):
                    break
                page += 1

        return mentions
