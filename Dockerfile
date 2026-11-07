# ─────────────────────────────────────────────────────────────────────────────
# Runtime. Backend FastAPI + frontend pre-built en dist/
# ─────────────────────────────────────────────────────────────────────────────
FROM mirror.gcr.io/library/python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    smbclient \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/
COPY tz_mx.py ./tz_mx.py
COPY dist/ ./dist/
COPY ECCSA_SHELL_VERSION ./ECCSA_SHELL_VERSION
COPY eccsa_logo.png ./eccsa_logo.png
COPY ["formatos excel/Formato Cotizaciones.xlsx", "./formatos_excel/FormatoCotizaciones.xlsx"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]