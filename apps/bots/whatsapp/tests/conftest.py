import pytest


@pytest.fixture(autouse=True)
def _no_live_services(monkeypatch):
    # Tests never reach a real API or translate service, whatever the shell has set.
    for name in ("API_BASE_URL", "TRANSLATE_URL", "WHATSAPP_ALLOWED_RECIPIENTS"):
        monkeypatch.delenv(name, raising=False)
