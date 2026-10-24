<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { api } from '$lib/api.js';
	import OfflineNotice from '../components/OfflineNotice.svelte';

	// Detalle completo de reporte (pantalla completa, sin modales)
	// Permiso: acceso_registro_reportes

	let { id } = $props();
	const idReporte = Number(id);

	let loading = $state(true);
	let error = $state('');
	let msg = $state('');
	let busy = $state(false);

	let reporte = $state({});
	let fotosSubiendo = $state([]);
	let fotosPreview = $state([]);
	const maxFotos = 6;

	// PDF blob for download/share (evita abrir en otra ventana)
	let pdfBlob = $state(null);
	let pdfLoading = $state(false);
	let showPdfPreview = $state(false);

	// Edit mode
	let editando = $state(false);
	let editForm = $state({});
	let tecnicosHub = $state([]);

	function tieneAcceso() {
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && u.acceso_registro_reportes);
		} catch {
			return false;
		}
	}

	function apiHeaders() {
		return { 'Content-Type': 'application/json', ...auth.authHeader() };
	}

	async function cargar() {
		loading = true;
		error = '';
		try {
			// Detalle con caché offline (red primero, fallback a caché local)
			reporte = await api.get(`/reportes/${idReporte}`);

			// Fotos: si no hay red ni caché quedan vacías (se cachean la
			// primera vez que se abre el detalle con conexión)
			try {
				reporte._fotos = (await api.get(`/reportes/${idReporte}/fotos`)) || [];
			} catch {
				reporte._fotos = [];
			}

			// Técnicos adicionales del reporte
			try {
				const tecnicos = (await api.get(`/reportes/${idReporte}/tecnicos`)) || [];
				reporte._tecnicos_adicionales = tecnicos.filter(t => t !== reporte.Tecnico);
			} catch {
				reporte._tecnicos_adicionales = [];
			}

			// Catálogo de técnicos para el select de edición
			try {
				const usuarios = (await api.get('/usuarios')) || [];
				tecnicosHub = usuarios.filter(u => u.Activo === 1).map(u => u.Nombre);
			} catch {
				tecnicosHub = [];
			}
		} catch (e) {
			error = e.message === 'Sesión expirada' ? e.message : `Error: ${e.message}`;
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

	function formatearFecha(val) {
		if (!val) return 'Sin registrar';
		const d = new Date(val);
		if (isNaN(d)) return String(val);
		return d.toLocaleString('es-MX', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
	}

	function toInputDate(val) {
		if (!val) return '';
		const d = new Date(val);
		if (isNaN(d)) return '';
		return d.toISOString().split('T')[0];
	}

	// Para <input type="datetime-local">: "YYYY-MM-DDTHH:MM" en hora LOCAL
	// (no usar toISOString, que pasa a UTC y puede correr el día).
	function toInputDateTime(val) {
		if (!val) return '';
		const d = new Date(String(val).replace(' ', 'T'));
		if (isNaN(d.getTime())) return '';
		const p = (n) => String(n).padStart(2, '0');
		return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
	}

	function estatusHtml(est) {
		const v = String(est || 'Borrador');
		if (v === 'Borrador') return `<span class="badge" style="background:#475569;">📝 Borrador</span>`;
		if (v === 'Completado') return `<span class="badge" style="background:#0EA5E9;">🔵 Completado</span>`;
		if (v === 'Firmado') return `<span class="badge" style="background:#10B981;">🟢 Firmado</span>`;
		return `<span class="badge">${v}</span>`;
	}

	async function loadPdfBlob() {
		if (pdfBlob) return true;
		pdfLoading = true;
		try {
			const token = auth.getToken();
			const res = await fetch(`/api/reportes/${idReporte}/pdf?token=${encodeURIComponent(token)}`, { headers: auth.authHeader() });
			if (res.ok) {
				pdfBlob = await res.blob();
				return true;
			}
			const d = await res.json().catch(() => ({}));
			error = d.detail || 'No se pudo generar el PDF.';
			return false;
		} catch {
			error = 'No se pudo obtener el PDF. Revisa tu conexión.';
			return false;
		} finally {
			pdfLoading = false;
		}
	}

	async function descargarPDF() {
		if (!(await loadPdfBlob())) return;
		const url = URL.createObjectURL(pdfBlob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `Reporte_${reporte.Folio}.pdf`;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	}

	async function compartirPDF() {
		if (!(await loadPdfBlob())) return;
		const file = new File([pdfBlob], `Reporte_${reporte.Folio}.pdf`, { type: 'application/pdf' });
		if (navigator.canShare && navigator.canShare({ files: [file] })) {
			try {
				await navigator.share({ files: [file], title: `Reporte ${reporte.Folio}` });
			} catch {
				// User canceló o error
			}
		} else {
			// Fallback: descargar
			await descargarPDF();
		}
	}

	async function abrirPreview() {
		// Navegar a página completa de preview en lugar de modal
		if (!(await loadPdfBlob())) return;
		navigate(`/registro_reportes/${idReporte}/preview`);
	}

	// Alias para compatibilidad
	async function verPDF() {
		await loadPdfBlob();
	}

	async function moverAPapelera() {
		if (!confirm(`¿Mover a PAPELERA el reporte ${reporte.Folio}?\n\nSe ocultará de la lista principal pero se podrá restaurar desde la pestaña "Papelera".\n\n¿Continuar?`)) return;
		error = '';
		msg = '';
		busy = true;
		try {
			const res = await fetch(`/api/reportes/${idReporte}`, { method: 'DELETE', headers: auth.authHeader() });
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al mover a papelera.');
			msg = '🗑️ Movido a papelera.';
			await cargar();
		} catch (e) {
			error = e.message || 'Error al mover a papelera.';
		} finally {
			busy = false;
		}
	}

	async function restaurar() {
		if (!confirm(`¿RESTAURAR el reporte ${reporte.Folio}?\n\nVolverá a la lista de "Firmados".`)) return;
		error = '';
		msg = '';
		busy = true;
		try {
			const res = await fetch(`/api/reportes/${idReporte}/restaurar`, { method: 'POST', headers: auth.authHeader() });
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al restaurar.');
			msg = '✅ Restaurado.';
			await cargar();
		} catch (e) {
			error = e.message || 'Error al restaurar.';
		} finally {
			busy = false;
		}
	}

	async function eliminarDefinitivo() {
		if (!confirm(`⚠️ ELIMINACIÓN PERMANENTE ⚠️\n\n¿Borrar DEFINITIVAMENTE el reporte ${reporte.Folio}?\n\n❌ NO SE PUEDE DESHACER\n❌ Se borran fotos, técnicos y todo el historial\n\nEscribe "ELIMINAR" para confirmar:`)) return;
		const input = prompt('Escribe "ELIMINAR" para confirmar borrado permanente:');
		if (input !== 'ELIMINAR') return;
		error = '';
		msg = '';
		busy = true;
		try {
			const res = await fetch(`/api/reportes/${idReporte}/purge`, { method: 'DELETE', headers: auth.authHeader() });
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al eliminar permanentemente.');
			navigate('/registro_reportes', { replace: true });
		} catch (e) {
			error = e.message || 'Error al eliminar permanentemente.';
			busy = false;
		}
	}

	// Fotos
	async function handleFotosSelect(e) {
		const files = Array.from(e.target.files || []);
		const existentes = reporte._fotos?.length || 0;
		const hueco = maxFotos - existentes;
		if (hueco <= 0) { error = 'Ya tiene 6 fotos (máximo).'; return; }
		const permitidos = files.slice(0, hueco);
		for (const f of permitidos) {
			if (!f.type.startsWith('image/')) continue;
			if (f.size > 5 * 1024 * 1024) continue;
			const reader = new FileReader();
			reader.onload = () => {
				fotosSubiendo.push(reader.result.split(',')[1]);
				fotosPreview.push(reader.result);
			};
			reader.readAsDataURL(f);
		}
		if (files.length > hueco) error = `Solo se permiten ${hueco} fotos más (máx 6).`;
	}

	async function guardarFotos() {
		if (fotosSubiendo.length === 0) return;
		error = '';
		msg = '';
		busy = true;
		try {
			const existentes = reporte._fotos || [];
			const todas = existentes.map(f => f.base64)
				.concat(fotosSubiendo);
			const res = await fetch(`/api/reportes/${idReporte}/fotos`, {
				method: 'POST',
				headers: apiHeaders(),
				body: JSON.stringify({ fotos: todas })
			});
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error guardando fotos.');
			msg = `🎉 ${fotosSubiendo.length} foto(s) guardada(s).`;
			fotosSubiendo = [];
			fotosPreview = [];
			await cargar();
		} catch (e) {
			error = e.message || 'Error guardando fotos.';
		} finally {
			busy = false;
		}
	}

	// Edit mode
	function empezarEdicion() {
		editForm = {
			cliente: reporte.Cliente || '',
			contacto: reporte.Contacto || '',
			correo_contacto: reporte.CorreoContacto || '',
			fecha: toInputDate(reporte.Fecha),
			tecnico: reporte.Tecnico || '',
			descripcion: reporte.DescripcionServicio || '',
			estatus: reporte.Estatus || 'Borrador',
			notas: reporte.Notas || '',
			fecha_inicio: toInputDateTime(reporte.FechaHoraInicio),
			fecha_fin: toInputDateTime(reporte.FechaHoraFin),
			tiempo_traslado: Number(reporte.TiempoTraslado || 0),
			tiempo_comida: Number(reporte.TiempoComida || 0),
			maquina_linea: reporte.MaquinaLinea || '',
			tecnicos_adicionales: ''
		};
		// Cargar técnicos adicionales actuales
		if (reporte._tecnicos_adicionales) {
			editForm.tecnicos_adicionales = reporte._tecnicos_adicionales.join(', ');
		}
		editando = true;
	}

	function cancelarEdicion() {
		editando = false;
	}

	async function guardarEdicion() {
		if (!editForm.cliente.trim() || !editForm.tecnico.trim()) {
			error = 'Cliente y técnico son obligatorios.';
			return;
		}
		if (!editForm.fecha_inicio || !editForm.fecha_fin) {
			error = 'Hora inicio y fin obligatorias.';
			return;
		}
		error = '';
		msg = '';
		busy = true;
		try {
			const tecnicosAdic = editForm.tecnicos_adicionales
				.split(',')
				.map(s => s.trim())
				.filter(Boolean);
			const res = await fetch(`/api/reportes/${idReporte}`, {
				method: 'PUT',
				headers: apiHeaders(),
				body: JSON.stringify({
					cliente: editForm.cliente.trim(),
					contacto: editForm.contacto.trim(),
					correo_contacto: editForm.correo_contacto.trim(),
					fecha: editForm.fecha,
					tecnico: editForm.tecnico.trim(),
					descripcion: editForm.descripcion.trim(),
					estatus: editForm.estatus.trim(),
					notas: editForm.notas.trim(),
					fecha_inicio: editForm.fecha_inicio,
					fecha_fin: editForm.fecha_fin,
					tiempo_traslado: parseFloat(editForm.tiempo_traslado) || 0,
					tiempo_comida: editForm.tiempo_comida ? 1 : 0,
					maquina_linea: editForm.maquina_linea.trim(),
					tecnicos_adicionales: tecnicosAdic
				})
			});
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al actualizar.');
			msg = '✅ Reporte actualizado.';
			editando = false;
			await cargar();
		} catch (e) {
			error = e.message || 'Error al actualizar.';
		} finally {
			busy = false;
		}
	}
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" on:click={() => navigate('/registro_reportes')} title="Volver">⬅️</button>
		<h1>📋 {reporte.Folio || 'Cargando…'}</h1>
		<div style="flex:1"></div>
		{#if !editando && !loading}
			<button class="btn btn-sm btn-primary" on:click={empezarEdicion}>✏️ Editar</button>
		{/if}
	</div>

	{#if loading}
		<div class="empty">Cargando…</div>
	{:else}
		<OfflineNotice compacto />
		{#if error}
			<div class="msg err">{error}</div>
		{/if}
		{#if msg}
			<div class="msg ok">{msg}</div>
		{/if}

		<!-- Datos principales -->
		<div class="card" style="margin-bottom: 0.75rem;">
			<div class="card-title">📄 Datos del reporte</div>

			{#if editando}
				<div class="grid-2">
					<div class="field">
						<label>Cliente *</label>
						<input class="input" bind:value={editForm.cliente} />
					</div>
					<div class="field">
						<label>Fecha *</label>
						<input type="date" class="input" bind:value={editForm.fecha} />
					</div>
				</div>
				<div class="grid-2">
					<div class="field">
						<label>Contacto</label>
						<input class="input" bind:value={editForm.contacto} />
					</div>
					<div class="field">
						<label>Correo</label>
						<input type="email" class="input" bind:value={editForm.correo_contacto} />
					</div>
				</div>
				<div class="field">
					<label>Ingeniero responsable *</label>
					<select class="input" bind:value={editForm.tecnico}>
						{#each tecnicosHub as t}
							<option value={t}>{t}</option>
						{/each}
					</select>
				</div>
				<div class="field">
					<label>Máquina / Línea</label>
					<input class="input" bind:value={editForm.maquina_linea} />
				</div>
				<div class="field">
					<label>Descripción *</label>
					<textarea class="input" bind:value={editForm.descripcion} rows="4"></textarea>
				</div>
				<div class="field">
					<label>Notas internas</label>
					<textarea class="input" bind:value={editForm.notas} rows="2"></textarea>
				</div>
				<div class="grid-2">
					<div class="field"><label>Fecha y hora inicio</label><input type="datetime-local" class="input" bind:value={editForm.fecha_inicio} /></div>
					<div class="field"><label>Fecha y hora fin</label><input type="datetime-local" class="input" bind:value={editForm.fecha_fin} /></div>
				</div>
				<div class="grid-2">
					<div class="field"><label>Traslado (h)</label><input type="number" step="0.5" min="0" class="input" bind:value={editForm.tiempo_traslado} /></div>
					<div class="field"><label>Comida</label><select class="input" bind:value={editForm.tiempo_comida}><option value="0">No</option><option value="1">Sí</option></select></div>
				</div>
				<div class="field">
					<label>Ingenieros adicionales (coma)</label>
					<input class="input" bind:value={editForm.tecnicos_adicionales} placeholder="Juan Pérez, María López…" />
				</div>
				<div class="field">
					<label>Estatus</label>
					<select class="input" bind:value={editForm.estatus}>
						<option value="Borrador">Borrador</option>
						<option value="En Curso">En Curso</option>
						<option value="Firmado">Firmado</option>
						<option value="Cancelado">Cancelado</option>
					</select>
				</div>
				<div class="grid-2" style="margin-top: 0.5rem;">
					<button class="btn btn-secondary btn-block" on:click={cancelarEdicion}>❌ Cancelar</button>
					<button class="btn btn-primary btn-block" on:click={guardarEdicion} disabled={busy}>💾 Guardar</button>
				</div>
			{:else}
				<div class="grid-2" style="font-size: 0.9rem;">
					<div><strong>Folio:</strong> {reporte.Folio}</div>
					<div><strong>Estatus:</strong> {@html estatusHtml(reporte.Estatus)}</div>
					<div><strong>Cliente:</strong> {reporte.Cliente}</div>
					<div><strong>Fecha:</strong> {formatearFecha(reporte.Fecha)}</div>
					<div><strong>Contacto:</strong> {reporte.Contacto || 'N/A'}</div>
					<div><strong>Correo:</strong> {reporte.CorreoContacto || 'N/A'}</div>
					<div><strong>Cotización Asociada:</strong> {reporte.Cotizacion || '*Sin cotización vinculada*'}</div>
					<div><strong>Ingeniero:</strong> <strong>{reporte.Tecnico}</strong></div>
					<div><strong>Máquina/Línea:</strong> {reporte.MaquinaLinea || '—'}</div>
					<div><strong>Inicio:</strong> {formatearFecha(reporte.FechaHoraInicio)}</div>
					<div><strong>Fin:</strong> {formatearFecha(reporte.FechaHoraFin)}</div>
					<div><strong>Traslado:</strong> {reporte.TiempoTraslado || 0} h</div>
					<div><strong>Comida:</strong> {reporte.TiempoComida ? 'Sí' : 'No'}</div>
				</div>

				<hr style="border-color: var(--color-border); margin: 0.75rem 0;" />

				<div><strong>🛠️ Descripción del Servicio:</strong></div>
				<div class="info-box" style="margin-top: 0.25rem;">{reporte.DescripcionServicio || '*Sin descripción registrada.*'}</div>

				{#if reporte.Notas}
					<div style="margin-top: 0.75rem;"><strong>📝 Notas:</strong></div>
					<div class="info-box" style="margin-top: 0.25rem;">{reporte.Notas}</div>
				{/if}

				{#if reporte.FirmaConformidad}
					<div style="margin-top: 0.75rem;"><strong>✍️ Firma de Conformidad:</strong></div>
					<img src={reporte.FirmaConformidad} alt="Firma" style="margin-top: 0.25rem; max-width: 280px; border: 1px solid var(--color-border); border-radius: 8px;" />
				{/if}
			{/if}
		</div>

		<!-- Fotos -->
		<div class="card" style="margin-bottom: 0.75rem;">
			<div class="card-title">📸 Evidencia Fotográfica ({(reporte._fotos?.length || 0)}/6)</div>

			{#if (reporte._fotos?.length || 0) < maxFotos}
				<input type="file" accept="image/*" multiple on:change={handleFotosSelect} class="input" style="margin: 0.5rem 0;" />
				{#if fotosPreview.length > 0}
					<div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.5rem;">
						{#each fotosPreview as p}
							<img src={p} alt="Preview" style="width: 100px; height: 100px; object-fit: cover; border-radius: 8px; border: 1px solid var(--color-border);" />
						{/each}
					</div>
					<button class="btn btn-primary btn-sm" on:click={guardarFotos} disabled={busy}>💾 Guardar Fotos</button>
				{/if}
			{:else}
				<p style="font-size: 0.85rem; color: var(--color-text-muted); margin-top: 0.5rem;">ℹ️ Este reporte ya tiene el máximo de 6 fotos.</p>
			{/if}

			{#if reporte._fotos && reporte._fotos.length > 0}
				<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 0.5rem; margin-top: 0.5rem;">
					{#each reporte._fotos as f}
						<div style="position: relative; border: 1px solid var(--color-border); border-radius: 8px; overflow: hidden;">
							<img src="data:image/jpeg;base64,{f.base64}" alt="Foto {f.orden}" style="width: 100%; aspect-ratio: 4/3; object-fit: cover;" />
							<span class="badge" style="position: absolute; top: 4px; left: 4px; font-size: 0.7rem;">#{f.orden}</span>
						</div>
					{/each}
				</div>
			{/if}
		</div>

		<!-- Acciones -->
		<div class="card">
			<div class="grid-2" style="gap: 0.5rem;">
				<button class="btn btn-primary" on:click={descargarPDF} disabled={pdfLoading} style="flex: 1;">
					{pdfLoading ? '⏳ Cargando…' : '📥 Descargar PDF'}
				</button>
				<button class="btn btn-info" on:click={abrirPreview} disabled={pdfLoading} style="flex: 1;">
					👁️ Previsualizar
				</button>
			</div>
			<div class="grid-2" style="margin-top: 0.5rem; gap: 0.5rem;">
				<button class="btn btn-secondary" on:click={compartirPDF} disabled={pdfLoading} style="flex: 1;">
					📤 Compartir
				</button>
				{#if reporte.Eliminado === 1 || reporte.Eliminado === true}
					<button class="btn btn-success" on:click={restaurar} disabled={busy} style="flex: 1;">
						♻️ Restaurar
					</button>
				{:else}
					<button class="btn btn-danger" on:click={moverAPapelera} disabled={busy} style="flex: 1;">
						🗑️ Mover a papelera
					</button>
				{/if}
			</div>
			{#if reporte.Eliminado === 1 || reporte.Eliminado === true}
				<div class="grid-1" style="margin-top: 0.5rem;">
					<button class="btn btn-danger" on:click={eliminarDefinitivo} disabled={busy} style="width: 100%;">
						💀 Eliminar definitivamente
					</button>
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.card-title { font-weight: 700; font-size: 1rem; margin-bottom: 0.25rem; }
	.msg { padding: 0.6rem 0.75rem; border-radius: 8px; font-size: 0.85rem; margin-bottom: 0.75rem; }
	.msg.err { background: rgba(239,68,68,0.1); color: #EF4444; }
	.msg.ok { background: rgba(34,197,94,0.1); color: #22C55E; }
	.info-box { padding: 0.75rem; background: rgba(255,255,255,0.03); border-radius: 8px; border: 1px solid var(--color-border); white-space: pre-wrap; font-size: 0.85rem; }
	.badge { padding: 0.1rem 0.5rem; border-radius: 12px; font-weight: 600; font-size: 0.7rem; color: #fff; }
	.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 1rem; }
	.modal { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 16px; max-width: 900px; width: 100%; max-height: 90vh; display: flex; flex-direction: column; }
	.modal-large { max-width: 95vw; }
	.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem; border-bottom: 1px solid var(--color-border); }
	.modal-header h3 { margin: 0; font-size: 1.1rem; }
	.modal-body { flex: 1; overflow: auto; }
	.btn-ghost { background: transparent; border: none; color: var(--color-text-muted); cursor: pointer; padding: 0.5rem; }
	.btn-info { background: var(--color-primary); color: white; border: none; }
	.btn-info:hover:not(:disabled) { filter: brightness(1.1); }
	.btn-info:disabled { opacity: 0.5; cursor: not-allowed; }
</style>