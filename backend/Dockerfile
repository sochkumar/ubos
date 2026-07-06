# ─── UBOS backend ────────────────────────────────────────────────────────
FROM python:3.11-slim

# System deps:
#   - poppler-utils: required by pdf2image (PDF page-1 thumbnails)
#   - libjpeg / zlib / libpng: Pillow runtime
#   - build-essential: for wheel builds that ship no manylinux wheels
#   - curl: healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
      poppler-utils \
      libjpeg62-turbo \
      zlib1g \
      libpng16-16 \
      libzbar0 \
      build-essential \
      curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/backend

# Install Python deps first for better layer caching.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# App code.
COPY . /app/backend

# Uploads land on a volume mount in production.
RUN mkdir -p /app/backend/uploads

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:8001/api/health || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
