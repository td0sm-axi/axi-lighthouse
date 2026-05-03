"""
Lighthouse scheduler — runs all crawlers every 5 hours.

Cadence: hour="*/5" → runs at 00:00, 05:00, 10:00, 15:00, 20:00 UTC.
This ensures any L4 mention is detected within 5 hours, inside the 6-hour response SLA.

On first run (no prior successful crawl for a platform), looks back 7 days.
Subsequent runs look back to the last successful crawl timestamp.

Usage:
    python scheduler.py
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import sentry_sdk
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from crawlers.app_stores import AppStoreCrawler, GooglePlayCrawler
from crawlers.base import RawMention
from crawlers.forex_forums import BabyPipsCrawler, ForexFactoryCrawler, ForexPeaceArmyCrawler
from crawlers.mql5 import MQL5Crawler
from crawlers.myfxbook import MyfxbookCrawler
from crawlers.reddit import RedditCrawler
from crawlers.tradingview import TradingViewCrawler
from crawlers.trustpilot import TrustpilotCrawler
from db.models import CrawlerRun, Mention
from db.session import SessionLocal
from enrichment.summariser import summarise

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger(__name__)

sentry_sdk.init(dsn=os.environ.get("SENTRY_DSN", ""), traces_sample_rate=0)

INITIAL_LOOKBACK_DAYS = 7

# Crawl order: cheapest / safest first, Playwright+proxy platforms last
CRAWLERS: list[tuple[str, object]] = [
    ("reddit",          RedditCrawler()),
    ("trustpilot",      TrustpilotCrawler()),
    ("babypips",        BabyPipsCrawler()),
    ("mql5",            MQL5Crawler()),
    ("tradingview",     TradingViewCrawler()),
    ("google_play",     GooglePlayCrawler()),
    ("app_store",       AppStoreCrawler()),
    ("myfxbook",        MyfxbookCrawler()),
    ("forexpeacearmy",  ForexPeaceArmyCrawler()),
    ("forexfactory",    ForexFactoryCrawler()),
]


def _last_successful_crawl(platform: str) -> datetime:
    with SessionLocal() as session:
        run = (
            session.query(CrawlerRun)
            .filter_by(platform=platform)
            .filter(CrawlerRun.errors.is_(None), CrawlerRun.finished_at.isnot(None))
            .order_by(CrawlerRun.finished_at.desc())
            .first()
        )
        if run and run.finished_at:
            return run.finished_at.replace(tzinfo=timezone.utc) if run.finished_at.tzinfo is None else run.finished_at
    return datetime.now(timezone.utc) - timedelta(days=INITIAL_LOOKBACK_DAYS)


def _save_mentions(raw: list[RawMention], platform: str) -> int:
    inserted = 0
    with SessionLocal() as session:
        for m in raw:
            key = m.dedup_key()
            exists = session.query(Mention).filter_by(platform=platform, dedup_key=key).first()
            if exists:
                continue
            summary = summarise(m.raw_text, platform)
            row = Mention(
                platform=platform,
                url=m.url,
                author=m.author,
                posted_at=m.posted_at,
                raw_text=m.raw_text,
                title=m.title,
                engagement=m.engagement,
                review_id=m.review_id,
                dedup_key=key,
                summary=summary,
            )
            session.add(row)
            inserted += 1
        session.commit()
    return inserted


async def _run_crawler(platform: str, crawler) -> None:
    since = _last_successful_crawl(platform)
    run = CrawlerRun(platform=platform)

    with SessionLocal() as session:
        session.add(run)
        session.commit()
        run_id = run.id

    error_msg: str | None = None
    inserted = 0

    try:
        raw = await crawler.fetch(since)
        inserted = _save_mentions(raw, platform)
        if len(raw) == 0:
            log.warning("%s: 0 results returned — selector may be broken", platform)
    except NotImplementedError:
        log.info("%s: not yet implemented, skipping", platform)
    except Exception as exc:
        error_msg = str(exc)
        log.exception("%s: crawl failed", platform)
        sentry_sdk.capture_exception(exc)

    with SessionLocal() as session:
        run = session.get(CrawlerRun, run_id)
        run.finished_at = datetime.now(timezone.utc)
        run.mentions_found = inserted
        run.errors = error_msg
        session.commit()

    log.info("%s: %d new mention(s)", platform, inserted)


async def crawl_all() -> None:
    log.info("=== Crawl cycle starting ===")
    for platform, crawler in CRAWLERS:
        await _run_crawler(platform, crawler)
    log.info("=== Crawl cycle complete ===")


def main() -> None:
    from init_db import init
    init()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(crawl_all, "cron", hour="*/5", id="crawl_all", misfire_grace_time=300)
    scheduler.start()
    log.info("Scheduler running — crawl every 5 hours (00:00 / 05:00 / 10:00 / 15:00 / 20:00 UTC)")

    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped")


if __name__ == "__main__":
    main()
