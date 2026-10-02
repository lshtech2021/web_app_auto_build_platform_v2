# kwresearch

Stages 1–2 of a "Keyword-to-Product Engine": collect keyword ideas from the **Google Ads API
(Keyword Planner)**, score them, label intent, and export a ranked CSV.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then fill in credentials
```

### Google Ads credentials

1. **Developer token**: sign in to a Google Ads *manager (MCC)* account → Tools → API Center →
   apply for a developer token. "Test" access only works with test accounts; apply for
   Basic access for Keyword Planner on real accounts.
2. **OAuth client**: in Google Cloud Console, enable the *Google Ads API*, configure the OAuth
   consent screen, and create an OAuth client ID (type *Desktop app*). Put the client id/secret in `.env`.
3. **Refresh token**: run Google's `authenticate_in_desktop_application.py` example from the
   [google-ads-python repo](https://github.com/googleads/google-ads-python/tree/main/examples/authentication)
   with your client secret JSON, sign in with a user that has access, and copy the printed
   refresh token to `GOOGLE_ADS_REFRESH_TOKEN`.
4. **Customer ids**: `GOOGLE_ADS_CUSTOMER_ID` is the account used for the call;
   `GOOGLE_ADS_LOGIN_CUSTOMER_ID` is the manager account id (if you access via an MCC). Digits only.

Secrets live only in `.env` (git-ignored) or real environment variables.

## Usage

```bash
kwresearch collect --seeds "invoice generator,pdf compressor" --geo US --lang en
kwresearch collect --url https://example.com --seeds "crm"
kwresearch score --profile ad_revenue        # presets: ad_revenue, saas, lead_gen, or a YAML path
kwresearch export --top 100 --out ranked.csv
```

Responses are cached in the database (`CACHE_TTL_HOURS`, default 168) so repeat calls
aren't metered; use `--no-cache` to force a refresh. Quota/transient errors are retried with
exponential backoff. `DATABASE_URL` defaults to SQLite; any SQLAlchemy URL (e.g. Postgres) works.

### Scoring

`score = 100 * (w1*demand + w2*commercial + w3*trend − w4*difficulty + w5*fit)`, with every
component normalized to 0–1 and the result rescaled into 0–100. Weights, plus optional
`include`/`exclude` keyword lists for the fit component, come from a YAML profile
(see `src/kwresearch/profiles/`):

```yaml
weights: {demand: 0.4, commercial: 0.2, trend: 0.15, difficulty: 0.2, fit: 0.05}
include: [invoice]
exclude: [porn]
```

### Intent → product type

tool/utility → `web_tool`, informational → `content_site`, comparison/transactional →
`affiliate_site`, problem queries ("how to track …") → `saas_app`.

## Development

```bash
ruff check . && pytest   # tests mock the Google Ads client; no live calls
```

## Roadmap

3. Clustering (embeddings/HDBSCAN or SERP overlap) and cluster-level intent
4. LLM opportunity briefs
5. Site/app scaffold generator (Next.js/Astro) that opens PRs
6. Dashboard and predicted-vs-actual feedback loop

No license is included; the owner should choose one.
