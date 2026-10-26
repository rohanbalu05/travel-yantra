FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# Build from the repo root: docker build -f apps/mcp/Dockerfile .
WORKDIR /srv
COPY packages/contracts packages/contracts
COPY apps/mcp/server.py apps/mcp/server.py
RUN pip install ./packages/contracts "mcp>=1.2,<2" "httpx>=0.27"
WORKDIR /srv/apps/mcp
CMD ["python", "server.py"]
