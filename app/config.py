# app/config.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    # DB
    DATABASE_URL: str = "sqlite:///./app.db"

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Allow any localhost/127.0.0.1 with any port (useful for Flutter/Vite dev servers)
    ALLOWED_ORIGIN_REGEX: str | None = r"^https?://(localhost|127\\.0\\.0\\.1)(:\\d+)?$"

    # fal.ai
    FAL_API_KEY: str | None = None
    FAL_MODEL: str = "fal-ai/seedream-v4"
    FAL_ENDPOINT: str = "https://fal.run"
    FAL_TIMEOUT: int = 120
    POLL_INTERVAL: float = 1.5
    POLL_MAX_WAIT: int = 120

    # Storage backend: "local" (default) or "s3" (for AWS S3 / R2 / S3-compatible)
    STORAGE_BACKEND: str = "local"

    # S3 configuration (used when STORAGE_BACKEND == "s3")
    S3_BUCKET: str | None = None
    S3_REGION: str | None = None
    S3_ENDPOINT: str | None = None  # optional (useful for R2 or custom endpoints)
    S3_ACCESS_KEY_ID: str | None = None
    S3_SECRET_ACCESS_KEY: str | None = None
    # Public base URL for serving objects (recommended for non-AWS like R2)
    # Example: https://cdn.example.com/ or https://<accountid>.r2.cloudflarestorage.com/<bucket>/
    S3_PUBLIC_BASE_URL: str | None = None

    # pydantic v2 settings
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        extra="ignore",         # fazladan anahtar gelirse görmezden gelir
        case_sensitive=False,   # .env'de büyük/küçük farkı önemsemez
    )

settings = Settings()
