FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# Build context is apps/mcp (deploy.yml uses --source apps/mcp), so contracts come from the public repo.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN pip install "git+https://github.com/rohanbalu05/travel-yantra.git@main#subdirectory=packages/contracts" "mcp>=1.2,<2" "httpx>=0.27"
WORKDIR /srv
COPY server.py .
CMD ["python", "server.py"]
