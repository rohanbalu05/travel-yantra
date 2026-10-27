import os

# Tests never call a model: force the fake for every lane's tests, even if the shell has it off.
os.environ["TY_FAKE_LLM"] = "1"
