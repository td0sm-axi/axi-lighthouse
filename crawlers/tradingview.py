"""
TradingView crawler — uses the tradingview-scraper PyPI library (v0.4.20).

Note: Axi does not appear in TradingView's broker directory.
Monitoring targets:
  - News articles mentioning "AXI"
  - Community ideas mentioning "AXI"
  - Minds posts (requires Playwright + proxy for CloudFront-protected pages)

ClaudeBot and PerplexityBot are blocked by robots.txt — use standard browser User-Agent.
"""
from datetime import datetime

from crawlers.base import BaseCrawler, RawMention


class TradingViewCrawler(BaseCrawler):
    async def fetch(self, since: datetime) -> list[RawMention]:
        raise NotImplementedError(
            "TradingView extraction not yet implemented — "
            "install tradingview-scraper and verify: "
            "from tradingview_scraper.news import News; n=News(); print(n.get_news(symbol='AXI'))"
        )
