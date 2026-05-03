"""
Reddit crawler — uses PRAW (official OAuth API).

Monitors r/Forex, r/algotrading, r/investing, r/CFD, r/forextrading
plus a broad search across all subreddits.

Env vars required:
    REDDIT_CLIENT_ID
    REDDIT_CLIENT_SECRET
    REDDIT_USER_AGENT   (e.g. "AXI-Lighthouse/1.0 by u/your_username")
"""
import os
from datetime import datetime, timezone

import praw

from crawlers.base import BaseCrawler, RawMention

SEARCH_TERMS = ["axi broker", "axi trading", "axitrader", "axi forex"]
TARGET_SUBREDDITS = ["Forex", "algotrading", "investing", "CFD", "forextrading"]


class RedditCrawler(BaseCrawler):
    def _client(self) -> praw.Reddit:
        return praw.Reddit(
            client_id=os.environ["REDDIT_CLIENT_ID"],
            client_secret=os.environ["REDDIT_CLIENT_SECRET"],
            user_agent=os.environ.get("REDDIT_USER_AGENT", "AXI-Lighthouse/1.0"),
        )

    async def fetch(self, since: datetime) -> list[RawMention]:
        reddit = self._client()
        since_ts = since.timestamp()
        seen: set[str] = set()
        mentions: list[RawMention] = []

        # Per-subreddit search (higher signal)
        for sub in TARGET_SUBREDDITS:
            for term in SEARCH_TERMS[:1]:  # "axi broker" covers most
                for post in reddit.subreddit(sub).search(term, sort="new", limit=100):
                    if post.created_utc < since_ts or post.id in seen:
                        continue
                    seen.add(post.id)
                    mentions.append(RawMention(
                        platform="reddit",
                        url=f"https://www.reddit.com{post.permalink}",
                        author=str(post.author) if post.author else "[deleted]",
                        posted_at=datetime.fromtimestamp(post.created_utc, tz=timezone.utc),
                        raw_text=f"{post.title}\n\n{post.selftext}".strip(),
                        title=post.title,
                        review_id=post.id,
                        engagement=post.score + post.num_comments,
                    ))

        # Broad search across all of Reddit
        for term in SEARCH_TERMS:
            for post in reddit.subreddit("all").search(term, sort="new", limit=100):
                if post.created_utc < since_ts or post.id in seen:
                    continue
                seen.add(post.id)
                mentions.append(RawMention(
                    platform="reddit",
                    url=f"https://www.reddit.com{post.permalink}",
                    author=str(post.author) if post.author else "[deleted]",
                    posted_at=datetime.fromtimestamp(post.created_utc, tz=timezone.utc),
                    raw_text=f"{post.title}\n\n{post.selftext}".strip(),
                    title=post.title,
                    review_id=post.id,
                    engagement=post.score + post.num_comments,
                ))

        return mentions
