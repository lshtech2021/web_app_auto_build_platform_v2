import csv

from sqlalchemy.orm import Session
from typer.testing import CliRunner

from kwresearch.cli import EXPORT_COLUMNS, app
from kwresearch.config import get_settings
from kwresearch.db import make_engine, upsert_keywords
from kwresearch.models import KeywordMetrics


def test_score_and_export(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 't.db'}")
    get_settings.cache_clear()
    with Session(make_engine(get_settings().database_url)) as s:
        upsert_keywords(
            s,
            [
                KeywordMetrics(
                    text="free pdf compressor online",
                    avg_monthly_searches=9000,
                    monthly_searches=list(range(1, 13)),
                    competition_index=10,
                ),
                KeywordMetrics(text="obscure thing", avg_monthly_searches=10, competition_index=90),
            ],
            "US",
            "en",
        )
    runner = CliRunner()
    assert runner.invoke(app, ["score", "--profile", "saas"]).exit_code == 0
    out = tmp_path / "r.csv"
    assert runner.invoke(app, ["export", "--top", "1", "--out", str(out)]).exit_code == 0
    rows = list(csv.DictReader(out.open()))
    assert list(rows[0]) == EXPORT_COLUMNS
    assert len(rows) == 1 and rows[0]["keyword"] == "free pdf compressor online"
    assert rows[0]["product_type"] == "web_tool"
    get_settings.cache_clear()
