FROM python:3.12-slim
# Build context is the repo root (ci docker job and deploy.yml): docker build -f apps/api/Dockerfile .
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    HF_HOME=/opt/hf
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /app/apps/api
# Same layout as the repo, so the path dependency ../../packages/contracts and the samples resolve.
COPY packages/contracts /app/packages/contracts
COPY apps/api/pyproject.toml apps/api/uv.lock ./
# Locked deps plus the embeddings extra (sentence-transformers on CPU-only torch); no dev group.
RUN uv sync --frozen --no-dev --extra embeddings --no-install-project
# Bake the guide's e5 model into the image so a cold start never downloads it.
RUN .venv/bin/python -c "from sentence_transformers import SentenceTransformer as S; S('intfloat/multilingual-e5-small')" \
    && rm -rf /opt/hf/xet /root/.cache
COPY apps/api/main.py ./
COPY apps/api/core core
COPY apps/api/guide guide
COPY apps/api/routes routes
# Offline at runtime: the model comes from the image, never from the network.
ENV PATH="/app/apps/api/.venv/bin:$PATH" PORT=8080 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
