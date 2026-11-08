// Helper de API estilo Field (src/lib/api): fetch con Bearer token del store,
// base '/api', errores tipados y logout en 401.
// - GET: red primero -> guarda en IndexedDB (offlineCache) -> si no hay red
//   devuelve lo último cacheado (últimos 10 registros + detalles por módulo,
//   precargados por offlinePrefetch.js). Ver src/lib/offline.js.
// - Escrituras: offline lanzan NetworkError('Sin conexión') con mensaje claro.
import { auth } from './stores/auth.js';
import { navigate } from './router.js';
import { NetworkError, cachePut, cacheGet, servingFromCache } from './offline.js';

const BASE = '/api';

async function request(path, options = {}) {
	const headers = { ...(options.headers || {}) };
	const token = localStorage.getItem('admon_token');
	if (token) headers['Authorization'] = `Bearer ${token}`;
	if (!(options.body instanceof FormData)) {
		headers['Content-Type'] = 'application/json';
	} else {
		delete headers['Content-Type'];
	}
	let res;
	try {
		res = await fetch(`${BASE}${path}`, { ...options, headers });
	} catch {
		// fetch falló a nivel de conexión (offline/DNS/timeout): no es un
		// error HTTP de la API. Se tipa para que los helpers decidan fallback.
		throw new NetworkError();
	}

	if (res.status === 401) {
		auth.logout();
		navigate('/login', { replace: true });
		throw new Error('Sesión expirada');
	}
	if (!res.ok) {
		const err = await res.json().catch(() => ({}));
		let detail = err.detail || err.message || 'Error del servidor';
		// FastAPI 422 devuelve detail como array de objetos {loc, msg, type}
		if (Array.isArray(detail)) {
			detail = detail.map((d) => d?.msg || JSON.stringify(d)).join('; ');
		}
		throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
	}
	return res.json();
}

export const api = {
	// GET con caché offline: red primero; si no hay red, caché local.
	// La llave de caché es el path COMPLETO incluyendo '/api' (consistente
	// con lo que cachean cotizacionesApi.js y el prefetch).
	get: async (path) => {
		try {
			const data = await request(path);
			await cachePut(BASE + path, data);
			servingFromCache.set(false);
			return data;
		} catch (e) {
			// Solo ante falta real de red se intenta la caché local;
			// los errores HTTP (403/404/500) se propagan tal cual.
			if (e && e.code === 'NETWORK') {
				const cached = await cacheGet(BASE + path);
				if (cached !== null && cached !== undefined) {
					servingFromCache.set(true);
					return cached;
				}
			}
			throw e;
		}
	},
	post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
	postForm: (path, formData) => request(path, { method: 'POST', body: formData }),
	put: (path, body) => request(path, { method: 'PUT', body: JSON.stringify(body) }),
	delete: (path) => request(path, { method: 'DELETE' })
};
