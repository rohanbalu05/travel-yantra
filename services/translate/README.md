# services/translate (TY5 voice)

IndicTrans2 translation service. Phrasebook and language QA come later (TY5-02, TY5-03).

## API

- `POST /translate` with `{"texts": [...], "target": "hi|kn|ta|te|bn", "source": "en"}`
  returns `{"translations": [...], "target": "hi"}`. Unknown targets return 422.
- `GET /health`

## Settings (env vars)

- `TY_FAKE_TRANSLATOR` (default `1`): deterministic fake, no model download. The Docker image sets `0`.
- `TY_MAX_BATCH` (default 16), `TY_CACHE_SIZE` (default 4096 entries, LRU on text and target).

## Tests

```
cd services/translate
uv run --group dev pytest            # fast tests, fake translator
uv run --group dev --extra model pytest -m slow   # real model, CI only
```

The slow test needs `TY_MODEL_DIR` (a directory with pre-provisioned weights, loaded with `local_files_only=True`, no network) and loads `ai4bharat/indictrans2-en-indic-dist-200M` and translates one paragraph
into all five languages. The model is about 0.9 GB on disk; expect roughly 10 to 30 s cold
start on Cloud Run CPU with weights baked into the image (assumption, not measured).
