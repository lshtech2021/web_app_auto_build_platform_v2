"""Settings loaded from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_ads_developer_token: str = ""
    google_ads_client_id: str = ""
    google_ads_client_secret: str = ""
    google_ads_refresh_token: str = ""
    google_ads_login_customer_id: str = ""
    google_ads_customer_id: str = ""
    database_url: str = "sqlite:///kwresearch.db"
    cache_ttl_hours: int = Field(default=168, ge=0)

    def google_ads_config(self) -> dict[str, object]:
        """Config dict accepted by ``GoogleAdsClient.load_from_dict``."""
        missing = [
            k
            for k in (
                "google_ads_developer_token",
                "google_ads_client_id",
                "google_ads_client_secret",
                "google_ads_refresh_token",
                "google_ads_customer_id",
            )
            if not getattr(self, k)
        ]
        if missing:
            raise ValueError(f"Missing settings: {', '.join(m.upper() for m in missing)}")
        cfg: dict[str, object] = {
            "developer_token": self.google_ads_developer_token,
            "client_id": self.google_ads_client_id,
            "client_secret": self.google_ads_client_secret,
            "refresh_token": self.google_ads_refresh_token,
            "use_proto_plus": True,
        }
        if self.google_ads_login_customer_id:
            cfg["login_customer_id"] = self.google_ads_login_customer_id.replace("-", "")
        return cfg


@lru_cache
def get_settings() -> Settings:
    return Settings()
