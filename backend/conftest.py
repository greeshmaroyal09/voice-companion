import pytest


@pytest.fixture(autouse=True)
def isolate_optional_live_gemini(monkeypatch):
    """Keep repository .env credentials from leaking into provider-mocked tests."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
