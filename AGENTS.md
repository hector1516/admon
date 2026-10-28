# AGENTS.md — Admon

Admon es una de las **3 apps del ecosistema ECCSA-Shell** (Field, Admon y el
panel de WorkersAdmon). Antes de tocar el diseño, el banner o la versión, leé
esto: casi todo lo que parece "de esta app" en realidad es del shell y está
generado.

## Lo que NO se edita a mano (se genera)

| Archivo | Quién lo pone |
|---|---|
| `src/styles/app.css` | `ECCSA-Shell/tools/build_shell.py` → `sync_shell.py`. **Es un archivo generado.** Edítalo en el repo `ECCSA-Shell` (`tokens.css` / `src/body.css`) y propagá |
| `src/lib/shell.js` | Lo genera `sync_shell.py` con las versiones |
| `src/components/SyncHeader.svelte` | Copia canónica del shell. No la personalices acá |
| `src/components/ActionsBar.svelte` | ídem |
| `src/components/Changelog.svelte` | ídem |
| `src/lib/changelog.js` | ídem |
| `api/lugar.py` | Copia canónica de la regla de ubicación |
| `ECCSA_SHELL_VERSION` / `ECCSA_SHELL_SHA` | Los estampa `sync_shell.py` |

`check.yml` falla el build si edita `src/styles/app.css` a mano (compara el
SHA). No lo esquives: cambialo en el shell.

Ojo: el CSS de Admon está en `src/app.css` (igual que Field). Es la variante Tailwind **v4**.

## Lo que SÍ es de Admon

- **El cableado.** Los componentes del shell no importan nada del proyecto: el
  estado, el usuario y el clic entran por props. Eso es lo que se cablea acá.

  ```svelte
  <SyncHeader
      estado={shellEstado()}
      pendientes={$pendingCount}
      usuario={$auth.user.nombre}
      appVersion={APP_VERSION}
      shellVersion={SHELL_VERSION}
      fetcher={shellFetch}      // API: aporta el header Bearer
      onsync={shellSync}
  />
  ```

- **`fetcher` es obligatorio.** `GET /api/shell/state` exige sesión y Admon
  autentica con `Authorization: Bearer`, no con cookie. Sin `fetcher` da 401 y
  el 🏢/🏠 se queda en `📍` sin que se note. (Así estaba antes: el banner
  mostraba siempre 📍.)

- `ActionsBar` no necesita `onnotif` ni `ononline` si no los tenés: un botón
  se pinta solo si su manejador está. Por eso Admon solo expone ⚙️ y 🚪.

- **El popup de novedades** se monta **una vez**, en `App.svelte`, no en cada
  página: si viviera en el header no saltaría al entrar por cualquier ruta.

## La versión tiene UNA sola fuente

`package.json` → `sync_shell.py` lo lee → lo estampa en `src/lib/shell.js` →
lo pintan el banner, el `.version-badge` y el popup de novedades.

El `.version-badge` de `App.svelte` usa `v{APP_VERSION}`, no un número
escrito a mano. (Estaba fijo en "Admon v1.0.1" mientras `package.json` decía
1.0.0: dos números y ya desincronizados.)

Al sacar una versión, en este orden:

1. `package.json`: subí la versión (SemVer).
2. `public/changelog.json`: poné la misma versión y los cambios, en palabras de
   usuario, una línea por cambio.
3. Corré el check: `ECCSA-Shell/tools/check_changelog.py` falla si los dos
   números no coinciden, y avisa si un cambio es tan largo que no entra en un
   iPhone.

## Deploy

La app vive en **WebbApps** (`10.188.141.17`, Debian): contenedor `admon`,
imagen **`ghcr.io/hector1516/admon:latest`**, puerto host `8103` → `8000`
interno. Ya NO se despliega en el ServerVM (10.188.141.31); ese pipeline quedó
como un éxito falso, porque GitHub reportaba `success` y la app no cambiaba.

**El estándar es el de las 6 apps:** build en `ubuntu-latest` → `ghcr.io` →
Arcane ve el digest → el operador da `Update`. Ver `ReglasUpdateAdmon.md`.

`build-image.yml` dispara en cada push a `master` y tiene **un solo job**:

- **build** (`ubuntu-latest`): construye y publica en `ghcr.io/hector1516/admon`
  (`:latest` + `:<sha>`). **Acá se compila.** No toca el servidor: no hace pull,
  no recrea nada.

Hasta el 2026-10-23 había cuatro jobs (`desbloquear`, `gate`, `build-image`,
`deploy` en el runner `admon-deploy`). Se retiraron al estandarizar: el
servidor ya no interviene en el despliegue, así que no hay nada que
desbloquear ni que bajar. `deploy/hotsync-linux.sh` y `deploy/rebuild-linux.sh`
quedan solo para una instalación legacy fuera de Arcane.

Modos (solo legacy, ya no los usa la CI):

- **hotsync** — no cambió nada de la imagen. **Si Arcane es el dueño, no aplica:
  delega en rebuild**, porque lo que se copia al contenedor se pierde en el
  siguiente `Update` de Arcane. Solo en una instalación legacy compila el
  frontend en un contenedor `node:20-alpine` y copia `dist/` y `api/` al
  contenedor que ya corre. ~2 min. `deploy/hotsync-linux.sh` (tiene `--dry-run`).
- **rebuild** — cambió `Dockerfile`, `requirements.txt` o `api/requirements.txt`:
  **no compila acá**, baja la imagen que ya publicó `build-image` desde
  `ghcr.io` y se detiene. El `docker build` en el servidor se quitó: competía por
  RAM con producción. ~1 min. `deploy/rebuild-linux.sh`.

**Arcane es el dueño del contenedor.** Los dos scripts consultan la etiqueta
`com.docker.compose.project`; si está, imprimen
`ATENCION: 'admon' lo administra Arcane` y **no recrean nada**. Solo en una
instalación legacy (sin esa etiqueta) se recurre a `run_app.sh`. Si alguien
recrea el contenedor a mano, el Project queda sin contenedor y Arcane **deja de
marcar actualizaciones**.

**El host no tiene node instalado**: en el camino legacy, por eso el build del
frontend va dentro de un contenedor. El contenedor node corre con el usuario del
runner (`--user`), porque como root dejaba archivos que el runner no podía
borrar y la limpieza fallaba.

La configuración del contenedor (puertos, red, credenciales) **no está en este
repo**. Con Arcane sale de `/app/data/projects/admon/compose.yaml`, dentro del
volumen `arcane_arcane-data`; el camino legacy (`/opt/apps/admon/app.conf` +
`/opt/apps/_lib/run_app.sh`) sigue existiendo pero **no debe usarse**. El env con
secretos está en `/etc/admon.env` (root, 600). El runner tiene sudo sin password
solo para `run_app.sh`, `verify_app.sh` y el helper `admon-set-secret`: nunca
para leer el env.

El backend corre **uvicorn como PID 1**, sin supervisor: para que cargue código
nuevo hay que reiniciar el contenedor, no un programa de supervisor. Y
`docker restart` **no** recarga el env: para cambiar una variable hay que
recrear el contenedor.

## Base de datos

`ECCSA_Admon` con `pymssql`. El archivo de configuración se resuelve por
prioridad: variables de entorno `HUB_DB_*` > `secretos_local.py` > defaults.
Nunca subir `secretos_local.py`.

Las 3 apps comparten BD, passkeys (RP raíz `ecc-sa.com.mx`), push y PDFs, así
que las versiones de `api/requirements.txt` las manda Field. Ver
`ECCSA-Shell/docs/VERSIONES.md`.

### Migraciones de BD

Los cambios de esquema de `ECCSA_Admon` viven en **`migrations/` de ESTE
repo** (`.sql` numerado, ej. `0040_notas.sql`). El repo HUB (`hector1516/Admon`)
ya no se usa (2026-09-28): no meter migraciones ahí — un push a ese repo
dispara su workflow y **recrea el contenedor `hub_python` sin motivo**.

Convención al aplicar (no hay runner todavía):
1. Ejecutar el `.sql` contra la BD (`pymssql`, `autocommit=True`).
2. Registrarlo: `INSERT INTO schema_migrations (version) VALUES ('NNNN_nombre.sql')`.
3. Pruebas primero (`ECCSA_Admon_Pruebas`), después producción.

## Avisos push (los avisos al teléfono)

> **El contrato completo está en `ECCSA-Shell/docs/PUSH.md`** (repo
> `hector1516/ECCSA-Shell`, vendorizado en `WorkersAdmon/shell/docs/PUSH.md`):
> las tres condiciones de iOS, el payload, los handlers del service worker, los
> endpoints y la receta para añadir push a otra app. Lo de aquí es solo lo que
> le toca a Admon.

Cuatro endpoints en `api/main.py` (`vapid-public-key`, `subscribe`,
`unsubscribe`, `suscripciones`, `prueba`), el cliente en `src/lib/push.js`, los
handlers `push`/`notificationclick` en `public/sw.js` y la tarjeta de
Configuración.

**Quien decide los avisos NO es esta app**: los detecta `notif_dispatch.py` en
WorkersAdmon (`cron_avisos_push.py`), que es el único que escribe y borra filas de
la cola. Aquí solo se guarda de qué dispositivo se trata. La tabla de
suscripciones es `HUB_PushSuscripciones`, creada por la migración
**`0056_avisos_push.sql` del repo `hector1516/WorkersAdmon`**, NO en el
`migrations/` de este repo: la comparten el worker y las dos apps, y
`schema_migrations` es un registro único para las tres.

Reglas que ya se aprendieron (están razonadas en Mailbox, que es la app que
funciona en iOS):

1. **Las suscripciones van en `HUB_PushSuscripciones`, no en
   `HUB_PushSubscriptions`.** La vieja no tiene columna `App`, así que una
   suscripción de Admon es indistinguible de una de Field y los avisos de una app
   aparecerían dentro del service worker de la otra.
2. **La privada VAPID va como base64url de los 32 bytes CRUDOS.** Con una PEM o
   un DER, `pywebpush` falla siempre y el error no dice por qué.
   `_normalizar_vapid_privada()` la convierte sola.
3. **iOS tiene tres condiciones que el navegador no avisa** (16.4+, PWA instalada
   y permiso pedido desde un gesto). Ninguna da un error legible, así que
   `src/lib/push.js` ENVUELVE la API y devuelve `{ok, motivo}` para que la
   pantalla pueda decir qué hacer. En iOS el permiso nunca llega a `'denied'`: se
   queda en `'default'`, por eso se exige ver `'granted'`.
4. **Al tocar la notificación se enfoca la pestaña que ya existe**, no se abre una
   ventana nueva: en iOS eso deja la PWA en blanco. Por eso el SW manda
   `postMessage({type:'ABRIR_RUTA'})` y **`App.svelte` tiene que escucharlo**
   (`onMensajeSW`): si nadie escucha, el toque no hace nada.
5. **`badge` cambia de significado según la plataforma**: en iOS es un NÚMERO y en
   Android la URL de una imagen. El servidor manda `badge_count` y el SW decide.
6. **El botón de prueba va solo a quien lo apretó** (por `IdUsuario`), nunca en
   broadcast: probar el teléfono propio no puede ser un aviso a media empresa.

## Comandos

```bash
npm ci && npm run dev            # desarrollo
npm run build                    # build de producción (vite → dist/)
python3 -m py_compile api/*.py   # la API
```
