FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TY_TRANSLATOR=gemini
# Build context is the repo root (ci docker job and deploy.yml):
#   docker build -f services/translate/Dockerfile .
# Gemini 3.1 Flash-Lite on Vertex AI; no model weights in the image. IndicTrans2 (off) has its
# own image: services/translate/Dockerfile.indictrans2.
WORKDIR /srv
COPY services/translate/pyproject.toml ./
RUN pip install ".[gemini]"
COPY services/translate/app ./app
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
