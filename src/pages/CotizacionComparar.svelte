<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { listar } from '$lib/cotizacionesApi.js';
	import { mapEstatus, fmtMXN, folioFmt } from '$lib/cotizaciones.js';

	let cotizaciones = $state([]);
	let seleccionadas = $state([]);
	let loading = $state(true);
	let error = $state('');

	async function cargar() {
		loading = true;
		error = '';
		try {
			const r = await listar({ pagina: 1, porPagina: 200 });
			cotizaciones = r.rows;
		} catch (e) {
			error = e.message === 'Sesión expirada' ? e.message : 'No se pudo cargar.';
		} finally {
			loading = false;
		}
	}

	onMount(async () => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
		await cargar();
	});

	function toggleSeleccion(c) {
		const id = c.idLocal;
		if (seleccionadas.includes(id)) {
			seleccionadas = seleccionadas.filter(x => x !== id);
		} else if (seleccionadas.length < 3) {
			seleccionadas = [...seleccionadas, id];
		}
	}

	let seleccionadasData = $derived(
		cotizaciones.filter(c => seleccionadas.includes(c.idLocal))
	);

	function estatusBadge(est) {
		const e = mapEstatus(est);
		if (e.includes('FACTURADA')) return 'badge-success';
		if (e.includes('LISTA')) return 'badge-warning';
		return 'badge-info';
	}
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" on:click={() => navigate('/cotizaciones_materiales')} title="Volver">←</button>
		<h1>⚖️ Comparador de Cotizaciones</h1>
	</div>

	<p style="color: var(--color-text-muted); font-size: 0.85rem; margin-bottom: 1rem;">
		Selecciona hasta 3 cotizaciones para compararlas lado a lado.
	</p>

	{#if loading}
		<div class="empty">Cargando…</div>
	{:else if error}
		<div class="card"><p style="color: var(--color-danger); margin: 0;">{error}</p></div>
	{:else}
		<!-- Selector de cotizaciones -->
		<div class="selector">
			{#each cotizaciones as c (c.idLocal)}
				<button
					class="selector-card"
					class:selected={seleccionadas.includes(c.idLocal)}
					on:click={() => toggleSeleccion(c)}
					disabled={!seleccionadas.includes(c.idLocal) && seleccionadas.length >= 3}
				>
					<span class="folio">{c.folio != null ? folioFmt(c.folio) : 'Sin folio'}</span>
					<span class="cliente">{c.cliente || c.id_cliente}</span>
					<span class="total">{fmtMXN(c.total)}</span>
				</button>
			{/each}
		</div>

		<!-- Comparación -->
		{#if seleccionadasData.length >= 2}
			<div class="comparacion">
				<h2>Comparación</h2>
				<div class="comp-grid" style="grid-template-columns: repeat({seleccionadasData.length}, 1fr);">
					<!-- Header -->
					<div class="comp-row header-row">
						{#each seleccionadasData as c}
							<div class="comp-cell header-cell">
								<span class="folio">{c.folio != null ? folioFmt(c.folio) : 'Sin folio'}</span>
							</div>
						{/each}
					</div>

					<!-- Cliente -->
					<div class="comp-row">
						<div class="comp-label">Cliente</div>
						{#each seleccionadasData as c}
							<div class="comp-cell">{c.cliente || c.id_cliente}</div>
						{/each}
					</div>

					<!-- Contacto -->
					<div class="comp-row">
						<div class="comp-label">Contacto</div>
						{#each seleccionadasData as c}
							<div class="comp-cell">{c.contacto || '—'}</div>
						{/each}
					</div>

					<!-- Estatus -->
					<div class="comp-row">
						<div class="comp-label">Estatus</div>
						{#each seleccionadasData as c}
							<div class="comp-cell">
								<span class="badge {estatusBadge(c.estatus)}" style="font-size: 0.65rem;">{mapEstatus(c.estatus)}</span>
							</div>
						{/each}
					</div>

					<!-- Fecha -->
					<div class="comp-row">
						<div class="comp-label">Fecha</div>
						{#each seleccionadasData as c}
							<div class="comp-cell">{c.fecha || '—'}</div>
						{/each}
					</div>

					<!-- Descripción -->
					<div class="comp-row">
						<div class="comp-label">Descripción</div>
						{#each seleccionadasData as c}
							<div class="comp-cell desc">{c.descripcion || '—'}</div>
						{/each}
					</div>

					<!-- Autor -->
					<div class="comp-row">
						<div class="comp-label">Autor</div>
						{#each seleccionadasData as c}
							<div class="comp-cell">{c.autor || '—'}</div>
						{/each}
					</div>

					<!-- Total -->
					<div class="comp-row total-row">
						<div class="comp-label">Total</div>
						{#each seleccionadasData as c}
							<div class="comp-cell total">{fmtMXN(c.total)}</div>
						{/each}
					</div>
				</div>
			</div>
		{:else}
			<div class="empty" style="margin-top: 2rem;">
				Selecciona al menos 2 cotizaciones para comparar
			</div>
		{/if}
	{/if}
</div>

<style>
	.page { max-width: 1400px; margin: 0 auto; padding: 1rem; }
	.header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
	.header h1 { font-size: 1.25rem; margin: 0; color: #f1f5f9; }
	.empty { text-align: center; color: #94a3b8; padding: 3rem 1rem; font-size: 0.9rem; }

	.selector {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: 0.5rem;
		margin-bottom: 1.5rem;
		max-height: 300px;
		overflow-y: auto;
	}
	.selector-card {
		text-align: left;
		background: #1e293b;
		border: 1px solid rgba(255, 255, 255, 0.07);
		border-radius: 8px;
		padding: 0.5rem 0.75rem;
		cursor: pointer;
		transition: transform 0.1s, border-color 0.1s;
		color: inherit;
		font: inherit;
	}
	.selector-card:hover { border-color: rgba(255, 107, 0, 0.4); }
	.selector-card.selected { border-color: #FFAE00; background: rgba(255, 107, 0, 0.08); }
	.selector-card:disabled { opacity: 0.4; cursor: not-allowed; }
	.selector-card .folio { font-family: ui-monospace, monospace; font-weight: 800; font-size: 0.85rem; color: #FFAE00; display: block; }
	.selector-card .cliente { font-size: 0.75rem; color: #e2e8f0; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.selector-card .total { font-size: 0.8rem; font-weight: 700; color: var(--color-primary-light, #FFAE00); display: block; margin-top: 0.2rem; }

	.comparacion { margin-top: 1rem; }
	.comparacion h2 { font-size: 1.1rem; margin-bottom: 0.75rem; color: #f1f5f9; }
	.comp-grid { display: grid; gap: 0; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; overflow: hidden; }
	.comp-row { display: contents; }
	.comp-label { background: #0f172a; padding: 0.6rem 0.75rem; font-size: 0.75rem; font-weight: 700; color: #94a3b8; border-bottom: 1px solid rgba(255, 255, 255, 0.05); border-right: 1px solid rgba(255, 255, 255, 0.05); }
	.comp-cell { background: #1e293b; padding: 0.6rem 0.75rem; font-size: 0.8rem; color: #e2e8f0; border-bottom: 1px solid rgba(255, 255, 255, 0.05); border-right: 1px solid rgba(255, 255, 255, 0.05); overflow: hidden; text-overflow: ellipsis; }
	.comp-cell.desc { white-space: normal; }
	.comp-cell.total { font-weight: 800; color: #FFAE00; font-size: 0.95rem; }
	.header-row .header-cell { background: #0f172a; padding: 0.75rem; text-align: center; border-bottom: 2px solid rgba(255, 107, 0, 0.3); }
	.header-row .folio { font-size: 1rem; }
	.total-row .comp-label { background: #0f172a; font-weight: 800; }
	.total-row .comp-cell { background: #0f172a; }
</style>
