# Build from the repo root: docker build -f apps/api/Dockerfile .
# (ty-contracts is a path dependency in packages/contracts, so the context must include it.)
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY packages/contracts packages/contracts
COPY apps/api apps/api
WORKDIR /app/apps/api
ENV UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"
RUN uv sync --no-dev
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
