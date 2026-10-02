"""Pydantic domain model and SQLAlchemy tables."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MICROS = 1_000_000


def micros_to_currency(micros: int | None) -> float | None:
    """Convert Google Ads micros (1/1,000,000 of a currency unit) to currency units."""
    if micros is None:
        return None
    return micros / MICROS


def utcnow() -> datetime:
    return datetime.now(UTC)


class KeywordMetrics(BaseModel):
    """Metrics for one keyword as returned by Keyword Planner."""

    text: str
    avg_monthly_searches: int = 0
    monthly_searches: list[int] = Field(default_factory=list)  # oldest -> newest, up to 12
    competition: str = "UNSPECIFIED"  # LOW / MEDIUM / HIGH / UNSPECIFIED
    competition_index: int = 0  # 0-100
    low_top_of_page_bid: float | None = None
    high_top_of_page_bid: float | None = None
    fetched_at: datetime = Field(default_factory=utcnow)


class Base(DeclarativeBase):
    pass


class KeywordRow(Base):
    __tablename__ = "keywords"
    __table_args__ = (UniqueConstraint("text", "geo", "lang", name="uq_keyword_market"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(255), index=True)
    geo: Mapped[str] = mapped_column(String(8), default="US")
    lang: Mapped[str] = mapped_column(String(8), default="en")
    avg_monthly_searches: Mapped[int] = mapped_column(Integer, default=0)
    monthly_searches: Mapped[list[int]] = mapped_column(JSON, default=list)
    competition: Mapped[str] = mapped_column(String(16), default="UNSPECIFIED")
    competition_index: Mapped[int] = mapped_column(Integer, default=0)
    low_top_of_page_bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_top_of_page_bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trend: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)


class CacheRow(Base):
    """Cached raw response (list of keyword dicts) keyed by request hash."""

    __tablename__ = "api_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    note: Mapped[str] = mapped_column(Text, default="")
