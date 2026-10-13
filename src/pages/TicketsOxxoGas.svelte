<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { api } from '$lib/api.js';
	import Paginacion from '../components/Paginacion.svelte';

	// Tickets de OxxoGas: lectura de HUB_OxxoGasTickets (captura en Field/HUB)
	// con factura CFDI enlazada y estación. Orden: más reciente arriba.
	// Identificador principal: folio del ticket impreso (FolioTicket).

	let tickets = $state([]);
	let pagina = $state(1);
	let loading = $state(true);
	let error = $state('');
	let busqueda = $state('');

	// Saldo Go Vale (HUB_Config): lo refresca el worker del HUB cada ~5 min.
	// Mismo estilo/umbral que la vista "Vales OxxoGas" del HUB: rojo si < $2,000.
	let saldo = $state(null);       // number | null (null = sin dato/oculto)
	let saldoFecha = $state('');
	let valesRestantes = $state(null);   // number | null (null = sin dato)
	let montoVale = $state(500);   // monto por vale que reporta el API
	const UMBRAL_SALDO = 2000;

	function fmtSaldo(v) {
		return v.toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	}

	function tieneAcceso() {
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && u.acceso_vales_oxxogas);
		} catch {
			return false;
		}
	}

	// Las imágenes solo se muestran en la página de detalle (/tickets_oxxogas/:id).

	function fmtFecha(iso) {
		if (!iso) return '—';
		const d = new Date(iso);
		const p = (n) => String(n).padStart(2, '0');
		return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
	}

	// Búsqueda por folio, cliente, estación, vehículo, capturó, descripción y
	// factura; "pendiente" encuentra tickets sin factura o sin estación.
	let filtrados = $derived.by(() => {
		const q = busqueda.trim().toLowerCase();
		if (!q) return tickets;
		return tickets.filter((t) => {
			const texto = [t.folio, t.cliente, t.estacion, t.marca_modelo, t.placas, t.capturo, t.descripcion, t.factura, t.concepto]
				.filter(Boolean)
				.join(' ')
				.toLowerCase();
			if (texto.includes(q)) return true;
			if (q.includes('pendiente')) return !t.factura || !t.estacion;
			return false;
		});
	});

	const POR_PAGINA = 100;
	const pagActual = $derived(filtrados.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA));

	// Cada búsqueda arranca en la primera página: si no, el usuario puede
	// quedarse en una página vacía con el listado ya filtrado.
	$effect(() => {
		busqueda;
		pagina = 1;
	});

	async function cargar() {
		loading = true;
		error = '';
		try {
			// Saldo y tickets en paralelo: si el saldo falla solo se oculta la card.
			const [lista, s] = await Promise.all([
				api.get('/tickets-oxxogas'),
				api.get('/tickets-oxxogas/saldo').catch(() => null)
			]);
			tickets = lista;
			if (s && typeof s.saldo === 'number') {
				saldo = s.saldo;
				saldoFecha = s.fecha || 'Nunca';
			}
			if (s && typeof s.vales_restantes === 'number') {
				valesRestantes = s.vales_restantes;
				if (typeof s.monto_por_vale === 'number') montoVale = s.monto_por_vale;
			}
		} catch (e) {
			error = e.message === 'Sesión expirada' ? e.message : e.message || 'No se pudo cargar.';
		} finally {
			loading = false;
		}
	}

	onMount(async () => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
		if (!tieneAcceso()) {
			navigate('/dashboard', { replace: true });
			return;
		}
		await cargar();
	});
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" onclick={() => navigate('/dashboard')} title="Volver">⬅️</button>
		<h1>⛽ Tickets de OxxoGas</h1>
		<div style="flex:1"></div>
		<span class="count">{filtrados.length} ticket{filtrados.length === 1 ? '' : 's'}</span>
	</div>

	{#if saldo !== null}
		{@const bajo = saldo < UMBRAL_SALDO}
		{@const sinVales = valesRestantes !== null && valesRestantes < 1}
		<div class="saldo-card" class:bajo>
			<div class="saldo-label">💰 Saldo Go Vale</div>
			<div class="saldo-num" class:rojo={bajo} class:verde={!bajo}>${fmtSaldo(saldo)}</div>
			<div class="saldo-alerta" class:rojo={bajo} class:verde={!bajo}>
				{bajo ? '⚠️ Saldo bajo — recarga pronto' : '✅ Saldo disponible para generar vales'}
			</div>
			{#if valesRestantes !== null}
				<div class="vales-estimado" class:sin-vales={sinVales}>
					<span class="vales-num">
						{sinVales ? '⚠️ No alcanza para 1 vale' : `🎫 ~${valesRestantes} vale${valesRestantes === 1 ? '' : 's'}`}
					</span>
					<span class="vales-nota">aprox. a ${fmtSaldo(montoVale)} c/u</span>
				</div>
			{/if}
			<div class="saldo-meta">
				<span>🔄 Revisado: {saldoFecha}</span>
				<span>Umbral alerta: ${UMBRAL_SALDO.toLocaleString('es-MX')}</span>
			</div>
		</div>
	{/if}

	<div class="field">
		<input class="input" placeholder="🔍 Buscar por folio, cliente, estación, vehículo, factura…" bind:value={busqueda} />
	</div>

	<p class="hint">Tickets capturados desde Field/HUB · orden por fecha y hora de captura (más reciente arriba) · escribe <strong>pendiente</strong> para filtrar los que faltan</p>

	{#if loading}
		<div class="state">⏳ Cargando tickets…</div>
	{:else if error}
		<div class="state err">⚠️ {error}</div>
	{:else if filtrados.length === 0}
		<div class="state">🎫 No hay tickets{busqueda.trim() ? ` que coincidan con “${busqueda.trim()}”` : ''}.</div>
	{:else}
		<div class="grid">
			{#each pagActual as t (t.id)}
				<button class="card-ticket" onclick={() => navigate(`/tickets_oxxogas/${t.id}`)} title="Ver detalle completo">
					<div class="body">
						<div class="folio">#{t.folio}</div>
						<div class="fecha">🧾 Ticket: {fmtFecha(t.fecha)}</div>
						{#if t.fecha_vale}
							<div class="fecha">🎫 Vale: {fmtFecha(t.fecha_vale)}</div>
						{/if}
						<div class="chips">
							{#if t.factura}
								<span class="chip ok" title="Factura enlazada">🧾 {t.factura}</span>
							{:else}
								<span class="chip pend" title="Sin factura">⏳ Factura: Pendiente</span>
							{/if}
							{#if t.estacion}
								<span class="chip ok" title="Estación capturada">⛽ {t.estacion}</span>
							{:else}
								<span class="chip pend" title="Sin estación">⏳ Estación: Pendiente</span>
							{/if}
						</div>
						{#if t.cliente}<div class="row">🏢 {t.cliente}</div>{/if}
						{#if t.marca_modelo || t.placas}
							<div class="row">🚗 {[t.marca_modelo, t.placas].filter(Boolean).join(' · ')}</div>
						{/if}
						{#if t.capturo}<div class="row">👤 Capturó: {t.capturo}</div>{/if}
					</div>
				</button>
			{/each}
		</div>
		<!-- La rejilla es CSS grid; la paginación va debajo para que no ocupe una celda. -->
		<Paginacion total={filtrados.length} bind:pagina porPagina={POR_PAGINA} etiqueta="tickets" />
	{/if}
</div>

<style>
	.page { max-width: 1200px; margin: 0 auto; padding: 1rem; }
	.header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
	.header h1 { font-size: 1.25rem; margin: 0; color: #f1f5f9; }
	.count { font-size: 0.8rem; color: #94a3b8; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 999px; padding: 0.25rem 0.7rem; }
	.hint { font-size: 0.75rem; color: #64748b; margin: 0 0 0.9rem; }
	.hint strong { color: #FFAE00; }
	.state { text-align: center; color: #94a3b8; padding: 3rem 1rem; font-size: 0.9rem; }
	.state.err { color: #f87171; }

	.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 0.9rem; }

	.card-ticket { text-align: left; background: #1e293b; border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 14px; overflow: hidden; padding: 0; cursor: pointer; transition: transform 0.15s, border-color 0.15s; color: inherit; font: inherit; }
	.card-ticket:hover { transform: translateY(-3px); border-color: rgba(255, 107, 0, 0.5); }

	.body { padding: 0.75rem 0.85rem 0.9rem; }
	.folio { font-family: ui-monospace, 'Cascadia Mono', monospace; font-weight: 800; font-size: 1.05rem; color: #FFAE00; letter-spacing: 0.5px; }
	.fecha { font-size: 0.72rem; color: #94a3b8; margin-top: 0.15rem; }
	.chips { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.55rem; }
	.chip { font-size: 0.68rem; font-weight: 700; border-radius: 999px; padding: 0.22rem 0.6rem; border: 1px solid transparent; }
	.chip.ok { color: #4ade80; background: rgba(74, 222, 128, 0.1); border-color: rgba(74, 222, 128, 0.25); }
	.chip.pend { color: #fbbf24; background: rgba(251, 191, 36, 0.1); border-color: rgba(251, 191, 36, 0.3); }
	.row { font-size: 0.75rem; color: #cbd5e1; margin-top: 0.4rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

	/* Saldo Go Vale — mismo look que la vista Vales OxxoGas del HUB.
	   Bloque apilado: etiqueta → monto → alerta → meta (revisado/umbral)
	   al pie de la tarjeta, para que quede cuadrado con el texto principal. */
	.saldo-card { border-radius: 14px; padding: 16px 24px; margin: 0 0 14px; box-shadow: 0 4px 18px rgba(0,0,0,.35); background: linear-gradient(135deg, #052E16 0%, #022C22 100%); border: 2px solid #16A34A; }
	.saldo-card.bajo { background: linear-gradient(135deg, #7F1D1D 0%, #450A0A 100%); border-color: #EF4444; }
	.saldo-label { color: #94a3b8; font-size: .85rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
	.saldo-num { font-size: 2.4rem; font-weight: 800; line-height: 1.15; margin-top: 2px; color: #DCFCE7; }
	.saldo-num.rojo { color: #EF4444; }
	.saldo-num.verde { color: #22C55E; }
	.saldo-alerta { font-size: .95rem; font-weight: 600; margin-top: 2px; color: #FEE2E2; }
	.saldo-alerta.verde { color: #DCFCE7; }
	.saldo-meta { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,.12); color: #94a3b8; font-size: .78rem; }

	/* Estimado de vales = saldo // monto por vale. Va con su propia línea para
	   que se lea rápido ("¿cuántos vales me alcanza?") sin mezclarlo con el
	   saldo, que es el dato real. */
	.vales-estimado { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; flex-wrap: wrap; margin-top: 8px; padding: 8px 10px; border-radius: 10px; background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.12); }
	.vales-num { font-size: 1rem; font-weight: 700; color: #FDE68A; }
	.vales-estimado.sin-vales { background: rgba(239,68,68,.16); border-color: rgba(239,68,68,.5); }
	.vales-estimado.sin-vales .vales-num { color: #FCA5A5; }
	.vales-nota { font-size: .74rem; color: #94a3b8; }
</style>
