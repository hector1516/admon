# Deploy de la app Admon (FastAPI + Svelte)

> ⚠️ **Documento LEGACY en su mayor parte.** La imagen ya no es `hub-admon:latest`:
> se construye en `ubuntu-latest` y se publica como
> **`ghcr.io/hector1516/admon`**. El deploy vigente está en `ReglasUpdateAdmon.md`
> (CI → ghcr.io → Arcane → *Updates → Update*). Lo de `run_app.sh`, los tags
> `hub-admon:*` y el "flujo canónico" de abajo solo aplican a una instalación
> fuera de Arcane.

Runbook de despliegue de `admon` (la PWA en `admon.ecc-sa.com.mx`). Repo: **hector1516/AdmonApp**
(no confundir con `hector1516/Admon`, que es el HUB de Streamlit).

## Topología

- Contenedor `admon` → imagen **`ghcr.io/hector1516/admon:latest`** (legacy:
  `hub-admon:latest`), puerto host `8103` → `8000` interno.
- Servidor: **WebbApps, Debian, `10.188.141.17`** (el ServerVM `10.188.141.31` ya no publica la app).
- Config del contenedor: **`/opt/apps/admon/app.conf`** en el servidor, aplicada con
  `/opt/apps/_lib/run_app.sh`. Secretos en `/etc/admon.env` (root, 600). Nada de eso está en el repo.
- Red `hub_default`. **El contenedor NO monta volúmenes**: el código entra a la imagen
  durante el `docker build` (o por `docker cp` en el hotsync). Editar archivos dentro del
  contenedor a mano es un error: el siguiente deploy lo pisa.

## Flujo canónico

```bash
# en WebbApps (10.188.141.17), como root
sudo /opt/apps/_lib/run_app.sh admon      # recrea el contenedor desde app.conf
docker logs -f admon

# deploy rápido sin rebuild (equivale al hotsync del CI)
sudo -u deploy bash deploy/hotsync-linux.sh
sudo -u deploy bash deploy/hotsync-linux.sh --dry-run
```

Normalmente no hace falta ninguno de los dos: **el deploy es automático** en
cada push a `master` (ver abajo).

## Tags de imagen

| Tag | Significado |
|---|---|
| `hub-admon:sat01` | salida del build actual (destino del `docker build`) |
| `hub-admon:latest` | lo que corre en producción (sigue a `sat01`) |
| `hub-admon:legends` | alias de `latest` (histórico) |
| `hub-admon:rollback` | imagen anterior, para volver atrás |

## Verificar qué está REALMENTE vivo

La app se sirve desde la imagen: backend en `/app/api` y el frontend compilado por Vite en
`/app/dist/assets/index-<hash>.js`.

- **No grepear `api/main.py` para validar cambios de UI**: todo cambio de pantalla vive en
  `src/**` y se compila al bundle. Un `grep` de un texto de UI en `api/main.py` da 0
  **siempre**, desplegado o no: no prueba nada (ya pasó: se creyó que un deploy faltaba).
- Lo válido es el **hash del bundle** y el texto **dentro del bundle**:
  - `GET https://admon.ecc-sa.com.mx/` → `assets/index-<hash>.js`, luego `GET` ese JS y contar.
  - Dentro del contenedor (sin `docker` CLI, vía API de Docker):
    `GET /v1.41/containers/<id>/archive?path=/app/dist/assets` → tar con los nombres de los assets.
- **Nunca `docker cp` dentro del contenedor**: lo desincroniza de su imagen y el siguiente
  swap/recreate lo revierte en silencio.

## Lecciones (no repetir)

1. **`docker stop` puede dar timeout y aplicar el stop igual.** El 2026-09-26 el script abortó en
   ese paso y dejó `admon` *exited* con el nombre tomado: **producción cayó ~2 min**. Por eso
   `build.ps1` verifica `.State.Running` antes de renombrar y aborta con prod intacta si sigue
   corriendo. Rescate en ese caso: `docker rename admon admon_old` + `docker run` desde
   `hub-admon:latest` con la config del anterior.
2. **Un `docker rm/stop` que "falla" puede haberse aplicado**: re-consulta `docker inspect` /
   `docker ps -a` antes de reintentar o harás doble trabajo.
3. **`dist/` está gitignored**: sin `npm run build` en el server, la imagen se construye con el
   bundle viejo (o falla). `build.ps1` lo verifica y aborta si no encuentra `index-*.js`.
4. El daemon puede ir lento: los timeouts del cliente no implican fallo del build. Confirmá con
   `Successfully tagged` en el log y con `docker images`.
5. El contenedor de test (`admon_test`, puerto 8104) usa las **mismas variables de entorno que
   producción** → sus endpoints tocan la BD real. Solo usá GETs de lectura.

## Desarrollo local (este workspace)

El código de la app vive en el clon del workspace: `/workspace/admon` (este repo).
Para levantarla contra la BD de pruebas:

```bash
cd /workspace/admon
npm run build
HUB_DB_DATABASE=ECCSA_Admon_Pruebas uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Commits: **locales hasta que se publiquen en AdmonApp**. No hacer force-push ni tocar
`hector1516/Admon` (el HUB).

---

## Deploy automático (desde 2026-09-27)

Ya no hace falta correr `build.ps1` a mano. Cada push a `master` dispara
`.github/workflows/deploy.yml`, que decide entre dos caminos mirando **qué
archivos** cambió:

| Modo | Cuándo | Qué hace | Tiempo |
|---|---|---|---|
| **hotsync** | No cambió `Dockerfile`, `requirements.txt` ni `api/requirements.txt` | **Con Arcane como dueño delega en rebuild y no toca el contenedor.** En legacy compila el frontend en un `node:20-alpine` descartable, copia `dist/` + `api/` al contenedor que corre y lo reinicia (`deploy/hotsync-linux.sh`) | ~2 min |
| **rebuild** | Cambió alguno de esos | Baja de `ghcr.io/hector1516/admon` la imagen que publicó `build-image`; **no compila y no recrea** si el contenedor es un Project de Arcane. En legacy hace `docker build` y recrea con `run_app.sh` (`deploy/rebuild-linux.sh`) | ~1 min |

El hotsync **no reconstruye la imagen**: por eso compila dentro de un
contenedor y no en el host (WebbApps no tiene node).

Para verlo sin ejecutar nada:

```bash
bash deploy/hotsync-linux.sh --dry-run
```

El gate corre en `ubuntu-latest` y el deploy en el runner de WebbApps
(`admon-deploy`). Antes el pipeline corría en un runner Windows del ServerVM
con PowerShell, `C:\admon` y una tarea programada: daba `success` sin publicar
nada, porque ese servidor dejó de servir la app.

**El primer deploy con el workflow conviene vigilarlo**: antes todo era manual.
Los dos caminos dicen en el log qué modo eligieron y por qué.

## Verificación

`.github/workflows/check.yml` corre en cada push y PR:

- que `src/styles/app.css` **no** fue editado a mano (compara `ECCSA_SHELL_SHA`),
- que `public/changelog.json` dice la misma versión que el banner,
- que el frontend compila.

Que la copia del shell no esté **atrás** lo comprueba el repo `ECCSA-Shell`
(propaga solo con `propagate.yml`).
