<script>
	import { Save , ArrowLeft } from 'lucide-svelte';

	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { header, actualizar, clienteNombre, clienteContactos } from '$lib/cotizacionesApi.js';
	import { COLOR_LABEL, folioFmt } from '$lib/cotizaciones.js';

	let { clave } = $props();

	let idCliente = $state('');
	let nombreCliente = $state(null);
	let buscando = $state(false);
	let contactos = $state([]);
	let contactoSel = $state('');
	let contactoNuevo = $state('');
	let modoContacto = $state('existe');
	let descripcion = $state('');
	let color = $state(0);
	let error = $state('');
	let msg = $state('');
	let busy = $state(false);
	let loading = $state(true);
	let folio = $state(null);
	let timer = null;

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
			folio = h.folio ?? h.idLocal;
			if ((h.color ?? 0) === 1 || (h.color ?? 0) === 2) {
				error = '🔒 Cotización bloqueada (lista para facturar / facturada). Solo se puede cambiar el estatus.';
			}
			idCliente = h.id_cliente || '';
			contactoSel = h.contacto || '';
			descripcion = h.descripcion || '';
			color = h.color ?? 0;
			await lookup(false);
			if (contactoSel && !contactos.includes(contactoSel)) contactos = [contactoSel, ...contactos];
		} catch (e) {
			error = e.message === 'Sesión expirada' ? e.message : `No se pudo cargar (${e.message || 'sin conexión'}).`;
		} finally {
			loading = false;
		}
	});

	async function lookup(resetContact = true) {
		const idc = idCliente.trim().toUpperCase();
		nombreCliente = null;
		if (resetContact) contactos = [];
		if (!idc) return;
		buscando = true;
		try {
			nombreCliente = await clienteNombre(idc);
			if (nombreCliente) {
				const hist = await clienteContactos(idc);
				contactos = resetContact ? hist : [...new Set([...(contactos || []), ...hist])];
			}
			modoContacto = 'existe';
		} finally {
			buscando = false;
		}
	}

	function onIdInput() {
		idCliente = idCliente.toUpperCase().slice(0, 4);
		clearTimeout(timer);
		timer = setTimeout(() => lookup(true), 500);
	}

	let contactoFinal = $derived(
		modoContacto === 'nuevo' || contactoSel === 'nuevo' ? contactoNuevo.trim() : contactoSel
	);

	let listo = $derived(idCliente.trim() && nombreCliente && contactoFinal && descripcion.trim() && !busy);

	async function onGuardar() {
		error = '';
		msg = '';
		busy = true;
		try {
			const r = await actualizar(clave, {
				id_cliente: idCliente,
				contacto: contactoFinal,
				descripcion: descripcion.trim(),
				color: parseInt(color, 10)
			});
			msg = r.pendiente ? '⏳ Cambios guardados offline. Se sincronizarán.' : '✅ Cotización actualizada.';
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
		<h1>✏️ Modificar {folio != null ? folioFmt(folio) : ''}</h1>
	</div>

	{#if loading}
		<div class="empty">Cargando…</div>
	{:else}
		<div class="card">
			<div class="field">
				<label for="ed-id">ID de cliente (máximo 4 letras):</label>
				<input id="ed-id" class="input" maxlength="4" bind:value={idCliente} on:input={onIdInput} />
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
						<label for="ed-contacto">Contacto:</label>
						<select
							id="ed-contacto"
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
						<label for="ed-contacto-nuevo">Nombre del contacto:</label>
						<input id="ed-contacto-nuevo" class="input" bind:value={contactoNuevo} />
					</div>
				{/if}
			{/if}

			<div class="field">
				<label for="ed-desc">Descripción breve:</label>
				<textarea id="ed-desc" class="input" rows="3" bind:value={descripcion}></textarea>
			</div>

			<div class="field">
				<label for="ed-color">Estatus:</label>
				<select id="ed-color" class="input" bind:value={color}>
					<option value={0}>{COLOR_LABEL[0]}</option>
					<option value={1}>{COLOR_LABEL[1]}</option>
					<option value={2}>{COLOR_LABEL[2]}</option>
				</select>
			</div>

			{#if error}
				<div class="msg err">{error}</div>
			{/if}
			{#if msg}
				<div class="msg ok">{msg}</div>
			{/if}

			<button class="btn btn-primary btn-block" on:click={onGuardar} disabled={!listo}>
				{busy ? 'Guardando…' : '<Save size={16} /> Guardar cambios'}
			</button>
		</div>
	{/if}
</div>

<style>
	.msg { padding: 0.6rem 0.75rem; border-radius: 8px; font-size: 0.85rem; margin-bottom: 0.75rem; }
	.msg.err { background: rgba(239,68,68,0.1); color: #EF4444; }
	.msg.ok { background: rgba(34,197,94,0.1); color: #22C55E; }
	.hint { font-size: 0.8rem; color: var(--color-text-muted); }
	.card { margin-bottom: 0.75rem; }
	select.input { appearance: auto; }
</style>
