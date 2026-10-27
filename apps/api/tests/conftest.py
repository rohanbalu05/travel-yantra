import os

# Tests never call a model: force the fake for every lane's tests, even if the shell has it off.
os.environ["TY_FAKE_LLM"] = "1"
# Tests never call live APIs: drop keys that switch providers to live mode (names only; values never read).
for name in ("GOOGLE_MAPS_API_KEY", "SERPAPI_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(name, None)
