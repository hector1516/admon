<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { clientes } from '$lib/cotizacionesApi.js';
	import OfflineNotice from '$lib/components/OfflineNotice.svelte';

	// Catálogo de clientes como el HUB: buscar, editar, eliminar y registrar.
	// La lista se lee de Dexie (cotizacionesApi) así que abre sin conexión;
	// los cambios (alta/edición/borrado) sí requieren conexión.

	let lista = $state([]);
	let loading = $state(true);
	let error = $state('');
	let msg = $state('');
	let busqueda = $state('');
	let busy = $state(false);

	// Selección / edición
	let selId = $state(null);
	let editNombre = $state('');
	let editDias = $state(30);

	// Nuevo
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
		<button class="btn btn-sm btn-secondary" on:click={() => navigate('/dashboard')} title="Volver">⬅️</button>
		<h1>📇 Clientes</h1>
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
				<input id="nc-nombre" class="input" placeholder="Ej: Hussmann American…" bind:value={newNombre} />
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
			<button class="btn btn-danger btn-block" on:click={eliminar} disabled={busy}>🚨 Eliminar cliente</button>
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
		<div class="list">
			{#each filtrados as c (c.id_cliente)}
				<button class="list-card" class:selected={selId === c.id_cliente} on:click={() => navigate(`/clientes/${c.id_cliente}`)}>
					<div>
						<div style="font-weight: 800; color: var(--color-primary-light);">{c.id_cliente}</div>
						<div style="font-size: 0.9rem;">{c.nombre}</div>
					</div>
					<div style="text-align: right; font-size: 0.8rem; color: var(--color-text-muted);">
						{c.dias_pago ?? 30} días
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
	.list-card.selected { border-color: var(--color-primary); }
</style>
