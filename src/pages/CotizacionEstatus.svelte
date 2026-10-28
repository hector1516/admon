<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { header, actualizar } from '$lib/cotizacionesApi.js';
	import { COLOR_LABEL, folioFmt } from '$lib/cotizaciones.js';
	import Paginacion from '$lib/components/Paginacion.svelte';

	// Cambio rápido de estatus (los 3 colores del HUB).

	let { clave } = $props();

	const OPCIONES = [
		{ color: 0, titulo: 'COTIZACIÓN ENVIADA', desc: 'Recién enviada al cliente. Se puede editar.', emoji: '⚪' },
		{ color: 1, titulo: 'LISTA PARA FACTURAR', desc: 'Aceptada. Bloquea edición de datos y partidas.', emoji: '🟡' },
		{ color: 2, titulo: 'FACTURADA', desc: 'Facturada. Bloqueada y solo lectura.', emoji: '🟢' }
	];

	let h = $state(null);
	let sel = $state(0);
	let loading = $state(true);
	let error = $state('');
	let msg = $state('');
	let busy = $state(false);

	// Solo hay 3 estatus, así que la paginación nunca se dibuja; se deja el
	// corte por si mañana la lista crece (mismo patrón que el resto del HUB).
	const POR_PAGINA = 100;
	let pagina = $state(1);
	const pagActual = $derived(OPCIONES.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA));

	function tieneAcceso() {
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && u.acceso_cotizaciones);
		} catch {
			return false;
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
		try {
			h = await header(clave);
			sel = h.color ?? 0;
		} catch (e) {
			error = e.message === 'Sesión expirada' ? e.message : `No se pudo cargar (${e.message || 'sin conexión'}).`;
		} finally {
			loading = false;
		}
	});

	async function onGuardar() {
		if (!h) return;
		error = '';
		msg = '';
		busy = true;
		try {
			const r = await actualizar(h.folio ?? h.idLocal, {
				id_cliente: h.id_cliente,
				contacto: h.contacto,
				descripcion: h.descripcion,
				color: parseInt(sel, 10)
			});
			h = { ...h, color: parseInt(sel, 10) };
			msg = r.pendiente
				? '⏳ Estatus guardado offline. Ojo: el bloqueo aplica al sincronizar.'
				: `✅ Estatus actualizado a ${COLOR_LABEL[sel]}.`;
		} catch (e) {
			error = e.message || 'No se pudo guardar.';
		} finally {
			busy = false;
		}
	}
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" on:click={() => navigate(`/cotizaciones/${clave}`)} title="Volver">⬅️</button>
		<h1>🚦 Estatus {h ? folioFmt(h.folio ?? h.idLocal) : ''}</h1>
	</div>

	{#if loading}
		<div class="empty">Cargando…</div>
	{:else if error && !h}
		<div class="card"><p style="color: var(--color-danger); margin: 0;">{error}</p></div>
	{:else if h}
		<div class="list">
			{#each pagActual as op}
				<button
					class="list-card estatus-opt"
					class:sel={parseInt(sel, 10) === op.color}
					on:click={() => (sel = op.color)}
				>
					<div style="font-size: 1.6rem;">{op.emoji}</div>
					<div style="flex: 1; text-align: left;">
						<div style="font-weight: 800;">{op.titulo}</div>
						<div style="font-size: 0.8rem; color: var(--color-text-muted);">{op.desc}</div>
					</div>
					{#if parseInt(sel, 10) === op.color}
						<span style="color: var(--color-success); font-size: 1.3rem;">✔</span>
					{/if}
				</button>
			{/each}
			<Paginacion total={OPCIONES.length} bind:pagina porPagina={POR_PAGINA} etiqueta="estatus" />
		</div>

		{#if error}
			<div class="msg err" style="margin-top: 0.75rem;">{error}</div>
		{/if}
		{#if msg}
			<div class="msg ok" style="margin-top: 0.75rem;">{msg}</div>
		{/if}

		<button class="btn btn-primary btn-block" style="margin-top: 0.75rem;" on:click={onGuardar} disabled={busy}>
			{busy ? 'Guardando…' : '💾 Guardar estatus'}
		</button>
		<p class="hint" style="margin-top: 0.5rem;">Actual: {COLOR_LABEL[h.color] || h.color}</p>
	{/if}
</div>

<style>
	.estatus-opt.sel { border-color: var(--color-primary); }
	.msg { padding: 0.6rem 0.75rem; border-radius: 8px; font-size: 0.85rem; margin-bottom: 0.75rem; }
	.msg.err { background: rgba(239,68,68,0.1); color: #EF4444; }
	.msg.ok { background: rgba(34,197,94,0.1); color: #22C55E; }
	.hint { font-size: 0.8rem; color: var(--color-text-muted); }
</style>
