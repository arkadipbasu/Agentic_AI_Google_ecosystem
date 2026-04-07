"""
config.py — Centralised settings for the multi-agent system.
All secrets come from environment variables injected by Cloud Run
(backed by Secret Manager via --set-secrets).
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Google Cloud ──────────────────────────────────────────
    GCP_PROJECT_ID: str
    GCP_REGION: str = "us-central1"

    # ── Vertex AI / Gemini ────────────────────────────────────
    VERTEX_MODEL: str = "gemini-1.5-pro-preview-0409"

    # ── AlloyDB ───────────────────────────────────────────────
    # Cloud Run connects via the AlloyDB Auth Proxy sidecar
    ALLOYDB_HOST: str = "127.0.0.1"
    ALLOYDB_PORT: int = 5432
    ALLOYDB_DB: str = "agents"
    ALLOYDB_USER: str = "agents_user"
    ALLOYDB_PASSWORD: str          # injected via Secret Manager

    # ── Google OAuth (service account JSON path) ──────────────
    GOOGLE_SA_KEY_PATH: str = "/secrets/google-sa-key.json"

    # ── Google Maps ───────────────────────────────────────────
    GOOGLE_MAPS_API_KEY: str       # injected via Secret Manager

    # ── App ───────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = ["*"]

    @property
    def alloydb_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.ALLOYDB_USER}:{self.ALLOYDB_PASSWORD}"
            f"@{self.ALLOYDB_HOST}:{self.ALLOYDB_PORT}/{self.ALLOYDB_DB}"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
