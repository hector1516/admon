<script>
	import { onMount } from 'svelte';
	import { api } from '$lib/api.js';
	import { auth } from '$lib/stores/auth.js';
	import { navigate } from '$lib/router.js';
	import ActionsBar from '$lib/components/ActionsBar.svelte';

	let { onSalir = null } = $props();

	let logs = $state([]);
	let cargando = $state(true);
	let error = $state('');
	let filtroUsuario = $state('');
	let filtroModulo = $state('');
	let filtroTipo = $state('');
	let limit = $state(50);

	const TIPOS = ['click', 'navigate', 'insert', 'update', 'delete', 'error', 'login', 'logout', 'view'];

	onMount(async () => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
		const user = JSON.parse(localStorage.getItem('admon_user') || 'null');
		if (!user?.acceso_usuarios) {
			navigate('/dashboard', { replace: true });
			return;
		}
		await cargar();
	});

	async function cargar() {
		cargando = true;
		error = '';
		try {
			let url = `/audit/log?limit=${limit}`;
			if (filtroUsuario) url += `&usuario=${encodeURIComponent(filtroUsuario)}`;
			if (filtroModulo) url += `&modulo=${filtroModulo}`;
			if (filtroTipo) url += `&tipo=${filtroTipo}`;
			const r = await api.get(url);
			logs = r || [];
		} catch (e) {
			error = e.message || 'Error al cargar bitácora.';
			logs = [];
		} finally {
			cargando = false;
		}
	}

	async function limpiar() {
		if (!confirm('¿Limpiar registros de más de 30 días?')) return;
		try {
			const r = await api.delete('/audit/log/clean?dias=30');
			alert(`Se eliminaron ${r.deleted} registros.`);
			await cargar();
		} catch (e) {
			alert(e.message || 'Error');
		}
	}

	function tipoColor(tipo) {
		const colores = {
			click: '#3b82f6',
			navigate: '#8b5cf6',
			insert: '#22c55e',
			update: '#eab308',
			delete: '#ef4444',
			error: '#ef4444',
			login: '#22c55e',
			logout: '#6b7280',
			view: '#6b7280',
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
			<h1 class="brand">Bitácora de Actividad</h1>
		</div>
		<ActionsBar onlogout={onSalir} />
	</div>

	<!-- Filtros -->
	<div class="card" style="margin-bottom: 1rem; padding: 1rem;">
		<div style="display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center;">
			<input type="text" class="input" placeholder="Usuario..." bind:value={filtroUsuario} style="flex: 1; min-width: 120px;" />
			<select class="input" bind:value={filtroModulo} style="min-width: 100px;">
				<option value="">Todos los módulos</option>
				<option value="COT">Cotizaciones</option>
				<option value="CLI">Clientes</option>
				<option value="REP">Reportes</option>
				<option value="USR">Usuarios</option>
				<option value="KIL">Kilómetros</option>
				<option value="TIX">Tickets</option>
				<option value="DAS">Dashboard</option>
				<option value="EST">Estatus</option>
				<option value="PFL">Perfil</option>
				<option value="BUS">Búsqueda</option>
			</select>
			<select class="input" bind:value={filtroTipo} style="min-width: 100px;">
				<option value="">Todos los tipos</option>
				{#each TIPOS as t}
					<option value={t}>{t}</option>
				{/each}
			</select>
			<button class="btn btn-sm btn-primary" onclick={cargar}>Filtrar</button>
			<button class="btn btn-sm btn-secondary" onclick={limpiar}>Limpiar >30d</button>
		</div>
	</div>

	{#if cargando}
		<div class="empty">
			<div class="mb-spinner"></div>
			<p>Cargando bitácora...</p>
		</div>
	{:else if error}
		<div class="alert alert-danger">
			<span>{error}</span>
			<button class="btn btn-sm" onclick={cargar}>Reintentar</button>
		</div>
	{:else if logs.length === 0}
		<div class="empty">
			<p>Sin registros en la bitácora.</p>
		</div>
	{:else}
		<div class="card">
			{#each logs as log (log.id)}
				<div class="log-row">
					<span class="log-fecha">{log.fecha}</span>
					<span class="log-usuario">{log.usuario}</span>
					<span class="log-modulo">{log.modulo || '-'}</span>
					<span class="log-tipo" style="color: {tipoColor(log.tipo)}">{log.tipo}</span>
					<span class="log-accion">{log.accion}</span>
					{#if log.duracion_ms}
						<span class="log-duracion">{log.duracion_ms}ms</span>
					{/if}
				</div>
			{/each}
		</div>
		<div style="text-align: center; margin-top: 0.5rem; font-size: var(--font-size-xs); color: var(--color-text-muted);">
			Mostrando {logs.length} registros
		</div>
	{/if}
</div>

<style>
	.brand-col { display: flex; flex-direction: column; gap: 0; }
	.brand { display: flex; align-items: center; gap: 0.5rem; margin: 0; font-size: var(--font-size-xl); }

	.mb-spinner {
		width: 28px; height: 28px; margin: 0 auto 0.75rem;
		border: 3px solid var(--color-surface-2);
		border-top-color: var(--color-primary);
		border-radius: 50%;
		animation: mb-spin 0.8s linear infinite;
	}
	@keyframes mb-spin { to { transform: rotate(360deg); } }

	.alert { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.85rem 1rem; border-radius: var(--radius-sm); font-size: var(--font-size-sm); margin-bottom: 1rem; }
	.alert-danger { background: rgba(239, 68, 68, 0.15); color: var(--color-danger); }

	.card { background: var(--color-surface-1, var(--color-surface)); border-radius: var(--radius-sm, 8px); padding: 1rem; margin-bottom: 0.75rem; }

	.log-row {
		display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap;
		padding: 0.4rem 0; border-bottom: 1px solid var(--color-border, var(--color-surface-2));
		font-size: var(--font-size-xs);
	}
	.log-fecha { font-family: monospace; font-size: var(--font-size-2xs); color: var(--color-text-muted); min-width: 120px; }
	.log-usuario { font-weight: 600; min-width: 80px; }
	.log-modulo { background: var(--color-surface-2, var(--color-surface-2)); padding: 0.1rem 0.4rem; border-radius: 3px; font-size: var(--font-size-2xs); }
	.log-tipo { font-weight: 600; font-size: var(--font-size-xs); }
	.log-accion { flex: 1; font-size: var(--font-size-xs); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.log-duracion { font-family: monospace; font-size: var(--font-size-2xs); color: var(--color-text-muted); }

	.empty { text-align: center; padding: 2rem; color: var(--color-text-muted); }

	.btn { padding: 0.4rem 0.75rem; border-radius: 6px; border: none; cursor: pointer; font-size: var(--font-size-sm); }
	.btn-primary { background: var(--color-primary, var(--color-info)); color: white; }
	.btn-secondary { background: var(--color-surface-2, var(--color-surface-2)); color: white; }
	.btn-sm { padding: 0.25rem 0.5rem; font-size: var(--font-size-xs); }
	.btn:disabled { opacity: 0.5; cursor: not-allowed; }
	.input { padding: 0.4rem 0.6rem; border-radius: 6px; border: 1px solid var(--color-border, var(--color-surface-2)); background: var(--color-surface-2, var(--color-surface-2)); color: var(--color-text); font-size: var(--font-size-sm); }
</style>