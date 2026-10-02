from kwresearch.intent import label_intent, suggest_product_type
from kwresearch.models import KeywordMetrics, micros_to_currency
from kwresearch.scoring import Profile, load_profile, score_keyword, trend_slope


def test_micros_conversion() -> None:
    assert micros_to_currency(1_500_000) == 1.5
    assert micros_to_currency(None) is None
    assert micros_to_currency(0) == 0.0


def test_trend_slope() -> None:
    assert trend_slope([10] * 12) == 0.0
    assert trend_slope([]) == 0.0
    assert trend_slope(list(range(1, 13))) > 0
    assert trend_slope(list(range(12, 0, -1))) < 0
    assert abs(trend_slope([100, 110, 120]) - 0.1 / 1.1) < 1e-9


def test_intent_labels_and_products() -> None:
    assert label_intent("pdf compressor online") == "tool/utility"
    assert label_intent("buy running shoes") == "transactional"
    assert label_intent("facebook login") == "navigational"
    assert label_intent("how do volcanoes form") == "informational"
    assert suggest_product_type("pdf compressor online") == "web_tool"
    assert suggest_product_type("how do volcanoes form") == "content_site"
    assert suggest_product_type("best crm vs hubspot") == "affiliate_site"
    assert suggest_product_type("how to track expenses") == "saas_app"


def _m(**kw) -> KeywordMetrics:
    base = dict(
        text="free invoice generator",
        avg_monthly_searches=50_000,
        monthly_searches=list(range(10, 22)),
        competition_index=20,
        low_top_of_page_bid=1.0,
        high_top_of_page_bid=5.0,
    )
    base.update(kw)
    return KeywordMetrics(**base)


def test_score_bounds_and_ordering() -> None:
    p = load_profile("ad_revenue")
    good = score_keyword(_m(), p)
    weak = score_keyword(
        _m(
            text="xyz",
            avg_monthly_searches=10,
            competition_index=95,
            low_top_of_page_bid=None,
            high_top_of_page_bid=None,
            monthly_searches=list(range(22, 10, -1)),
        ),
        p,
    )
    assert 0 <= weak < good <= 100


def test_presets_load_and_exclude_lowers_score() -> None:
    for name in ("ad_revenue", "saas", "lead_gen"):
        assert load_profile(name).weights.demand > 0
    p = Profile(exclude=["invoice"])
    assert score_keyword(_m(), p) < score_keyword(_m(), Profile())
