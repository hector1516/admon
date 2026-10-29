/* Admon Service Worker — espejo del de Field, alcance "/" servido por FastAPI.
 * REGLA DURA (lección Field): solo interceptar GET. Nunca responder POST/PUT
 * con FormData: el SW perdería el body y el backend recibiría size=0 (422).
 */
const CACHE = 'admon-v1.0.5';
const APP_SHELL = [
	'/',
	'/index.html',
	'/manifest.webmanifest',
	'/admon_logo.png',
	'/engrane.png',
	'/icons/icon-192x192.png',
	'/icons/icon-512x512.png'
];

// Prefijos que son API (network-only, jamás cachear: llevan auth y POSTs).
// La API vive bajo /api/*; la SPA es dueña de la raíz (sin colisiones).
const API_PREFIXES = ['/api', '/docs', '/openapi.json', '/redoc'];

self.addEventListener('install', (e) => {
	e.waitUntil(
		caches.open(CACHE).then((c) =>
			Promise.all(APP_SHELL.map((u) => c.add(u).catch(() => {})))
		).then(() => self.skipWaiting())
	);
});

self.addEventListener('activate', (e) => {
	e.waitUntil(
		caches.keys()
			.then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
			.then(() => self.clients.claim())
	);
});

// ── Notificaciones push ──────────────────────────────────────────────────────
// iOS exige la PWA instalada y iOS 16.4+ para que esto se dispare; el cliente
// (src/lib/push.js) es quien verifica esas condiciones antes de pedir permiso.
function _esIOS() {
	const ua = navigator.userAgent || '';
	if (/iP(hone|ad|od)/.test(ua)) return true;
	return /Macintosh/.test(ua) && (navigator.maxTouchPoints || 0) > 1;
}

self.addEventListener('push', (e) => {
	// Con userVisibleOnly:true el servidor SIEMPRE manda body. Si no llega, no
	// hay nada que mostrar y mostrar un aviso vacío sería peor que nada.
	if (!e.data) return;

	let payload = {};
	try {
		payload = e.data.json();
	} catch {
		payload = { title: 'Admon', body: e.data.text() };
	}

	const title = payload.title || 'Admon';

	const options = {
		body: payload.body || '',
		data: { url: payload.url || '/' },
		// El tag agrupa: si llegan tres avisos del mismo tipo, el segundo
		// reemplaza al primero en lugar de apilar tres. En iPhone la pila de
		// notificaciones se llena rápido y tapar la pantalla es peor que
		// resumir.
		tag: payload.tag || 'admon',
		renotify: !!payload.tag,
		silent: !!payload.silent,
		// iOS NO usa imágenes remotas: el ícono tiene que estar empaquetado con
		// la app, así que se referencia uno local siempre.
		icon: '/icons/icon-192x192.png',
		// El badge tiene semántica distinta por plataforma y mandarlo igual en
		// los dos casos se ve mal en alguno:
		//   · iOS      → `badge` es un NÚMERO que se pinta en el ícono.
		//   · Android  → `badge` es la URL de una IMAGEN pequeña.
		// Por eso el servidor manda `badge_count` y acá se decide.
		badge: _esIOS() ? String(payload.badge_count || 0) : '/icons/icon-192x192.png'
	};

	// En iOS el ícono grande de la notificación (Aperture) sale del bundle, no
	// de la app: no se controla desde acá y no se intenta.
	if (payload.vibrate && navigator.vibrate) {
		options.vibrate = payload.vibrate;
	}

	e.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (e) => {
	e.notification.close();

	const url = e.notification.data?.url || '/';

	e.waitUntil((async () => {
		// Primero se intenta despertar una pestaña que YA esté abierta: en iOS
		// abrir una ventana nueva desde una notificación deja la PWA en un
		// estado raro (a veces en blanco), así que enfocar la existente es
		// siempre la opción preferida.
		const tabs = await self.clients.matchAll({
			type: 'window',
			includeUncontrolled: true
		});

		for (const tab of tabs) {
			if (tab.url.startsWith(self.location.origin)) {
				await tab.focus();
				// Se le pasa la ruta para que la app navegue. Se usa postMessage
				// en vez de tab.navigate() porque la ruta puede llevar query y el
				// router de la app la lee del history, no de un evento.
				tab.postMessage({ type: 'ABRIR_RUTA', url });
				return;
			}
		}

		// No había ninguna pestaña: se abre la PWA.
		await self.clients.openWindow(url);
	})());
});

self.addEventListener('message', (e) => {
	if (e.data && e.data.type === 'SKIP_WAITING') self.skipWaiting();
	if (e.data && e.data.type === 'FORCE_RELOAD') {
		self.clients.matchAll({ type: 'window' }).then((clients) => {
			clients.forEach((c) => c.postMessage({ type: 'FORCE_RELOAD' }));
		});
	}
	if (e.data && e.data.type === 'LIMPIAR_BADGE') {
		// El ícono del iPhone lo pinta el SO y no hay otra forma de quitarlo.
		// Va por `registration`, que es donde existe la API del Badging dentro
		// de un service worker (no en `self`).
		e.waitUntil((async () => {
			if (typeof self.registration.clearAppBadge === 'function') {
				await self.registration.clearAppBadge();
			}
		})());
	}
});

self.addEventListener('fetch', (e) => {
	const { request } = e;
	// Solo GET: el resto pasa directo a red (ver regla dura arriba)
	if (request.method !== 'GET') return;
	const url = new URL(request.url);
	if (url.origin !== self.location.origin) return;

	// API -> siempre red, sin cache
	if (API_PREFIXES.some((p) => url.pathname === p || url.pathname.startsWith(p + '/'))) {
		return;
	}

	// Navegaciones (rutas SPA) -> red primero, fallback al shell cacheado.
	// Solo se cachea el shell si la red respondió OK (un 403/404 no debe
	// quedar guardado como index.html para el modo offline).
	if (request.mode === 'navigate') {
		e.respondWith(
			fetch(request)
				.then((res) => {
					if (res && res.ok) {
						const copy = res.clone();
						caches.open(CACHE).then((c) => c.put('/index.html', copy)).catch(() => {});
					}
					return res;
				})
				.catch(() => caches.match('/index.html').then((r) => r || caches.match('/')))
		);
		return;
	}

	// Estáticos (assets, iconos, imágenes) -> cache primero, actualiza en fondo
	e.respondWith(
		caches.match(request).then((cached) => {
			const network = fetch(request).then((res) => {
				if (res && res.ok) {
					const copy = res.clone();
					caches.open(CACHE).then((c) => c.put(request, copy)).catch(() => {});
				}
				return res;
			}).catch(() => cached);
			return cached || network;
		})
	);
});
