<script>
	import { onMount } from 'svelte';
	import { api } from '$lib/api.js';
	import { auth } from '$lib/stores/auth.js';
	import { navigate } from '$lib/router.js';
	import ActionsBar from '$lib/components/ActionsBar.svelte';

	let { onSalir = null } = $props();

	let termino = $state('');
	let resultados = $state([]);
	let total = $state(0);
	let cargando = $state(false);
	let error = $state('');
	let buscado = $state(false);

	onMount(() => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
		}
	});

	async function buscar() {
		if (!termino.trim()) {
			alert('Escribe un término de búsqueda');
			return;
		}
		cargando = true;
		error = '';
		buscado = true;
		try {
			const r = await api.get(`/busqueda-global?q=${encodeURIComponent(termino.trim())}`);
			resultados = r.resultados || [];
			total = r.total || 0;
		} catch (e) {
			error = e.message || 'Error en la búsqueda.';
			resultados = [];
			total = 0;
		} finally {
			cargando = false;
		}
	}

	function irAResultado(r) {
		if (r.url) navigate(r.url);
	}

	function tipoIcono(tipo) {
		const iconos = {
			cotizacion: 'COT',
			cliente: 'CLI',
			reporte: 'REP',
			ticket: 'TKT',
			usuario: 'USR',
		};
		return iconos[tipo] || 'DOC';
	}

	function tipoColor(tipo) {
		const colores = {
			cotizacion: '#3b82f6',
			cliente: '#10b981',
			reporte: '#f59e0b',
			ticket: '#ef4444',
			usuario: '#8b5cf6',
		};
		return colores[tipo] || '#6b7280';
	}
</script>

<div class="page">
	<div class="header">
		<div class="brand-col" style="display: flex; align-items: center; gap: 0.5rem;">
			<button class="btn btn-sm btn-secondary" onclick={() => navigate('/dashboard')} title="Volver">
				Volver
			</button>
			<h1 class="brand">Búsqueda Global</h1>
		</div>
		<ActionsBar onlogout={onSalir} />
	</div>

	<div class="card" style="margin-bottom: 1rem; padding: 1rem;">
		<div style="display: flex; gap: 0.5rem; align-items: center;">
			<input
				type="text"
				class="input"
				placeholder="Buscar en todos los módulos..."
				bind:value={termino}
				onkeydown={(e) => e.key === 'Enter' && buscar()}
				style="flex: 1;"
			/>
			<button class="btn btn-primary" onclick={buscar} disabled={cargando}>
				{cargando ? 'Buscando...' : 'Buscar'}
			</button>
		</div>
		{#if buscado}
			<div style="margin-top: 0.5rem; font-size: 0.85rem; color: var(--color-text-muted);">
				{total} resultado{total !== 1 ? 's' : ''} encontrado{total !== 1 ? 's' : ''}
			</div>
		{/if}
	</div>

	{#if error}
		<div class="alert alert-danger">
			<span>{error}</span>
		</div>
	{/if}

	{#if cargando}
		<div class="empty">
			<div class="mb-spinner"></div>
			<p>Buscando...</p>
		</div>
	{:else if buscado && resultados.length === 0}
		<div class="empty">
			<p>No se encontraron resultados para "{termino}"</p>
		</div>
	{:else if resultados.length > 0}
		<div class="card">
			{#each resultados as r (r.url + r.titulo)}
				<button class="resultado-row" onclick={() => irAResultado(r)}>
					<div class="resultado-tipo" style="background: {tipoColor(r.tipo)}">
						{tipoIcono(r.tipo)}
					</div>
					<div class="resultado-info">
						<div class="resultado-titulo">{r.titulo}</div>
						{#if r.descripcion}
							<div class="resultado-desc">{r.descripcion}</div>
						{/if}
						{#if r.fecha}
							<div class="resultado-fecha">{r.fecha}</div>
						{/if}
					</div>
				</button>
			{/each}
		</div>
	{/if}
</div>

<style>
	.brand-col { display: flex; flex-direction: column; gap: 0; }
	.brand { display: flex; align-items: center; gap: 0.5rem; margin: 0; font-size: 1.2rem; }

	.mb-spinner {
		width: 28px; height: 28px; margin: 0 auto 0.75rem;
		border: 3px solid var(--color-surface-2);
		border-top-color: var(--color-primary);
		border-radius: 50%;
		animation: mb-spin 0.8s linear infinite;
	}
	@keyframes mb-spin { to { transform: rotate(360deg); } }

	.alert { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.85rem 1rem; border-radius: var(--radius-sm); font-size: 0.85rem; margin-bottom: 1rem; }
	.alert-danger { background: rgba(239, 68, 68, 0.15); color: var(--color-danger); }

	.resultado-row {
		display: flex; gap: 0.75rem; align-items: center;
		padding: 0.6rem 0; border-bottom: 1px solid var(--color-border, #334155);
		width: 100%; text-align: left; background: none; cursor: pointer;
	}
	.resultado-row:hover { background: var(--color-surface-2, #334155); }
	.resultado-tipo {
		width: 36px; height: 36px; border-radius: 8px;
		display: flex; align-items: center; justify-content: center;
		font-size: 0.7rem; font-weight: 700; color: white; flex-shrink: 0;
	}
	.resultado-info { flex: 1; min-width: 0; }
	.resultado-titulo { font-weight: 600; font-size: 0.9rem; }
	.resultado-desc { font-size: 0.8rem; color: var(--color-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.resultado-fecha { font-size: 0.7rem; color: var(--color-text-muted); margin-top: 0.15rem; }

	.empty { text-align: center; padding: 2rem; color: var(--color-text-muted); }

	.btn { padding: 0.4rem 0.75rem; border-radius: 6px; border: none; cursor: pointer; font-size: 0.85rem; }
	.btn-primary { background: var(--color-primary, #3b82f6); color: white; }
	.btn-secondary { background: var(--color-surface-2, #334155); color: white; }
	.btn-sm { padding: 0.25rem 0.5rem; font-size: 0.8rem; }
	.btn:disabled { opacity: 0.5; cursor: not-allowed; }
	.input { width: 100%; padding: 0.5rem 0.75rem; border-radius: 6px; border: 1px solid var(--color-border, #334155); background: var(--color-surface-2, #334155); color: var(--color-text); font-size: 0.9rem; box-sizing: border-box; }
	.card { background: var(--color-surface-1, #1e293b); border-radius: var(--radius-sm, 8px); padding: 1rem; margin-bottom: 0.75rem; }
	.field { margin-bottom: 0.75rem; }
	.field label { display: block; font-size: 0.85rem; color: var(--color-text-muted); margin-bottom: 0.35rem; }
</style>