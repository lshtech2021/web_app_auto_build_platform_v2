"""Rule-based intent labeling and product-type suggestion."""

from __future__ import annotations

import re

INFORMATIONAL = "informational"
TRANSACTIONAL = "transactional"
NAVIGATIONAL = "navigational"
UTILITY = "tool/utility"

COMPARISON_WORDS = {
    "best",
    "top",
    "vs",
    "versus",
    "review",
    "reviews",
    "alternative",
    "alternatives",
    "compare",
    "comparison",
}
UTILITY_WORDS = {
    "calculator",
    "generator",
    "converter",
    "checker",
    "maker",
    "compressor",
    "tool",
    "tools",
    "online",
    "template",
    "templates",
    "extractor",
    "counter",
}
TRANSACTIONAL_WORDS = {
    "buy",
    "price",
    "prices",
    "pricing",
    "cheap",
    "discount",
    "coupon",
    "order",
    "deal",
    "deals",
    "purchase",
    "hire",
    "subscription",
}
INFORMATIONAL_WORDS = {
    "how",
    "what",
    "why",
    "when",
    "who",
    "guide",
    "tutorial",
    "meaning",
    "examples",
    "example",
    "tips",
    "learn",
}
PROBLEM_PHRASES = (
    "how to track",
    "how to manage",
    "how to automate",
    "how to organize",
    "how to keep track",
    "how to fix",
)
NAVIGATIONAL_WORDS = {
    "login",
    "log in",
    "sign in",
    "signin",
    "website",
    "official",
    "app download",
    "download",
    "homepage",
}

PRODUCT_MAP = {
    UTILITY: "web_tool",
    INFORMATIONAL: "content_site",
    TRANSACTIONAL: "affiliate_site",
    NAVIGATIONAL: "none",
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def label_intent(keyword: str) -> str:
    """Return one of informational / transactional / navigational / tool/utility."""
    low = keyword.lower()
    toks = _tokens(low)
    if any(p in low for p in NAVIGATIONAL_WORDS if " " in p) or toks & {
        "login",
        "signin",
        "official",
        "homepage",
    }:
        return NAVIGATIONAL
    if toks & UTILITY_WORDS:
        return UTILITY
    if toks & TRANSACTIONAL_WORDS:
        return TRANSACTIONAL
    if toks & COMPARISON_WORDS:
        return TRANSACTIONAL  # commercial investigation; product type refines it
    return INFORMATIONAL


def suggest_product_type(keyword: str, intent: str | None = None) -> str:
    """Map a keyword (and its intent) to a suggested product type."""
    intent = intent or label_intent(keyword)
    low = keyword.lower()
    if any(p in low for p in PROBLEM_PHRASES):
        return "saas_app"
    if _tokens(low) & COMPARISON_WORDS:
        return "affiliate_site"
    return PRODUCT_MAP[intent]
