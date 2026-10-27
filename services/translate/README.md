# services/translate (TY5 voice)

IndicTrans2 translation service. About 100 UI phrases per language (`app/phrasebook.tsv`) skip the model. Language QA is in `app/qa.py` (TY5-03): `run_qa` checks back-translation chrF, entities, script, length and an injected adequacy judge (1-5), falls back to English with `fallback_en` on failure, and `report_json` / `report_markdown` give per-language accuracy. Thresholds: `Thresholds(min_chrf, min_adequacy)`.

## API

- `POST /translate` with `{"texts": [...], "target": "hi|kn|ta|te|bn", "source": "en"}`
  returns `{"translations": [...], "target": "hi", "via": [...], "flags": [[...]]}`. Unknown targets return 422.
  Optional `entities` (place names) are kept out of the model and restored in native form.
  `flags` per text can be `wrong_script`, `length` or `entity_lost:<name>`.
- `GET /health`

## Settings (env vars)

- `TY_TRANSLATOR`: `fake` (default; tests), `gemini` (deployed: Gemini 3.1 Flash-Lite on Vertex AI, model `TY_MODEL_LITE`, Vertex from `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` (default `global`); one call per batch, each call logged without text; a stray ` |` or `。` at the end becomes `।`), or `indictrans2` (kept, off; `Dockerfile.indictrans2`, gated weights). The older `TY_FAKE_TRANSLATOR` still works when `TY_TRANSLATOR` is unset.
- Image: `docker build -f services/translate/Dockerfile .` from the repo root (275 MB, no weights).
- `TY_ENTITY_NAMES_FILE` (optional): JSON of Wikidata native names, `{"Hampi": {"hi": "..."}}`.
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
