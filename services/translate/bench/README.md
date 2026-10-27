# Translation bench (P2): IndicTrans2 on CPU vs the Gemini fallback

Not tests: these scripts make live calls and are run by hand. Inputs: `answers.json`, 10 English
guide-style sample answers with `[n]` citation markers and 15 place names. Outputs go to `results/`.

## IndicTrans2 (Docker, the production image and code path)

Needs a Hugging Face account that has accepted the terms of
`ai4bharat/indictrans2-en-indic-dist-200M` and `ai4bharat/indictrans2-indic-en-dist-200M`, and
`HF_TOKEN` set in the shell (never printed).

```
docker build --secret id=hf_token,env=HF_TOKEN -t ty-translate-bench services/translate
# Cloud Run sizes: try --cpus 1/2/4 with --memory 2g/4g
docker run --rm --cpus 2 --memory 4g -v "$PWD/services/translate/bench:/bench" \
  ty-translate-bench python /bench/bench_it2.py forward /bench/results/it2_forward.json
```

`forward` prints load time, peak RSS and per-sentence latency (median, p90, max) and writes the 50
translations. Then `python bench/gemini.py judge` and `qa` score both systems.

## Gemini fallback (host, Vertex via ADC; about 15 calls in all, logged in results/calls.log)

```
cd services/translate/bench
uv run --no-project --python 3.12 --with google-genai --with pydantic python gemini.py translate
uv run --no-project --python 3.12 --with google-genai --with pydantic python gemini.py back
uv run --no-project --python 3.12 --with google-genai --with pydantic python gemini.py judge
uv run --no-project --python 3.12 --with google-genai --with pydantic python gemini.py qa
```

Translation and back-translation use `TY_MODEL_LITE` (gemini-3.1-flash-lite); the adequacy judge
uses `TY_MODEL_FLASH` (gemini-3.5-flash). Back-translating Gemini's output with Gemini flatters it;
use IndicTrans2 indic-en (`bench_it2.py back`) once the weights are available.

## Results (27 Oct 2026)

See `results/qa.md`. Gemini Flash-Lite: 50 of 50 outputs pass `run_qa` (chrF 0.71 to 0.87,
adequacy 4.9 to 5.0); every `[n]` marker and place name kept. QA does not catch stray final
punctuation (one Hindi `|` for `।`, one Bengali `。`). IndicTrans2: not measured (gated weights).
