<!-- BusquedaGlobal.svelte - Búsqueda global estilo Cmd+K -->
<script>
	import { onMount, onDestroy } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';

	let abierto = $state(false);
	let query = $state('');
	let resultados = $state([]);
	let buscando = $state(false);
	let seleccionado = $state(0);
	let inputRef = $state(null);

	// Módulos disponibles para búsqueda
	const modulos = [
		{ id: 'cotizaciones', label: 'Cotizaciones', icon: '📋', path: '/cotizaciones_materiales', perm: 'acceso_cotizaciones' },
		{ id: 'reportes', label: 'Reportes', icon: '🔧', path: '/reportes', perm: 'acceso_reportes' },
		{ id: 'clientes', label: 'Clientes', icon: '🏢', path: '/clientes', perm: 'acceso_cotizaciones' },
		{ id: 'usuarios', label: 'Usuarios', icon: '👥', path: '/usuarios', perm: 'acceso_usuarios' },
	];

	function tienePermiso(perm) {
		if (!perm) return true;
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && u[perm]);
		} catch {
			return false;
		}
	}

	async function buscar(q) {
		if (!q.trim()) {
			resultados = [];
			return;
		}
		buscando = true;
		const qLower = q.trim().toLowerCase();
		const res = [];

		// Búsqueda en clientes (desde Dexie)
		try {
			const { clientes } = await import('$lib/cotizacionesApi.js');
			const cls = await clientes();
			for (const c of cls) {
				if (String(c.id_cliente || '').toLowerCase().includes(qLower) || String(c.nombre || '').toLowerCase().includes(qLower)) {
					res.push({ tipo: 'cliente', icon: '🏢', titulo: c.id_cliente, subtitulo: c.nombre, path: `/clientes` });
				}
			}
		} catch {}

		// Búsqueda en cotizaciones (desde Dexie)
		try {
			const { listar } = await import('$lib/cotizacionesApi.js');
			const r = await listar({ pagina: 1, porPagina: 50, q: q.trim() });
			for (const c of (r.rows || [])) {
				res.push({ tipo: 'cotizacion', icon: '📋', titulo: c.folio_fmt || `CM${String(c.folio).padStart(5, '0')}`, subtitulo: c.cliente || c.id_cliente, path: `/cotizaciones/${c.folio ?? c.idLocal}` });
			}
		} catch {}

		// Búsqueda en módulos
		for (const m of modulos) {
			if (!tienePermiso(m.perm)) continue;
			if (m.label.toLowerCase().includes(qLower)) {
				res.push({ tipo: 'modulo', icon: m.icon, titulo: m.label, subtitulo: 'Ir al módulo', path: m.path });
			}
		}

		resultados = res.slice(0, 20);
		buscando = false;
	}

	function abrir() {
		abierto = true;
		query = '';
		resultados = [];
		seleccionado = 0;
		setTimeout(() => inputRef?.focus(), 50);
	}

	function cerrar() {
		abierto = false;
		query = '';
		resultados = [];
	}

	function seleccionar(r) {
		cerrar();
		navigate(r.path);
	}

	function handleKeydown(e) {
		if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
			e.preventDefault();
			if (abierto) cerrar();
			else abrir();
		}
		if (!abierto) return;
		if (e.key === 'Escape') {
			cerrar();
		} else if (e.key === 'ArrowDown') {
			e.preventDefault();
			seleccionado = Math.min(seleccionado + 1, resultados.length - 1);
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			seleccionado = Math.max(seleccionado - 1, 0);
		} else if (e.key === 'Enter' && resultados.length > 0) {
			e.preventDefault();
			seleccionar(resultados[seleccionado]);
		}
	}

	let debounceTimer;
	$effect(() => {
		const q = query;
		clearTimeout(debounceTimer);
		if (!q.trim()) {
			resultados = [];
			return;
		}
		debounceTimer = setTimeout(() => buscar(q), 300);
	});

	onMount(() => {
		window.addEventListener('keydown', handleKeydown);
	});
	onDestroy(() => {
		window.removeEventListener('keydown', handleKeydown);
	});
</script>

{#if abierto}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="overlay" on:click={cerrar}>
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="modal" on:click|stopPropagation>
			<input
				bind:this={inputRef}
				class="search-input"
				placeholder="🔍 Buscar en todos los módulos…"
				bind:value={query}
			/>
			{#if buscando}
				<div class="loading">Buscando…</div>
			{:else if resultados.length === 0 && query.trim()}
				<div class="empty">Sin resultados para "{query}"</div>
			{:else if resultados.length > 0}
				<div class="resultados">
					{#each resultados as r, i (i)}
						<button
							class="resultado"
							class:selected={i === seleccionado}
							on:click={() => seleccionar(r)}
						>
							<span class="icon">{r.icon}</span>
							<div class="info">
								<div class="titulo">{r.titulo}</div>
								<div class="subtitulo">{r.subtitulo}</div>
							</div>
							<span class="tipo">{r.tipo}</span>
						</button>
					{/each}
				</div>
			{:else}
				<div class="hint">
					Escribe para buscar en cotizaciones, clientes y módulos…
					<br />
					<span class="shortcut">↑↓ navegar · Enter abrir · Esc cerrar</span>
				</div>
			{/if}
		</div>
	</div>
{/if}

<!-- Botón flotante -->
<button class="fab" on:click={abrir} title="Búsqueda global (Ctrl+K)">
	🔍
</button>

<style>
	.overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.6);
		backdrop-filter: blur(4px);
		z-index: 9999;
		display: flex;
		align-items: flex-start;
		justify-content: center;
		padding-top: 15vh;
	}
	.modal {
		width: 90%;
		max-width: 560px;
		background: #1e293b;
		border: 1px solid rgba(255, 255, 255, 0.1);
		border-radius: 16px;
		overflow: hidden;
		box-shadow: 0 24px 48px rgba(0, 0, 0, 0.4);
	}
	.search-input {
		width: 100%;
		padding: 1rem 1.25rem;
		font-size: 1.1rem;
		background: transparent;
		border: none;
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
		color: #f1f5f9;
		outline: none;
	}
	.search-input::placeholder { color: #64748b; }
	.loading, .empty, .hint {
		padding: 2rem 1.25rem;
		text-align: center;
		color: #94a3b8;
		font-size: 0.9rem;
	}
	.shortcut { font-size: 0.75rem; color: #64748b; }
	.resultados { max-height: 400px; overflow-y: auto; }
	.resultado {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		width: 100%;
		padding: 0.75rem 1.25rem;
		background: transparent;
		border: none;
		color: inherit;
		cursor: pointer;
		text-align: left;
		transition: background 0.1s;
	}
	.resultado:hover, .resultado.selected {
		background: rgba(255, 107, 0, 0.1);
	}
	.resultado .icon { font-size: 1.25rem; }
	.resultado .info { flex: 1; min-width: 0; }
	.resultado .titulo { font-weight: 600; color: #f1f5f9; font-size: 0.9rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.resultado .subtitulo { font-size: 0.75rem; color: #94a3b8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.resultado .tipo { font-size: 0.65rem; color: #64748b; text-transform: uppercase; }
	.fab {
		position: fixed;
		bottom: 24px;
		right: 24px;
		width: 48px;
		height: 48px;
		border-radius: 50%;
		background: #FF6B00;
		color: white;
		border: none;
		font-size: 1.25rem;
		cursor: pointer;
		box-shadow: 0 4px 12px rgba(255, 107, 0, 0.4);
		z-index: 9998;
		transition: transform 0.15s;
	}
	.fab:hover { transform: scale(1.1); }
</style>
