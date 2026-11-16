/* ECCSA-Shell — audit.js — Bitácora de actividad (audit trail) */
/* Uso: import { logAction, logError, logClick, logNavigation } from '$lib/audit.js' */

const APP_PREFIX = 'FLD';

function getUser() {
    try {
        return JSON.parse(localStorage.getItem('field_user') || 'null');
    } catch {
        return null;
    }
}

function authHeader() {
    const token = localStorage.getItem('field_token');
    return token ? { Authorization: `Bearer ${token}` } : {};
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
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify(entry),
    }).catch(() => {});

    console.log(`[AUDIT] ${APP_PREFIX}-${modulo}-${accion}`, datos);
}

export function logError(codigo, modulo, mensaje, contexto = {}) {
    fetch('/api/debug/log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify({ codigo, app: APP_PREFIX, modulo, mensaje, contexto, url: window.location.href }),
    }).catch(() => {});

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

export const ERROR_CODES = {
    AUTH_LOGIN_FAIL: 'FLD-AUTH-001',
    AUTH_SESSION_EXPIRED: 'FLD-AUTH-002',
    TKT_LIST_LOAD: 'FLD-TKT-LST-001',
    TKT_CREATE: 'FLD-TKT-NEW-001',
    TKT_OCR: 'FLD-TKT-OCR-001',
    VAL_LIST_LOAD: 'FLD-VAL-LST-001',
    VAL_CREATE: 'FLD-VAL-NEW-001',
    REP_LIST_LOAD: 'FLD-REP-LST-001',
    REP_CREATE: 'FLD-REP-NEW-001',
    KM_LIST_LOAD: 'FLD-KM-LST-001',
    KM_CREATE: 'FLD-KM-NEW-001',
    NET_ERROR: 'FLD-NET-001',
    API_ERROR: 'FLD-API-001',
    UI_ERROR: 'FLD-UI-001',
};