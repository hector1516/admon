<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { online } from '$lib/stores/online.js';
	import Paginacion from '$lib/components/Paginacion.svelte';

	// Lista de reportes como el HUB: buscar, filtrar por tǸcnico, crear nuevo.

	let lista = $state([]);
	let pagina = $state(1);
	let loading = $state(true);
	let error = $state('');
	let msg = $state('');
	let busqueda = $state('');
	let filtroTecnico = $state('');
	let busy = $state(false);

	function tieneAcceso() {
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && (u.acceso_reportes || u.acceso_registro_reportes));
		} catch {
			return false;
		}
	}

	function apiHeaders() {
		return { 'Content-Type': 'application/json', ...auth.authHeader() };
	}

	let filtrados = $derived(
		lista.filter((r) => {
			const q = busqueda.trim().toLowerCase();
			const t = filtroTecnico.trim().toLowerCase();
			const matchB = !q || String(r.Folio || '').toLowerCase().includes(q) || String(r.Cliente || '').toLowerCase().includes(q) || String(r.Contacto || '').toLowerCase().includes(q);
			const matchT = !t || String(r.Tecnico || '').toLowerCase().includes(t);
			return matchB && matchT;
		})
	);

	const POR_PAGINA = 100;
	const pagActual = $derived(filtrados.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA));

	$effect(() => {
		busqueda;
		filtroTecnico;
		pagina = 1;
	});

	async function cargar() {
		loading = true;
		error = '';
		try {
			const params = new URLSearchParams();
			if (filtroTecnico) params.set('tecnico', filtroTecnico);
			const res = await fetch(`/api/reportes?${params}`, { headers: auth.authHeader() });
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al cargar.');
			lista = data || [];
		} catch (e) {
			error = e.message === 'Sesión expirada' ? e.message : 'No se pudo cargar. Revisa tu conexión.';
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

	function nuevo() {
		navigate('/reporte_nuevo');
	}

	function ver(r) {
		navigate(`/reporte_detalle/${r.IdReporte}`);
	}

	function estatusColor(est) {
		const e = String(est || '').toUpperCase();
		if (e === 'FIRMADO') return '#22C55E';
		if (e === 'EN CURSO') return '#F59E0B';
		if (e === 'BORRADOR') return '#64748B';
		if (e === 'CANCELADO') return '#EF4444';
		return '#3B82F6';
	}
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" on:click={() => navigate('/dashboard')} title="Volver">←</button>
		<h1>🔧 Reportes de Servicio</h1>
		<div style="flex:1"></div>
		<button class="btn btn-primary btn-sm" on:click={nuevo} title="Nuevo reporte">➕ Nuevo</button>
	</div>

	<div class="card" style="margin-bottom: 0.75rem;">
		<div class="grid-2" style="gap: 0.5rem;">
			<input class="input" placeholder="🔍 Buscar folio, cliente, contacto…" bind:value={busqueda} />
			<input class="input" placeholder="👤 Filtrar por ingeniero…" bind:value={filtroTecnico} on:input={() => cargar()} />
		</div>
	</div>

	{#if !$online}
		<div class="card" style="margin-bottom: 0.75rem; border-color: rgba(239,68,68,0.4);">
			<p style="margin: 0; font-size: 0.85rem;">📡 Lista maestra: requiere conexión.</p>
		</div>
	{/if}

	{#if error}
		<div class="msg err">{error}</div>
	{/if}
	{#if msg}
		<div class="msg ok">{msg}</div>
	{/if}

	<p style="color: var(--color-text-muted); font-size: 0.8rem;">Mostrando {filtrados.length} de {lista.length} reportes.</p>

	{#if loading}
		<div class="empty">Cargando…</div>
	{:else if filtrados.length === 0}
		<div class="empty">No hay reportes registrados.</div>
	{:else}
		<div class="grid">
			{#each pagActual as r (r.IdReporte)}
				<button class="card-reporte" on:click={() => ver(r)} title="Ver detalle">
					<div class="body">
						<div class="folio-row">
							<span class="folio">{r.Folio}</span>
							<span class="badge" style="font-size: 0.6rem; background: {estatusColor(r.Estatus)}20; color: {estatusColor(r.Estatus)}; font-weight: 700; padding: 0.15rem 0.4rem; border-radius: 4px;">{r.Estatus || 'Borrador'}</span>
						</div>
						<div class="cliente">{r.Cliente}</div>
						<div class="meta">{r.Fecha} · {r.Tecnico}</div>
						{#if r.Contacto}
							<div class="contacto">📞 {r.Contacto}</div>
						{/if}
						{#if r.TiempoTraslado}
							<div class="tiempo">⏱️ {r.TiempoTraslado}h traslado</div>
						{/if}
					</div>
				</button>
			{/each}
		</div>
		<Paginacion total={filtrados.length} bind:pagina porPagina={POR_PAGINA} etiqueta="reportes" />
	{/if}
</div>

<style>
	.msg { padding: 0.6rem 0.75rem; border-radius: 8px; font-size: 0.85rem; margin-bottom: 0.75rem; }
	.msg.err { background: rgba(239,68,68,0.1); color: #EF4444; }
	.msg.ok { background: rgba(34,197,94,0.1); color: #22C55E; }
	.card { margin-bottom: 0.75rem; }
	.empty { text-align: center; color: #94a3b8; padding: 3rem 1rem; font-size: 0.9rem; }

	.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 0.75rem; }

	.card-reporte {
		text-align: left;
		background: #1e293b;
		border: 1px solid rgba(255, 255, 255, 0.07);
		border-radius: 12px;
		overflow: hidden;
		padding: 0;
		cursor: pointer;
		transition: transform 0.15s, border-color 0.15s;
		color: inherit;
		font: inherit;
		width: 100%;
	}
	.card-reporte:hover {
		transform: translateY(-3px);
		border-color: rgba(255, 107, 0, 0.5);
	}

	.body { padding: 0.65rem 0.75rem 0.75rem; }
	.folio-row { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 0.35rem; }
	.folio { font-family: ui-monospace, 'Cascadia Mono', monospace; font-weight: 800; font-size: 0.95rem; color: #FFAE00; letter-spacing: 0.5px; }
	.cliente { font-size: 0.85rem; font-weight: 600; color: #e2e8f0; margin-bottom: 0.2rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.meta { font-size: 0.7rem; color: #94a3b8; margin-bottom: 0.3rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.contacto { font-size: 0.72rem; color: #cbd5e1; margin-bottom: 0.2rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.tiempo { font-size: 0.65rem; color: #64748b; margin-top: 0.15rem; }
</style>
