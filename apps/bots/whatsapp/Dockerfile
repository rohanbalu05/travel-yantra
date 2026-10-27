FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# Build context is the repo root (ci docker job and deploy.yml): docker build -f apps/bots/whatsapp/Dockerfile .
COPY packages/contracts/pyproject.toml /build/contracts/pyproject.toml
COPY packages/contracts/src /build/contracts/src
RUN pip install /build/contracts "fastapi>=0.115" "uvicorn>=0.30" "httpx>=0.27" && rm -rf /build
WORKDIR /srv
COPY apps/bots/whatsapp/app ./app
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
