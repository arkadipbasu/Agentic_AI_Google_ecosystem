"""
Configuration settings for the Agentic AI Google Ecosystem.
All values are loaded from environment variables (or a .env file).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Gemini / Vertex AI
    # ------------------------------------------------------------------ #
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")

    # Optional Vertex AI settings (used when GOOGLE_GENAI_USE_VERTEXAI=true)
    google_cloud_project: str = Field(default="", alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field(default="us-central1", alias="GOOGLE_CLOUD_LOCATION")
    use_vertex_ai: bool = Field(default=False, alias="GOOGLE_GENAI_USE_VERTEXAI")

    # ------------------------------------------------------------------ #
    # Google Calendar / OAuth2
    # ------------------------------------------------------------------ #
    google_credentials_path: str = Field(
        default="credentials.json", alias="GOOGLE_CREDENTIALS_PATH"
    )
    google_token_path: str = Field(default="token.json", alias="GOOGLE_TOKEN_PATH")

    # ------------------------------------------------------------------ #
    # Google Maps
    # ------------------------------------------------------------------ #
    google_maps_api_key: str = Field(default="", alias="GOOGLE_MAPS_API_KEY")

    # ------------------------------------------------------------------ #
    # AlloyDB
    # ------------------------------------------------------------------ #
    alloydb_instance_uri: str = Field(default="", alias="ALLOYDB_INSTANCE_URI")
    alloydb_db_name: str = Field(default="agentic_ai", alias="ALLOYDB_DB_NAME")
    alloydb_db_user: str = Field(default="postgres", alias="ALLOYDB_DB_USER")
    alloydb_db_password: str = Field(default="", alias="ALLOYDB_DB_PASSWORD")
    # Optional direct URL (takes precedence over individual fields)
    database_url: str = Field(default="", alias="DATABASE_URL")

    # ------------------------------------------------------------------ #
    # Application
    # ------------------------------------------------------------------ #
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


settings = Settings()
