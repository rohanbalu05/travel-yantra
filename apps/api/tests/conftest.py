import os

# Tests never call a model: force the fake for every lane's tests, even if the shell has it off.
os.environ["TY_FAKE_LLM"] = "1"
# Tests never call live APIs: drop keys that switch providers to live mode (names only; values never read).
for name in ("GOOGLE_MAPS_API_KEY", "SERPAPI_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(name, None)
# Sample places, options and stays (core/fakes.py) fill gaps in tests only; real users never get them.
os.environ["TY_SAMPLE_DATA"] = "1"
# No lane warm-up in tests (it would load the e5 model); tests/core/test_warm_up.py turns it on with fake lanes.
os.environ["TY_WARM_UP"] = "0"
