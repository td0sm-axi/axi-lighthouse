from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Mention(Base):
    __tablename__ = "mentions"
    __table_args__ = (
        UniqueConstraint("platform", "dedup_key", name="uq_platform_dedup"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)

    # Crawler fields (Som)
    platform: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(256), nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    engagement: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    dedup_key: Mapped[str] = mapped_column(String(128), nullable=False)

    # Enrichment fields (Som) — screenshot_path always NULL in v1
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    detected_language: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Classification fields (Julie)
    sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sentiment_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(4), nullable=True, index=True)
    risk_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_client_info: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pending_axi_reply: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    routing_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    watch_flags: Mapped[str | None] = mapped_column(String(256), nullable=True)
    classification_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    classification_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Response / escalation fields (Timur)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    jira_ticket_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    jira_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolution_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_breached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class CrawlerRun(Base):
    __tablename__ = "crawler_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    platform: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mentions_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[str | None] = mapped_column(Text, nullable=True)
