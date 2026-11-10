import { get } from 'svelte/store';
import db from './db/admonDb.js';
import { auth } from './stores/auth.js';
import { online } from './stores/online.js';
import { navigate } from './router.js';
import { uuid } from './cotizaciones.js';
import { cachePut, cacheGet } from './offline.js';

// API online-first con caché Dexie + cola offline (outbox estilo Field).
// - Lecturas: red -> actualiza caché -> devuelve mezclado (servidor + pendientes).
// - Escrituras online en fila sincronizada: directo + actualiza caché.
// - Escrituras offline o en fila pendiente: muta caché + encola para /sync/push.
// - Filas pendientes: idLocal uuid, folio null. folioKey = folio ?? idLocal.

function headers() {
	const h = { 'Content-Type': 'application/json' };
	const t = localStorage.getItem('admon_token');
	if (t) h['Authorization'] = `Bearer ${t}`;
	return h;
}

async function req(method, path, body) {
	const res = await fetch(path, {
		method,
		headers: headers(),
		body: body !== undefined ? JSON.stringify(body) : undefined
	});
	if (res.status === 401 || res.status === 403) {
		auth.logout();
		navigate('/login', { replace: true });
		throw new Error('Sesión expirada');
	}
	if (!res.ok) {
		const err = await res.json().catch(() => ({}));
		throw new Error(err.detail || 'Error del servidor');
	}
	return res.json();
}

function isOnline() {
	try {
		return get(online) && navigator.onLine !== false;
	} catch {
		return get(online);
	}
}

function isNetworkError(e) {
	return e instanceof TypeError; // fetch lanza TypeError ante fallo de red
}

async function queueOp(entity, action, idLocal, payload) {
	await db.syncQueue.add({ entity, action, idLocal, payload, retries: 0, timestamp: Date.now() });
	const { refreshPending } = await import('./sync.js');
	refreshPending().catch(() => {});
}

const srvKey = (folio) => `srv-${folio}`;
const folioKeyOf = (row) => (row.folio ?? row.idLocal);

// ---- Lecturas ----

/**
 * Listado de cotizaciones, de 100 en 100.
 *
 * La paginación va en el servidor porque son más de mil cotizaciones y pedir
 * todas de golpe hacía que SQL Server leyera cientos de páginas de la columna
 * `Descripcion` (que es varchar(max)); con el caché en frío eso tardaba 25 s y
 * la app entera se iba con ella.
 *
 * Cada página que se visita se guarda en IndexedDB, así que sin conexión se
 * siguen viendo las páginas ya descargadas. El total sale del servidor; sin
 * red se usa el conteo de lo que hay en local.
 */
export async function listar({ pagina = 1, porPagina = 100, q = '' } = {}) {
	let total = 0;
	// Folios de la página que trajo el servidor. La pantalla debe pintar SOLO
	// estos: la caché local va guardando todas las páginas que se han visitado,
	// y si se devolviera el caché entero se acumularían las tarjetas (la página
	// 2 llegaba con las 200 de las páginas 1 y 2 juntas).
	let foliosDeLaPagina = null;
	if (isOnline()) {
		try {
			const params = new URLSearchParams({ pagina: String(pagina), porPagina: String(porPagina) });
			if (q) params.set('q', q);
			const r = await req('GET', `/api/cotizaciones/resumen?${params}`);
			const filas = r.cotizaciones || [];
			total = r.total ?? filas.length;
			foliosDeLaPagina = new Set(filas.map((c) => srvKey(c.folio)));
			const items = filas.map((c) => ({
				idLocal: srvKey(c.folio),
				folio: c.folio,
				id_cliente: c.id_cliente,
				cliente: c.cliente,
				contacto: c.contacto,
				fecha: c.fecha,
				descripcion: c.descripcion,
				autor: c.autor,
				estatus: c.estatus,
				suma_partidas: c.suma_partidas,
				flete: c.flete,
				subtotal: c.subtotal,
				iva: c.iva,
				total: c.total,
				synced: true,
				ts: Date.now()
			}));
			try {
				await db.cotizaciones.bulkPut(items);
			} catch (e) {
				console.error('bulkPut error:', e);
				// Fallback to individual puts
				for (const item of items) {
					await db.cotizaciones.put(item);
				}
			}
		} catch (e) {
			if (!isNetworkError(e)) throw e;
			// sin red: se sirve de la caché local
		}
	}
	let all;
	if (foliosDeLaPagina) {
		const t0 = performance.now();
		all = await db.cotizaciones.where('idLocal').anyOf([...foliosDeLaPagina]).toArray();

	} else {
		const t0 = performance.now();
		all = await db.cotizaciones.toArray();

	}
	all.sort((a, b) => {
		if (a.folio == null && b.folio == null) return 0;
		if (a.folio == null) return -1;
		if (b.folio == null) return 1;
		return b.folio - a.folio;
	});
	if (q) {
		const t = q.trim().toLowerCase();
		const f = all.filter((c) =>
			[c.folio_fmt || folioFmtFallback(c.folio), c.id_cliente, c.cliente, c.contacto, c.autor]
				.map((v) => String(v || '').toLowerCase())
				.some((v) => v.includes(t))
		);
		return { rows: f, total: total || f.length };
	}
	if (foliosDeLaPagina) {
		const rows = all.filter((c) => foliosDeLaPagina.has(c.idLocal));
		return { rows, total: total || rows.length };
	}
	// Sin conexión el servidor no puede paginar: se corta lo que hay guardado.
	const desde = (pagina - 1) * porPagina;
	return { rows: all.slice(desde, desde + porPagina), total: all.length };
}

function folioFmtFallback(folio) {
	return folio == null ? '' : `CM${String(folio).padStart(5, '0')}`;
}

export async function header(folioOrLocal) {
	const key = String(folioOrLocal);
	const isLocal = key.startsWith('local-');
	const folio = isLocal ? null : parseInt(key, 10);
	if (!isLocal && isOnline()) {
		try {
			const h = await req('GET', `/api/cotizaciones/${folio}`);
			const prev = (await db.cotizaciones.get(srvKey(folio))) || {};
			await db.cotizaciones.put({
				...prev,
				idLocal: prev.idLocal || srvKey(folio),
				folio,
				id_cliente: h.id_cliente,
				cliente_nombre: h.cliente_nombre,
				contacto: h.contacto,
				fecha: h.fecha,
				descripcion: h.descripcion,
				nota: h.nota,
				autor: h.autor,
				color: h.color,
				synced: true,
				ts: Date.now()
			});
			return await db.cotizaciones.get(prev.idLocal || srvKey(folio));
		} catch (e) {
			if (!isNetworkError(e)) throw e;
		}
	}
	const row = isLocal
		? await db.cotizaciones.get(key)
		: (await db.cotizaciones.where('folio').equals(folio).first());
	if (!row) throw new Error('Cotización no encontrada en caché.');
	return row;
}

export async function partidas(folioKey) {
	const key = String(folioKey);
	if (isOnline() && !key.startsWith('local-')) {
		try {
			const items = await req('GET', `/api/cotizaciones/${key}/partidas`);
			await db.partidas.where('folioKey').equals(key).delete();
			for (const p of items) {
				await db.partidas.add({ ...p, folioKey: key, synced: true });
			}
		} catch (e) {
			if (!isNetworkError(e)) throw e;
		}
	}
	const cached = await db.partidas.where('folioKey').equals(key).toArray();
	cached.sort((a, b) => (a.partida || 0) - (b.partida || 0));
	return cached;
}

// ---- Escrituras ----

export async function crear({ id_cliente, contacto, descripcion }) {
	if (!id_cliente || !contacto.trim() || !descripcion.trim()) {
		throw new Error('Cliente, contacto y descripción son obligatorios.');
	}
	const payload = {
		id_cliente: id_cliente.trim().toUpperCase(),
		contacto: contacto.trim(),
		descripcion: descripcion.trim()
	};
	if (isOnline()) {
		try {
			const r = await req('POST', '/api/cotizaciones', payload);
			await db.cotizaciones.put({
				idLocal: srvKey(r.folio), folio: r.folio, ...payload,
				autor: localStorage.getItem('admon_user') ? JSON.parse(localStorage.getItem('admon_user')).nombre || '' : '',
				estatus: 'PENDIENTE', color: 0, synced: true, ts: Date.now()
			});
			return { folio: r.folio, folioKey: r.folio, pendiente: false };
		} catch (e) {
			if (!isNetworkError(e)) throw e;
		}
	}
	const idLocal = uuid();
	await db.cotizaciones.put({
		idLocal, folio: null, ...payload,
		autor: '', estatus: 'PENDIENTE', color: 0, synced: false, ts: Date.now()
	});
	await queueOp('cotizacion', 'create', idLocal, payload);
	return { folio: null, folioKey: idLocal, pendiente: true };
}

export async function actualizar(folioKey, patch) {
	const key = String(folioKey);
	const row = key.startsWith('local-')
		? await db.cotizaciones.get(key)
		: await db.cotizaciones.where('folio').equals(parseInt(key, 10)).first();
	if (!row) throw new Error('Cotización no encontrada.');
	const body = {
		id_cliente: patch.id_cliente, contacto: patch.contacto,
		descripcion: patch.descripcion, color: patch.color ?? row.color ?? 0
	};
	if (isOnline() && row.folio != null) {
		try {
			await req('PUT', `/api/cotizaciones/${row.folio}`, body);
			await db.cotizaciones.update(row.idLocal, { ...body, synced: true, ts: Date.now() });
			return { pendiente: false };
		} catch (e) {
			if (!isNetworkError(e)) throw e;
		}
	}
	await db.cotizaciones.update(row.idLocal, { ...body, synced: false, ts: Date.now() });
	await queueOp('cotizacion', 'update', row.idLocal, { folio: row.folio ?? null, id_local: row.idLocal, ...body });
	return { pendiente: true };
}

export async function guardarNota(folioKey, nota) {
	const key = String(folioKey);
	const row = key.startsWith('local-')
		? await db.cotizaciones.get(key)
		: await db.cotizaciones.where('folio').equals(parseInt(key, 10)).first();
	if (!row) throw new Error('Cotización no encontrada.');
	if (isOnline() && row.folio != null) {
		try {
			await req('PUT', `/api/cotizaciones/${row.folio}/nota`, { nota });
			await db.cotizaciones.update(row.idLocal, { nota, synced: true, ts: Date.now() });
			return { pendiente: false };
		} catch (e) {
			if (!isNetworkError(e)) throw e;
		}
	}
	await db.cotizaciones.update(row.idLocal, { nota, synced: false, ts: Date.now() });
	await queueOp('cotizacion', 'nota', row.idLocal, { folio: row.folio ?? null, id_local: row.idLocal, nota });
	return { pendiente: true };
}

export async function borrar(folio) {
	// Borrado destructivo: solo online (igual que el HUB, irreversible).
	const res = await req('DELETE', `/api/cotizaciones/${parseInt(folio, 10)}`);
	await db.cotizaciones.where('folio').equals(parseInt(folio, 10)).delete();
	await db.partidas.where('folioKey').equals(String(folio)).delete();
	return res;
}

export async function clonar(folio) {
	const src = await header(folio);
	const items = await partidas(folioKeyOf(src));
	if (isOnline()) {
		try {
			const r = await req('POST', `/api/cotizaciones/${src.folio}/clonar`);
			return { folio: r.folio, folioKey: r.folio, pendiente: false };
		} catch (e) {
			if (!isNetworkError(e)) throw e;
		}
	}
	// Clon offline: crea pendiente + encola sus partidas (el servidor mapea en el lote)
	const idLocal = uuid();
	await db.cotizaciones.put({
		idLocal, folio: null, id_cliente: src.id_cliente, contacto: src.contacto,
		descripcion: src.descripcion, autor: '', estatus: 'PENDIENTE', color: 0,
		nota: src.nota || '', synced: false, ts: Date.now()
	});
	await queueOp('cotizacion', 'create', idLocal, {
		id_cliente: src.id_cliente, contacto: src.contacto, descripcion: src.descripcion
	});
	for (const p of items) {
		await db.partidas.add({
			folioKey: idLocal, partida: p.partida, cantidad: p.cantidad,
			descripcion: p.descripcion, precio_compra: p.precio_compra, factor: p.factor,
			proveedor: p.proveedor, tiempo_entrega: p.tiempo_entrega, dolar: p.dolar,
			flete: p.flete, synced: false
		});
		await queueOp('partida', 'add', idLocal, {
			id_local: idLocal, cantidad: p.cantidad, descripcion: p.descripcion,
			precio_compra: p.precio_compra, factor: p.factor, proveedor: p.proveedor,
			tiempo_entrega: p.tiempo_entrega, dolar: p.dolar, flete: p.flete
		});
	}
	return { folio: null, folioKey: idLocal, pendiente: true };
}

async function parentRow(folioKey) {
	const key = String(folioKey);
	return key.startsWith('local-')
		? await db.cotizaciones.get(key)
		: await db.cotizaciones.where('folio').equals(parseInt(key, 10)).first();
}

export async function partidaAdd(folioKey, item) {
	if (!item.descripcion.trim() || parseInt(item.cantidad, 10) < 1) {
		throw new Error('Descripción y cantidad (≥1) obligatorias.');
	}
	const row = await parentRow(folioKey);
	if (!row) throw new Error('Cotización no encontrada.');
	const payload = {
		cantidad: parseInt(item.cantidad, 10),
		descripcion: item.descripcion.trim(),
		precio_compra: parseFloat(item.precio_compra) || 0,
		factor: parseFloat(item.factor) || 0,
		proveedor: (item.proveedor || '').trim(),
		tiempo_entrega: parseInt(item.tiempo_entrega, 10) || 0,
		dolar: parseFloat(item.dolar) || 0,
		flete: parseFloat(item.flete) || 0,
		// Códigos SAT (vacío = el servidor los resuelve solo: índice → reglas → IA)
		sat_prod_serv: (item.sat_prod_serv || '').trim(),
		sat_unidad: (item.sat_unidad || '').trim(),
		// Artículo genérico de compras (distinto del código SAT): "disyuntor"
		articulo_generico: (item.articulo_generico || '').trim()
	};
	if (isOnline() && row.folio != null) {
		try {
			const r = await req('POST', `/api/cotizaciones/${row.folio}/partidas`, payload);
			return { pendiente: false, partida: r.partida };
		} catch (e) {
			if (!isNetworkError(e)) throw e;
		}
	}
	const sibs = await db.partidas.where('folioKey').equals(String(folioKeyOf(row))).toArray();
	const maxNum = sibs.reduce((m, p) => Math.max(m, p.partida || 0), 0);
	await db.partidas.add({ folioKey: folioKeyOf(row), partida: maxNum + 1, ...payload, synced: false });
	await queueOp('partida', 'add', row.idLocal, { folio: row.folio ?? null, id_local: row.idLocal, ...payload });
	return { pendiente: true, partida: maxNum + 1 };
}

export async function partidaUpdate(folioKey, partidaNum, item) {
	if (!item.descripcion.trim() || parseInt(item.cantidad, 10) < 1) {
		throw new Error('Descripción y cantidad (≥1) obligatorias.');
	}
	const row = await parentRow(folioKey);
	if (!row) throw new Error('Cotización no encontrada.');
	const payload = {
		partida: parseInt(partidaNum, 10),
		cantidad: parseInt(item.cantidad, 10),
		descripcion: item.descripcion.trim(),
		precio_compra: parseFloat(item.precio_compra) || 0,
		factor: parseFloat(item.factor) || 0,
		proveedor: (item.proveedor || '').trim(),
		tiempo_entrega: parseInt(item.tiempo_entrega, 10) || 0,
		dolar: parseFloat(item.dolar) || 0,
		flete: parseFloat(item.flete) || 0,
		// Códigos SAT (vacío = el servidor re-resuelve si cambió la descripción)
		sat_prod_serv: (item.sat_prod_serv || '').trim(),
		sat_unidad: (item.sat_unidad || '').trim(),
		// Artículo genérico de compras (distinto del código SAT): "disyuntor"
		articulo_generico: (item.articulo_generico || '').trim()
	};
	const key = folioKeyOf(row);
	if (isOnline() && row.folio != null) {
		try {
			await req('PUT', `/api/cotizaciones/${row.folio}/partidas/${payload.partida}`, payload);
			const ex = await db.partidas.where('folioKey').equals(String(key)).toArray();
			const hit = ex.find((p) => p.partida === payload.partida);
			if (hit) await db.partidas.update(hit.id, { ...payload, synced: true });
			return { pendiente: false };
		} catch (e) {
			if (!isNetworkError(e)) throw e;
		}
	}
	const ex = await db.partidas.where('folioKey').equals(String(key)).toArray();
	const hit = ex.find((p) => p.partida === payload.partida);
	if (hit) await db.partidas.update(hit.id, { ...payload, synced: false });
	await queueOp('partida', 'update', row.idLocal, { folio: row.folio ?? null, id_local: row.idLocal, ...payload });
	return { pendiente: true };
}

export async function partidaDelete(folioKey, partidaNum) {
	const row = await parentRow(folioKey);
	if (!row) throw new Error('Cotización no encontrada.');
	const key = folioKeyOf(row);
	if (isOnline() && row.folio != null) {
		try {
			await req('DELETE', `/api/cotizaciones/${row.folio}/partidas/${partidaNum}`);
			const ex = await db.partidas.where('folioKey').equals(String(key)).toArray();
			const hit = ex.find((p) => p.partida === parseInt(partidaNum, 10));
			if (hit) await db.partidas.delete(hit.id);
			return { pendiente: false };
		} catch (e) {
			if (!isNetworkError(e)) throw e;
		}
	}
	const ex = await db.partidas.where('folioKey').equals(String(key)).toArray();
	const hit = ex.find((p) => p.partida === parseInt(partidaNum, 10));
	if (hit) await db.partidas.delete(hit.id);
	await queueOp('partida', 'delete', row.idLocal, { folio: row.folio ?? null, id_local: row.idLocal, partida: parseInt(partidaNum, 10) });
	return { pendiente: true };
}

// ---- Clientes ----

export async function clientes({ limit = 100, offset = 0, q = '' } = {}) {
	let total = 0;
	if (isOnline()) {
		try {
			const params = new URLSearchParams({ limit, offset, q });
			const res = await req('GET', '/api/clientes?' + params.toString());
			const rows = Array.isArray(res) ? res : (res.items || []);
			total = Array.isArray(res) ? rows.length : (res.total || 0);
			await db.clientes.bulkPut(rows.map((c) => ({ id_cliente: c.id_cliente, nombre: c.nombre, dias_pago: c.dias_pago })));
		} catch (e) {
			if (!isNetworkError(e)) throw e;
		}
	}
	let local = await db.clientes.toArray();
	if (local.length === 0) {
		const cached = await cacheGet('/api/clientes');
		if (Array.isArray(cached)) return cached;
	}
	// Si hay búsqueda, filtrar local
	if (q) {
		const ql = q.toLowerCase();
		local = local.filter((c) => (c.nombre || '').toLowerCase().includes(ql) || (c.id_cliente || '').toLowerCase().includes(ql));
	}
	// Paginar local (offline o fallback)
	const paged = local.slice(offset, offset + limit);
	return { items: paged, total: total || local.length, limit, offset };
}

export async function clienteNombre(idCliente) {
	const idc = (idCliente || '').trim().toUpperCase();
	if (!idc) return null;
	if (isOnline()) {
		try {
			const r = await req('GET', `/api/clientes/${idc}/nombre`);
			return r.nombre;
		} catch (e) {
			if (!isNetworkError(e) && !String(e.message || '').includes('no existe')) throw e;
		}
	}
	const c = await db.clientes.get(idc);
	return c ? c.nombre : null;
}

export async function clienteContactos(idCliente) {
	const idc = (idCliente || '').trim().toUpperCase();
	if (!idc) return [];
	const key = `/api/clientes/${idc}/contactos`;
	if (isOnline()) {
		try {
			const rows = await req('GET', key);
			await cachePut(key, rows);
			return rows;
		} catch {
			// error HTTP o de red: se intenta la caché local debajo
		}
	}
	// Offline (o sin respuesta): últimos contactos cacheados de este cliente.
	return (await cacheGet(key)) || [];
}

// ---- SAT CFDI 4.0 (migración 0037: HUB_SatArticulos / HUB_PartidasSat) ----

export async function satSugerir(descripcion) {
	const r = await req('POST', '/api/sat/sugerir', { descripcion: descripcion || '' });
	return r.sugerencia || null;
}

// ---- Remisiones (port del módulo del HUB; tablas IndiceRemisiones/RemisionPartidas) ----

export async function remisiones(folio) {
	return req('GET', `/api/cotizaciones/${folio}/remisiones`);
}

export async function remisionCrear(folio, partidas) {
	return req('POST', `/api/cotizaciones/${folio}/remisiones`, { partidas });
}

export async function remisionBorrar(id) {
	return req('DELETE', `/api/remisiones/${id}`);
}

export async function remisionAsignar(id, idUsuario) {
	return req('PUT', `/api/remisiones/${id}/asignar`, { id_usuario: idUsuario });
}

export async function remisionUsuarios() {
	return req('GET', '/api/remisiones/usuarios');
}

export async function remisionPdfDownload(id, folioRm) {
	const res = await fetch(`/api/remisiones/${id}/pdf`, { headers: auth.authHeader() });
	if (res.status === 401 || res.status === 403) {
		auth.logout();
		navigate('/login', { replace: true });
		throw new Error('Sesión expirada');
	}
	if (!res.ok) {
		const d = await res.json().catch(() => ({}));
		throw new Error(d.detail || 'No se pudo generar el PDF.');
	}
	const blob = await res.blob();
	const url = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = url;
	a.download = `${folioRm || 'remision'}.pdf`;
	document.body.appendChild(a);
	a.click();
	document.body.removeChild(a);
	setTimeout(() => URL.revokeObjectURL(url), 10000);
}
