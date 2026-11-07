<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { api } from '$lib/api.js';

	let autos = $state([]);
	let usuarios = $state([]);
	let loading = $state(true);
	let error = $state('');
	let msg = $state('');
	let showModal = $state(false);
	let editId = $state(null);
	let form = $state({ marca_modelo: '', placas: '', poliza_seguro: '', ultimo_servicio_kms: 0, id_usuario_asignado: null });
	let busy = $state(false);

	async function cargar() {
		loading = true;
		error = '';
		try {
			const [a, u] = await Promise.all([
				api.get('/automoviles'),
				api.get('/automoviles/usuarios'),
			]);
			autos = Array.isArray(a) ? a : (a || []);
			usuarios = Array.isArray(u) ? u : (u || []);
		} catch (e) {
			error = e.message || 'No se pudo cargar.';
		} finally {
			loading = false;
		}
	}

	function abrirNuevo() {
		editId = null;
		form = { marca_modelo: '', placas: '', poliza_seguro: '', ultimo_servicio_kms: 0, id_usuario_asignado: null };
		showModal = true;
	}

	function abrirEditar(a) {
		editId = a.id;
		form = {
			marca_modelo: a.marca_modelo,
			placas: a.placas,
			poliza_seguro: a.poliza_seguro || '',
			ultimo_servicio_kms: a.ultimo_servicio_kms || 0,
			id_usuario_asignado: a.id_usuario_asignado,
		};
		showModal = true;
	}

	async function guardar() {
		busy = true;
		msg = '';
		try {
			if (editId) {
				await api.put(`/automoviles/${editId}?marca_modelo=${encodeURIComponent(form.marca_modelo)}&placas=${encodeURIComponent(form.placas)}&poliza_seguro=${encodeURIComponent(form.poliza_seguro)}&ultimo_servicio_kms=${form.ultimo_servicio_kms}`);
				if (form.id_usuario_asignado !== null) {
					await api.put(`/automoviles/${editId}/asignar/${form.id_usuario_asignado}`);
				} else {
					await api.put(`/automoviles/${editId}/desasignar`);
				}
				msg = 'Automóvil actualizado.';
			} else {
				await api.post(`/automoviles?marca_modelo=${encodeURIComponent(form.marca_modelo)}&placas=${encodeURIComponent(form.placas)}&poliza_seguro=${encodeURIComponent(form.poliza_seguro)}&ultimo_servicio_kms=${form.ultimo_servicio_kms}`);
				msg = 'Automóvil agregado.';
			}
			showModal = false;
			await cargar();
		} catch (e) {
			msg = e.message || 'Error al guardar.';
		} finally {
			busy = false;
		}
	}

	async function desasignar(id) {
		if (!confirm('¿Desasignar este automóvil?')) return;
		busy = true;
		try {
			await api.put(`/automoviles/${id}/desasignar`);
			msg = 'Automóvil desasignado.';
			await cargar();
		} catch (e) {
			msg = e.message || 'Error.';
		} finally {
			busy = false;
		}
	}

	onMount(() => {
		if (!auth.isLoggedIn()) { navigate('/login', { replace: true }); return; }
		cargar();
	});
</script>

<div class="page">
	<div class="header">
		<div class="brand-col">
			<button class="btn btn-sm btn-secondary" on:click={() => navigate('/dashboard')} title="Volver">←</button>
			<h1>🚗 Automóviles</h1>
		</div>
		<div style="flex:1"></div>
		<button class="btn btn-primary btn-sm" on:click={abrirNuevo}>+ Nuevo</button>
	</div>

	{#if msg}
		<div class="msg ok">{msg}</div>
	{/if}

	{#if loading}
		<div class="empty">Cargando…</div>
	{:else if autos.length === 0}
		<div class="empty">No hay automóviles registrados.</div>
	{:else}
		<div class="grid">
			{#each autos as a (a.id)}
				<div class="card-auto">
					{#if a.imagen}
						<div class="auto-img">
							<img src={a.imagen} alt={a.marca_modelo} />
						</div>
					{/if}
					<div class="auto-header">
						<span class="auto-marca">{a.marca_modelo}</span>
						<span class="auto-placas">{a.placas}</span>
					</div>
					<div class="auto-info">
						{#if a.usuario_asignado}
							<span class="badge badge-info">👤 {a.usuario_asignado}</span>
						{:else}
							<span class="badge badge-warning">Sin asignar</span>
						{/if}
						{#if a.ultimo_servicio_kms}
							<span class="kms">{a.ultimo_servicio_kms.toLocaleString()} km</span>
						{/if}
					</div>
					<div class="auto-actions">
						<button class="btn btn-sm btn-secondary" on:click={() => abrirEditar(a)}>✏️ Editar</button>
						{#if a.id_usuario_asignado}
							<button class="btn btn-sm btn-danger" on:click={() => desasignar(a.id)}>🔓 Desasignar</button>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

{#if showModal}
	<div class="modal-overlay" on:click={() => (showModal = false)}>
		<div class="modal" on:click|stopPropagation>
			<h2>{editId ? 'Editar automóvil' : 'Nuevo automóvil'}</h2>
			<div class="field">
				<label>Marca y modelo</label>
				<input class="input" bind:value={form.marca_modelo} placeholder="Ej: Nissan Versa Blanco" />
			</div>
			<div class="field">
				<label>Placas</label>
				<input class="input" bind:value={form.placas} placeholder="Ej: RWS671B" />
			</div>
			<div class="field">
				<label>Póliza de seguro</label>
				<input class="input" bind:value={form.poliza_seguro} placeholder="Opcional" />
			</div>
			<div class="field">
				<label>Último servicio (km)</label>
				<input class="input" type="number" bind:value={form.ultimo_servicio_kms} />
			</div>
			{#if editId}
				<div class="field">
					<label>Asignado a</label>
					<select class="input" bind:value={form.id_usuario_asignado}>
						<option value={null}>— Sin asignar —</option>
						{#each usuarios as u (u.id)}
							<option value={u.id}>{u.nombre}</option>
						{/each}
					</select>
				</div>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-secondary" on:click={() => (showModal = false)}>Cancelar</button>
				<button class="btn btn-primary" on:click={guardar} disabled={busy || !form.marca_modelo || !form.placas}>
					{busy ? 'Guardando…' : 'Guardar'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 0.75rem; }
	.card-auto { background: var(--color-surface); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 1rem; overflow: hidden; }
	.auto-img { width: 100%; height: 120px; display: flex; align-items: center; justify-content: center; margin-bottom: 0.75rem; background: rgba(255,255,255,0.03); border-radius: 8px; overflow: hidden; }
	.auto-img img { max-width: 100%; max-height: 100%; object-fit: contain; }
	.auto-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
	.auto-marca { font-weight: 700; font-size: 0.95rem; }
	.auto-placas { font-size: 0.8rem; color: var(--color-text-muted); font-family: monospace; }
	.auto-info { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.75rem; flex-wrap: wrap; }
	.auto-actions { display: flex; gap: 0.5rem; }
	.kms { font-size: 0.75rem; color: var(--color-text-muted); }
	.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 1rem; }
	.modal { background: var(--color-surface); border-radius: 12px; padding: 1.5rem; width: 100%; max-width: 420px; max-height: 90vh; overflow-y: auto; }
	.modal h2 { margin: 0 0 1rem; font-size: 1.1rem; }
	.modal-actions { display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 1rem; }
	.field { margin-bottom: 0.75rem; }
	.field label { display: block; font-size: 0.8rem; color: var(--color-text-muted); margin-bottom: 0.3rem; }
	.msg { padding: 0.75rem; border-radius: 8px; margin-bottom: 1rem; font-size: 0.85rem; }
	.msg.ok { background: rgba(34,197,94,0.1); color: var(--color-success); }
	.empty { text-align: center; padding: 2rem; color: var(--color-text-muted); }
	.badge { font-size: 0.7rem; padding: 0.2rem 0.6rem; border-radius: 999px; }
	.badge-info { background: rgba(59,130,246,0.15); color: #3B82F6; }
	.badge-warning { background: rgba(245,158,11,0.15); color: var(--color-warning); }
</style>