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

    # pydantic v2 settings
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        extra="ignore",         # fazladan anahtar gelirse görmezden gelir
        case_sensitive=False,   # .env'de büyük/küçük farkı önemsemez
    )

settings = Settings()
