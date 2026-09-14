# Server Dockerfile — CRUD + RAG API, no heavy local ML libs.
# Drops sentence-transformers, torch, transformers, docling, easyocr,
# paddleocr, opencv, pymupdf, pdfplumber from the runtime image. Embeddings
# come from OpenAI API. PDFs are parsed digitally with pypdf; OCR for
# image-only cells will be provided via an external API later. See
# docs/PDF_PROCESSING.md.

# ---- Stage 1: Build ----
FROM python:3.11-slim AS builder

WORKDIR /app

# Build deps for native wheels (psycopg, bcrypt, ...)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-server.txt .
RUN pip install --no-cache-dir --user -r requirements-server.txt

# ---- Stage 2: Production ----
FROM python:3.11-slim

WORKDIR /app

# Runtime libs that psycopg needs at import time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Create the non-root user up front so we can chown the copied site-packages.
RUN useradd -m appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

# Copy pip-installed packages from builder and chown to appuser so the
# uvicorn entrypoint in /root/.local/bin/uvicorn stays executable.
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application code
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Render sets $PORT; default to 8000 for local Docker usage.
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
