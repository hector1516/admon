# Admon

> ⚠️ **LEGACY (ServerVM `10.188.141.31`):** lo que sigue describe el host
> viejo, que **ya no se usa**. Las apps se despliegan en WebbApps con Arcane
> (ver `AGENTS.md` de la raíz, §2). **No ejecutes estos pasos en ServerVM.**

App de administración de ECCSA — [`admon.ecc-sa.com.mx`](https://admon.ecc-sa.com.mx).

Interfaz **Svelte 5 + Vite + Tailwind v3**, API **FastAPI** sobre
`pymssql` contra la base `ECCSA_Admon`. Se instala como PWA y funciona sin
conexión con los últimos registros cacheados en IndexedDB.

> ⚠️ No confundir con `hector1516/admon`, que es el **HUB de Streamlit** — un
> proyecto distinto.

## Apps del ecosistema

Admon es una de las 3 apps que comparten el diseño y el shell:

| App | Qué es | Stack |
|---|---|---|
| **Field** | PWA de los ingenieros de campo | SvelteKit + Tailwind v4 |
| **Admon** (esta) | Administración: cotizaciones, clientes, remisiones, tickets | Svelte 5 + Vite + Tailwind v3 |
| **WorkersAdmon** | Panel de control de los workers de fondo | Python stdlib, sin build |

Las tres comparten el diseño, el banner, la barra de acciones y la regla de
ubicación desde el repo [`ECCSA-Shell`](https://github.com/hector1516/ECCSA-Shell).
**Ese CSS y esos componentes están generados: no se editan en esta app.**
Ver [`AGENTS.md`](AGENTS.md) para el detalle de qué es de Admon y qué es del
shell.

## Módulos

Cotizaciones (materiales y servicios/proyectos), clientes, remisiones con
códigos SAT CFDI 4.0, tickets de OxxoGas, registro de reportes, ECCSA IA,
usuarios y permisos, Legends, configuración.

## Desarrollo

```bash
npm ci
npm run dev          # http://localhost:5173
npm run build        # → dist/
```

La API se levanta aparte:

```bash
uvicorn api.main:app --reload --port 8000
```

Variables de entorno (prioridad sobre `secretos_local.py`, que nunca se sube):

```
HUB_DB_SERVER, HUB_DB_USER, HUB_DB_PASSWORD, HUB_DB_DATABASE, HUB_SMTP_PASSWORD
```

## Documentación

- [`AGENTS.md`](AGENTS.md) — reglas: qué es generado, cómo se cablea el banner,
  versión, deploy.
- [`docs/DEPLOY.md`](docs/DEPLOY.md) — runbook de despliegue, topología en el
  ServerVM, deploy automático con gate de rebuild, rollback.
- [`CHANGELOG.md`](CHANGELOG.md) — qué cambió en cada versión. Lo que está acá
  es también lo que muestra el popup 📋 de novedades dentro de la app.
