import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RawMention:
    platform: str
    url: str
    author: str
    posted_at: datetime        # must be timezone-aware UTC
    raw_text: str
    title: str | None = None
    review_id: str | None = None   # platform-native ID; used as dedup_key when present
    engagement: int | None = None

    def dedup_key(self) -> str:
        if self.review_id:
            return self.review_id
        fingerprint = f"{self.author}|{self.posted_at.isoformat()}|{self.raw_text[:100]}"
        return hashlib.sha256(fingerprint.encode()).hexdigest()


class BaseCrawler(ABC):
    @abstractmethod
    async def fetch(self, since: datetime) -> list[RawMention]:
        """Return mentions published at or after `since`. Empty list = no new results."""
        ...
