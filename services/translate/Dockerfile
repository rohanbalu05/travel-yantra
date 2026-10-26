FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TY_FAKE_TRANSLATOR=0 HF_HOME=/models
WORKDIR /srv
COPY pyproject.toml ./
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu ".[model]" \
    || pip install ".[model]"
COPY app ./app
# Bake the weights into the image so cold start does not download them.
RUN python -c "from transformers import AutoModelForSeq2SeqLM as M, AutoTokenizer as T; n='ai4bharat/indictrans2-en-indic-dist-200M'; T.from_pretrained(n,trust_remote_code=True); M.from_pretrained(n,trust_remote_code=True)"
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
