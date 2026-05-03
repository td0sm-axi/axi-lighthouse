"""
App store crawlers — Google Play and Apple App Store.

Package names / App IDs (confirmed):
    Google Play  — com.lagom           (Axi Trading Platform)
                   com.axi.pelican     (Axi Copy Trading)
    App Store    — 1537332269          (Axi Trading Platform)
                   1589937901          (Axi Copy Trading)

Google Play:
    Uses google-play-scraper (JoMingyu, v1.2.7).
    No API key required.

Apple App Store:
    Primary method: App Store Connect API (/v1/apps/{id}/customerReviews) — preferred
    because Axi owns the app and this gives stable IDs and full history.
    Fallback: app-store-web-scraper (v0.2.0) against the iTunes RSS endpoint.
    Max ~500 reviews per country via RSS; use SHA-256 content hash for dedup.

Country coverage for both stores: au, gb, us, sg, za, ae
"""
from datetime import datetime, timezone

from crawlers.base import BaseCrawler, RawMention

COUNTRIES = ["au", "gb", "us", "sg", "za", "ae"]

GOOGLE_PLAY_PACKAGES = ["com.lagom", "com.axi.pelican"]
APP_STORE_IDS = [1537332269, 1589937901]


class GooglePlayCrawler(BaseCrawler):
    async def fetch(self, since: datetime) -> list[RawMention]:
        from google_play_scraper import reviews, Sort

        mentions: list[RawMention] = []
        since_ts = since.timestamp()

        for package in GOOGLE_PLAY_PACKAGES:
            for country in COUNTRIES:
                token = None
                while True:
                    kwargs: dict = dict(
                        app_id=package,
                        lang="en",
                        country=country,
                        sort=Sort.NEWEST,
                        count=200,
                    )
                    if token:
                        kwargs["continuation_token"] = token

                    result, token = reviews(**kwargs)
                    if not result:
                        break

                    for r in result:
                        if r["at"].timestamp() < since_ts:
                            token = None  # stop pagination for this country
                            break
                        mentions.append(RawMention(
                            platform="google_play",
                            url=f"https://play.google.com/store/apps/details?id={package}",
                            author=r.get("userName", "Anonymous"),
                            posted_at=r["at"].replace(tzinfo=timezone.utc),
                            raw_text=r.get("content", ""),
                            title=None,
                            review_id=r.get("reviewId"),
                            engagement=r.get("thumbsUpCount", 0),
                        ))

                    if token is None:
                        break

        return mentions


class AppStoreCrawler(BaseCrawler):
    async def fetch(self, since: datetime) -> list[RawMention]:
        raise NotImplementedError(
            "App Store Connect API not yet wired up. "
            "Configure Apple API key/issuer/key_id in .env, then implement JWT auth "
            "against GET /v1/apps/{id}/customerReviews. "
            "Fallback: use app-store-web-scraper against the iTunes RSS endpoint."
        )
