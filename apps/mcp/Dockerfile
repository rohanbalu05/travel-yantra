FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# Build context is the repo root (ci docker job and deploy.yml): docker build -f apps/mcp/Dockerfile .
COPY packages/contracts/pyproject.toml /build/contracts/pyproject.toml
COPY packages/contracts/src /build/contracts/src
RUN pip install /build/contracts "mcp>=1.2,<2" "httpx>=0.27" && rm -rf /build
WORKDIR /srv
COPY apps/mcp/server.py .
COPY apps/mcp/samples samples
CMD ["python", "server.py"]
