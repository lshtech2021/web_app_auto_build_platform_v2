"""Collector wrapping ``KeywordPlanIdeaService.GenerateKeywordIdeas`` with DB caching."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..models import CacheRow, KeywordMetrics, micros_to_currency, utcnow

log = logging.getLogger(__name__)

# Country code -> Google geo target constant id (pass a numeric id for anything else).
GEO_TARGETS = {
    "US": 2840, "GB": 2826, "CA": 2124, "AU": 2036, "IN": 2356,
    "DE": 2276, "FR": 2250, "ES": 2724, "IT": 2380, "BR": 2076,
}  # fmt: skip
# Language code -> Google language constant id.
LANGUAGES = {
    "en": 1000, "de": 1001, "fr": 1002, "es": 1003, "it": 1004,
    "ja": 1005, "pt": 1014, "nl": 1010,
}  # fmt: skip


class QuotaExceededError(RuntimeError):
    """Raised when quota/rate limits persist after all retries."""


def geo_constant(geo: str) -> str:
    gid = GEO_TARGETS.get(geo.upper()) if not geo.isdigit() else int(geo)
    if gid is None:
        raise ValueError(f"Unknown geo '{geo}'. Use one of {sorted(GEO_TARGETS)} or a numeric id.")
    return f"geoTargetConstants/{gid}"


def language_constant(lang: str) -> str:
    lid = LANGUAGES.get(lang.lower()) if not lang.isdigit() else int(lang)
    if lid is None:
        raise ValueError(f"Unknown lang '{lang}'. Use one of {sorted(LANGUAGES)} or a numeric id.")
    return f"languageConstants/{lid}"


def _enum_name(value: Any) -> str:
    return str(getattr(value, "name", value))


def _enum_int(value: Any) -> int:
    return int(getattr(value, "value", value))


def idea_to_metrics(idea: Any) -> KeywordMetrics:
    """Convert a ``GenerateKeywordIdeaResult`` into :class:`KeywordMetrics`."""
    m = idea.keyword_idea_metrics
    series = sorted(m.monthly_search_volumes, key=lambda v: (int(v.year), _enum_int(v.month)))
    return KeywordMetrics(
        text=idea.text,
        avg_monthly_searches=int(m.avg_monthly_searches or 0),
        monthly_searches=[int(v.monthly_searches or 0) for v in series][-12:],
        competition=_enum_name(m.competition),
        competition_index=int(m.competition_index or 0),
        low_top_of_page_bid=micros_to_currency(m.low_top_of_page_bid_micros or None),
        high_top_of_page_bid=micros_to_currency(m.high_top_of_page_bid_micros or None),
    )


def _is_retryable(exc: Exception) -> bool:
    """True for quota / rate-limit / transient errors from the Google Ads client."""
    failure = getattr(exc, "failure", None)
    for err in getattr(failure, "errors", []) or []:
        code = err.error_code
        if _enum_int(getattr(code, "quota_error", 0) or 0) != 0:
            return True
    status = getattr(exc, "code", None)
    name = _enum_name(status() if callable(status) else status)
    return name in {"RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE_EXCEEDED", "INTERNAL"}


class GoogleAdsCollector:
    """Fetches keyword ideas, with retries/backoff and a DB response cache."""

    def __init__(
        self,
        client: Any,
        customer_id: str,
        session: Session | None = None,
        cache_ttl_hours: int = 168,
        max_retries: int = 5,
        base_delay: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.customer_id = customer_id.replace("-", "")
        self.session = session
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.max_retries = max_retries
        self.base_delay = base_delay
        self._sleep = sleep

    @staticmethod
    def cache_key(seeds: Sequence[str], url: str | None, geo: str, lang: str) -> str:
        raw = json.dumps([sorted(seeds), url or "", geo.upper(), lang.lower()])
        return hashlib.sha256(raw.encode()).hexdigest()

    def collect(
        self,
        seeds: Sequence[str] = (),
        url: str | None = None,
        geo: str = "US",
        lang: str = "en",
        use_cache: bool = True,
    ) -> list[KeywordMetrics]:
        if not seeds and not url:
            raise ValueError("Provide at least one seed keyword or a seed URL.")
        key = self.cache_key(seeds, url, geo, lang)
        if use_cache:
            cached = self._cache_get(key)
            if cached is not None:
                log.info("Cache hit for %s", key[:8])
                return cached
        results = self._with_retries(lambda: self._fetch(seeds, url, geo, lang))
        self._cache_put(key, results, f"seeds={list(seeds)} url={url} geo={geo} lang={lang}")
        return results

    def _fetch(
        self, seeds: Sequence[str], url: str | None, geo: str, lang: str
    ) -> list[KeywordMetrics]:
        service = self.client.get_service("KeywordPlanIdeaService")
        request = self.client.get_type("GenerateKeywordIdeasRequest")
        request.customer_id = self.customer_id
        request.language = language_constant(lang)
        request.geo_target_constants.append(geo_constant(geo))
        request.include_adult_keywords = False
        request.keyword_plan_network = (
            self.client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH_AND_PARTNERS
        )
        if seeds and url:
            request.keyword_and_url_seed.url = url
            request.keyword_and_url_seed.keywords.extend(seeds)
        elif url:
            request.url_seed.url = url
        else:
            request.keyword_seed.keywords.extend(seeds)
        # The returned pager transparently follows next_page_token.
        return [idea_to_metrics(idea) for idea in service.generate_keyword_ideas(request=request)]

    def _with_retries(self, fn: Callable[[], list[KeywordMetrics]]) -> list[KeywordMetrics]:
        for attempt in range(self.max_retries + 1):
            try:
                return fn()
            except Exception as exc:
                if not _is_retryable(exc):
                    raise
                if attempt == self.max_retries:
                    raise QuotaExceededError(
                        "Google Ads quota/rate limit persisted after retries"
                    ) from exc
                delay = self.base_delay * 2**attempt
                log.warning("Retryable error (%s); sleeping %.1fs", type(exc).__name__, delay)
                self._sleep(delay)
        raise AssertionError("unreachable")

    def _cache_get(self, key: str) -> list[KeywordMetrics] | None:
        if self.session is None:
            return None
        row = self.session.get(CacheRow, key)
        if row is None:
            return None
        created = row.created_at
        if created.tzinfo is None:  # SQLite drops tzinfo
            created = created.replace(tzinfo=utcnow().tzinfo)
        if utcnow() - created > self.cache_ttl:
            return None
        return [KeywordMetrics.model_validate(p) for p in row.payload]

    def _cache_put(self, key: str, items: list[KeywordMetrics], note: str) -> None:
        if self.session is None:
            return
        payload = [i.model_dump(mode="json") for i in items]
        row = self.session.get(CacheRow, key)
        if row is None:
            self.session.add(CacheRow(key=key, payload=payload, created_at=utcnow(), note=note))
        else:
            row.payload, row.created_at, row.note = payload, utcnow(), note
        self.session.commit()
