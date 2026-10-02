"""0-100 keyword scoring from normalized components and a YAML weight profile."""

from __future__ import annotations

import math
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .models import KeywordMetrics

PROFILES_DIR = Path(__file__).parent / "profiles"
PRESETS = ("ad_revenue", "saas", "lead_gen")

COMMERCIAL_WORDS = {
    "best",
    "buy",
    "price",
    "pricing",
    "online",
    "free",
    "generator",
    "calculator",
    "cheap",
    "top",
    "tool",
    "software",
}
VOLUME_CAP = 1_000_000  # volume at which demand saturates to 1.0
CPC_CAP = 10.0  # currency units at which CPC saturates to 1.0
TREND_CAP = 0.05  # +/-5% of mean volume per month saturates the trend component


class Weights(BaseModel):
    demand: float = Field(0.3, ge=0)
    commercial: float = Field(0.3, ge=0)
    trend: float = Field(0.15, ge=0)
    difficulty: float = Field(0.2, ge=0)
    fit: float = Field(0.05, ge=0)


class Profile(BaseModel):
    weights: Weights = Field(default_factory=Weights)
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)


def load_profile(name_or_path: str) -> Profile:
    """Load a preset (ad_revenue, saas, lead_gen) or a YAML file path."""
    path = Path(name_or_path)
    if not path.suffix and name_or_path in PRESETS:
        path = PROFILES_DIR / f"{name_or_path}.yaml"
    if not path.is_file():
        raise ValueError(f"Unknown profile '{name_or_path}'. Presets: {', '.join(PRESETS)}")
    return Profile.model_validate(yaml.safe_load(path.read_text()) or {})


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def trend_slope(series: list[int]) -> float:
    """Least-squares slope of the series, relative to its mean (fraction per month)."""
    n = len(series)
    if n < 2:
        return 0.0
    mean_y = sum(series) / n
    if mean_y == 0:
        return 0.0
    mean_x = (n - 1) / 2
    den = sum((i - mean_x) ** 2 for i in range(n))
    num = sum((i - mean_x) * (y - mean_y) for i, y in enumerate(series))
    return (num / den) / mean_y


def demand_component(volume: int) -> float:
    return _clip(math.log10(1 + max(volume, 0)) / math.log10(1 + VOLUME_CAP))


def intent_heuristic(keyword: str) -> float:
    hits = len(set(re.findall(r"[a-z0-9]+", keyword.lower())) & COMMERCIAL_WORDS)
    return _clip(hits / 2)


def commercial_component(keyword: str, low: float | None, high: float | None) -> float:
    bids = [b for b in (low, high) if b is not None]
    cpc = _clip((sum(bids) / len(bids)) / CPC_CAP) if bids else 0.0
    return 0.5 * cpc + 0.5 * intent_heuristic(keyword)


def trend_component(series: list[int]) -> float:
    return _clip(trend_slope(series) / TREND_CAP * 0.5 + 0.5)


def fit_component(keyword: str, include: list[str], exclude: list[str]) -> float:
    low = keyword.lower()
    if any(x.lower() in low for x in exclude):
        return 0.0
    if include:
        return 1.0 if any(i.lower() in low for i in include) else 0.3
    return 0.5


def score_keyword(m: KeywordMetrics, profile: Profile) -> float:
    """Score in [0, 100]. Components are 0-1; difficulty is subtracted then range-shifted."""
    w = profile.weights
    positive = (
        w.demand * demand_component(m.avg_monthly_searches)
        + w.commercial * commercial_component(m.text, m.low_top_of_page_bid, m.high_top_of_page_bid)
        + w.trend * trend_component(m.monthly_searches)
        + w.fit * fit_component(m.text, profile.include, profile.exclude)
    )
    raw = positive - w.difficulty * _clip(m.competition_index / 100)
    span = w.demand + w.commercial + w.trend + w.fit + w.difficulty
    if span == 0:
        return 0.0
    return round(100 * _clip((raw + w.difficulty) / span), 2)
