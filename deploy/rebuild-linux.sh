#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Admon · despliegue en WebbApps (Linux) — BAJA la imagen y verifica.
#
# ESTÁNDAR DE DESPLIEGUE — el mismo en las 6 apps:
#   1. build + push a ghcr.io   → job `build-image` en ubuntu-latest (la nube)
#   2. el servidor solo BAJA la imagen  → este script
#   3. Arcane ve el digest nuevo y el operador da "Update" en la UI
#
# ── Por qué este script ya no compila ──────────────────────────────────────────
# Antes hacía aquí el `npm run build` del frontend (node:20-alpine) y el
# `docker build` de una imagen de ~2.4 GB con Playwright. En un servidor de
# 1 vCPU y 1.9 GB de RAM eso competía por memoria con las apps que estaban
# corriendo: el riesgo real no era tiempo, era un OOM matando producción.
# El Dockerfile ahora arma el frontend en una etapa node, así que la imagen
# llega lista desde la nube y acá solo se baja.
#
# ── Por qué NO recrea el contenedor ────────────────────────────────────────────
# admon es un Project de Arcane (docker.ecc-sa.com.mx) y Arcane es el dueño:
# `run_app.sh` hace `docker rm admon` y dejaría al Project sin contenedor.
# Por eso solo se recrea si la app todavía NO está administrada por Arcane.
#
# De dónde sale la configuración: /opt/apps/admon/app.conf (puertos, red,
# política de reinicio, app.env), que NO está en el repo a propósito — el env
# tiene credenciales de la base de datos.
#
# Uso:  bash deploy/rebuild-linux.sh [--dry-run]
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

CONTAINER=admon
# app.conf declara este nombre exacto; es el mismo que usa el compose de Arcane.
IMAGE=ghcr.io/hector1516/admon:latest
# El workflow pasa el tag por sha (inmutable). Sin él, cae a :latest.
IMAGE_REF="${IMAGE_REF:-$IMAGE}"
PORT=8103
HEALTH_URL="http://localhost:${PORT}/health"
RUN_APP=/opt/apps/_lib/run_app.sh

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

run() {
  if [ "$DRY" = "1" ]; then echo "  [dry-run] $*"; else "$@"; fi
}
run_sudo() {
  if [ "$DRY" = "1" ]; then echo "  [dry-run] sudo $*"; else sudo "$@"; fi
}
say() { echo "[admon] $*"; }
die() { say "ERROR: $*" >&2; exit 1; }

# ── 0. Precondiciones ──────────────────────────────────────────────────────────
[ "$DRY" = "0" ] && { docker ps >/dev/null 2>&1 || die "'docker' no responde desde $(id -un)"; }

# ── 1. ¿Arcane es el dueño? ───────────────────────────────────────────────────
# Va ANTES del pull. Bajar la imagen y retaguear :latest movería el tag que
# Arcane usa para comparar, y lo dejaría creyendo que el contenedor ya está
# actualizado: has_update=false con producción atrasada. Comprobado el
# 2026-10-23 con colaboradores. El único que mueve :latest es Arcane.
COMPOSE_PROJECT=""
if [ "$DRY" = "0" ]; then
  COMPOSE_PROJECT=$(docker inspect \
    -f '{{ index .Config.Labels "com.docker.compose.project" }}' \
    "$CONTAINER" 2>/dev/null || echo "")
fi

if [ -n "$COMPOSE_PROJECT" ]; then
  say "1/3 '$CONTAINER' lo administra Arcane (project=$COMPOSE_PROJECT): no lo toco."
  say "    La imagen nueva ya está publicada en el registry."
  say "    Para aplicarla: Arcane → Projects → $CONTAINER → Updates → Update."
  say "2/3 sin pull y sin retag: mover el tag :latest esconde la actualización."
  say "3/3 sin verificación de salud: el contenedor sigue con la imagen anterior."
  exit 0
fi

# ── 2. Bajar la imagen (solo instalación legacy) ──────────────────────────────
say "2/3 bajando ${IMAGE_REF} (la construyó el job build-image en la nube)"
if [ "${GHCR_TOKEN:-}" != "" ]; then
  printf '%s' "$GHCR_TOKEN" \
    | docker login ghcr.io -u "${GHCR_USER:-hector1516}" --password-stdin >/dev/null
fi
if [ "$DRY" = "0" ]; then
  # Un pull a secas sobre :latest puede quedarse "Up to date" si el tag no se
  # movió; por eso se baja el tag por sha cuando viene.
  docker pull "$IMAGE_REF" || die "no se pudo bajar ${IMAGE_REF}. ¿Falló el job build-image?"
  # app.conf declara IMAGE (sin tag extra): sin esto run_app.sh no la encontraría.
  docker tag "$IMAGE_REF" "$IMAGE"
  say "    ${IMAGE} -> $(docker images --format '{{.ID}}' "$IMAGE" | head -1)"
fi
[ "${GHCR_TOKEN:-}" != "" ] && docker logout ghcr.io >/dev/null 2>&1 || true

# ── 3. Recrear y verificar ─────────────────────────────────────────────────────
# Solo llega aquí si la app NO está en Arcane (instalación legacy).
say "3/3 recreando el contenedor con ${RUN_APP} (lee /opt/apps/${CONTAINER}/app.conf)"
run_sudo "$RUN_APP" "$CONTAINER"

if [ "$DRY" = "1" ]; then
  say "OK · (dry-run) la imagen quedaría bajada y el contenedor recreado"
  exit 0
fi

# app.conf tiene APP_AUTO_START=0 (la app se apagó cuando WebbApps no tenía RAM).
# Se arranca igual: el health check de abajo es el que avisa si no alcanza.
ESTADO=$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo desconocido)
if [ "$ESTADO" != "running" ]; then
  say "    el contenedor quedó en '$ESTADO'; lo arranco"
  docker start "$CONTAINER" >/dev/null
fi

say "esperando salud en ${HEALTH_URL}"
for i in $(seq 1 60); do
  CODE=$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" || true)
  if [ "$CODE" = "200" ]; then
    say "OK · contenedor recreado y sano (intento $i)"
    exit 0
  fi
  sleep 2
done

die "'$CONTAINER' no respondió en ${HEALTH_URL} en 120 s (docker logs --tail 50 $CONTAINER)"