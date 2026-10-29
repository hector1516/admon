<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { online } from '$lib/stores/online.js';

	// Detalle completo: editar, fotos (cámara/archivo), firma, técnicos, PDF, email, eliminar.

	let { id } = $props();
	const idReporte = Number(id);

	let loading = $state(true);
	let error = $state('');
	let msg = $state('');
	let busy = $state(false);

	let reporte = $state({});
	let fotos = $state([]);
	let tecnicos = $state([]);
	let tecnicosHub = $state([]);
	let nuevaFoto = $state(null);
	let nuevaFotoPreview = $state('');
	let editando = $state(false);
	let editForm = $state({});
	let firmando = $state(false);
	let canvasRef = $state(null);
	let ctx = $state(null);

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

	async function cargar() {
		loading = true;
		error = '';
		try {
			const [rRes, fRes, tRes, uRes] = await Promise.all([
				fetch(`/api/reportes/${idReporte}`, { headers: auth.authHeader() }),
				fetch(`/api/reportes/${idReporte}/fotos`, { headers: auth.authHeader() }),
				fetch(`/api/reportes/${idReporte}/tecnicos`, { headers: auth.authHeader() }),
				fetch('/api/usuarios', { headers: auth.authHeader() })
			]);
			const [r, f, t, u] = await Promise.all([
				rRes.json().catch(() => ({})),
				fRes.json().catch(() => []),
				tRes.json().catch(() => []),
				uRes.json().catch(() => [])
			]);
			if (!rRes.ok) throw new Error(r.detail || 'Error cargando reporte.');
			reporte = r;
			fotos = f || [];
			tecnicos = t || [];
			tecnicosHub = u.filter(x => x.Activo === 1).map(x => x.Nombre);
			editForm = {
				cliente: r.Cliente || '',
				contacto: r.Contacto || '',
				correo_contacto: r.CorreoContacto || '',
				fecha: r.Fecha ? String(r.Fecha).split('T')[0] : '',
				tecnico: r.Tecnico || '',
				descripcion: r.DescripcionServicio || '',
				estatus: r.Estatus || 'Borrador',
				notas: r.Notas || '',
				fecha_inicio: r.FechaHoraInicio ? String(r.FechaHoraInicio).slice(11, 16) : '08:00',
				fecha_fin: r.FechaHoraFin ? String(r.FechaHoraFin).slice(11, 16) : '17:00',
				tiempo_traslado: Number(r.TiempoTraslado || 0),
				tiempo_comida: Number(r.TiempoComida || 0),
				maquina_linea: r.MaquinaLinea || '',
				tecnicos_adicionales: (t || []).filter(x => x !== r.Tecnico)
			};
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

	async function guardarCambios() {
		error = '';
		msg = '';
		busy = true;
		try {
			const tecnicosAdic = Array.isArray(editForm.tecnicos_adicionales)
				? editForm.tecnicos_adicionales
				: (editForm.tecnicos_adicionales || '').split(',').map(s => s.trim()).filter(Boolean);
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

	async function eliminar() {
		if (!confirm(`¿Eliminar el reporte ${reporte.Folio}? Esta acción no se puede deshacer.`)) return;
		error = '';
		msg = '';
		busy = true;
		try {
			const res = await fetch(`/api/reportes/${idReporte}`, { method: 'DELETE', headers: auth.authHeader() });
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al eliminar.');
			navigate('/reportes', { replace: true });
		} catch (e) {
			error = e.message || 'Error al eliminar.';
			busy = false;
		}
	}

	// Fotos
	function handleFileSelect(e) {
		const file = e.target.files[0];
		if (!file) return;
		if (!file.type.startsWith('image/')) { error = 'Solo imágenes.'; return; }
		if (file.size > 5 * 1024 * 1024) { error = 'Máx 5 MB.'; return; }
		const reader = new FileReader();
		reader.onload = () => {
			nuevaFoto = reader.result.split(',')[1];
			nuevaFotoPreview = reader.result;
		};
		reader.readAsDataURL(file);
	}

	async function subirFoto() {
		if (!nuevaFoto) return;
		error = '';
		msg = '';
		busy = true;
		try {
			const res = await fetch(`/api/reportes/${idReporte}/fotos`, {
				method: 'POST',
				headers: apiHeaders(),
				body: JSON.stringify({ fotos: [nuevaFoto] })
			});
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error subiendo foto.');
			msg = '📸 Foto agregada.';
			nuevaFoto = null;
			nuevaFotoPreview = '';
			await cargar();
		} catch (e) {
			error = e.message || 'Error subiendo foto.';
		} finally {
			busy = false;
		}
	}

	async function borrarFoto(idFoto) {
		if (!confirm('¿Eliminar esta foto?')) return;
		error = '';
		msg = '';
		busy = true;
		try {
			const res = await fetch(`/api/reportes/${idReporte}/fotos/${idFoto}`, { method: 'DELETE', headers: auth.authHeader() });
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error eliminando foto.');
			msg = '🗑️ Foto eliminada.';
			await cargar();
		} catch (e) {
			error = e.message || 'Error eliminando foto.';
		} finally {
			busy = false;
		}
	}

	// Firma
	function startFirma() {
		firmando = true;
		setTimeout(() => {
			const canvas = canvasRef;
			if (canvas) {
				ctx = canvas.getContext('2d');
				ctx.strokeStyle = '#000';
				ctx.lineWidth = 2;
				ctx.lineCap = 'round';
			}
		}, 0);
	}

	let drawing = false;
	function onPointerDown(e) {
		if (!ctx) return;
		drawing = true;
		const rect = canvasRef.getBoundingClientRect();
		ctx.beginPath();
		ctx.moveTo(e.clientX - rect.left, e.clientY - rect.top);
	}
	function onPointerMove(e) {
		if (!ctx || !drawing) return;
		const rect = canvasRef.getBoundingClientRect();
		ctx.lineTo(e.clientX - rect.left, e.clientY - rect.top);
		ctx.stroke();
	}
	function onPointerUp() { drawing = false; }

	async function guardarFirma() {
		if (!canvasRef) return;
		error = '';
		msg = '';
		busy = true;
		try {
			const dataUrl = canvasRef.toDataURL('image/png');
			const b64 = dataUrl.split(',')[1];
			const res = await fetch(`/api/reportes/${idReporte}/firma`, {
				method: 'POST',
				headers: apiHeaders(),
				body: JSON.stringify({ signature_base64: b64 })
			});
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error guardando firma.');
			msg = '✍️ Firma guardada. Estatus → Firmado.';
			firmando = false;
			await cargar();
		} catch (e) {
			error = e.message || 'Error guardando firma.';
		} finally {
			busy = false;
		}
	}

	function limpiarFirma() {
		if (!ctx || !canvasRef) return;
		ctx.clearRect(0, 0, canvasRef.width, canvasRef.height);
	}

	// PDF
	function abrirPDF() {
		const token = auth.getToken();
		window.open(`/api/reportes/${idReporte}/pdf?token=${encodeURIComponent(token)}`, '_blank');
	}

	// Email
	let emailEnviar = $state('');
	let enviando = $state(false);
	async function enviarPDF() {
		if (!emailEnviar.trim() || !emailEnviar.includes('@')) { error = 'Email válido requerido.'; return; }
		error = '';
		msg = '';
		enviando = true;
		try {
			const res = await fetch(`/api/reportes/${idReporte}/enviar?email=${encodeURIComponent(emailEnviar.trim())}`, {
				method: 'GET',
				headers: auth.authHeader()
			});
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error enviando.');
			msg = `📧 Enviado a ${emailEnviar}`;
			emailEnviar = '';
		} catch (e) {
			error = e.message || 'Error enviando.';
		} finally {
			enviando = false;
		}
	}

	function estatusColor(est) {
		const e = String(est || '').toUpperCase();
		if (e === 'FIRMADO') return '#22C55E';
		if (e === 'EN CURSO') return '#F59E0B';
		if (e === 'BORRADOR') return '#64748B';
		if (e === 'CANCELADO') return '#EF4444';
		return '#3B82F6';
	}
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" on:click={() => navigate('/reportes')} title="Volver">⬅️</button>
		<h1>📋 {reporte.Folio || 'Cargando…'}</h1>
		<div style="flex:1"></div>
		{#if reporte.Folio}
			<select class="input" style="width: auto; min-width: 160px;" bind:value={editForm.estatus} disabled={!editando}>
				<option value="Borrador">Borrador</option>
				<option value="En Curso">En Curso</option>
				<option value="Firmado">Firmado</option>
				<option value="Cancelado">Cancelado</option>
			</select>
		{/if}
	</div>

	{#if loading}
		<div class="empty">Cargando…</div>
	{:else}
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
						<label>Contacto:</label>
						{#if tecnicosHub.length > 0}
							<select class="input" bind:value={editForm.contacto}>
								<option value="">-- Seleccionar --</option>
								{#each tecnicosHub as t}<option value={t.Nombre || t}>{t.Nombre || t}</option>{/each}
								<option value="__custom">[+] Nuevo contacto</option>
							</select>
						{/if}
						{#if tecnicosHub.length === 0 || editForm.contacto === '__custom'}
							<input class="input" bind:value={editForm.contacto} placeholder="Nombre del contacto" />
						{/if}
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
				<div class="grid-4">
					<div class="field"><label>Hora inicio</label><input type="time" class="input" bind:value={editForm.fecha_inicio} /></div>
					<div class="field"><label>Hora fin</label><input type="time" class="input" bind:value={editForm.fecha_fin} /></div>
					<div class="field"><label>Traslado (h)</label><input type="number" step="0.5" min="0" class="input" bind:value={editForm.tiempo_traslado} /></div>
					<div class="field"><label>Comida</label><select class="input" bind:value={editForm.tiempo_comida}><option value="0">No</option><option value="1">Sí</option></select></div>
				</div>
				<div class="field">
					<label>Ingenieros Adicionales:</label>
					<div class="tech-grid">
						{#each tecnicosHub.filter(t => t !== editForm.tecnico) as t}
							<label class="tech-check">
								<input type="checkbox" checked={Array.isArray(editForm.tecnicos_adicionales) && editForm.tecnicos_adicionales.includes(t)} onchange={() => {
									if (!Array.isArray(editForm.tecnicos_adicionales)) editForm.tecnicos_adicionales = [];
									const idx = editForm.tecnicos_adicionales.indexOf(t);
									if (idx >= 0) editForm.tecnicos_adicionales.splice(idx, 1);
									else editForm.tecnicos_adicionales.push(t);
								}} />
								{t}
							</label>
						{/each}
					</div>
				</div>
				<div class="grid-2">
					<button class="btn btn-secondary btn-block" on:click={() => { editando = false; editForm = { ...editForm }; }}>❌ Cancelar</button>
					<button class="btn btn-primary btn-block" on:click={guardarCambios} disabled={busy}>💾 Guardar</button>
				</div>
			{:else}
				<div class="grid-2" style="font-size: 0.9rem;">
					<div><strong>Folio:</strong> {reporte.Folio}</div>
					<div><strong>Estatus:</strong> <span style="padding: 0.1rem 0.5rem; border-radius: 4px; background: {estatusColor(reporte.Estatus)}20; color: {estatusColor(reporte.Estatus)}; font-weight: 700; font-size: 0.8rem;">{reporte.Estatus || 'Borrador'}</span></div>
					<div><strong>Cliente:</strong> {reporte.Cliente}</div>
					<div><strong>Fecha:</strong> {reporte.Fecha ? String(reporte.Fecha).split('T')[0] : '-'}</div>
					<div><strong>Contacto:</strong> {reporte.Contacto || '-'}</div>
					<div><strong>Correo:</strong> {reporte.CorreoContacto || '-'}</div>
					<div><strong>Ingeniero:</strong> {reporte.Tecnico}</div>
					<div><strong>Máquina/Línea:</strong> {reporte.MaquinaLinea || '-'}</div>
					<div><strong>Inicio:</strong> {reporte.FechaHoraInicio ? String(reporte.FechaHoraInicio).slice(11, 16) : '-'}</div>
					<div><strong>Fin:</strong> {reporte.FechaHoraFin ? String(reporte.FechaHoraFin).slice(11, 16) : '-'}</div>
					<div><strong>Traslado:</strong> {reporte.TiempoTraslado || 0} h</div>
					<div><strong>Comida:</strong> {reporte.TiempoComida ? 'Sí' : 'No'}</div>
					<div><strong>Cotización:</strong> {reporte.Cotizacion || '-'}</div>
				</div>
				<div style="margin-top: 0.5rem;">
					<strong>Descripción:</strong>
					<div style="white-space: pre-wrap; margin-top: 0.25rem;">{reporte.DescripcionServicio || '-'}</div>
				</div>
				<div style="margin-top: 0.5rem;">
					<strong>Notas:</strong>
					<div style="white-space: pre-wrap; margin-top: 0.25rem; color: var(--color-text-muted);">{reporte.Notas || '-'}</div>
				</div>
				<div class="grid-3" style="margin-top: 0.75rem;">
					<button class="btn btn-primary btn-sm" on:click={() => { editForm = { ...editForm }; editando = true; }}>✏️ Editar</button>
					<button class="btn btn-secondary btn-sm" on:click={abrirPDF}>📄 Ver PDF</button>
					<button class="btn btn-danger btn-sm" on:click={eliminar} disabled={busy}>🚨 Eliminar</button>
				</div>
			{/if}
		</div>

		<!-- Ingenieros adicionales -->
		<div class="card" style="margin-bottom: 0.75rem;">
			<div class="card-title">👥 Ingenieros del reporte</div>
			<div style="font-size: 0.9rem;">
				<strong>Responsable:</strong> {reporte.Tecnico}
			</div>
			{#if tecnicos.length > 0}
				<div style="margin-top: 0.5rem;">
					<strong>Adicionales:</strong>
					<ul style="margin: 0.25rem 0 0 1.2rem; font-size: 0.85rem;">
						{#each tecnicos as t}
							{#if t !== reporte.Tecnico}
								<li>{t}</li>
							{/if}
						{/each}
					</ul>
				</div>
			{/if}
			{#if editando}
				<div class="field" style="margin-top: 0.5rem;">
					<label>Ingenieros Adicionales:</label>
					<div class="tech-grid">
						{#each tecnicosHub.filter(t => t !== editForm.tecnico) as t}
							<label class="tech-check">
								<input type="checkbox" checked={Array.isArray(editForm.tecnicos_adicionales) && editForm.tecnicos_adicionales.includes(t)} onchange={() => {
									if (!Array.isArray(editForm.tecnicos_adicionales)) editForm.tecnicos_adicionales = [];
									const idx = editForm.tecnicos_adicionales.indexOf(t);
									if (idx >= 0) editForm.tecnicos_adicionales.splice(idx, 1);
									else editForm.tecnicos_adicionales.push(t);
								}} />
								{t}
							</label>
						{/each}
					</div>
				</div>
			{/if}
		</div>

		<!-- Fotos -->
		<div class="card" style="margin-bottom: 0.75rem;">
			<div class="card-title">📸 Fotos ({fotos.length})</div>
			<div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.5rem;">
				<input type="file" accept="image/*" on:change={handleFileSelect} class="input" style="flex: 1; min-width: 180px;" disabled={busy} />
				<button class="btn btn-primary btn-sm" on:click={subirFoto} disabled={busy || !nuevaFoto}>📤 Subir</button>
			</div>
			{#if nuevaFotoPreview}
				<div style="margin-bottom: 0.5rem;">
					<img src={nuevaFotoPreview} alt="Preview" style="max-width: 200px; border-radius: 8px; border: 1px solid var(--color-border);" />
				</div>
			{/if}
			{#if fotos.length === 0}
				<p style="font-size: 0.85rem; color: var(--color-text-muted);">Sin fotos.</p>
			{:else}
				<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 0.5rem;">
					{#each fotos as f}
						<div style="position: relative; border: 1px solid var(--color-border); border-radius: 8px; overflow: hidden;">
							<img src="data:image/jpeg;base64,{f.base64}" alt="Foto {f.orden}" style="width: 100%; aspect-ratio: 4/3; object-fit: cover;" />
							<button class="btn btn-sm btn-danger" style="position: absolute; top: 4px; right: 4px; padding: 0.2rem 0.4rem; font-size: 0.7rem;" on:click={() => borrarFoto(f.id)}>🗑️</button>
						</div>
					{/each}
				</div>
			{/if}
		</div>

		<!-- Firma -->
		<div class="card" style="margin-bottom: 0.75rem;">
			<div class="card-title">✍️ Firma de conformidad {reporte.FirmaConformidad ? '(FIRMADO)' : ''}</div>
			{#if firmando}
				<canvas bind:this={canvasRef} width="100%" height="200" style="border: 1px solid var(--color-border); border-radius: 8px; background: #fff; touch-action: none;" on:pointerdown={onPointerDown} on:pointermove={onPointerMove} on:pointerup={onPointerUp} on:pointerleave={onPointerUp}></canvas>
				<div class="grid-3" style="margin-top: 0.5rem;">
					<button class="btn btn-secondary btn-sm" on:click={limpiarFirma}>🧹 Limpiar</button>
					<button class="btn btn-secondary btn-sm" on:click={() => firmando = false}>❌ Cancelar</button>
					<button class="btn btn-primary btn-sm" on:click={guardarFirma} disabled={busy}>💾 Guardar firma</button>
				</div>
			{:else if reporte.FirmaConformidad}
				<img src="data:image/png;base64,{reporte.FirmaConformidad}" alt="Firma" style="max-width: 100%; border: 1px solid var(--color-border); border-radius: 8px;" />
			{:else}
				<button class="btn btn-primary btn-block" on:click={startFirma} disabled={busy}>✍️ Firmar ahora</button>
			{/if}
		</div>

		<!-- Enviar PDF -->
		<div class="card">
			<div class="card-title">📧 Enviar PDF por email</div>
			<div class="grid-2" style="align-items: end;">
				<div class="field" style="margin-bottom: 0;">
					<label for="email_env">Destinatario</label>
					<input id="email_env" type="email" class="input" bind:value={emailEnviar} placeholder="cliente@dominio.com" />
				</div>
				<button class="btn btn-primary btn-sm" style="height: 38px;" on:click={enviarPDF} disabled={enviando || !emailEnviar.trim()}>📤 Enviar</button>
			</div>
			<p class="hint">Se adjunta el PDF del reporte. Si hay firma, se incluye en el PDF.</p>
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
	canvas { cursor: crosshair; }
</style>