from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from kwresearch.collector import GoogleAdsCollector, QuotaExceededError
from kwresearch.collector.google_ads import geo_constant, idea_to_metrics
from kwresearch.db import make_engine, upsert_keywords


def _idea(text="best crm"):
    vols = [NS(year=2024, month=m, monthly_searches=m * 10) for m in (3, 1, 2)]
    m = NS(
        avg_monthly_searches=100,
        monthly_search_volumes=vols,
        competition="HIGH",
        competition_index=80,
        low_top_of_page_bid_micros=1_000_000,
        high_top_of_page_bid_micros=2_500_000,
    )
    return NS(text=text, keyword_idea_metrics=m)


def _client(ideas=None, side_effect=None):
    client = MagicMock()
    svc = client.get_service.return_value
    if side_effect:
        svc.generate_keyword_ideas.side_effect = side_effect
    else:
        svc.generate_keyword_ideas.return_value = ideas or [_idea()]
    return client, svc


def quota_error():
    err = NS(error_code=NS(quota_error=2))
    return type("E", (Exception,), {"failure": NS(errors=[err])})()


def test_idea_conversion_sorts_series_and_converts_micros() -> None:
    m = idea_to_metrics(_idea())
    assert m.monthly_searches == [10, 20, 30]
    assert m.low_top_of_page_bid == 1.0 and m.high_top_of_page_bid == 2.5


def test_geo_constant() -> None:
    assert geo_constant("us") == "geoTargetConstants/2840"
    with pytest.raises(ValueError):
        geo_constant("zz")


def test_collect_caches_responses() -> None:
    client, svc = _client()
    with Session(make_engine("sqlite://")) as s:
        c = GoogleAdsCollector(client, "123-456", session=s)
        first = c.collect(["crm"])
        second = c.collect(["crm"])
        assert first[0].text == second[0].text == "best crm"
        assert svc.generate_keyword_ideas.call_count == 1
        assert upsert_keywords(s, first, "US", "en") == 1


def test_retries_then_succeeds_and_gives_up() -> None:
    sleeps: list[float] = []
    client, svc = _client(side_effect=[quota_error(), [_idea()]])
    c = GoogleAdsCollector(client, "1", sleep=sleeps.append)
    assert len(c.collect(["a"])) == 1 and sleeps == [1.0]

    client, _ = _client(side_effect=quota_error())
    c = GoogleAdsCollector(client, "1", max_retries=2, sleep=sleeps.append)
    with pytest.raises(QuotaExceededError):
        c.collect(["a"])


def test_requires_seed() -> None:
    with pytest.raises(ValueError):
        GoogleAdsCollector(MagicMock(), "1").collect([])
