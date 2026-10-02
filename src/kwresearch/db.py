"""Database engine/session helpers and persistence functions."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .models import Base, KeywordMetrics, KeywordRow


def make_engine(url: str) -> Engine:
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return engine


def upsert_keywords(session: Session, items: Iterable[KeywordMetrics], geo: str, lang: str) -> int:
    """Insert or update keyword metrics; returns number of keywords written."""
    n = 0
    for m in items:
        row = session.scalar(
            select(KeywordRow).where(
                KeywordRow.text == m.text, KeywordRow.geo == geo, KeywordRow.lang == lang
            )
        )
        if row is None:
            row = KeywordRow(text=m.text, geo=geo, lang=lang)
            session.add(row)
        row.avg_monthly_searches = m.avg_monthly_searches
        row.monthly_searches = m.monthly_searches
        row.competition = m.competition
        row.competition_index = m.competition_index
        row.low_top_of_page_bid = m.low_top_of_page_bid
        row.high_top_of_page_bid = m.high_top_of_page_bid
        row.fetched_at = m.fetched_at
        n += 1
    session.commit()
    return n
