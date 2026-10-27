FROM python:3.12-slim
# Build context is the repo root (ci docker job and deploy.yml): docker build -f apps/api/Dockerfile .
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /app/apps/api
# Same layout as the repo, so the path dependency ../../packages/contracts and the samples resolve.
COPY packages/contracts /app/packages/contracts
COPY apps/api/pyproject.toml apps/api/uv.lock ./
# No dev group and no embeddings extra (sentence-transformers pulls torch); guide retrieval runs with EMBEDDER=fake until HQ decides.
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/api/main.py ./
COPY apps/api/core core
COPY apps/api/guide guide
COPY apps/api/routes routes
ENV PATH="/app/apps/api/.venv/bin:$PATH" PORT=8080
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
