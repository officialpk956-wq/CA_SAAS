from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/gst_copilot_dev"
    STORAGE_DIR: str = str(Path(__file__).parent.parent.parent / "storage")
    # Login ("Standard" policy): 12-hour sessions; 5 wrong passwords lock that email for 15 minutes.
    SESSION_COOKIE: str = "gsth_session"
    SESSION_HOURS: int = 12
    LOGIN_MAX_FAILURES: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    COOKIE_SECURE: bool = False  # set true whenever the app is served over HTTPS

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
