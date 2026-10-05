import pytest
from backend.gst_copilot.config import Settings


@pytest.mark.parametrize("given", ["postgres://u:p@h:5432/d", "postgresql://u:p@h:5432/d", "postgresql+asyncpg://u:p@h:5432/d"])
def test_hosted_urls_use_asyncpg(given, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", given)
    assert Settings().DATABASE_URL == "postgresql+asyncpg://u:p@h:5432/d"


def test_ssl_only_when_asked(monkeypatch):
    monkeypatch.setenv("DATABASE_SSL", "false")
    assert Settings().db_connect_args == {}
    monkeypatch.setenv("DATABASE_SSL", "true")
    assert Settings().db_connect_args == {"ssl": "require"}
