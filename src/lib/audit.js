// src/lib/audit.js — Bitácora de actividad (audit trail)
// Registra cada acción del usuario: clicks, navegación, inserts, updates, deletes, errores.

const APP_PREFIX = 'ADM';

function getUser() {
    try {
        return JSON.parse(localStorage.getItem('admon_user') || 'null');
    } catch {
        return null;
    }
}

function authHeader() {
    const token = localStorage.getItem('admon_token');
    return token ? { Authorization: `Bearer ${token}` } : {};
}

export function logAction(tipo, modulo, accion, datos = {}, duracionMs = null) {
    const user = getUser();
    const entry = {
        app: APP_PREFIX,
        modulo,
        tipo_accion: tipo,
        accion,
        detalle: accion,
        datos,
        duracion_ms: duracionMs,
    };

    // Enviar al backend (async, no bloquea UI)
    fetch('/api/audit/log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify(entry),
    }).catch(() => {});

    // Log en console para debug
    console.log(`[AUDIT] ${APP_PREFIX}-${modulo}-${accion}`, datos);
}

export function logError(codigo, modulo, mensaje, contexto = {}) {
    const user = getUser();
    // Enviar al backend de debug
    fetch('/api/debug/log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify({
            codigo,
            app: APP_PREFIX,
            modulo,
            mensaje,
            contexto,
            url: window.location.href,
        }),
    }).catch(() => {});

    // También registrar en audit
    logAction('error', modulo, codigo, { mensaje, ...contexto });

    console.error(`[${codigo}] ${mensaje}`, contexto);
    return codigo;
}

export function logNavigation(from, to) {
    logAction('navigate', '', `nav_${from}_to_${to}`, { from, to });
}

export function logClick(modulo, boton, datos = {}) {
    logAction('click', modulo, `click_${boton}`, datos);
}

// Códigos de error estándar
export const ERROR_CODES = {
    // Auth
    AUTH_LOGIN_FAIL: 'ADM-AUTH-001',
    AUTH_SESSION_EXPIRED: 'ADM-AUTH-002',
    AUTH_NO_PERMISSION: 'ADM-AUTH-003',

    // Cotizaciones
    COT_LIST_LOAD: 'ADM-COT-LST-001',
    COT_DETAIL_LOAD: 'ADM-COT-DET-001',
    COT_CREATE: 'ADM-COT-NEW-001',
    COT_UPDATE: 'ADM-COT-EDT-001',
    COT_DELETE: 'ADM-COT-DEL-001',
    COT_SEARCH: 'ADM-COT-SRH-001',

    // Clientes
    CLI_LIST_LOAD: 'ADM-CLI-LST-001',
    CLI_DETAIL_LOAD: 'ADM-CLI-DET-001',
    CLI_SEARCH: 'ADM-CLI-SRH-001',

    // Reportes
    REP_LIST_LOAD: 'ADM-REP-LST-001',
    REP_DETAIL_LOAD: 'ADM-REP-DET-001',
    REP_CREATE: 'ADM-REP-NEW-001',

    // Usuarios
    USR_LIST_LOAD: 'ADM-USR-LST-001',
    USR_DETAIL_LOAD: 'ADM-USR-DET-001',
    USR_UPDATE: 'ADM-USR-EDT-001',

    // General
    NET_ERROR: 'ADM-NET-001',
    API_ERROR: 'ADM-API-001',
    UI_ERROR: 'ADM-UI-001',
};