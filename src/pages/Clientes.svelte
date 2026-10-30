<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { clientes } from '$lib/cotizacionesApi.js';
	import OfflineNotice from '$lib/components/OfflineNotice.svelte';

	let lista = $state([]);
	let loading = $state(true);
	let error = $state('');
	let msg = $state('');
	let busqueda = $state('');
	let busy = $state(false);

	let selId = $state(null);
	let editNombre = $state('');
	let editDias = $state(30);

	let mostrandoNuevo = $state(false);
	let newId = $state('');
	let newNombre = $state('');
	let newDias = $state(30);

	function tieneAcceso() {
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && u.acceso_cotizaciones);
		} catch {
			return false;
		}
	}

	function apiHeaders() {
		return { 'Content-Type': 'application/json', ...auth.authHeader() };
	}

	let filtrados = $derived(
		!busqueda.trim()
			? lista
			: lista.filter((c) => {
					const q = busqueda.trim().toLowerCase();
					return String(c.id_cliente || '').toLowerCase().includes(q) || String(c.nombre || '').toLowerCase().includes(q);
				})
	);

	async function cargar() {
		loading = true;
		error = '';
		try {
			lista = await clientes();
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

	function seleccionar(c) {
		msg = '';
		error = '';
		mostrandoNuevo = false;
		if (selId === c.id_cliente) {
			selId = null;
			return;
		}
		selId = c.id_cliente;
		editNombre = c.nombre || '';
		editDias = c.dias_pago ?? 30;
	}

	async function guardarEdicion() {
		if (!editNombre.trim()) {
			error = 'La razón social no puede estar vacía.';
			return;
		}
		error = '';
		msg = '';
		busy = true;
		try {
			const res = await fetch(`/api/clientes/${selId}`, {
				method: 'PUT',
				headers: apiHeaders(),
				body: JSON.stringify({ nombre: editNombre.trim(), dias_pago: parseInt(editDias, 10) || 0 })
			});
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al actualizar.');
			msg = '✅ Cliente actualizado.';
			selId = null;
			await cargar();
		} catch (e) {
			error = e.message || 'Error al actualizar.';
		} finally {
			busy = false;
		}
	}

	async function eliminar() {
		if (!selId) return;
		if (!confirm(`¿Eliminar al cliente ${selId}? Si tiene cotizaciones asociadas no se podrá.`)) return;
		error = '';
		msg = '';
		busy = true;
		try {
			const res = await fetch(`/api/clientes/${selId}`, { method: 'DELETE', headers: auth.authHeader() });
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al eliminar.');
			msg = '✅ Cliente eliminado.';
			selId = null;
			await cargar();
		} catch (e) {
			error = e.message || 'Error al eliminar.';
		} finally {
			busy = false;
		}
	}

	async function crear() {
		const idc = newId.trim().toUpperCase();
		if (!idc || !newNombre.trim()) {
			error = 'ID y razón social son obligatorios.';
			return;
		}
		error = '';
		msg = '';
		busy = true;
		try {
			const res = await fetch('/api/clientes', {
				method: 'POST',
				headers: apiHeaders(),
				body: JSON.stringify({ id_cliente: idc, nombre: newNombre.trim(), dias_pago: parseInt(newDias, 10) || 0 })
			});
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al registrar.');
			msg = '🎉 ¡Cliente registrado!';
			mostrandoNuevo = false;
			newId = '';
			newNombre = '';
			newDias = 30;
			await cargar();
		} catch (e) {
			error = e.message || 'Error al registrar.';
		} finally {
			busy = false;
		}
	}
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" on:click={() => navigate('/dashboard')} title="Volver">←</button>
		<h1>🏢 Clientes</h1>
		<div style="flex:1"></div>
		<button
			class="btn btn-sm btn-primary"
			on:click={() => {
				mostrandoNuevo = !mostrandoNuevo;
				selId = null;
				error = '';
				msg = '';
			}}
			title="Nuevo cliente"
		>
			➕
		</button>
	</div>

	<div class="field">
		<input class="input" placeholder="🔍 Buscar por ID o razón social…" bind:value={busqueda} />
	</div>

	<OfflineNotice />

	{#if mostrandoNuevo}
		<div class="card" style="margin-bottom: 0.75rem; border-color: rgba(255,107,0,0.35);">
			<div class="card-title">➕ Registrar nuevo cliente</div>
			<div class="field">
				<label for="nc-id">ID (máximo 4 letras):</label>
				<input id="nc-id" class="input" maxlength="4" placeholder="Ej: HUSA" bind:value={newId} on:input={() => (newId = newId.toUpperCase().slice(0, 4))} />
			</div>
			<div class="field">
				<label for="nc-nombre">Razón social:</label>
				<input id="nc-nombre" class="input" placeholder="Ej: Hussmann América…" bind:value={newNombre} />
			</div>
			<div class="field">
				<label for="nc-dias">Días de pago:</label>
				<input id="nc-dias" type="number" class="input" min="0" bind:value={newDias} />
			</div>
			<button class="btn btn-primary btn-block" on:click={crear} disabled={busy}>💾 Guardar cliente</button>
		</div>
	{/if}

	{#if selId}
		<div class="card" style="margin-bottom: 0.75rem; border-color: rgba(255,107,0,0.35);">
			<div class="card-title">✏️ Editar: {selId}</div>
			<div class="field">
				<label for="ec-nombre">Razón social:</label>
				<input id="ec-nombre" class="input" bind:value={editNombre} />
			</div>
			<div class="field">
				<label for="ec-dias">Días de pago:</label>
				<input id="ec-dias" type="number" class="input" min="0" bind:value={editDias} />
			</div>
			<div class="grid-2" style="margin-bottom: 0.5rem;">
				<button class="btn btn-secondary btn-block" on:click={() => (selId = null)}>❌ Cancelar</button>
				<button class="btn btn-primary btn-block" on:click={guardarEdicion} disabled={busy}>💾 Guardar</button>
			</div>
			<button class="btn btn-danger btn-block" on:click={eliminar} disabled={busy}>🗑️ Eliminar cliente</button>
		</div>
	{/if}

	{#if error}
		<div class="msg err">{error}</div>
	{/if}
	{#if msg}
		<div class="msg ok">{msg}</div>
	{/if}

	<p style="color: var(--color-text-muted); font-size: 0.8rem;">Mostrando {filtrados.length} de {lista.length} clientes.</p>

	{#if loading}
		<div class="empty">Cargando…</div>
	{:else if filtrados.length === 0}
		<div class="empty">No hay clientes registrados.</div>
	{:else}
		<div class="grid">
			{#each filtrados as c (c.id_cliente)}
				<button class="card-cliente" class:selected={selId === c.id_cliente} on:click={() => seleccionar(c)} title="Seleccionar para editar">
					<div class="body">
						<div class="id">{c.id_cliente}</div>
						<div class="nombre">{c.nombre}</div>
						<div class="dias">📅 {c.dias_pago ?? 30} días de pago</div>
					</div>
				</button>
			{/each}
		</div>
	{/if}
</div>

<style>
	.card-title { font-weight: 700; font-size: 1rem; margin-bottom: 0.25rem; }
	.msg { padding: 0.6rem 0.75rem; border-radius: 8px; font-size: 0.85rem; margin-bottom: 0.75rem; }
	.msg.err { background: rgba(239,68,68,0.1); color: #EF4444; }
	.msg.ok { background: rgba(34,197,94,0.1); color: #22C55E; }
	.card { margin-bottom: 0.75rem; }
	.empty { text-align: center; color: #94a3b8; padding: 3rem 1rem; font-size: 0.9rem; }

	.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.75rem; }

	.card-cliente {
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
	.card-cliente:hover {
		transform: translateY(-3px);
		border-color: rgba(255, 107, 0, 0.5);
	}
	.card-cliente.selected {
		border-color: var(--color-primary, #FFAE00);
		background: rgba(255, 107, 0, 0.08);
	}

	.body { padding: 0.65rem 0.75rem 0.75rem; }
	.id { font-family: ui-monospace, 'Cascadia Mono', monospace; font-weight: 800; font-size: 1.1rem; color: #FFAE00; letter-spacing: 0.5px; margin-bottom: 0.2rem; }
	.nombre { font-size: 0.85rem; font-weight: 600; color: #e2e8f0; margin-bottom: 0.25rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.dias { font-size: 0.7rem; color: #94a3b8; }
</style>
