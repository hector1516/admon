<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { online } from '$lib/stores/online.js';
	import { listar } from '$lib/cotizacionesApi.js';
	import { mapEstatus, fmtMXN, folioFmt } from '$lib/cotizaciones.js';
	import Paginacion from '$lib/components/Paginacion.svelte';

	let cotizaciones = $state([]);
	let pagina = $state(1);
	let total = $state(0);
	let loading = $state(true);
	let error = $state('');
	let busqueda = $state('');

	function tieneAcceso() {
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && u.acceso_cotizaciones);
		} catch {
			return false;
		}
	}

	function estatusBadge(est) {
		const e = mapEstatus(est);
		if (e.includes('FACTURADA')) return 'badge-success';
		if (e.includes('LISTA')) return 'badge-warning';
		return 'badge-info';
	}

	let filtradas = $derived(
		!busqueda.trim()
			? cotizaciones
			: cotizaciones.filter((c) => {
					const q = busqueda.trim().toLowerCase();
					return [c.folio_fmt || folioFmt(c.folio), c.id_cliente, c.cliente, c.contacto, c.autor, c.descripcion, String(c.total ?? '')]
						.map((v) => String(v || '').toLowerCase())
						.some((v) => v.includes(q));
				})
	);

	const POR_PAGINA = 100;
	const pagActual = $derived(filtradas);

	async function cargar() {
		loading = true;
		error = '';
		try {
			const r = await listar({ pagina, porPagina: POR_PAGINA, q: busqueda.trim() });
			cotizaciones = r.rows;
			total = r.total;
		} catch (e) {
			console.error('Error cargando cotizaciones:', e);
			error = e.message === 'Sesión expirada' ? e.message : 'No se pudo cargar. Revisa tu conexión.';
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		pagina;
		if (cargar) cargar();
	});

	let temporizador;
	$effect(() => {
		const q = busqueda.trim();
		clearTimeout(temporizador);
		if (!q) return;
		temporizador = setTimeout(() => {
			pagina = 1;
			cargar();
		}, 450);
	});

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
		<button class="btn btn-sm btn-secondary" on:click={() => navigate('/dashboard')} title="Volver">←</button>
		<h1>📋 Cotizaciones</h1>
		<div style="flex:1"></div>
		<button class="btn btn-sm btn-primary" on:click={() => navigate('/cotizaciones/nueva')} title="Nueva cotización">➕</button>
	</div>

	<div class="field">
		<input
			class="input"
			placeholder="🔍 folio, cliente, contacto, autor, descripción o monto"
			bind:value={busqueda}
		/>
	</div>

	{#if !$online}
		<div class="card" style="margin-bottom: 0.75rem; border-color: rgba(239,68,68,0.4);">
			<p style="margin: 0; font-size: 0.85rem;">📡 Sin conexión — mostrando datos guardados.</p>
		</div>
	{/if}

	<p style="color: var(--color-text-muted); font-size: 0.8rem;">
		{#if busqueda.trim()}
			{filtradas.length} resultado{filtradas.length === 1 ? '' : 's'} para "{busqueda.trim()}"
		{:else}
			Mostrando {cotizaciones.length} de <b>{total || cotizaciones.length}</b> cotizaciones
		{/if}
	</p>

	{#if loading}
		<div class="empty">Cargando…</div>
	{:else if error}
		<div class="card"><p style="color: var(--color-danger); margin: 0;">{error}</p></div>
	{:else if filtradas.length === 0}
		<div class="empty">No hay cotizaciones registradas.</div>
	{:else}
		<div class="grid">
			{#each pagActual as c (c.idLocal)}
				<button
					class="card-cotizacion"
					on:click={() => navigate(`/cotizaciones/${c.folio ?? c.idLocal}`)}
					title="Ver detalle"
				>
					<div class="body">
						<div class="folio-row">
							<span class="folio">{c.folio != null ? folioFmt(c.folio) : '⚠ Sin folio'}</span>
							<span class="badge {estatusBadge(c.estatus)}" style="font-size: 0.6rem;">{mapEstatus(c.estatus)}</span>
							{#if c.folio == null || !c.synced}
								<span class="badge badge-warning" style="font-size: 0.6rem;">⏳ pendiente</span>
							{/if}
						</div>
						<div class="cliente">{c.cliente || c.id_cliente || 'N/A'}</div>
						<div class="meta">{c.contacto || '—'} · {c.fecha || ''}</div>
						{#if c.descripcion}
							<div class="desc">{c.descripcion}</div>
						{/if}
						<div class="total">{fmtMXN(c.total)}</div>
						{#if c.autor}
							<div class="autor">por {c.autor}</div>
						{/if}
					</div>
				</button>
			{/each}
		</div>
		<Paginacion total={busqueda.trim() ? filtradas.length : total} bind:pagina
			porPagina={POR_PAGINA} etiqueta="cotizaciones" />
	{/if}
</div>

<style>
	.page { max-width: 1400px; margin: 0 auto; padding: 1rem; }
	.header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
	.header h1 { font-size: 1.25rem; margin: 0; color: #f1f5f9; }
	.field { margin-bottom: 0.75rem; }
	.empty { text-align: center; color: #94a3b8; padding: 3rem 1rem; font-size: 0.9rem; }

	.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 0.75rem; }

	.card-cotizacion {
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
	.card-cotizacion:hover {
		transform: translateY(-3px);
		border-color: rgba(255, 107, 0, 0.5);
	}

	.body { padding: 0.65rem 0.75rem 0.75rem; }
	.folio-row { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 0.35rem; }
	.folio { font-family: ui-monospace, 'Cascadia Mono', monospace; font-weight: 800; font-size: 0.95rem; color: #FFAE00; letter-spacing: 0.5px; }
	.cliente { font-size: 0.85rem; font-weight: 600; color: #e2e8f0; margin-bottom: 0.2rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.meta { font-size: 0.7rem; color: #94a3b8; margin-bottom: 0.3rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.desc { font-size: 0.72rem; color: #cbd5e1; margin-bottom: 0.35rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.total { font-size: 1.1rem; font-weight: 800; color: var(--color-primary-light, #FFAE00); margin-top: 0.25rem; }
	.autor { font-size: 0.65rem; color: #64748b; margin-top: 0.15rem; }
</style>
