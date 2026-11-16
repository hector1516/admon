// src/lib/cache.js — Caché local estándar para Admon
// Usa localStorage para datos pequeños y sessionStorage para datos de sesión.
// TTL configurable por tipo de dato.

const CACHE_PREFIX = 'admon_cache_';

// TTL por defecto (en ms)
const TTL_DEFAULT = 5 * 60 * 1000; // 5 minutos
const TTL_CONFIG = 60 * 60 * 1000; // 1 hora
const TTL_CATALOGO = 10 * 60 * 1000; // 10 minutos

export function cacheKey(modulo, params = '') {
    return `${CACHE_PREFIX}${modulo}_${params}`;
}

export function cacheGet(modulo, params = '') {
    try {
        const key = cacheKey(modulo, params);
        const raw = localStorage.getItem(key);
        if (!raw) return null;
        const entry = JSON.parse(raw);
        if (Date.now() > entry.expires) {
            localStorage.removeItem(key);
            return null;
        }
        return entry.data;
    } catch {
        return null;
    }
}

export function cacheSet(modulo, params = '', data, ttl = TTL_DEFAULT) {
    try {
        const key = cacheKey(modulo, params);
        const entry = { data, expires: Date.now() + ttl, created: Date.now() };
        localStorage.setItem(key, JSON.stringify(entry));
    } catch (e) {
        // localStorage lleno — limpiar caché viejo
        limpiarCacheViejo();
    }
}

export function cacheInvalidate(modulo, params = '') {
    try {
        if (params) {
            localStorage.removeItem(cacheKey(modulo, params));
        } else {
            // Invalidar todos los entries del módulo
            const prefix = cacheKey(modulo, '');
            Object.keys(localStorage).forEach(key => {
                if (key.startsWith(prefix)) {
                    localStorage.removeItem(key);
                }
            });
        }
    } catch {}
}

export function limpiarCacheViejo() {
    try {
        const now = Date.now();
        Object.keys(localStorage).forEach(key => {
            if (key.startsWith(CACHE_PREFIX)) {
                try {
                    const entry = JSON.parse(localStorage.getItem(key));
                    if (entry.expires && now > entry.expires) {
                        localStorage.removeItem(key);
                    }
                } catch {
                    localStorage.removeItem(key);
                }
            }
        });
    } catch {}
}

// TTLs exportados
export const TTL = {
    DEFAULT: TTL_DEFAULT,
    CONFIG: TTL_CONFIG,
    CATALOGO: TTL_CATALOGO,
};

// Limpiar caché viejo al cargar
if (typeof window !== 'undefined') {
    setTimeout(limpiarCacheViejo, 1000);
}