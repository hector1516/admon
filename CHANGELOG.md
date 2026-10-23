# Historial de cambios — Admon

> App de administración ECCSA (`AdmonApp`). Versión y novedades visibles para
> el usuario en `public/changelog.json` y en el popup 📋 del shell.

## [1.8.0] - 2026-10-23

### Nuevo
- **ECCSA Legends rediseñado en Admon**: la misma experiencia que Field, con
  ranking semanal, temporada trimestral, racha, nivel y 20 logros. La pantalla
  usa `/api/legends/overview` y ya no tiene partículas ni canvas.
- **Puntos por dinero**: cotización pagada +15 a +75 según el subtotal sin IVA,
  entregada +10, cliente nuevo cotizado +5, primeras partidas +2, cobranza +3,
  fotos de evidencia +2 y cierre el mismo día +3.
- **Castigos**: vale sin comprobante −2, reporte tardío −2 y retrabajo −5.
  Los vales solo se castigan en la semana actual.
- **Logros de dinero**: Primer cliente, Cazador de clientes, Primer pago,
  Cerrador, Evidencia, Mismo día y Vale limpio.

### Cambiado
- **La cotización pagada se premia por transición** a `Color=2`, no por estado,
  y el auditor solo revisa cotizaciones de la semana actual.
- **El reporte suma para el técnico**, no para quien sube la foto: el punto de
  fotos se protege globalmente y se registra una sola vez.
- **El borrado de un reporte firmado** ahora genera retrabajo −5.

### Base de datos
- **Migración `0046_legends_rediseno.sql`**: agrega `RachaMax`, `SemanaKey`,
  `HUB_UserLogros` y los índices de idempotencia. Ya aplicada y validada en
  `ECCSA_Admon_Pruebas`; en producción requiere aprobación explícita.

## [1.7.4] - 2026-10-06

### Agregado
- **Avisos al teléfono** desde Configuración: una tarjeta nueva para activar las
  notificaciones en este equipo, ver en qué equipos están registradas y mandar un
  🧪 aviso de prueba. Los avisos los decide `notif_dispatch.py` en WorkersAdmon
  (panel → módulo "📣 Avisos"): reporte firmado, kilometraje sin registrar, ticket
  OxxoGas, cotización firmada y cotización facturada.
- **Solo los avisos de los módulos que tienes abiertos.** El reparto sale de tus
  permisos, no de una lista: quien puede abrir Cotizaciones es quien recibe el
  aviso de una cotización firmada.
- **Fuera de lunes a viernes de 9:00 a 18:30 no suena nada.** Lo que se acumula
  sale junto al siguiente día laboral, en un solo resumen.
- **El aviso dice quién lo causó** ("Rosa firmó el reporte RS-123"), no solo que
  pasó algo.
- **Endpoints** `GET /api/push/vapid-public-key`, `POST /api/push/subscribe`,
  `POST /api/push/unsubscribe`, `GET /api/push/suscripciones` y
  `POST /api/push/prueba`.

### Corregido
- **El botón "📣 Enviar aviso push" no le llegaba a nadie.** Buscaba las
  suscripciones en `HUB_PushSubscriptions`, la tabla vieja: está vacía (a ella
  solo escribe `mcp_server`) y no tiene columna de app. Ahora usa
  `HUB_PushSuscripciones`, la que sí distingue el origen.
- **Una clave VAPID guardada en PEM o DER hacía fallar TODOS los push** con un
  error que no dice por qué: `pywebpush` quiere la privada como base64url de los
  32 bytes crudos. Ahora se convierte sola.
- **Tocar una notificación no llevaba a ninguna parte.** El service worker
  enfoca la pestaña que ya está abierta (en iOS abrir una ventana nueva desde una
  notificación deja la PWA en blanco) y le pasa la ruta por `postMessage`, pero
  nadie escuchaba ese mensaje.

### Notas para iPhone
- Requiere iOS 16.4 o superior y la app **instalada** en la pantalla de inicio.
- El permiso solo se pregunta desde un toque, nunca al abrir la app.
- En iOS el permiso nunca llega a "bloqueado": si no lo aceptas se queda en
  "sin decidir" para siempre, por eso la pantalla pide el motivo exacto en vez de
  decir "no se pudo".

## [1.7.3] - 2026-10-05

### Corregido
- **La asistencia mostraba la hora equivocada cuando el escáner se atrasaba.**
  `HUB_NetworkPresence` guarda DOS fechas y su propio docstring dice que la
  asistencia debe leer `FechaDeteccion` (el instante del escaneo que prueba el
  evento) y no `FechaHora` (cuándo lo procesó el worker). Ambas apps leían la
  segunda. Mientras el worker va al día da igual, pero el 5 de octubre se
  quedó 6 h atascado y drenó de golpe 1 195 escaneos: las columnas se
  separaron hasta 51 minutos y las llegadas se veían con la hora del drenaje.
  Rosa aparecía a las 09:22 cuando llegó a las 08:35, y el ajuste de 4 min
  caía sobre el número equivocado. Ahora ambas apps usan
  `COALESCE(FechaDeteccion, FechaHora)`, con respaldo para los registros
  anteriores a esa columna.
- **El aviso "el escáner no corre" volvía a ser un falso positivo.** El latido se
  medía sobre `HUB_NetworkScanRuns` y, si esa tabla tenía filas, no se miraba la
  otra. Con el escáner escribiendo en el camino viejo, la nueva quedó con miles
  de filas viejas y la pantalla anunciaba "16 h sin escanear" con el escáner
  escribiendo hace 1 min. Ahora el latido es el máximo de las dos.

## [1.7.2] - 2026-10-05

### Corregido
- **🖼️ La pantalla de portada apuntaba al servidor muerto.** El valor por defecto
  de `HUB_PANEL_URL` en `api/notas_pantalla.py` era `10.188.141.31:8101`
  (ServerVM). El kiosco `dashboard` se mudó a WebbApps (10.188.141.17:8101) y
  ese servidor ya no responde, así que la pantalla estaba rota sin que saltara
  ninguna alarma: el error se veía como un 404 del kiosco.
- **El workflow del panel token escribía donde nadie leía.** Depositaba el
  secret en `C:\admon\.secrets\panel_token` del ServerVM Windows, que era el
  camino del `build.ps1` viejo. Ahora rota `HUB_PANEL_TOKEN` en
  `/etc/admon.env` de WebbApps (lo que lee `/opt/apps/_lib/run_app.sh`) y
  recrea el contenedor, porque `docker restart` NO recarga el env.
  Se agrega `admon-set-secret`, un helper de root que escribe una sola clave del
  env-file: el runner tiene sudo para ese script, no para el archivo, y así no
  puede leer las credenciales de la base de datos.

### Verificado
- El camino **REBUILD** del pipeline se probó de punta a punta (tocando
  `requirements.txt` a propósito): compiló el front, `docker build` en 45 s,
  recreó el contenedor por `/opt/apps/_lib/run_app.sh` yy quedó en salud a los
  2 s. El camino hotsync también, varias veces. Los dos  dos fallos
  aparecieron al probarlos de verdad, no al leer el YAML: `npm ci` corría sobre
  el montaje de solo lectura, y una línea de comentario sin `#` en `app.conf`
  rompía el `source` (el conf se carga con `source`, así que un comentario mal
  puesto es un error de sintaxis).

### Cambiado
- **`APP_AUTO_START=1` en `/opt/apps/admon/app.conf`.** Estaba en 0 porque WebbApps
  no tenía RAM para esta app (154 MB). Hoy hay memoria de sobra y la app está en
  servicio; dejarlo en `created` hacía que cada rebuild la apagara y había que
  arrancarla a mano.
- Se eliminan `deploy/build.ps1`, `deploy/hotsync.sh` y `deploy/register_task.ps1`:
  eran del camino Windows (PowerShell, `C:\admon`, tarea programada `AdmonBuild`).
  Este repo ya no los usa; quedan en el historial de git.

## [1.7.1] - 2026-10-05

### Corregido
- **El deploy automático volvía a publicar donde nadie llega.** El workflow
  corría en un runner **Windows del ServerVM (10.188.141.31)**, que ya no publica
  la app: GitHub reportaba `success` mientras los usuarios seguían con la
  versión vieja. Ahora corre en **WebbApps (Debian, 10.188.141.17)**, que es donde
  está la app:
  - Runner nuevo `WebbApps-Runner` en WebbApps (Linux), con la etiqueta
    `admon-deploy` y servicio systemd `actions-runner-admonapp` para que no se
    caiga al reiniciar. Se pidió `admon-deploy` y no `self-hosted` a propósito:
    con `self-hosted` el job podía caer en el runner Windows viejo.
  - El gate (decidir rebuild vs hotsync) pasó a `ubuntu-latest` en bash: ya no
    depende de PowerShell 5.1 ni de que ningún runner esté vivo.
  - Scripts nuevos `deploy/hotsync-linux.sh` y `deploy/rebuild-linux.sh`. Sin
    cygpath ni MSYS: el frontend se compila con node dentro de un contenedor y
    en un directorio temporal, para no dejar `node_modules` de root en el clon.
  - La configuración del contenedor sigue saliendo de `/opt/apps/admon/app.conf`
    en el servidor (puertos, red, credenciales): no viaja en el repo.

## [1.7.0] - 2026-10-05

### Corregido
- **🎫 Tickets OxxoGas se caía (>20 s, timeout).** Emparejaba cada ticket con su
  vale con `XmlContent LIKE '%folio%'`: 22 tickets × 255 vales de 6 KB de XML
  son 36 MB de texto escaneados por petición, 8 s de CPU. La igualdad
  `XmlFolio = FolioTicket` no matchea ninguno, así que todo el costo era ese
  `LIKE`. Ahora los vales se leen una vez (0.5 s) y la coincidencia se hace en
  Python (0.08 s): **0.84 s**, con los mismos tickets emparejados a su factura.
- **🏆 Legends tardaba 5 s y pesaba 2.5 MB.** El ranking traía el avatar EN
  BASE64 de cada usuario (PNG de 578×432, 150-310 KB cada uno) y además lo
  metía en el `GROUP BY`. Ahora solo se pide la longitud del base64 y el avatar
  se recorta a 128 px **en el servidor** (5.7 KB), y solo se descargan los que
  no estén en caché: 156 KB y 0 s. La respuesta no cambia de forma, así que el
  front no se entera.
- **📦 Inventario devolvía 500 en todas partes**: la consulta pedía la columna
  `Id`, que no existe; la de llave es `IdInventario`.
- **🔎 La búsqueda de cotizaciones devolvía 500**: pymssql exige los parámetros
  como tupla y se le estaba pasando una lista. Y cuando sí respondía, tardaba 51 s. Filtrar por cliente con
  `ISNULL(C.Cliente,'') LIKE` hacía que el `COUNT` del total recorriera clientes
  por cada cotización (25 s). Con `IdCliente IN (subconsulta)` el mismo filtro
  tarda 0.01 s.
- **💾 El prefetch sin conexión tardaba 28 s en cada inicio de sesión**: pedía 500
  cotizaciones con su columna de texto. Bajó a 100 (~1 s); para trabajar sin
  conexión se sigue teniendo la última pantalla.
- **📋 Filas duplicadas en el listado de cotizaciones.** `clientes` tiene 7
  `IdCliente` repetidos y el `LEFT JOIN` multiplicaba las 57 cotizaciones de
  esos clientes. Se agrupa por `IdCliente` para que cada cotización aparezca
  una sola vez.
- **⚠️ Sigue pendiente arreglar los datos**: las 7 filas duplicadas de `clientes`
  (ATTC, Dail, GRMA, IJDM, ISAL, LEOS, SSMT) se siguen limpiando solo para
  mostrar; en la ficha pueden verse las dos.

### Agregado
- **📄 Paginación de 100 en 100 en todos los listados**, con barra al final de la
  lista: ⏮ ◀ Anterior · "Página X de Y" · Siguiente ▶ ⏭, más un campo para saltar
  a una página. Las flechas del teclado también funcionan. En Cotizaciones la
  paginación es **del servidor** (cada página pide solo sus 100 folios, para no
  arrastrar la columna de descripción entera) y el buscador va al servidor, así
  que la búsqueda ya no se limita a lo que está cargado.
  Componente nuevo: `src/components/Paginacion.svelte`.

## [1.6.3] - 2026-10-05

### Corregido
- **📦 Cotizaciones Materiales ya no tarda 26 s ni marca la app como "Sin conexión".**
  Dos problemas encadenados, los dos en el mismo par de endpoints
  (`GET /api/cotizaciones/resumen` y `GET /api/sync/pull`):
  - **La consulta**: usaban la vista `vw_ResumenCotizaciones`, que hace
    `GROUP BY I.Descripcion`. Esa columna es `varchar(max)`, y agrupar por una
    LOB cuesta ~26 s en SQL Server. Con un tope de 100 filas la misma consulta
    baja a milisegundos, así que además se topó el listado.
  - **El congelamiento**: ambos endpoints eran `async def` con pymssql
    **síncrono**, así que esas 26 s detenían el event loop de uvicorn. Con el
    loop ocupado, el ping a `/api/health` que hace el front tardaba 12 s y el
    front, con su timeout de 5 s, se declaraba "Sin conexión" y pintaba los
    datos guardados. `/api/sync/pull` se dispara en el prefetch del login, así
    que además **congelaba la app al iniciar sesión**. Los dos endpoints ahora
    son `def` y FastAPI los corre en el threadpool: aunque una consulta se
    ponga lenta ya no puede tumbar al servidor ni provocar un falso "Sin
    conexión".
- **Importes inflados al doble en el listado.** La vista hace
  `LEFT JOIN Clientes` y `Clientes` tiene 7 `IdCliente` repetidos (ATTC, Dail,
  GRMA, IJDM, ISAL, LEOS, SSMT), de modo que cada partida se contaba dos veces.
  El folio CM01135 se mostraba con total $20,114.55 cuando sus partidas suman
  $9,270.06. El detalle y el PDF leen `Partidas` directo, o sea que el listado
  mostraba una cifra que el PDF no respaldaba. El agregado ahora sale de
  `Partidas` sin pasar por `Clientes`, y coincide con el detalle y el PDF.
- El nuevo listado calcula el agregado de partidas **solo para los folios que
  devuelve** en vez de agrupar la tabla entera y descartar mil resultados.

## [1.6.2] - 2026-10-01

### Corregido
- **El aviso de "el escáner no reporta" era un falso positivo.** Se medía
  contra la última entrada o salida registrada, y eso no dice si el escáner
  vive: los movimientos son por evento, así que a media mañana, con todos
  sentados trabajando, no hay ni un registro nuevo en media hora y la pantalla
  avisaba de un escáner caído que estaba corriendo perfecto.
  Ahora lo que decide es el **latido del escáner**: su último ciclo en
  `HUB_NetworkScanRuns` (con respaldo en `HUB_NetworkScanResults`, según
  dónde esté escribiendo), que llega uno cada minuto.
  - El ciclo se busca primero en la tabla nueva y se cae a la vieja, como
    hace el worker.
  - La antigüedad la calcula el servidor SQL con `DATEDIFF`, no Python: el
    reloj del contenedor va horas adelantado.
  - Si el escáner nunca ha corrido, se dice "no se sabe" en vez de "no hay
    datos de hoy": sin escáner tampoco se puede afirmar que no vino nadie.
  - La barra ahora muestra el último ciclo **y** el último movimiento, que son
    dos cosas distintas.
- **La hora de "Actualizado" sale del reloj del servidor SQL**: se leía
  "Actualizado 15:12" cuando en la oficina eran las 09:12.

## [1.6.1] - 2026-10-01

### Corregido
- **La asistencia ya no marca "en sitio" cuando el escáner de red no está
  reportando.** El 30 de septiembre el escáner dejó de escribir a las 15:56 y,
  como nadie llegó a registrar su salida, la pantalla lanzaba "9 en sitio"
  con datos de hace horas: la última cosa que se sabía de cada quien era que
  habían entrado. Ahora:
  - El backend mide la edad del dato más reciente (`ultimo_evento`,
    `minutos_sin_actualizar`, `estado`) y la vista avisa cuando pasa de 10 min
    sin reportar (el escáner corre cada minuto con 5 min de tolerancia).
  - Con datos congelados sale un aviso ámbar arriba, las tarjetas pierden el
    color de estado (nada de "verde = en la oficina" sin saberlo) y las
    métricas se marcan "(¿?)". **Las horas de llegada y salida se conservan**:
    ésas no envejecen.
  - La barra deja de prometer el refresco automático y pasa a decir de cuándo
    es el último dato.
- **La asistencia tampoco se pinta cuando el detector escribe todos de un
  jalón.** Al reiniciarse el escáner (o caerse la red un momento) se registra
  una `SALIDA` y una `ENTRADA` para todo el mundo en el mismo segundo, y eso
  volvía a dejar la pantalla completa en verde con la oficina vacía. Ahora, si
  3 o más personas registran el mismo tipo de evento en el mismo minuto, la
  vista avisa que el detector cambió el estado de todos de un jalón y tampoco
  pinta el estado.
- **Relojes desfasados**: si algún movimiento trae fecha futura, la pantalla lo
  avisa en vez de darlo por bueno.
- **El endpoint abre una sola conexión** al SQL Server (antes cuatro: personas,
  fotos, frescura y marcha). Con varias personas mirando la pantalla a la vez se
  notaba: la respuesta pasó de segundos a ~30 ms.

## [1.6.0] - 2026-10-01

### Nuevo
- **El módulo de usuarios ahora es el módulo ⚙️ Administración, con pestañas**:
  la tarjeta del menú se llama **Administración** (antes *Administrador de
  Usuarios*) y dentro hay dos secciones:
  - **🕘 Asistencia** (la primera, y la que abre por default): quién llegó,
    quién sigue en la oficina y quién ya se fue **hoy**, con la misma
    información que muestra la pantalla *Asistencia de hoy* del Dashboard de
    la oficina. Arriba van las tres métricas (registradas / 🟢 en sitio / 🔴
    fuera) y luego una tarjeta por persona: foto (o iniciales), **Llegó**
    HH:MM y **Se fue** HH:MM sólo si ya salió. Los que siguen aquí van con
    tarjeta verde, los que ya se fueron en rojo. Cuando alguien salió y volvió
    se anota **↩️ volvió HH:MM** (la salida no se muestra porque ya no aplica).
    Se refresca **solo cada minuto** mientras la pestaña está a la vista, con
    botón **🔄 Actualizar** y la hora del último refresco a la vista.
  - **👥 Administración** (la segunda): la lista de usuarios que ya existía,
    tal cual (fotos, puesto, MAC del teléfono y acceso).
  - Cada pestaña es una ruta real: `/admin` (Asistencia) y `/admin/usuarios`
    (Administración), así el enlace se puede compartir y el ⬅️ del navegador
    retrocede. **La ruta vieja `/usuarios` sigue funcionando** y abre
    directo en la pestaña de Administración, que es adonde apuntan el botón
    "Volver" de cada ficha y los enlaces ya publicados.
- **Endpoint `GET /api/asistencia`**: calcula la asistencia del día leyendo
  `HUB_NetworkPresence` (la que escribe el `network_scanner_worker` cuando ve
  aparecer o desaparecer una MAC conocida). Toma la **primera entrada** y la
  **última salida** de cada persona, con el mismo ajuste de 4 min que usa el
  kiosco, y todo en **un solo SELECT** (el "último evento" se resuelve con
  `OUTER APPLY` en vez de una consulta por persona).
  Los horarios salen como `YYYY-MM-DD HH:MM` y cada persona trae `tiene_foto`,
  para que la vista pida la foto sólo de quienes la tienen (igual que la
  lista de usuarios).
  Los resultados se contrastaron contra el snapshot del kiosco: **idénticos**
  (mismas personas, mismas horas de llegada/salida y mismos estados).

### Corregido
- `admin` se agrega a las rutas de la SPA del backend: sin eso, abrir
  `/admin` directo (recargando o por enlace) devolvía 404 en vez de la app.

## [1.5.0] - 2026-10-01

### Nuevo
- **Registro de Reportes: exportación a Excel** del formato de cotizaciones
  (pestaña **📊 Excel**, junto a 🟢 Firmados y 🗑️ Papelera):
  - **Selección múltiple**: cada reporte firmado de la lista trae su casilla;
    solo se pueden marcar reportes del **mismo cliente** (el primero fija el
    cliente y el resto se bloquea con aviso), y se ve en la barra el cliente,
    cuántos van seleccionados y la suma de horas. Si un reporte no tiene hora
    de inicio o fin no se puede marcar.
  - **Columnas del formato** (hoja `Calculo`, un reporte por fila desde la 3):
    **A** = consecutivo (1, 2, 3…), **B** = total de horas
    `(fin − inicio) + traslado` con 2 cifras (la comida no se descuenta) y
    **C** = `Folio · descripción del servicio`. El resto de columnas (modelo,
    costos, precios) quedan como en el template, con las fórmulas de precio
    replicadas hacia abajo y los `=SUM(...)` de totales ajustados al rango
    real de filas.
  - **Validaciones en el servidor** (`GET /api/reportes/excel?ids=...`):
    reportes Firmados, fuera de papelera, todos del mismo cliente, con horas
    completas y máximo 500 por descarga; se ordenan por fecha y folio para
    que el consecutivo salga siempre corrido igual.
  - **Archivo descargado** con nombre genérico
    `Reportes_<Cliente>_AAAA-MM-DD.xlsx`, generado desde el template real
    `formatos excel/Formato Cotizaciones.xlsx` (la hoja `Cotizacion` no se
    toca).
- Se vuelve a agregar **openpyxl** a `requirements.txt` (lo había quitado el
  escaneo del 2026-09-27) y el `Dockerfile` ahora copia el template del
  formato al contenedor (sintaxis JSON: la forma con comillas la rechaza el
  BuildKit del ServerVM) — por eso este despliegue reconstruye la imagen.

## [1.4.1] - 2026-09-30

### Mejoras
- **Módulo de Usuarios, recuadros más grandes y con todo el contenido acomodado**
  (`src/pages/Usuarios.svelte`, `src/pages/UsuarioDetalle.svelte`):
  - **Lista**: cada recuadro creció (más relleno, avatar de 3.75 rem que sube a
    4.25 rem en escritorio) y el contenido ya no compite en una sola línea:
    nombre, correo, puesto y los badges (MAC / admin) van en filas propias con
    `flex-wrap`, así un correo o un puesto largo se parten en varias líneas en
    vez de sacar badges fuera del recuadro.
  - **Lista en escritorio (≥900px)**: los recuadros se muestran en dos
    columnas (`grid`), más anchos y sin estirarse de punta a punta.
  - **Ficha**: tarjetas con más aire (padding 1.5 rem), avatar de la foto más
    grande (7 rem, 9 rem en pantallas anchas) y los campos de "Datos" ahora en
    dos columnas cuando hay sitio (≥760px), con "Contraseña" y "Usuario activo"
    abajo a todo lo ancho.
  - **Permisos**: cada grupo (📊 Administración, 📋 Operativo…) es ahora su
    propia tarjetita con borde, y los grupos se acomodan en dos columnas en
    escritorio — se deja de hacer scroll interminable por una sola columna.
  - **La foto del usuario se muestra** en su recuadro de la lista (avatar
    circular con `object-fit: cover`) y en la ficha; mientras nadie tenga foto
    se ven las iniciales de cada quien, y en cuanto se suba una aparece sola
    (la lista la pide por `GET /api/users/<id>/foto` solo a los que tienen).


## [1.4.0] - 2026-09-30

### Nuevo
- **NSS, Puesto y fotografía en los usuarios** (migración `0045`), para alimentar
  los módulos que se van a armar después:
  - **NSS** (número de seguro social) y **Puesto** ("Supervisor de
    mantenimiento", "Analista"…) son columnas nuevas en `HUB_Users`, al final de
    la tabla para no mover los índices de los SELECT existentes. El NSS se
    normaliza a solo dígitos al guardar (así se captura con o sin guiones) y se
    guarda como texto plano, igual que CURP/RFC.
  - **Fotografía**: una por usuario, en la tabla nueva `HUB_UsuariosFotos`
    (VARBINARY(MAX)) en vez de en `HUB_Users` — HUB_Users se lee en cada login
    y en los listados de la HUB y del kiosco, y meter un binario ahí haría que
    todas esas consultas arrastraran la imagen. Sube y se reemplaza con una
    sola acción; 5 MB máximo; JPEG/PNG/WEBP/GIF.
  - **En la ficha** (`UsuarioDetalle`): tarjeta con la foto (o iniciales si no
    tiene), botón para quitarla, y campos NSS y Puesto junto a los datos.
  - **En la lista** de Usuarios: avatar circular de cada uno, con iniciales de
    respaldo, y el puesto bajo el correo.
  - **Para las otras apps**: la foto se pide por HTTP con
    `GET /api/users/<id>/foto`, y la lista `GET /api/users` ya trae `puesto` y
    `tiene_foto`. El NSS a propósito NO va en la lista (solo en la ficha de
    usuario): es dato personal y la lista es de lectura más amplia.
- Migración `0045` aplicada y registrada en `ECCSA_Admon_Pruebas` y
  producción (`ECCSA_Admon`).

## [1.3.0] - 2026-09-30

### Nuevo
- **Artículo genérico en las partidas de cotizaciones de materiales**: campo
  nuevo `ArticuloGenerico` en la tabla `Partidas` (migración `0043`) con el
  nombre del artículo en lenguaje de compras ("controlador lógico",
  "disyuntor", "cable de comunicación"), distinto de los códigos SAT que ya se
  manejaban. Va en el PDF de la cotización dentro de la línea gris de la
  descripción, en el orden **artículo → clave SAT → unidad**, antes pedido por
  compras: primero cómo se llama el artículo, luego la clave fiscal.
  - **Captura** (`src/pages/PartidasAdmin.svelte`): input propio debajo de la
    descripción y badge 📦 en la lista de partidas; viaja en el payload de
    alta/edición de `src/lib/cotizacionesApi.js` (y por lo tanto también en la
    cola offline, cuyo replay en `api/main.py` ya escribe el campo).
  - **Sugerencia 🤖** (`api/sat_helper.py`): ahora devuelve
    `articulo_generico` además de los códigos. Reglas locales → nombre de la
    propia regla; IA Gemini → lo pide el mismo prompt (1 sola llamada, sin
    costo extra); índice local → se aprendió en la resolución previa y si la
    fila es anterior se rellena con la regla en 0 tokens. Si el usuario ya
    escribió algo en el campo, el 🤖 no lo pisa.
  - **Conservación**: el valor se copia al clonar la cotización, se limpia a
    `''` (no `NULL`) si se borra, y se respeta en UPDATE/DELETE. La columna va
    al final de `Partidas`, así que los SELECT posicionales de HUB
    (`eccsa_db.py`, que sí escribe en esa tabla) y los INSERT con lista de
    columnas no cambian.
- **`0044_sat_articulo_generico.sql`**: el índice auto-alimentado
  `HUB_SatArticulos` guarda también el nombre genérico aprendido, para que el
  🤖 lo ofrezca en 0 tokens cuando la misma descripción se repita en otra
  cotización. Las filas anteriores a 0044 quedan con el nombre vacío y el
  backend hace fallback a las reglas.

### Técnico
- Migraciones `0043` y `0044` aplicadas a `ECCSA_Admon_Pruebas` y a
  producción (`ECCSA_Admon`), registradas en `schema_migrations`.
- Prueba E2E local (uvicorn contra Pruebas) cubre alta, lectura, edición,
  borrado a vacío, sugerencia por reglas e IA, orden en el PDF (extracción con
  pypdf) y clonado: **TODO OK**. Archivos: `api/main.py`, `api/sat_helper.py`,
  `api/pdf_cotizacion.py`, `src/lib/cotizacionesApi.js`,
  `src/pages/PartidasAdmin.svelte`, `migrations/0043_*.sql`,
  `migrations/0044_*.sql`.

### Fix
- **El botón 🤖 no llenaba el artículo genérico cuando la descripción ya era
  conocida por el índice SAT**: los códigos salían al instante (el índice las
  tiene), pero esas filas se escribieron antes de la migración 0044 y por tanto
  no tenían nombre genérico, y si ninguna regla local reconocía la descripción
  el campo quedaba vacío sin aviso. Ahora, cuando el índice no tiene nombre, se
  prueba primero la regla local (0 tokens) y si tampoco la hay se hace **una
  llamada corta a Gemini solo por el nombre** (`_articulo_ia` en
  `api/sat_helper.py`); el nombre se guarda en el índice, así que la siguiente
  vez que salga esa misma descripción se resuelve en 0 tokens. En la UI, cuando
  la sugerencia no trae artículo, se avisa que hay que escribirlo a mano.

## [1.2.0] - 2026-09-28

### Nuevo
- **Menú de módulos**: las tarjetas se volvían cuadradas de ~230px y dejaban
  un hueco enorme al centro en la PC. El shell global `.module-card` trae
  `aspect-ratio: 1` + `max-height: 230px` (el look cuadrado de Field) y el menú
  de Admon solo tenía `1fr 1fr` fijo, sin breakpoints. Ahora `.menu-grid` usa
  columnas por resolución (2 <560px · 3 ≥560 · 4 ≥900 · 5 ≥1280) y la tarjeta
  se anula el aspecto cuadrado en el alcance de `src/pages/Dashboard.svelte`
  (`aspect-ratio: auto`), sin tocar `styles/app.css` (CSS del shell, validado
  por hash). Medido con el CSS compilado: 1920 → 5 columnas de 365px de ancho.
- **Fix regression**: un rebuild con `dist/` viejo borró del contenedor el UI
  recién publicado (botón "📊 Dashboard" y el campo de MAC del teléfono dejaron
  de verse). El ServerVM no tiene npm, y `deploy/build.ps1` caía en "usar el
  dist/ precompilado" de `C:\admon`, que estaba desactualizado. Ahora el
  rebuild compila el frontend igual que hotsync: en un contenedor efímero
  `node:20-alpine` (npm ci && npm run build) y aborta si no genera `dist/`,
  dejando la producción intacta. El dist siempre refleja el commit recién
  hecho `git pull`.
- **HUB_PANEL_TOKEN**: el control remoto de la TV necesita este secret en el env
  del contenedor, y un env no se puede mutar en caliente. Se creó el Secret
  `HUB_PANEL_TOKEN` en el repo, `deploy/build.ps1` lo inyecta al recrear el
  contenedor (lo lee de `C:\admon\.secrets\panel_token`, fuera de git, porque
  el rebuild se lanza por `schtasks` y no hereda el entorno del workflow), el
  deploy normal lo deposita antes de cada rebuild, y se agrega
  `.github/workflows/apply-panel-token.yml` para (re)aplicarlo a mano sin push.
  El valor nunca está en el repo ni en los logs.
- **Fix CI**: el popup de novedades del banner (y el check `Check shell`) exige
  que cada cambio quepa en 160 caracteres. Se acortó el del botón Dashboard.
- **Fix CI "Check shell"**: el badge 📡 de la MAC en la lista de Usuarios se
  había puesto en `src/styles/app.css`, que es el CSS del shell canónico (lo
  genera `tools/sync_shell.py` y el CI valida por hash). Se movió al estilo
  local de `Usuarios.svelte`; el archivo del shell queda intacto.
- **Pestaña "Pantalla de la TV"** (📺): segunda pestaña del botón Dashboard con
  (a) el **control remoto del kiosco** y (b) la **imagen de portada**.
  - Control remoto contra el panel del snapshotter: `GET /api/panel/estado`
    (sin token, trae si la TV está conectada, las 12 pantallas que publica la
    propia TV al arrancar y el último comando con su confirmación) y
    `POST /api/panel/comando` (CON token: acciones `ver` | `avanzar` | `pausa` |
    `seguir`; `ver` reinicia el contador a 45 s). Los botones de pantalla se
    dibujan con lo que llegue, sin lista fija; la TV consulta cada 3 s, por eso
    la UI avisa "enviado" y luego muestra el "confirmado". Pausa y seguir van
    juntos para no congelar la pantalla sin salida.
  - El token es `HUB_PANEL_TOKEN` (GitHub Secret + variable de entorno);
    nunca en el código. Sin él el panel responde 403 y la app lo reporta en vez
    de fallar en silencio.
  - Imagen de portada: se sube a `HUB_PantallaImagenes` por la API y **no** se
    manda por HTTP al kiosco — el snapshotter la lee de ahí y la TV la toma en
    su próxima vuelta. Endpoints `GET/POST /api/pantalla/portada`,
    `POST .../{id}/restaurar`, `DELETE .../{id}`; la lógica vive en
    `api/notas_pantalla.py`. Se guarda la activa y las anteriores se
    desactivan (índice único por clave), así que se puede volver a una anterior
    sin resubirla; la activa no se puede borrar. Avisa si no mide 1920×1080.
  - Migración `0042_imagen_pantalla.sql` (idempotente; la tabla ya existía en
    producción por la 0041 del repo HUB — **no** se volvió a aplicar esa).
- **Botón "Dashboard" con pestañas**: nuevo botón `📊 Dashboard` en el menú
  que abre una página de pestañas (`src/pages/Panel.svelte`, ruta `/panel`)
  con la pestaña **📺 Pantalla de la TV** dentro (el módulo de notas, antes
  página propia) y sitio para las próximas funciones. Cada pestaña es una ruta real
  (`/panel`, `/notas`): el enlace se puede compartir, el botón atrás del
  navegador retrocede de pestaña y `/notas` queda como alias que abre el
  Panel con Notas activa (bookmarks y prefetch siguen igual). Para sumar
  funciones nuevas: entrada en `TABS` de `Panel.svelte`, ruta en `App.svelte`
  con `initialTab` y su bloque `{#if}`.
- **MAC del teléfono en Usuarios** (📡): la ficha de usuario tiene un campo
  nuevo para anotar la MAC del celular, que se guarda/relaciona en
  `HUB_NetworkDevices` (la tabla del escáner de Detección de Red, por
  `IdUsuario`) — así se empieza a medir **entradas y salidas de la oficina**.
  El detalle muestra el estado en vivo (🟢 en la oficina / ⚪ fuera), el último
  evento de entrada/salida y la última vez visto en la red; la lista de
  usuarios muestra el badge `📡 MAC`. Upsert sin borrar historia: quitar la
  MAC solo desvincula (`Activo = 0`) porque `HUB_NetworkPresence` y
  `HUB_NetworkState` tienen FK hacia esa fila. Se rechaza con 400 si la MAC ya
  pertenece a otro usuario activo. Endpoints `GET/PUT
  /api/users/{id}/telefono` + `mac_telefono` en `GET /api/users`.
- **Módulo Notas** (📝): tablero de notas del equipo con editor en panel
  (título, contenido, color y 📌 fijar), edición y borrado; cada nota muestra
  su autor y su fecha. Escribe en **`HUB_DashboardNotas`**, la misma tabla que
  lee la pantalla 📌 del Dashboard de la oficina (kiosco, solo lectura): lo que
  se captura en Admon aparece solo en la TV, con las fijas arriba y las 3
  primeras. Endpoints `GET/POST/PUT/DELETE /api/notas` (sin permiso propio,
  para todos los logueados) y página `src/pages/Notas.svelte` con tarjeta en el
  menú y ruta `/notas` (en `_SPA_ROUTES` y en el prefetch offline).
  Migración `0041_dashboard_notas.sql`: crea la tabla si falta (en producción ya
  existía, creada a mano y sin versionar; por eso la base de pruebas no la
  tenía).
- **ECCSA IA**: chat de una sola conversación (historial continuo en una
  conversación, con Markdown en las respuestas) y acceso directo desde el
  primer botón del Dashboard. `src/pages/EccsaIa.svelte`, `src/pages/Dashboard.svelte`.
- **Kilómetros → detalle de vehículo como página propia**: al tocar un vehículo
  se abre `/kilometros/vehiculo/:id` (deep-link, se puede compartir), en vez
  del popup anterior. Nueva página `src/pages/KilometroVehiculo.svelte`,
  ruta en `src/App.svelte`, tarjetas navegan en `src/pages/Kilometros.svelte`.

### Corregido
- **Hora de los registros de km**: el backend convierte fechas con offset (p. ej.
  `...Z` de UTC) a hora de México antes de guardar —antes las guardaba crudas,
  6 h adelantadas— y rechaza fechas futuras (`api/main.py`,
  `kilometros_registro`). El formulario ya no depende de la zona horaria del
  dispositivo: usa `Intl` con `America/Mexico_City` (`ahoraLocalInput` en
  `Kilometros.svelte` / `KilometroVehiculo.svelte`) y el detalle renderiza la
  fecha guardada sin convertirla (`fmtFecha`).
- **Datos de producción**: 58 registros históricos de `HUB_RegistroKilometros`
  que estaban +6 h se corrigieron con `DATEADD(hour,-6,...)` (respaldo en el
  servidor); verificados contra bitácora y cola de Telegram: 59/59 a 0 h.
- **Endpoint de ECCSA IA roto en producción**: `SELECT ApiKey, Modelo` contra
  `HUB_AiConfig`, pero la columna se llama `Model` → cada mensaje devolvía
  500. También se actualizó el modelo de respaldo a `gemini-3.5-flash-lite`
  (`api/main.py`).
- **Al tocar una tarjeta de vehículo salía "Not Found"**: la ruta
  `/kilometros/vehiculo/:id` tiene 4 segmentos y `App.svelte` leía el id de
  `split('/')[2]` (que era `"vehiculo"`) en vez de `[3]`; el API respondía
  404. Ahora el detalle abre correctamente (`src/App.svelte`).
- Se quitó la leyenda "N requieren servicio (≥9,500 km) / Ninguno requiere
  servicio" de debajo del KPI "Con lectura esta semana" en Kilómetros.
- **ECCSA IA se salía de la pantalla del teléfono**: `.chat-page` medía
  `100vh` pero vive debajo del banner fijo (que ya resta `--banner-h`), así
  que la página quedaba `100vh + banner`. Ahora usa
  `calc(100dvh - var(--banner-h))` y llena exacto la pantalla visible
  (`src/pages/EccsaIa.svelte`).

## [1.1.0] - 2026-09-27

### Nuevo
- **Adopta ECCSA-Shell 1.1.0** (`src/styles/app.css` como variante Tailwind
  v3 generada por el shell; ya no se edita a mano).
- **Banner común**: estado de sincronización, usuario, **oficina o remoto** y
  `v{app} · shell {versión}`, con el mismo markup y los mismos textos que Field
  y el panel.
- **Barra de acciones estándar** (⚙️ configuración · 🚪 salir) en el dashboard.
- **Popup de novedades 📋**: la primera vez que se abre una versión nueva
  muestra qué cambió. El texto vive en `public/changelog.json`, así se edita
  sin recompilar.
- **Modo offline**: últimos 10 registros y detalles de cada módulo en
  IndexedDB, con aviso de datos guardados y contactos de cliente offline.
- **Módulo de Remisiones** con códigos SAT CFDI 4.0 (port del HUB).
- **Tickets de OxxoGas**: consulta de saldo, Go Vale, retiro de Telegram y
  borrado de contacto.
- **Deploy**: script de build+deploy y runbook con el patrón de WorkersAdmon.

### Corregido
- **El banner mostraba siempre `📍`**: el `fetch` de `/api/shell/state` no
  mandaba la cabecera `Authorization: Bearer`, daba 401 y caía al
  `desconocido`. Ahora la app le pasa su `fetcher` al componente del shell.
- La versión de la app estaba **escrita a mano** (`Admon v1.0.1`) y ya no
  coincidía con `package.json` (`1.0.0`). Ahora sale de `$lib/shell.js`, que
  `sync_shell.py` genera desde `package.json`.
- Legends: la semana se calculaba en UTC y vaciaba la puntuación semanal.
- `GET /api/usuarios` no existía y el select de técnicos salía siempre vacío.
- Tickets de OxxoGas: la tarjeta de saldo iba apilada y el saldo offline no
  entraba en el prefetch.
- Dependencias alineadas al mandato de versiones de Field.

### Cambiado
- Las dependencias de `api/requirements.txt` se redujeron a lo que se importa
  de verdad (verificado con escaneo AST).
- Se quitó la guía "Cómo ganar ECCSA Points" del módulo Legends.

## [1.0.0]

Versión inicial de Admon.
