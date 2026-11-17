import { api } from './api.js';

// Prefetch offline de arranque: garantiza al menos los ÚLTIMOS 10 REGISTROS
// de cada módulo (lista + sus detalles) en IndexedDB para navegar sin red.
//
// Cómo funciona:
// - Por módulo se define la llave exacta de su LISTA (mismo path que pide la
//   página, para que el fallback offline la encuentre) y cómo derivar los
//   DETALLES de los primeros 10 ítems.
// - api.get cachea cada respuesta; si no hay red o no hay permiso (403) se
//   continúa con el siguiente módulo — cada quien cachea lo que puede ver.
// - Se dispara: al cargar la app con sesión (App.svelte -> $effect) y al
//   recuperar la conexión (evento 'online'), con throttle de 5 minutos.
// - Las fotos de reportes NO se prefetchan (pesadas, MBs); quedan cacheadas
//   de forma oportunista la primera vez que el usuario abre un detalle.

const LIMIT = 10;

function withTimeout(promise, ms) {
	return Promise.race([
		promise,
		new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), ms)),
	]);
}


const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const MODULES = [
	// 👥 Usuarios: lista + detalle completo (permisos) de los 10 primeros
	{ list: '/users', details: (l) => (l || []).slice(0, LIMIT).map((u) => `/users/${u.id}`) },
	// 📇 Clientes: la lista ya vive en Dexie (cotizacionesApi); aquí los
	// contactos de los 10 primeros, que ClienteDetalle necesita offline.
	// La llave debe ser /contactos/detalle (es la que pide la página: trae
	// contacto + en_catalogo + n_cotizaciones), NO /contactos pelado.
	{ list: '/clientes', details: (l) => (l || []).slice(0, LIMIT).map((c) => `/clientes/${c.id_cliente}/contactos/detalle`) },
	// 📋 Reportes: lista por defecto (misma llave `?` que arma la página,
	// recientes primero) + detalle y técnicos de los 10 primeros.
	// Las FOTOS no se prefetchan (base64, MBs): se cachean solas la primera
	// vez que el usuario abre el detalle (vía api.get), así que un reporte ya
	// visto sí muestra sus fotos sin red.
	{
		list: '/reportes?limit=10',
		details: (l) =>
			(l || []).slice(0, LIMIT).flatMap((r) => [`/reportes/${r.IdReporte}`, `/reportes/${r.IdReporte}/tecnicos`])
	},
	// 🧑‍🔧 Catálogo de usuarios para los selects de reporte
	{ list: '/usuarios' },
	// ⛽ Tickets OxxoGas: la lista YA trae todos los campos del detalle
	// (folio, factura, estación, cliente, vehículo…); solo falta la imagen,
	// que se muestra con fallback si no hay red.
	{ list: '/tickets-oxxogas' },
	// 💰 Saldo Go Vale: valor del último sync del worker del HUB; se precacha
	// para que la tarjeta muestre el último saldo conocido sin red y se
	// refresque al volver la conexión (mismo ciclo que el resto de módulos).
	{ list: '/tickets-oxxogas/saldo' },
	// 🛣️ Kilómetros: consumo semanal (KPIs + tabla por vehículo) y la flota para
	// el selector de captura. La captura (POST) no se cachea: requiere conexión.
	{ list: '/kilometros/consumo' },
	{ list: '/kilometros/vehiculos' },
	{ list: '/kilometros/recientes?n=15' },
	// 🤖 ECCSA IA: conversaciones (máx 10 por usuario) + sus mensajes
	{
		list: '/ia/conversaciones',
		details: (l) => (l || []).slice(0, LIMIT).map((c) => `/ia/conversaciones/${c.Id}/mensajes`)
	},
	// 📝 Notas del equipo (lista del módulo y del panel del Dashboard)
	{ list: '/notas' },
	// ⚙️ Configuración (liviana)
	{ list: '/dispositivo/ip' },
	{ list: '/passkeys/mine' },
	// 🏆 ECCSA Legends: sus endpoints livianos (la página además tiene su
	// propia caché legendsCache; esto garantiza datos aunque nunca se abra)
	{ list: '/legends/score' },
	{ list: '/legends/avatar' },
	{ list: '/legends/ranking' },
	{ list: '/legends/weekly-winner' },
	{ list: '/legends/winners' },
	{ list: '/legends/celebrations' },
	{ list: '/legends/score-log' }
];

let lastRun = 0;
let running = false;

export async function prefetchOffline({ force = false } = {}) {
	// Guardas: una sola corrida a la vez, con sesión, con red y con throttle.
	if (running) return;
	if (!localStorage.getItem('admon_token')) return;
	if (typeof navigator !== 'undefined' && navigator.onLine === false) return;
	if (!force && Date.now() - lastRun < 5 * 60 * 1000) return;
	running = true;
	lastRun = Date.now();
	try {
		for (const mod of MODULES) {
			// Si la sesión expiró en medio del prefetch, detenerse.
			if (!localStorage.getItem('admon_token')) break;
			try {
				// Timeout real (AbortController) para no dejar requests colgados
				// que bloqueen networkidle. Antes el Promise.race solo abandonaba
				// la promesa pero el fetch seguía vivo en el navegador.
				const ac = new AbortController();
				const timer = setTimeout(() => ac.abort(), 5000);
				try {
					const list = await api.get(mod.list, { signal: ac.signal });
					clearTimeout(timer);
					const details = mod.details ? mod.details(list).slice(0, LIMIT * 3) : [];
					for (const p of details) {
						if (!localStorage.getItem('admon_token')) break;
						const ac2 = new AbortController();
						const t2 = setTimeout(() => ac2.abort(), 5000);
						try {
							await api.get(p, { signal: ac2.signal });
						} catch {
							// 403 sin permiso, timeout o detalle inexistente: seguir
						} finally {
							clearTimeout(t2);
						}
						await sleep(60); // no saturar la red ni al backend
					}
				} finally {
					clearTimeout(timer);
				}
			} catch {
				// lista sin permiso (403), timeout u offline: siguiente módulo
			}
			await sleep(120);
		}
	} finally {
		running = false;
	}
}

// Auto-disparo: al cargar (App.svelte también lo llama vía $effect cuando
// hay sesión) y al recuperar la conexión.
if (typeof window !== 'undefined') {
	window.addEventListener('online', () => prefetchOffline({ force: true }));
}
