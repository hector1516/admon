<script>
	import { Save , X } from 'lucide-svelte';

	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';

	// Crear reporte como el HUB: datos generales + técnicos adicionales.

	let loading = $state(true);
	let error = $state('');
	let msg = $state('');
	let busy = $state(false);

	let form = $state({
		cliente: '',
		contacto: '',
		correo_contacto: '',
		fecha: new Date().toISOString().split('T')[0],
		tecnico: '',
		descripcion: '',
		notas: '',
		fecha_inicio: '08:00',
		fecha_fin: '17:00',
		tiempo_traslado: 0.0,
		tiempo_comida: 0,
		maquina_linea: '',
		tecnicos_adicionales: ''
	});

	let tecnicosHub = $state([]);

	function tieneAcceso() {
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && (u.acceso_reportes || u.acceso_registro_reportes));
		} catch {
			return false;
		}
	}

	function apiHeaders() {
		return { 'Content-Type': 'application/json', ...auth.authHeader() };
	}

	async function cargarTecnicos() {
		try {
			const res = await fetch('/api/usuarios', { headers: auth.authHeader() });
			const data = await res.json().catch(() => []);
			if (res.ok) tecnicosHub = data.filter(u => u.Activo === 1).map(u => u.Nombre);
		} catch {}
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
		await cargarTecnicos();
		loading = false;
	});

	async function guardar() {
		if (!form.cliente.trim()) { error = 'Cliente obligatorio.'; return; }
		if (!form.tecnico.trim()) { error = 'Ingeniero obligatorio.'; return; }
		if (!form.fecha_inicio || !form.fecha_fin) { error = 'Hora inicio y fin obligatorias.'; return; }

		error = '';
		msg = '';
		busy = true;
		try {
			const tecnicosAdic = form.tecnicos_adicionales
				.split(',')
				.map(s => s.trim())
				.filter(Boolean);
			const res = await fetch('/api/reportes', {
				method: 'POST',
				headers: apiHeaders(),
				body: JSON.stringify({
					cliente: form.cliente.trim(),
					contacto: form.contacto.trim(),
					correo_contacto: form.correo_contacto.trim(),
					fecha: form.fecha,
					tecnico: form.tecnico.trim(),
					descripcion: form.descripcion.trim(),
					notas: form.notas.trim(),
					fecha_inicio: form.fecha_inicio,
					fecha_fin: form.fecha_fin,
					tiempo_traslado: parseFloat(form.tiempo_traslado) || 0,
					tiempo_comida: form.tiempo_comida ? 1 : 0,
					maquina_linea: form.maquina_linea.trim(),
					tecnicos_adicionales: tecnicosAdic
				})
			});
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al crear.');
			msg = `✅ Reporte creado: ${data.folio}`;
			setTimeout(() => navigate('/reportes', { replace: true }), 1000);
		} catch (e) {
			error = e.message || 'Error al crear.';
		} finally {
			busy = false;
		}
	}
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" on:click={() => navigate('/reportes')} title="Volver">⬅️</button>
		<h1>📝 Nuevo Reporte</h1>
	</div>

	{#if loading}
		<div class="empty">Cargando…</div>
	{:else}
		<div class="card">
			<div class="card-title">Datos del reporte</div>

			<div class="grid-2">
				<div class="field">
					<label for="cliente">Cliente *</label>
					<input id="cliente" class="input" bind:value={form.cliente} placeholder="Razón social" />
				</div>
				<div class="field">
					<label for="fecha">Fecha *</label>
					<input id="fecha" type="date" class="input" bind:value={form.fecha} />
				</div>
			</div>

			<div class="grid-2">
				<div class="field">
					<label for="contacto">Contacto</label>
					<input id="contacto" class="input" bind:value={form.contacto} placeholder="Nombre contacto" />
				</div>
				<div class="field">
					<label for="correo">Correo contacto</label>
					<input id="correo" type="email" class="input" bind:value={form.correo_contacto} placeholder="email@dominio.com" />
				</div>
			</div>

			<div class="field">
				<label for="tecnico">Ingeniero responsable *</label>
				<select id="tecnico" class="input" bind:value={form.tecnico}>
					<option value="">Selecciona…</option>
					{#each tecnicosHub as t}
						<option value={t}>{t}</option>
					{/each}
				</select>
			</div>

			<div class="field">
				<label for="maquina">Máquina / Línea</label>
				<input id="maquina" class="input" bind:value={form.maquina_linea} placeholder="Ej: Línea 3, Inyector 5…" />
			</div>

			<div class="field">
				<label for="descripcion">Descripción del servicio *</label>
				<textarea id="descripcion" class="input" bind:value={form.descripcion} rows="4" placeholder="Detalle del trabajo realizado…"></textarea>
			</div>

			<div class="field">
				<label for="notas">Notas internas</label>
				<textarea id="notas" class="input" bind:value={form.notas} rows="2" placeholder="Solo visible en admon…"></textarea>
			</div>

			<div class="grid-4">
				<div class="field">
					<label for="ini">Hora inicio *</label>
					<input id="ini" type="time" class="input" bind:value={form.fecha_inicio} />
				</div>
				<div class="field">
					<label for="fin">Hora fin *</label>
					<input id="fin" type="time" class="input" bind:value={form.fecha_fin} />
				</div>
				<div class="field">
					<label for="traslado">Traslado (h)</label>
					<input id="traslado" type="number" step="0.5" min="0" class="input" bind:value={form.tiempo_traslado} />
				</div>
				<div class="field">
					<label for="comida">Comida</label>
					<select id="comida" class="input" bind:value={form.tiempo_comida}>
						<option value="0">No</option>
						<option value="1">Sí (1h)</option>
					</select>
				</div>
			</div>

			<div class="field">
				<label for="tecnicos_ad">Ingenieros adicionales (separados por coma)</label>
				<input id="tecnicos_ad" class="input" bind:value={form.tecnicos_adicionales} placeholder="Juan Pérez, María López…" />
				<p class="hint">Deben existir como usuarios activos en HUB.</p>
			</div>

			{#if error}
				<div class="msg err">{error}</div>
			{/if}
			{#if msg}
				<div class="msg ok">{msg}</div>
			{/if}

			<div class="grid-2" style="margin-top: 0.5rem;">
				<button class="btn btn-secondary btn-block" on:click={() => navigate('/reportes')}><X size={16} /> Cancelar</button>
				<button class="btn btn-primary btn-block" on:click={guardar} disabled={busy}><Save size={16} /> Crear reporte</button>
			</div>
		</div>
	{/if}
</div>

<style>
	.card-title { font-weight: 700; font-size: 1rem; margin-bottom: 0.25rem; }
	.hint { font-size: 0.75rem; color: var(--color-text-muted); margin-top: 0.15rem; }
	.msg { padding: 0.6rem 0.75rem; border-radius: 8px; font-size: 0.85rem; margin-bottom: 0.75rem; }
	.msg.err { background: rgba(239,68,68,0.1); color: #EF4444; }
	.msg.ok { background: rgba(34,197,94,0.1); color: #22C55E; }
	.card { margin-bottom: 0.75rem; }
</style>