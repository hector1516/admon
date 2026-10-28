<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { online } from '$lib/stores/online.js';
	import Paginacion from '$lib/components/Paginacion.svelte';

	// Lista de reportes como el HUB: buscar, filtrar por técnico, crear nuevo.

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

	// Cambiar el buscador o el filtro de ingeniero reinicia la página: con la
	// lista ya filtrada, si no, se puede quedar viendo una página vacía.
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
		<button class="btn btn-sm btn-secondary" on:click={() => navigate('/dashboard')} title="Volver">⬅️</button>
		<h1>📋 Reportes de Servicio</h1>
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
			<p style="margin: 0; font-size: 0.85rem;">🔴 Lista maestra: requiere conexión.</p>
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
		<div class="list">
			{#each pagActual as r (r.IdReporte)}
				<button class="list-card" on:click={() => ver(r)}>
					<div style="flex: 1;">
						<div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
							<span style="font-weight: 800; color: var(--color-primary-light);">{r.Folio}</span>
							<span style="font-size: 0.7rem; padding: 0.15rem 0.4rem; border-radius: 4px; background: {estatusColor(r.Estatus)}20; color: {estatusColor(r.Estatus)}; font-weight: 700;">{r.Estatus || 'Borrador'}</span>
						</div>
						<div style="font-size: 0.9rem; margin-top: 0.15rem;">{r.Cliente}</div>
						<div style="font-size: 0.75rem; color: var(--color-text-muted);">{r.Fecha} · {r.Tecnico}</div>
					</div>
					<div style="text-align: right; font-size: 0.75rem; color: var(--color-text-muted);">
						{String(r.TiempoTraslado || 0)}h traslado
					</div>
				</button>
			{/each}
			<Paginacion total={filtrados.length} bind:pagina porPagina={POR_PAGINA} etiqueta="reportes" />
		</div>
	{/if}
</div>

<style>
	.msg { padding: 0.6rem 0.75rem; border-radius: 8px; font-size: 0.85rem; margin-bottom: 0.75rem; }
	.msg.err { background: rgba(239,68,68,0.1); color: #EF4444; }
	.msg.ok { background: rgba(34,197,94,0.1); color: #22C55E; }
	.card { margin-bottom: 0.75rem; }
</style>