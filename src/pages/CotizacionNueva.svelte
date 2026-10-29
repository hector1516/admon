<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { crear, clienteNombre, clienteContactos } from '$lib/cotizacionesApi.js';

	let idCliente = $state('');
	let nombreCliente = $state(null);
	let buscando = $state(false);
	let contactos = $state([]);
	let modoContacto = $state('existe'); // existe | nuevo
	let contactoSel = $state('');
	let contactoNuevo = $state('');
	let descripcion = $state('');
	let error = $state('');
	let msg = $state('');
	let busy = $state(false);
	let timer = null;

	function tieneAcceso() {
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && u.acceso_cotizaciones);
		} catch {
			return false;
		}
	}

	onMount(() => {
		if (!auth.isLoggedIn()) navigate('/login', { replace: true });
		else if (!tieneAcceso()) navigate('/dashboard', { replace: true });
	});

	async function lookup() {
		const idc = idCliente.trim().toUpperCase();
		nombreCliente = null;
		contactos = [];
		if (!idc) return;
		buscando = true;
		try {
			nombreCliente = await clienteNombre(idc);
			if (nombreCliente) contactos = await clienteContactos(idc);
			if (contactos.length === 0) {
				modoContacto = 'nuevo';
			} else {
				modoContacto = 'existe';
			}
			contactoSel = '';
		} catch (e) {
			error = e.message === 'Sesión expirada' ? e.message : '';
		} finally {
			buscando = false;
		}
	}

	function onIdInput() {
		idCliente = idCliente.toUpperCase().slice(0, 4);
		clearTimeout(timer);
		timer = setTimeout(lookup, 500);
	}

	let contactoFinal = $derived(
		(contactos.length === 0 || modoContacto === 'nuevo') ? contactoNuevo.trim() :
		(contactoSel === 'nuevo' ? contactoNuevo.trim() : contactoSel)
	);

	let listo = $derived(
		idCliente.trim() && nombreCliente && (contactoFinal || contactoNuevo.trim()) && descripcion.trim() && !busy
	);

	async function onCrear() {
		error = '';
		msg = '';
		busy = true;
		try {
			const contacto = contactoFinal || contactoNuevo.trim();
		const r = await crear({ id_cliente: idCliente, contacto: contacto, descripcion: descripcion.trim() });
			if (r.pendiente) msg = '⏳ Guardada offline. Se sincronizará al volver la red.';
			navigate(`/cotizaciones/${r.folio ?? r.folioKey}`);
		} catch (e) {
			error = e.message || 'No se pudo crear.';
			busy = false;
		}
	}
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" on:click={() => navigate('/cotizaciones_materiales')} title="Volver">⬅️</button>
		<h1>➕ Nueva cotización</h1>
	</div>

	<div class="card">
		<div class="field">
			<label for="nc-id">ID de cliente (máximo 4 letras):</label>
			<input
				id="nc-id"
				class="input"
				placeholder="Ej: HUSA, JCEC…"
				maxlength="4"
				bind:value={idCliente}
				on:input={onIdInput}
			/>
		</div>

		{#if buscando}
			<p class="hint">Buscando cliente…</p>
		{:else if idCliente.trim() && nombreCliente === null}
			<div class="msg err">❌ El ID de cliente no existe en la base de datos.</div>
		{:else if nombreCliente}
			<div class="msg ok">✅ Cliente: <strong>{nombreCliente}</strong></div>
		{/if}

		{#if nombreCliente}
			{#if contactos.length > 0}
				<div class="field">
					<label for="nc-contacto">Contacto (historial del cliente):</label>
					<select
						id="nc-contacto"
						class="input"
						bind:value={contactoSel}
						on:change={() => (modoContacto = contactoSel === 'nuevo' ? 'nuevo' : 'existe')}
					>
						<option value="">-- Seleccionar contacto --</option>
						{#each contactos as c}
							<option value={c}>{c}</option>
						{/each}
						<option value="nuevo">[+] Registrar nuevo contacto…</option>
					</select>
				</div>
			{/if}
			{#if contactos.length === 0 || modoContacto === 'nuevo'}
				<div class="field">
					<label for="nc-contacto-nuevo">Nombre del contacto:</label>
					<input
						id="nc-contacto-nuevo"
						class="input"
						placeholder="Nombre completo del contacto…"
						bind:value={contactoNuevo}
					/>
				</div>
			{/if}
		{/if}

		<div class="field">
			<label for="nc-desc">Descripción breve:</label>
			<textarea
				id="nc-desc"
				class="input"
				rows="3"
				placeholder="Objeto o descripción general de la cotización…"
				bind:value={descripcion}
			></textarea>
		</div>

		{#if error}
			<div class="msg err">{error}</div>
		{/if}
		{#if msg}
			<div class="msg ok">{msg}</div>
		{/if}

		<button class="btn btn-primary btn-block" on:click={onCrear} disabled={!listo}>
			{busy ? 'Creando…' : '💾 Crear cotización'}
		</button>
	</div>
</div>

<style>
	.msg { padding: 0.6rem 0.75rem; border-radius: 8px; font-size: 0.85rem; margin-bottom: 0.75rem; }
	.msg.err { background: rgba(239,68,68,0.1); color: #EF4444; }
	.msg.ok { background: rgba(34,197,94,0.1); color: #22C55E; }
	.hint { font-size: 0.8rem; color: var(--color-text-muted); }
	.card { margin-bottom: 0.75rem; }
	select.input { appearance: auto; }
</style>
