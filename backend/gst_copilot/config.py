from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/gst_copilot_dev"
    # Hosted databases (Supabase) need TLS. "require" encrypts without verifying the certificate.
    DATABASE_SSL: bool = False
    STORAGE_DIR: str = str(Path(__file__).parent.parent.parent / "storage")
    # Login ("Standard" policy): 12-hour sessions; 5 wrong passwords lock that email for 15 minutes.
    SESSION_COOKIE: str = "gsth_session"
    SESSION_HOURS: int = 12
    LOGIN_MAX_FAILURES: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    COOKIE_SECURE: bool = False  # set true whenever the app is served over HTTPS

    @field_validator("DATABASE_URL")
    @classmethod
    def _asyncpg_url(cls, url: str) -> str:
        # Hosting dashboards hand out postgres:// or postgresql:// URLs; the app always uses the asyncpg driver.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+asyncpg://" + url[len(prefix):]
        return url

    @property
    def db_connect_args(self) -> dict:
        return {"ssl": "require"} if self.DATABASE_SSL else {}

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
