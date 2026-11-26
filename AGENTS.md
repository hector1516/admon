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

---

<!-- SKILLS-CATALOG:START -->
## Skills disponibles

> **Catálogo completo:** `C:\Users\ECCSAia\.config\opencode\SKILLS.md` (global).
> **Regla:** antes de empezar una tarea, si hay un skill que aplique, cárgalo con la herramienta `skill` y síguelo. Los skills son parte del flujo, no adornos.

### RTK — ahorro de tokens (uso obligatorio)

`rtk` está instalado y el plugin de OpenCode reescribe comandos de shell para comprimir su salida. **Úsalo siempre** que aplique:

- Deja que el plugin lo haga, o prefija `rtk`: `rtk git status`, `rtk cargo test`, `rtk npm test`, `rtk ls`, `rtk grep ...`.
- Mide el ahorro con `rtk gain`; para ver la salida completa, `rtk bypass <comando>`.
- Si el comando no está soportado (PowerShell nativo, scripts Python), sigue normal.

### Caveman — modo por defecto (uso obligatorio)

Caveman está activo por defecto en OpenCode (plugin nativo + bloque global). Responde corto, sin fluff; conserva código, comandos, rutas, números y errores. Cambia con `/ultracave` (máxima compresión) o `/megacave` (chino clásico); desactiva con `stop caveman` o `normal mode` solo si el usuario lo pide. Herramientas MCP: `caveman_compress`, `caveman_stats`, `caveman_toon_encode/decode`.

<details>
<summary><strong>Catálogo completo: 92 skills</strong></summary>

### Proceso, calidad y colaboración

| Skill | Para qué sirve |
|---|---|
| `brainstorming` | Explora el problema, requisitos y alternativas antes de crear; convierte una idea vaga en un diseño acordado. |
| `writing-plans` | Convierte una spec en un plan paso a paso con archivos, interfaces, verificación y commits. |
| `executing-plans` | Ejecuta un plan en la sesión actual, tarea por tarea, con checkpoints y verificación. |
| `subagent-driven-development` | Reparte tareas independientes a subagentes y revisa su trabajo antes de integrarlo. |
| `dispatching-parallel-agents` | Lanza varios agentes en paralelo para tareas sin dependencias ni estado compartido. |
| `systematic-debugging` | Diagnostica bugs con hipótesis y evidencia antes de proponer o tocar código. |
| `test-driven-development` | Escribe primero el test que falla y luego la implementación mínima. |
| `verification-before-completion` | Verifica con comandos reales antes de declarar que algo está listo o arreglado. |
| `requesting-code-review` | Prepara el trabajo para revisión con contexto, criterios y evidencia. |
| `receiving-code-review` | Procesa feedback de revisión con rigor, sin aceptar sugerencias a ciegas. |
| `finishing-a-development-branch` | Decide merge, PR, limpieza y cierre de una rama de desarrollo. |
| `using-git-worktrees` | Aísla el trabajo en worktrees de git para no mezclar cambios. |
| `writing-skills` | Crea o edita skills con estructura, disparadores y verificación. |
| `using-superpowers` | Regla base: invocar los skills relevantes antes de responder o actuar. |
| `diagnosing-superpowers` | Investiga por qué una sesión de Superpowers falló o se atascó. |

### Diseño, UI y visual

| Skill | Para qué sirve |
|---|---|
| `apple-design` | Audita UI/UX con las HIG de Apple y criterio de craft para Tauri, Electron, iOS o Android. |
| `frontend-design` | Da dirección visual distintiva a una UI nueva o a un rediseño, sin caer en plantillas. |
| `impeccable` | Diseña, rediseña, audita o pule interfaces: jerarquía, tipo, color, motion y accesibilidad. |
| `unslop` | Quita el look genérico de IA y convierte una pantalla en una interfaz con carácter. |
| `logo-design` | Diseña logos y marcas: brief, conceptos, SVG, pruebas y variantes de entrega. |
| `anatomy` | Crea figuras isométricas SVG interactivas que explican un sistema o componente. |
| `fun-isometric` | Genera stickers isométricos animados con presets de motion estilo Lottie. |
| `pixelfx` | Crea efectos pixel art y sprite sheets con 244 efectos listos y un loop de refinamiento. |
| `react-bits` | Añade componentes React animados de React Bits a un proyecto. |

### Video, media y sonido

| Skill | Para qué sirve |
|---|---|
| `hyperframes` | Produce o edita videos con HTML: launch films, explainers, charts, captions y overlays. |
| `hyperframes-cli` | CLI de HyperFrames: scaffold, preview, render, share e historial de proyecto. |
| `hyperframes-registry` | Unos 450 bloques y componentes HyperFrames listos para usar como fuente editable. |
| `media-use` | Consigue o genera música, SFX, imágenes, voz, video y transcripts para HyperFrames. |
| `reverse-any-video` | Reconstruye un video existente como proyecto HyperFrames editable, frame a frame. |
| `style-sampling` | Haz un episodio nuevo en un estilo de video probado (collage, finance, science, 3D). |
| `youtube` | Extrae transcript, metadata y comentarios de YouTube y los guarda en el vault. |
| `podcast` | Extrae metadata, transcript y resumen de un podcast y los guarda en el vault. |

### Investigación y conocimiento

| Skill | Para qué sirve |
|---|---|
| `research` | Investiga en web con citas: Perplexity si hay key, o fuentes gratuitas si no. |
| `research-deep` | Investigación profunda vault-first: detecta gaps, sintetiza y propaga al vault. |
| `notebooklm` | Investigación grounded con Gemini File Search, sin navegador. |
| `codebase-map` | Mapea un repo: arquitectura, flujos, archivos clave y preguntas abiertas. |
| `x-pulse` | Escanea X para ver tendencias, voces y hooks sobre un tema. |
| `x-read` | Lee a fondo un post o hilo de X: claims, sentimiento y voces a seguir. |
| `idea-discovery` | Propone 3-5 direcciones siguientes leyendo ideas y notas huérfanas del vault. |
| `vault-deep-synthesis` | Cruza todo lo que el vault sabe de un tema: acuerdos, contradicciones y gaps. |

### Obsidian / segundo cerebro

| Skill | Para qué sirve |
|---|---|
| `obsidian-architect` | Documenta un codebase en notas de arquitectura dentro del vault. |
| `obsidian-board` | Muestra o actualiza un tablero kanban y marca vencidos. |
| `obsidian-board-hygiene` | Triaje masivo del tablero: archiva, reprograma o marca hecho. |
| `obsidian-brainstorm` | Brainstorm socrático multi-turno que termina en una nota de diseño. |
| `obsidian-capture` | Captura rápida de ideas al vault y a la nota diaria. |
| `obsidian-catchup` | Procesa capturas del bot de Telegram: voz, texto, imágenes, PDFs y links. |
| `obsidian-challenge` | Red-team de una idea contra el historial del vault. |
| `obsidian-checkin` | Revisa notas viejas de personas y proyectos y actualiza lo que ya no aplica. |
| `obsidian-connect` | Conecta dos dominios no relacionados usando el grafo del vault. |
| `obsidian-core` | Motor compartido de los skills Obsidian; solo soporte, no se invoca. |
| `obsidian-daily` | Crea o actualiza la nota diaria con calendario, tareas y contexto. |
| `obsidian-decide` | Registra decisiones: ligero en la nota del proyecto o ADR formal. |
| `obsidian-distill` | Condensa una nota o fuente en claims con procedencia. |
| `obsidian-emerge` | Detecta patrones y temas no nombrados en notas recientes. |
| `obsidian-export` | Exporta el vault a JSON, índice markdown o bundle OKF. |
| `obsidian-find` | Busca en el vault y devuelve resultados con contexto. |
| `obsidian-graduate` | Promueve una idea a spec de proyecto con tareas y tablero. |
| `obsidian-health` | Chequeo de salud del vault: contradicciones, gaps y notas viejas. |
| `obsidian-ingest` | Ingesta una fuente o carpeta por lotes, actualizando entidades y conceptos. |
| `obsidian-init` | Escanea el vault y genera `_CLAUDE.md`, `index.md` y `log.md`. |
| `obsidian-learn` | Revisa y poda aprendizajes del vault; muestra patrones activos. |
| `obsidian-log` | Registra una sesión de trabajo o dev en el vault. |
| `obsidian-merge` | Fusiona notas casi duplicadas y redirige la retirada. |
| `obsidian-panel` | Convoca un panel de perspectivas independientes sobre una decisión. |
| `obsidian-person` | Crea o actualiza una nota de persona desde la conversación. |
| `obsidian-project` | Crea o actualiza una nota de proyecto y la añade al tablero. |
| `obsidian-projects` | Estado de proyectos desde git y docs locales, sin config. |
| `obsidian-recap` | Resume hoy, semana o mes desde el vault. |
| `obsidian-reconcile` | Encuentra y resuelve contradicciones en el vault. |
| `obsidian-recurring` | Sigue obligaciones recurrentes con cadencia y próxima fecha. |
| `obsidian-reindex` | Reconstruye el índice semántico del vault y reporta cobertura. |
| `obsidian-retrieval-eval` | Mide recall@k y MRR de la búsqueda del vault. |
| `obsidian-review` | Genera una revisión semanal o mensual desde el historial. |
| `obsidian-save` | Guarda en el vault lo que valga la pena de la conversación. |
| `obsidian-synthesize` | Síntesis automática: detecta patrones y escribe páginas nuevas. |
| `obsidian-task` | Añade una tarea al tablero con prioridad y fecha inferidas. |
| `obsidian-visualize` | Genera un canvas visual del vault y sus conexiones. |
| `obsidian-world` | Carga identidad, valores, prioridades y estado actual en un solo paso. |
| `create-command` | Crea un comando de obsidian-second-brain mediante entrevista. |
| `crew` | Comparte un logbook de carpeta entre Claude Code, Codex, Cursor y Grok. |

### Caveman / ahorro de tokens (default)

| Skill | Para qué sirve |
|---|---|
| `caveman` | Voz telegráfica por defecto: respuesta corta, sin fluff, hechos técnicos intactos. |
| `ultracave` | Compresión máxima: fragmentos, una palabra si basta, cada hecho una vez. |
| `megacave` | Variante en chino clásico (文言文), términos técnicos verbatim. |
| `caveman-commit` | Mensaje Conventional Commit comprimido a intención. |
| `caveman-review` | Review comprimido: una línea por hallazgo con ubicación, problema y fix. |
| `caveman-compress` | Comprime archivos de memoria (CLAUDE.md, todos) y deja backup. |
| `caveman-help` | Tarjeta de referencia de comandos y modos de Caveman. |
| `caveman-stats` | Uso de tokens de la sesión y reporte nativo del host. |
| `cavecrew` | Delega a subagentes investigator/builder/reviewer con salida comprimida. |

### Plataformas y utilidades

| Skill | Para qué sirve |
|---|---|
| `opencode` | Todo sobre OpenCode: config, agentes, skills, plugins, SDK y troubleshooting. |
| `expo` | Crea y opera apps Expo/React Native por proyecto, sin Expo global. |
| `report` | Reporta un bug de OpenCode con diagnóstico y GitHub CLI. |

</details>
<!-- SKILLS-CATALOG:END -->
