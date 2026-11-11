<script>
	import { Brain, Save , X , ArrowLeft, Clock } from 'lucide-svelte';

	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { api } from '$lib/api.js';
	// Admon no tiene toasts store; se usa alert()

	let vehiculos = $state([]);
	let clientes = $state([]);
	let estaciones = $state([]);
	let valesAbiertos = $state([]);
	let loading = $state(false);
	let ocrLoading = $state(false);
	let fotoFile = $state.raw(null);
	let fotoPreview = $state('');

	let form = $state({
		id_vehiculo: '',
		id_cliente: '',
		folio_ticket: '',
		estacion: '',
		descripcion: '',
		id_solicitud_vale: ''
	});

	function tieneAcceso() {
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && u.acceso_vales_oxxogas);
		} catch {
			return false;
		}
	}

	async function cargarCatalogos() {
		try {
			const v = await api.get('/automoviles');
			vehiculos = Array.isArray(v) ? v : (v.items || []);
		} catch {}
		try {
			const c = await api.get('/clientes');
			clientes = Array.isArray(c) ? c : (c.items || []);
		} catch {}
		try {
			const e = await api.get('/tickets-oxxogas/estaciones');
			estaciones = Array.isArray(e) ? e : [];
		} catch {}
	}

	async function cargarValesAbiertos(idVehiculo) {
		if (!idVehiculo) { valesAbiertos = []; return; }
		try {
			const r = await api.get(`/tickets-oxxogas/vales-abiertos?vehiculo=${idVehiculo}`);
			valesAbiertos = Array.isArray(r) ? r : [];
			if (valesAbiertos.length && !form.id_solicitud_vale) {
				form.id_solicitud_vale = String(valesAbiertos[0].Id);
			}
		} catch {
			valesAbiertos = [];
		}
	}

	// Al elegir un vale, prellenar cliente y descripción
	$effect(() => {
		const id = form.id_solicitud_vale;
		const sel = valesAbiertos.find((x) => String(x.Id) === String(id));
		if (!sel) return;
		if (!form.descripcion && sel.Descripcion) form.descripcion = sel.Descripcion;
		if (!form.id_cliente && sel.IdCliente) form.id_cliente = String(sel.IdCliente);
	});

	// Al cambiar vehículo, cargar vales abiertos
	$effect(() => {
		const v = form.id_vehiculo;
		cargarValesAbiertos(v);
	});

	onMount(async () => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
		if (!tieneAcceso()) {
			navigate('/dashboard', { replace: true });
			return;
		}
		await cargarCatalogos();
	});

	function onFoto(e) {
		const input = e.target;
		if (!input.files || !input.files[0]) return;
		const file = input.files[0];
		fotoFile = file;
		fotoPreview = URL.createObjectURL(file);
		input.value = '';
	}

	function removeFoto() {
		if (fotoPreview) URL.revokeObjectURL(fotoPreview);
		fotoFile = null;
		fotoPreview = '';
	}

	async function extraerFolioConIA() {
		if (!fotoFile) { alert('Toma o sube una foto primero.'); return; }
		ocrLoading = true;
		try {
			const formData = new FormData();
			formData.append('foto', fotoFile);
			const data = await api.postForm('/tickets/ai-extraer-folio', formData);
			if (data.folio) {
				form.folio_ticket = data.folio;
				if (data.estacion) {
					form.estacion = data.estacion;
					alert(`Folio: ${data.folio} · Estación: ${data.estacion}`);
				} else {
					alert(`Folio extraído: ${data.folio}`);
				}
			} else {
				alert('No se pudo extraer el folio. Intente manualmente.');
			}
		} catch (e) {
			alert('Error con IA: ' + (e?.message || ''));
		} finally {
			ocrLoading = false;
		}
	}

	async function guardar() {
		if (!form.id_vehiculo) { alert('Seleccione un vehículo.'); return; }
		if (!form.id_cliente) { alert('Seleccione un cliente.'); return; }
		if (!form.estacion || !form.estacion.trim()) { alert('Estación es obligatoria.'); return; }
		if (!form.folio_ticket || !form.folio_ticket.trim()) { alert('Ingrese o extraiga el folio del ticket.'); return; }
		if (!form.descripcion || !form.descripcion.trim()) { alert('Servicio/Proyecto es obligatorio.'); return; }
		if (!fotoFile) { alert('Foto del ticket es obligatoria.'); return; }

		loading = true;
		try {
			const idLocal = crypto.randomUUID();
			const formData = new FormData();
			formData.append('id_vehiculo', form.id_vehiculo);
			formData.append('idempotency_key', idLocal);
			formData.append('id_cliente', form.id_cliente);
			formData.append('folio_ticket', form.folio_ticket.trim());
			formData.append('estacion', form.estacion.trim());
			formData.append('descripcion', form.descripcion.trim());
			formData.append('id_solicitud_vale', form.id_solicitud_vale || '');
			formData.append('foto', fotoFile);

			const result = await api.postForm('/tickets-oxxogas/crear', formData);
			if (result.success) {
				alert('Ticket guardado correctamente.');
				removeFoto();
				form.folio_ticket = '';
				form.estacion = '';
				form.descripcion = '';
				form.id_solicitud_vale = '';
				navigate('/tickets_oxxogas');
			}
		} catch (e) {
			alert('Error al guardar: ' + (e?.message || ''));
		} finally {
			loading = false;
		}
	}
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" onclick={() => navigate('/tickets_oxxogas')} title="Volver"><ArrowLeft size={16} /> Volver</button>
		<h1>🎫 Capturar Ticket OxxoGas</h1>
	</div>

	<div class="card">
		<div class="field">
			<label>🚗 Vehículo:</label>
			<select class="input" bind:value={form.id_vehiculo}>
				<option value="">Seleccione un vehículo...</option>
				{#each vehiculos as v}
					<option value={v.Id || v.id}>{v.MarcaModelo || v.marcaModelo} — {v.Placas || v.placas}</option>
				{/each}
			</select>
		</div>

		<div class="field">
			<label>🏢 Cliente / Empresa:</label>
			<select class="input" bind:value={form.id_cliente}>
				<option value="">Seleccione un cliente...</option>
				{#each clientes as c}
					<option value={c.id_cliente || c.IdCliente}>{c.nombre || c.Cliente || c.cliente}</option>
				{/each}
			</select>
		</div>

		{#if valesAbiertos.length > 0}
			<div class="field">
				<label>🎫 Vale a consumir:</label>
				<select class="input" bind:value={form.id_solicitud_vale}>
					<option value="">-- Sin vale (carga manual) --</option>
					{#each valesAbiertos as v (v.Id)}
						<option value={v.Id}>
							VL-{String(v.Id).padStart(5, '0')} · {v.IdCliente || 'Sin cliente'} · {v.Descripcion || 'Sin servicio'}
						</option>
					{/each}
				</select>
				<p class="help">El vale se cierra con este ticket y le hereda cliente y servicio/proyecto.</p>
			</div>
		{/if}

		<div class="field">
			<label>📸 Foto del Ticket:</label>
			<div class="photo-btns">
				<label class="add-photo-btn camera">
					<input type="file" accept="image/*" capture="environment" onchange={onFoto} hidden />
					📷 Cámara
				</label>
				<label class="add-photo-btn gallery">
					<input type="file" accept="image/*" onchange={onFoto} hidden />
					🖼️ Galería
				</label>
			</div>
			{#if fotoPreview}
				<div class="foto-preview">
					<img src={fotoPreview} alt="Ticket" />
					<button class="photo-remove" onclick={removeFoto}><X size={16} /></button>
				</div>
			{/if}
		</div>

		<div class="field">
			<label>Folio del Ticket:</label>
			<div class="folio-row">
				<input class="input" placeholder="Ej. 1234567890" bind:value={form.folio_ticket} />
				<button class="btn btn-sm btn-info" onclick={extraerFolioConIA} disabled={ocrLoading || !fotoFile}>
					{ocrLoading ? '<Clock size={16} />' : '<Brain size={16} />'} IA
				</button>
			</div>
		</div>

		<div class="field">
			<label>⛽ Estación:</label>
			<input class="input" placeholder="Ej. ESTACION CENTRO" list="estaciones-list" bind:value={form.estacion} />
			<datalist id="estaciones-list">
				{#each estaciones as e}
					<option value={e} />
				{/each}
			</datalist>
		</div>

		<div class="field">
			<label>📝 Servicio / Proyecto:</label>
			<textarea class="input" rows="3" placeholder="Describa el servicio o proyecto..." bind:value={form.descripcion}></textarea>
		</div>

		<button class="btn btn-primary btn-block" onclick={guardar} disabled={loading}>
			{loading ? 'Guardando...' : '<Save size={16} /> Guardar Ticket'}
		</button>
	</div>
</div>

<style>
	.page { max-width: 800px; margin: 0 auto; padding: 1rem; }
	.header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
	.header h1 { font-size: 1.25rem; margin: 0; color: #f1f5f9; }
	.card { background: #1e293b; border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 14px; padding: 1.25rem; }
	.field { margin-bottom: 1rem; }
	.field label { display: block; font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.4rem; font-weight: 600; }
	.input { width: 100%; padding: 0.6rem 0.75rem; border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.1); background: #0f172a; color: #f1f5f9; font-size: 0.9rem; }
	.input:focus { outline: none; border-color: #ff6b00; }
	textarea.input { resize: vertical; }
	.help { font-size: 0.75rem; color: #64748b; margin-top: 0.3rem; }
	.btn { padding: 0.6rem 1rem; border-radius: 8px; border: none; cursor: pointer; font-size: 0.9rem; font-weight: 600; }
	.btn-primary { background: #ff6b00; color: #fff; }
	.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
	.btn-secondary { background: rgba(255, 255, 255, 0.08); color: #f1f5f9; }
	.btn-sm { padding: 0.4rem 0.7rem; font-size: 0.8rem; }
	.btn-info { background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
	.btn-block { width: 100%; margin-top: 0.5rem; }
	.folio-row { display: flex; gap: 0.5rem; }
	.folio-row input { flex: 1; }
	.photo-btns { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-bottom: 0.5rem; }
	.add-photo-btn { display: flex; align-items: center; justify-content: center; padding: 0.75rem; border: 2px dashed rgba(255, 255, 255, 0.15); border-radius: 12px; color: #94a3b8; cursor: pointer; font-weight: 600; font-size: 0.85rem; }
	.add-photo-btn:active { border-color: #ff6b00; }
	.camera { border-color: rgba(239, 68, 68, 0.3); color: #ef4444; }
	.gallery { border-color: rgba(59, 130, 246, 0.3); color: #3b82f6; }
	.foto-preview { position: relative; border-radius: 12px; overflow: hidden; border: 1px solid rgba(255, 255, 255, 0.1); margin-top: 0.5rem; }
	.foto-preview img { width: 100%; max-height: 200px; object-fit: contain; display: block; }
	.photo-remove { position: absolute; top: 6px; right: 6px; background: #ef4444; color: white; border: none; border-radius: 50%; width: 28px; height: 28px; font-size: 0.8rem; cursor: pointer; display: flex; align-items: center; justify-content: center; }
</style>