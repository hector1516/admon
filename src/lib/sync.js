import { writable, get } from 'svelte/store';
import db from './db/admonDb.js';
import { online } from './stores/online.js';

// Motor de sincronización offline estilo Field, adaptado a cotizaciones.
// Outbox: syncQueue {entity, action, idLocal, payload, retries}.
// - push: POST /sync/push en lote; el servidor resuelve id_local->folio
//   dentro del lote y devuelve el mapeo. Reescritura local: la fila pendiente
//   adopta su folio, las partidas cambian folioKey y la cola restante se
//   reescribe a folio para que los reintentos no dependan del mapa.
// - pull: GET /sync/pull (resumen + clientes); mezcla sin pisar pendientes.
// - fondo: cada 30 s + al volver la red + al volver visible la pestaña.

export const pendingCount = writable(0);
export const syncing = writable(false);
export const lastSyncResult = writable(null);

export async function refreshPending() {
	try {
		pendingCount.set(await db.syncQueue.count());
	} catch {}
}

function token() {
	return localStorage.getItem('admon_token');
}

function headers() {
	const h = { 'Content-Type': 'application/json' };
	const t = token();
	if (t) h['Authorization'] = `Bearer ${t}`;
	return h;
}

function isOnline() {
	try {
		return get(online) && navigator.onLine !== false;
	} catch {
		return get(online);
	}
}

export async function syncPush() {
	if (get(syncing) || !isOnline()) return { ok: 0, failed: 0 };
	if (!token()) return { ok: 0, failed: 0 };
	syncing.set(true);
	let ok = 0,
		failed = 0;
	try {
		const queue = await db.syncQueue.orderBy('id').toArray();
		if (queue.length === 0) {
			syncing.set(false);
			return { ok: 0, failed: 0 };
		}
		const res = await fetch('/api/sync/push', {
			method: 'POST',
			headers: headers(),
			body: JSON.stringify({
				items: queue.map((q) => ({
					entity: q.entity,
					action: q.action,
					id_local: q.idLocal,
					payload: q.payload || {}
				}))
			})
		});
		if (res.status === 401 || res.status === 403) {
			const { auth } = await import('./stores/auth.js');
			auth.logout();
			const { navigate } = await import('./router.js');
			navigate('/login', { replace: true });
			throw new Error('Sesión expirada');
		}
		if (!res.ok) throw new Error('Error del servidor');
		const data = await res.json();
		const touchedFolios = new Set();

		for (const r of data.results || []) {
			const item = queue.find((q) => q.idLocal === r.id_local);
			if (!item) continue;
			if (r.status === 'ok') {
				// Crear cotización: la fila pendiente adopta su folio real
				if (item.entity === 'cotizacion' && item.action === 'create' && r.folio) {
					const oldKey = item.idLocal;
					const row = await db.cotizaciones.get(oldKey);
					if (row) {
						await db.cotizaciones.delete(oldKey);
						await db.cotizaciones.put({ ...row, folio: r.folio, synced: true, ts: Date.now() });
					}
					// Partidas locales cambian de folioKey
					await db.partidas.where('folioKey').equals(oldKey).modify({ folioKey: String(r.folio) });
					// Cola restante del mismo id_local se reescribe a folio
					const rest = await db.syncQueue.where('idLocal').equals(oldKey).toArray();
					for (const q of rest) {
						if (q.id === item.id) continue;
						await db.syncQueue.update(q.id, {
							payload: { ...(q.payload || {}), folio: r.folio, id_local: oldKey }
						});
					}
					touchedFolios.add(String(r.folio));
				} else {
					if (r.folio) touchedFolios.add(String(r.folio));
					if (item.entity === 'cotizacion' && item.action === 'delete' && r.folio) {
						await db.cotizaciones.where('folio').equals(r.folio).delete();
						await db.partidas.where('folioKey').equals(String(r.folio)).delete();
					}
				}
				if (item.id != null) await db.syncQueue.delete(item.id);
				ok++;
			} else {
				const retries = (item.retries || 0) + 1;
				if (item.id != null) {
					if (retries >= 5) {
						await db.syncQueue.delete(item.id);
					} else {
						await db.syncQueue.update(item.id, { retries });
					}
				}
				failed++;
			}
		}

		// Refrescar partidas de los folios tocados (números Partida del servidor mandan)
		for (const f of touchedFolios) {
			try {
				const items = await fetch(`/api/cotizaciones/${f}/partidas`, { headers: headers() }).then((x) => {
					if (!x.ok) throw new Error('x');
					return x.json();
				});
				await db.partidas.where('folioKey').equals(f).delete();
				for (const p of items) await db.partidas.add({ ...p, folioKey: f, synced: true });
			} catch {}
		}

		await refreshPending();
		lastSyncResult.set({ ok, failed, time: new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }) });
	} catch (e) {
		console.error('Sync failed:', e);
	} finally {
		syncing.set(false);
	}
	return { ok, failed };
}

// Throttle: App.svelte y la suscripción a `online` llaman a syncPull casi al
// mismo tiempo al arrancar. Sin esto se hacían 2 peticiones /sync/pull por
// página. 10 s es de sobra para deduplicar el arranque.
let _lastPullAt = 0;

export async function syncPull() {
	if (!token()) return;
	const _now = Date.now();
	if (_now - _lastPullAt < 10000) return;
	_lastPullAt = _now;
	try {
		const res = await fetch('/api/sync/pull', { headers: headers() });
		if (!res.ok) return;
		const data = await res.json();
		for (const r of data.cotizaciones || []) {
			const idLocal = `srv-${r.folio}`;
			const prev = await db.cotizaciones.get(idLocal);
			// No pisar filas pendientes (folio null) ni nota/color editados offline
			await db.cotizaciones.put({
				...(prev || {}),
				idLocal,
				folio: r.folio,
				id_cliente: r.id_cliente,
				cliente: r.cliente,
				contacto: r.contacto,
				fecha: r.fecha,
				descripcion: r.descripcion,
				autor: r.autor,
				estatus: r.estatus,
				suma_partidas: r.suma_partidas,
				flete: r.flete,
				subtotal: r.subtotal,
				iva: r.iva,
				total: r.total,
				synced: prev ? !!prev.synced : true,
				ts: Date.now()
			});
		}
		if (data.clientes) {
			await db.clientes.bulkPut(
				data.clientes.map((c) => ({ id_cliente: c.id_cliente, nombre: c.nombre, dias_pago: c.dias_pago }))
			);
		}
	} catch (e) {
		console.error('Pull failed:', e);
	}
}

// Fondo: cada 30 s + al volver la red + al volver visible
let syncInterval = null;

function startBackgroundSync() {
	if (syncInterval) return;
	syncInterval = setInterval(async () => {
		try {
			const count = await db.syncQueue.count();
			if (count > 0 && isOnline() && !get(syncing)) await syncPush();
		} catch {}
	}, 30000);
}

if (typeof window !== 'undefined') {
	startBackgroundSync();
	refreshPending();
	online.subscribe((isOnline) => {
		if (isOnline && token()) {
			syncPush();
			syncPull();
		}
	});
	document.addEventListener('visibilitychange', async () => {
		if (document.visibilityState === 'visible' && isOnline()) {
			try {
				const count = await db.syncQueue.count();
				if (count > 0 && !get(syncing)) await syncPush();
			} catch {}
		}
	});
}
