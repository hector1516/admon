/* ECCSA-Shell — debug.js — Sistema de debugging con códigos de error únicos */
/* Uso: import { logError, ERROR_CODES } from '$lib/debug.js' */

const APP_PREFIX = 'APP';

export function logError(code, message, context = {}) {
    const error = {
        code,
        message,
        context,
        timestamp: new Date().toISOString(),
        url: typeof window !== 'undefined' ? window.location.href : '',
    };
    console.error(`[${code}] ${message}`, context);

    // Enviar al backend (async, no bloquea UI)
    try {
        const token = localStorage.getItem('admon_token') || localStorage.getItem('field_token');
        if (token) {
            fetch('/api/debug/log', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ codigo: code, app: APP_PREFIX, modulo: code.split('-')[1] || '', mensaje: message, contexto: context, url: error.url }),
            }).catch(() => {});
        }
    } catch (e) {}

    return code;
}

export function logAction(tipo, modulo, accion, datos = {}, duracionMs = null) {
    const entry = {
        app: APP_PREFIX,
        modulo,
        tipo_accion: tipo,
        accion,
        detalle: accion,
        datos,
        duracion_ms: duracionMs,
    };

    fetch('/api/audit/log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('admon_token') || localStorage.getItem('field_token')}` },
        body: JSON.stringify(entry),
    }).catch(() => {});

    console.log(`[AUDIT] ${APP_PREFIX}-${modulo}-${accion}`, datos);
}

export function logNavigation(from, to) {
    logAction('navigate', '', `nav_${from}_to_${to}`, { from, to });
}

export function logClick(modulo, boton, datos = {}) {
    logAction('click', modulo, `click_${boton}`, datos);
}

// Códigos de error estándar
export const ERROR_CODES = {
    AUTH_LOGIN_FAIL: 'ADM-AUTH-001',
    AUTH_SESSION_EXPIRED: 'ADM-AUTH-002',
    AUTH_NO_PERMISSION: 'ADM-AUTH-003',
    COT_LIST_LOAD: 'ADM-COT-LST-001',
    COT_DETAIL_LOAD: 'ADM-COT-DET-001',
    COT_CREATE: 'ADM-COT-NEW-001',
    COT_UPDATE: 'ADM-COT-EDT-001',
    COT_DELETE: 'ADM-COT-DEL-001',
    COT_SEARCH: 'ADM-COT-SRH-001',
    CLI_LIST_LOAD: 'ADM-CLI-LST-001',
    CLI_DETAIL_LOAD: 'ADM-CLI-DET-001',
    CLI_SEARCH: 'ADM-CLI-SRH-001',
    REP_LIST_LOAD: 'ADM-REP-LST-001',
    REP_DETAIL_LOAD: 'ADM-REP-DET-001',
    REP_CREATE: 'ADM-REP-NEW-001',
    USR_LIST_LOAD: 'ADM-USR-LST-001',
    USR_DETAIL_LOAD: 'ADM-USR-DET-001',
    USR_UPDATE: 'ADM-USR-EDT-001',
    KIL_LIST_LOAD: 'ADM-KIL-LST-001',
    TIX_LIST_LOAD: 'ADM-TIX-LST-001',
    NET_ERROR: 'ADM-NET-001',
    API_ERROR: 'ADM-API-001',
    UI_ERROR: 'ADM-UI-001',
};