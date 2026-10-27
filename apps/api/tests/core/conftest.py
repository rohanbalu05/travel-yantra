import os

# tests never call a model
os.environ.setdefault("TY_FAKE_LLM", "1")
