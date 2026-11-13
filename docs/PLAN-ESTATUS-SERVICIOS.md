# Plan: Módulo "Estatus de Servicios" en Admon

## Objetivo

Módulo dentro de la app Admon que monitorea el estatus de todos los servicios
que usa la oficina (externos e internos) con semáforo visual, gráficos de
historial en tiempo real, detalle de incidencias y alertas. Incluye API pública
para consumo desde otras apps y widget para iPhone (Scriptable).

## Servicios a monitorear

### Externos (vía APIs públicas de status)

| Servicio | Fuente | Tipo de API |
|---|---|---|
| Microsoft 365 (Exchange, Teams, SharePoint, OneDrive) | status.office.com | RSS feed |
| GoDaddy (hosting, email, DNS) | status.godaddy.com | Statuspage v2 (JSON) |
| Cloudflare (DNS, CDN, WAF, Workers) | cloudflarestatus.com | Statuspage v2 (JSON) |

### Internos (vía health endpoints HTTP)

| Servicio | URL de salud | Puerto |
|---|---|---|
| Admon | localhost:8103/health | 8103 |
| Field | localhost:8100/api/health | 8100 |
| Dashboard | localhost:8101/healthz | 8101 |
| Mailbox | localhost:8104/health | 8104 |
| Colaboradores | localhost:8105/healthz | 8105 |
| WorkersAdmon | localhost:8200/healthz | 8200 |
| SQL Server | 10.188.141.15:1433 | 1433 |
| WebbApps (servidor) | 10.188.141.17 (SSH/ping) | — |

## Arquitectura

### Backend (Admon API)

**Nuevo router:** `api/routers/estatus_servicios.py`

**Endpoints (API interna para el módulo):**
- `GET /api/estatus-servicios` — lista todos los servicios con estatus actual
- `GET /api/estatus-servicios/{id}` — detalle de un servicio
- `GET /api/estatus-servicios/{id}/historial` — historial de checks (últimas 24h/7d/30d)
- `POST /api/estatus-servicios/verificar` — fuerza verificación manual
- `GET /api/estatus-servicios/resumen` — resumen global (cuántos verdes/amarillos/rojos)

**Endpoints (API pública para otras apps y widget):**
- `GET /api/estatus-servicios/api/v1/servicios` — lista compacta de servicios (JSON simple)
- `GET /api/estatus-servicios/api/v1/servicio/{id}` — estatus de un servicio individual
- `GET /api/estatus-servicios/api/v1/resumen` — resumen global compacto
- `GET /api/estatus-servicios/api/v1/widget` — payload optimizado para Scriptable (iOS)

**Autenticación de API pública:**
- Header `X-API-Key` (misma key que Arcane) o token de sesión
- Rate limiting: 60 requests/min por IP

**Verificación periódica:**
- Worker en WorkersAdmon que corre cada 5 minutos
- Cada check guarda un registro en `HUB_EstatusHistorial`
- Se actualiza el estatus actual en `HUB_EstatusServicios`
- Detección de cambios → crea incidencia + alerta Telegram

### Base de datos (nuevas tablas)

**HUB_EstatusServicios** — catálogo de servicios
```sql
Id, Nombre, Tipo (externo/interno), Categoria, UrlCheck, UrlStatus,
Icono, Activo, UltimoCheck, UltimoEstatus, UltimoDetalle, TiempoRespuestaMs,
Creado, Actualizado
```

**HUB_EstatusHistorial** — historial de checks
```sql
Id, IdServicio, Estatus (verde/amarillo/rojo/gris), Detalle, TiempoRespuestaMs,
FechaCheck, IncidenciaId (nullable)
```

**HUB_EstatusIncidencias** — incidencias detectadas
```sql
Id, IdServicio, Titulo, Descripcion, Estatus (activa/resuelta),
FechaInicio, FechaResolucion, Fuente (api/manual)
```

### Frontend (Admon Svelte)

**Nueva página:** `EstatusServicios.svelte`

**Vista principal — Grid de tarjetas:**
- Cada tarjeta muestra: icono, nombre, semáforo (verde/amarillo/rojo/gris), último check
- Ordenadas por: críticos primero, luego por nombre
- Auto-refresh cada 60 segundos (polling)
- Filtro por categoría (externo/interno) y por estatus

**Vista de detalle (al hacer click en una tarjeta):**
- Header: nombre, icono, semáforo grande, último check, tiempo de respuesta
- Gráfico de uptime en tiempo real (últimas 24h, actualización cada 60s)
- Historial de checks (tabla con fecha, estatus, detalle, tiempo de respuesta)
- Incidencias activas (si las hay) con descripción y tiempo transcurrido
- Incidencias resueltas (últimos 30 días)
- Botón "Verificar ahora" para forzar un check manual

**Resumen global (widget superior):**
- Contador: X verdes, Y amarillos, Z rojos
- Gráfico de tendencia (últimas 24h)
- Última verificación

### Widget para iPhone (Scriptable)

**Script de Scriptable (JavaScript para iOS):**
- Llama a `GET /api/estatus-servicios/api/v1/widget`
- Muestra un widget en la pantalla de inicio del iPhone con:
  - Semáforo global (verde/amarillo/rojo)
  - Lista compacta de servicios con estatus
  - Última actualización
- Refresh automático cada 15 minutos (límite de iOS)
- Colores: verde #22c55e, amarillo #eab308, rojo #ef4444, gris #6b7280

**Payload del endpoint widget:**
```json
{
  "global": "verde",
  "total": 11,
  "verdes": 9,
  "amarillos": 1,
  "rojos": 1,
  "actualizado": "2026-11-12T15:30:00",
  "servicios": [
    {"nombre": "Microsoft 365", "estatus": "verde", "icono": "📧"},
    {"nombre": "GoDaddy", "estatus": "verde", "icono": "🌐"},
    {"nombre": "Cloudflare", "estatus": "amarillo", "icono": "☁️"},
    {"nombre": "Admon", "estatus": "verde", "icono": "📋"},
    ...
  ]
}
```

### Alertas

- Reutilizar infraestructura de Telegram (ya existe en Field/workersadmon)
- Enviar alerta cuando un servicio cambia de verde a amarillo/rojo
- Enviar alerta cuando se resuelve una incidencia (rojo → verde)
- Configurable: solo alertas para servicios críticos
- Formato: "🔴 Microsoft 365: Exchange Online degradado — 15:32 MX"

## Fuentes de datos

### Microsoft 365 (RSS)
- **Feed:** https://status.office.com (RSS/XML)
- **Parseo:** Extraer estado de cada servicio del feed XML
- **Servicios:** Exchange Online, Teams, SharePoint, OneDrive, Azure AD

### GoDaddy (Statuspage v2)
- **API:** https://status.godaddy.com/api/v2/summary.json
- **Parseo:** JSON con componentes y su status
- **Servicios:** Hosting, Email, DNS, Dominios

### Cloudflare (Statuspage v2)
- **API:** https://www.cloudflarestatus.com/api/v2/summary.json
- **Parseo:** JSON con componentes y su status
- **Servicios:** DNS, CDN, WAF, Workers, Pages

### Internos (HTTP health checks)
- **Admon:** GET http://localhost:8103/health → 200 OK
- **Field:** GET http://localhost:8100/api/health → 200 OK
- **Dashboard:** GET http://localhost:8101/healthz → 200 OK
- **Mailbox:** GET http://localhost:8104/health → 200 OK
- **Colaboradores:** GET http://localhost:8105/healthz → 200 OK
- **WorkersAdmon:** GET http://localhost:8200/healthz → 200 OK
- **SQL Server:** TCP connection test al puerto 1433
- **WebbApps:** ping o SSH al servidor

## Pasos de implementación

### Fase 1: Base de datos + Backend core (1-2 días)
1. Crear migración SQL con las 3 tablas
2. Crear router `estatus_servicios.py` con endpoints CRUD
3. Implementar verificadores para servicios internos (HTTP health checks)
4. Implementar verificador para GoDaddy (Statuspage API)
5. Implementar verificador para Cloudflare (Statuspage API)
6. Implementar verificador para Microsoft 365 (RSS feed)
7. Registrar router en `main.py`

### Fase 2: Worker de verificación (1 día)
8. Crear script de verificación periódica (cada 5 min)
9. Integrar en WorkersAdmon
10. Guardar resultados en HUB_EstatusHistorial
11. Detectar cambios de estatus y crear incidencias
12. Alertas Telegram para cambios

### Fase 3: API pública (0.5 días)
13. Endpoints `/api/estatus-servicios/api/v1/*` con formato compacto
14. Endpoint `/api/estatus-servicios/api/v1/widget` para Scriptable
15. Autenticación por API key
16. Rate limiting

### Fase 4: Frontend (2-3 días)
17. Crear página `EstatusServicios.svelte`
18. Grid de tarjetas con semáforo
19. Vista de detalle con gráficos en tiempo real (chart.js)
20. Historial de checks (tabla)
21. Incidencias activas y resueltas
22. Integrar en router de Admon
23. Agregar tarjeta en Home de Admon
24. Auto-refresh cada 60 segundos

### Fase 5: Widget Scriptable (0.5 días)
25. Crear script JavaScript para Scriptable (iOS)
26. Configurar widget en pantalla de inicio
27. Refresh automático cada 15 min

### Fase 6: Deploy y pruebas (1 día)
28. Commit, push, CI, deploy en Arcane
29. Verificar que todos los checks funcionan
30. Ajustar umbrales y tiempos

## Estimación total: 5-7 días

## Dependencias

- `chart.js` o `svelte-chartjs` para gráficos en frontend
- `requests` (ya disponible en backend) para HTTP checks
- `feedparser` para RSS de Microsoft 365
- Telegram bot token (ya configurado en Field/workersadmon)
- Scriptable app en iPhone (gratis en App Store)

## Consideraciones

- **Rate limiting:** No hacer checks más frecuentes de cada 5 minutos
- **Caché:** Guardar el último resultado para no saturar las APIs
- **Offline:** Mostrar último estatus conocido si no hay conexión
- **Permisos:** Solo usuarios con AccesoMailbox o nuevo permiso "AccesoEstatus"
- **Retención:** Guardar historial por 30 días, luego purgar
- **Seguridad:** API pública requiere API key, no expone datos sensibles

## Preguntas abiertas

1. ¿Quieres monitorear servicios adicionales? (AWS, Azure, etc.)
2. ¿Los gráficos deben actualizar en tiempo real (WebSocket) o polling cada 60s?
3. ¿Quieres un widget en el Dashboard principal de Admon además de la página?
4. ¿El widget de iPhone debe mostrar todos los servicios o solo los críticos?
