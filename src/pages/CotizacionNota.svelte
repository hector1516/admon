<script>
	import { Save , ArrowLeft } from 'lucide-svelte';

	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { header, guardarNota } from '$lib/cotizacionesApi.js';
	import { folioFmt } from '$lib/cotizaciones.js';

	let { clave } = $props();

	let nota = $state('');
	let folio = $state(null);
	let loading = $state(true);
	let error = $state('');
	let msg = $state('');
	let busy = $state(false);

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
			const h = await header(clave);
			nota = h.nota || '';
			folio = h.folio ?? h.idLocal;
		} catch (e) {
			error = e.message === 'Sesión expirada' ? e.message : `No se pudo cargar (${e.message || 'sin conexión'}).`;
		} finally {
			loading = false;
		}
	});

	async function onGuardar() {
		error = '';
		msg = '';
		busy = true;
		try {
			const r = await guardarNota(clave, nota);
			msg = r.pendiente ? '⏳ Nota guardada offline. Se sincronizará.' : '✅ Nota guardada.';
		} catch (e) {
			error = e.message || 'No se pudo guardar.';
		} finally {
			busy = false;
		}
	}
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" on:click={() => navigate(`/cotizaciones/${clave}`)} title="Volver"><ArrowLeft size={16} /></button>
		<h1>📝 Nota interna {folio != null ? folioFmt(folio) : ''}</h1>
	</div>

	{#if loading}
		<div class="empty">Cargando…</div>
	{:else}
		<div class="card">
			<div class="field">
				<label for="nt-text">Nota / comentarios:</label>
				<textarea
					id="nt-text"
					class="input"
					rows="8"
					placeholder="Comentarios, detalles adicionales o notas…"
					bind:value={nota}
				></textarea>
			</div>

			{#if error}
				<div class="msg err">{error}</div>
			{/if}
			{#if msg}
				<div class="msg ok">{msg}</div>
			{/if}

			<button class="btn btn-primary btn-block" on:click={onGuardar} disabled={busy}>
				{busy ? 'Guardando…' : '<Save size={16} /> Guardar nota'}
			</button>
		</div>
	{/if}
</div>

<style>
	.msg { padding: 0.6rem 0.75rem; border-radius: 8px; font-size: 0.85rem; margin-bottom: 0.75rem; }
	.msg.err { background: rgba(239,68,68,0.1); color: #EF4444; }
	.msg.ok { background: rgba(34,197,94,0.1); color: #22C55E; }
	.card { margin-bottom: 0.75rem; }
</style>
