# ─────────────────────────────────────────────────────────────────────────────
# Etapa 1 — frontend Svelte (Vite) -> dist/
#
# ANTES esta etapa no existía: el `npm run build` se ejecutaba en el servidor
# antes de `docker build`, y por eso el CI de admon necesitaba un runner propio
# sobre la máquina — que competía por CPU y RAM con las apps que ahí corren.
# Con esta etapa la imagen se arma completa en ubuntu-latest y el servidor
# solamente la baja.
#
# Base estándar del ecosistema: mirror.gcr.io, el espejo pull-through de Docker
# Hub. Docker Hub y ECR Public aplican cuotas POR IP a los pulls anónimos y ya
# tumbaron la CI dos veces (2026-10-09 y 2026-10-23); el espejo sirve el MISMO
# manifiesto y no tiene esa cuota.
# ─────────────────────────────────────────────────────────────────────────────
FROM mirror.gcr.io/library/node:20-alpine AS build

WORKDIR /app

# Primero solo los manifiestos: si cambia package-lock.json, esta capa se
# invalida sola y npm ci corre de nuevo; el resto del contexto no la toca.
COPY package*.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# ─────────────────────────────────────────────────────────────────────────────
# Etapa 2 — runtime. Backend FastAPI. No lleva Node: la imagen final no carga
# npm ni el contexto del frontend.
# ─────────────────────────────────────────────────────────────────────────────
FROM mirror.gcr.io/library/python:3.11-slim

WORKDIR /app

# pymssql (manylinux) no necesita freetds-dev para instalar, pero curl
# sirve para el HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/
COPY tz_mx.py ./tz_mx.py
# Frontend compilado por la etapa de arriba (npm run build) -> lo sirve FastAPI en "/"
COPY --from=build /app/dist ./dist/
# Versión del shell común (ECCSA-Shell): la lee GET /api/shell/state para el
# banner. Es un archivo generado por tools/sync_shell.py en la app.
COPY ECCSA_SHELL_VERSION ./ECCSA_SHELL_VERSION
# Logo ECCSA para el encabezado del PDF de cotizaciones (opcional: el builder lo omite si falta)
COPY eccsa_logo.png ./eccsa_logo.png
# Template del formato de Excel (hoja "Calculo") que llena el endpoint
# /api/reportes/excel. Destino sin espacios para simplificar la ruta en Python.
# OJO: la forma JSON es la que SÍ funciona aquí — la forma con comillas
# (`COPY "formatos excel/…" …`) la rechaza el BuildKit del ServerVM con
# `failed to process "\"formatos"` (falló el deploy 2026-10-01).
COPY ["formatos excel/Formato Cotizaciones.xlsx", "./formatos_excel/FormatoCotizaciones.xlsx"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Proceso único en primer plano (PID 1): si uvicorn cae, Docker lo reinicia.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
