"""``kwresearch`` command line interface."""

from __future__ import annotations

import csv
from pathlib import Path

import typer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import make_engine, upsert_keywords
from .intent import label_intent, suggest_product_type
from .models import KeywordRow
from .scoring import load_profile, score_keyword, trend_slope

app = typer.Typer(help="Keyword research: collect, score, export.", no_args_is_help=True)

EXPORT_COLUMNS = [
    "keyword", "volume", "cpc_low", "cpc_high", "competition",
    "trend", "intent", "product_type", "score",
]  # fmt: skip


@app.command()
def collect(
    seeds: str = typer.Option("", help="Comma-separated seed keywords."),
    url: str = typer.Option(None, help="Seed URL."),
    geo: str = typer.Option("US", help="Country code or geo target id."),
    lang: str = typer.Option("en", help="Language code or id."),
    no_cache: bool = typer.Option(False, help="Bypass the response cache."),
) -> None:
    """Fetch keyword ideas from Google Ads and store them."""
    from google.ads.googleads.client import GoogleAdsClient

    from .collector import GoogleAdsCollector

    settings = get_settings()
    seed_list = [s.strip() for s in seeds.split(",") if s.strip()]
    if not seed_list and not url:
        raise typer.BadParameter("Provide --seeds and/or --url.")
    client = GoogleAdsClient.load_from_dict(settings.google_ads_config())
    with Session(make_engine(settings.database_url)) as session:
        collector = GoogleAdsCollector(
            client,
            settings.google_ads_customer_id,
            session=session,
            cache_ttl_hours=settings.cache_ttl_hours,
        )
        items = collector.collect(seed_list, url, geo, lang, use_cache=not no_cache)
        n = upsert_keywords(session, items, geo.upper(), lang.lower())
    typer.echo(f"Stored {n} keywords.")


@app.command()
def score(profile: str = typer.Option("ad_revenue", help="Preset name or YAML path.")) -> None:
    """Label intent, compute trend and score for all stored keywords."""
    prof = load_profile(profile)
    with Session(make_engine(get_settings().database_url)) as session:
        rows = session.scalars(select(KeywordRow)).all()
        for r in rows:
            r.intent = label_intent(r.text)
            r.product_type = suggest_product_type(r.text, r.intent)
            r.trend = trend_slope(r.monthly_searches or [])
            r.score = score_keyword(_to_metrics(r), prof)
        session.commit()
    typer.echo(f"Scored {len(rows)} keywords with profile '{profile}'.")


def _to_metrics(r: KeywordRow):  # noqa: ANN202
    from .models import KeywordMetrics

    return KeywordMetrics(
        text=r.text,
        avg_monthly_searches=r.avg_monthly_searches,
        monthly_searches=r.monthly_searches or [],
        competition=r.competition,
        competition_index=r.competition_index,
        low_top_of_page_bid=r.low_top_of_page_bid,
        high_top_of_page_bid=r.high_top_of_page_bid,
        fetched_at=r.fetched_at,
    )


@app.command()
def export(
    top: int = typer.Option(100, help="Number of top-scored keywords."),
    out: Path = typer.Option(Path("ranked.csv"), help="Output CSV path."),
) -> None:
    """Export the top scored keywords to CSV."""
    with Session(make_engine(get_settings().database_url)) as session:
        rows = session.scalars(
            select(KeywordRow)
            .where(KeywordRow.score.is_not(None))
            .order_by(KeywordRow.score.desc())
            .limit(top)
        ).all()
        with out.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(EXPORT_COLUMNS)
            for r in rows:
                w.writerow([
                    r.text, r.avg_monthly_searches, r.low_top_of_page_bid,
                    r.high_top_of_page_bid, r.competition, r.trend,
                    r.intent, r.product_type, r.score,
                ])  # fmt: skip
    typer.echo(f"Wrote {len(rows)} rows to {out}.")


if __name__ == "__main__":
    app()
