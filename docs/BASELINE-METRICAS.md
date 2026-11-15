# Baseline de Métricas de Rendimiento

## Fecha: 2026-11-15

## Admon

| Módulo | Tiempo render (ms) | Tiempo total (ms) | Contenido |
|---|---|---|---|
| Dashboard | 126 | 2034 | ✅ |
| Cotizaciones | 126 | 2035 | ✅ |
| Clientes | 126 | 2026 | ✅ |
| Administración | 126 | 2041 | ✅ |
| Legends | 126 | 2028 | ✅ |
| Kilómetros | 126 | 2032 | ✅ |
| TicketsOxxoGas | 126 | 2035 | ✅ |
| EstatusServicios | 126 | 2031 | ✅ |
| Perfil | 126 | 2035 | ✅ |

**Promedio render: 126ms | Promedio total: 2127ms**

## Field

| Módulo | Tiempo render (ms) | Tiempo total (ms) | Contenido |
|---|---|---|---|
| Home | 114 | 2028 | ✅ |
| Tickets | 114 | 2137 | ✅ |
| Vales | 114 | 2138 | ✅ |
| Reportes | 114 | 2161 | ✅ |
| Kilómetros | 114 | 2095 | ✅ |
| Legends | 114 | 2137 | ✅ |

**Promedio render: 114ms | Promedio total: 2116ms**

## Observaciones

1. **Render time es rápido** (~120ms) — el problema no es el renderizado
2. **Total time es ~2s** — el problema es la carga de datos (API calls)
3. **Todos los módulos son igual de lentos** (~2s) — el problema es sistémico
4. **La mayoría del tiempo es la espera de datos del servidor** (network + DB query)
5. **No hay variación significativa entre módulos** — todos hacen ~2-3 API calls

## Causas probables

1. **Queries sin índices** — SQL Server hace table scans
2. **Sin paginación** — se cargan todos los registros
3. **N+1 queries** — se cargan detalles en serie
4. **Sin caché** — cada navegación hace fetch completo
5. **Sin debounce** — búsquedas en cada keystroke

## Objetivos post-optimización

| Métrica | Actual | Objetivo |
|---|---|---|
| Carga de lista (25 items) | 2-5s | < 500ms |
| Búsqueda | 1-3s | < 300ms |
| Detalle de item | 1-2s | < 400ms |
| Dashboard | 3-5s | < 1s |
| Cambio de módulo | 1-2s | < 300ms |