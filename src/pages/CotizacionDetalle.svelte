<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { header, partidas, borrar, clonar, remisiones, remisionCrear, remisionBorrar, remisionAsignar, remisionUsuarios, remisionPdfDownload } from '$lib/cotizacionesApi.js';
	import { folioFmt, fmtMXN, totales, mapEstatus, COLOR_LABEL } from '$lib/cotizaciones.js';

	let { clave } = $props();

	let h = $state(null);
	let items = $state([]);
	let loading = $state(true);
	let error = $state('');
	let msg = $state('');
	let busy = $state(false);
	let mostrandoHistorial = $state(false);
	let historial = $state([]);
	let cargandoHistorial = $state(false);

	// --- Remisiones (port del HUB) ---
	let rems = $state([]);
	let mostrandoCrear = $state(false);
	let remRows = $state([]); // { incluida, partida, cantidad, descripcion }
	let remBusy = $state(false);
	let usuarios = $state([]);
	let asignandoId = $state(null); // id de remisión en modo asignar
	let asignSel = $state('');

	function tieneAcceso() {
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && u.acceso_cotizaciones);
		} catch {
			return false;
		}
	}

	let tots = $derived(totales(items));
	let bloqueado = $derived((h?.color ?? 0) === 1 || (h?.color ?? 0) === 2);
	let pendiente = $derived(!h || h.folio == null || !h.synced);

	async function cargarHistorial() {
		cargandoHistorial = true;
		try {
			const res = await fetch(`/api/cotizaciones/${h?.folio}/historial`, { headers: auth.authHeader() });
			const data = await res.json().catch(() => []);
			historial = Array.isArray(data) ? data : [];
		} catch (e) {
			historial = [];
		} finally {
			cargandoHistorial = false;
		}
	}

	async function abrirHistorial() {
		mostrandoHistorial = true;
		await cargarHistorial();
	}

	async function cargar() {
		loading = true;
		error = '';
		msg = '';
		try {
			h = await header(clave);
			items = await partidas(h.folio ?? h.idLocal);
			// Remisiones solo existen con folio real (online); sin folio queda vacío
			if (h.folio != null) {
				try {
					rems = await remisiones(h.folio);
				} catch {
					rems = [];
				}
			} else {
				rems = [];
			}
		} catch (e) {
			console.error('Error cargando detalle:', e);
			error = e.message === 'Sesión expirada' ? e.message : `No se pudo cargar (${e.message || 'sin conexión'}).`;
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

	async function onClonar() {
		if (!h || h.folio == null) {
			error = 'Primero sincroniza esta cotización para clonarla.';
			return;
		}
		if (!confirm(`¿Clonar ${folioFmt(h.folio)} con todas sus partidas?`)) return;
		busy = true;
		error = '';
		try {
			const r = await clonar(h.folio);
			navigate(`/cotizaciones/${r.folio ?? r.folioKey}`, { replace: true });
			await cargar();
		} catch (e) {
			error = e.message || 'No se pudo clonar.';
		} finally {
			busy = false;
		}
	}

	async function onBorrar() {
		if (!h || h.folio == null) {
			error = 'Solo se puede borrar online con folio asignado.';
			return;
		}
		if (!confirm(`¿Eliminar definitivamente ${folioFmt(h.folio)} y sus partidas? Es irreversible.`)) return;
		busy = true;
		error = '';
		try {
			await borrar(h.folio);
			navigate('/cotizaciones_materiales', { replace: true });
		} catch (e) {
			error = e.message || 'No se pudo eliminar. Revisa tu conexión.';
			busy = false;
		}
	}

	// ---- Remisiones (port del módulo del HUB) ----

	let remSelCount = $derived(remRows.filter((r) => r.incluida && (parseInt(r.cantidad, 10) || 0) >= 1).length);

	function abrirCrearRemision() {
		if (!h || h.folio == null) return;
		// Editor en línea: cantidades editables + checkbox para quitar partidas
		remRows = items.map((p) => ({
			incluida: true,
			partida: p.partida,
			cantidad: p.cantidad,
			descripcion: p.descripcion
		}));
		mostrandoCrear = true;
		error = '';
		msg = '';
	}

	function cancelarCrearRemision() {
		mostrandoCrear = false;
		remRows = [];
	}

	async function crearRemision() {
		const sel = remRows.filter((r) => r.incluida && (parseInt(r.cantidad, 10) || 0) >= 1);
		if (!sel.length) {
			error = 'Selecciona al menos una partida para la remisión.';
			return;
		}
		remBusy = true;
		error = '';
		msg = '';
		try {
			const r = await remisionCrear(
				h.folio,
				sel.map((s) => ({
					partida: s.partida,
					cantidad: parseInt(s.cantidad, 10) || 1,
					descripcion: s.descripcion
				}))
			);
			msg = `🎉 Remisión creada: ${r.folio}`;
			mostrandoCrear = false;
			remRows = [];
			rems = await remisiones(h.folio);
		} catch (e) {
			error = e.message || 'No se pudo crear la remisión.';
		} finally {
			remBusy = false;
		}
	}

	async function borrarRemision(r) {
		if (!confirm(`¿Eliminar la remisión ${r.folio}? Se borrará el índice y sus partidas (irreversible).`)) return;
		remBusy = true;
		error = '';
		msg = '';
		try {
			await remisionBorrar(r.id);
			msg = `Remisión ${r.folio} eliminada.`;
			rems = await remisiones(h.folio);
		} catch (e) {
			error = e.message || 'No se pudo eliminar la remisión.';
		} finally {
			remBusy = false;
		}
	}

	async function abrirAsignar(r) {
		asignandoId = asignandoId === r.id ? null : r.id;
		if (asignandoId !== r.id) return;
		asignSel = r.id_asignado ? String(r.id_asignado) : '';
		if (!usuarios.length) {
			try {
				usuarios = await remisionUsuarios();
			} catch (e) {
				error = e.message || 'No se pudieron cargar los usuarios.';
				asignandoId = null;
			}
		}
	}

	async function guardarAsignar(r) {
		remBusy = true;
		error = '';
		msg = '';
		try {
			await remisionAsignar(r.id, asignSel ? parseInt(asignSel, 10) : null);
			msg = asignSel ? '✅ Remisión asignada (firmará en Field).' : '✅ Asignación removida.';
			asignandoId = null;
			rems = await remisiones(h.folio);
		} catch (e) {
			error = e.message || 'No se pudo guardar la asignación.';
		} finally {
			remBusy = false;
		}
	}

	async function descargarRemisionPdf(r) {
		error = '';
		msg = '';
		try {
			await remisionPdfDownload(r.id, r.folio);
			msg = `📥 Descargando ${r.folio}.pdf`;
		} catch (e) {
			error = e.message || 'No se pudo generar el PDF.';
		}
	}
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" on:click={() => navigate('/cotizaciones_materiales')} title="Volver">⬅️</button>
		<h1>📋 {h ? folioFmt(h.folio ?? h.idLocal) : '…'}</h1>
		{#if pendiente}
			<span class="badge badge-warning">⏳ pendiente</span>
		{/if}
	</div>

	{#if loading}
		<div class="empty">Cargando…</div>
	{:else if error && !h}
		<div class="card"><p style="color: var(--color-danger); margin: 0;">{error}</p></div>
	{:else if h}
		<div class="card" style="margin-bottom: 0.75rem;">
			<div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.5rem;">
				<span class="badge {mapEstatus(h.estatus).includes('FACTURADA') ? 'badge-success' : mapEstatus(h.estatus).includes('LISTA') ? 'badge-warning' : 'badge-info'}">
					{COLOR_LABEL[h.color] || mapEstatus(h.estatus)}
				</span>
			</div>
			<p style="margin: 0.2rem 0;"><strong>Cliente:</strong> {h.cliente_nombre || h.cliente || h.id_cliente || 'N/A'}</p>
			<p style="margin: 0.2rem 0;"><strong>Contacto:</strong> {h.contacto || 'N/A'}</p>
			<p style="margin: 0.2rem 0;"><strong>Descripción:</strong> {h.descripcion || '—'}</p>
			<p style="margin: 0.2rem 0; color: var(--color-text-muted); font-size: 0.85rem;">
				Creado por {h.autor || '—'} · {h.fecha || ''}
			</p>
			<p style="margin: 0.4rem 0 0; font-size: 1.2rem; font-weight: 800; color: var(--color-primary-light);">
				Total: {fmtMXN(tots.total)}
			</p>
		</div>

		<div class="card" style="margin-bottom: 0.75rem;">
			<div class="card-title">📝 Nota interna</div>
			{#if (h.nota || '').trim()}
				<p style="margin: 0; font-size: 0.9rem;">{h.nota}</p>
			{:else}
				<p style="margin: 0; font-size: 0.85rem; color: var(--color-text-muted);">Sin notas registradas.</p>
			{/if}
		</div>

		<div class="card" style="margin-bottom: 0.75rem;">
			<div class="card-title">📦 Partidas ({items.length})</div>
			{#if items.length === 0}
				<p style="margin: 0; font-size: 0.85rem; color: var(--color-text-muted);">Sin partidas registradas.</p>
			{:else}
				<div class="list">
					{#each items as p (p.partida)}
						<div class="list-card" style="cursor: default;">
							<div style="flex: 1; min-width: 0;">
								<div style="font-size: 0.75rem; color: var(--color-text-muted);">
									#{p.partida} · cant. {p.cantidad}
									{#if !p.synced}<span class="badge badge-warning" style="font-size: 0.6rem;">⏳</span>{/if}
								</div>
								<div style="font-size: 0.9rem; font-weight: 600;">{p.descripcion}</div>
								<div style="font-size: 0.75rem; color: var(--color-text-muted);">{p.proveedor || 'Sin proveedor'}</div>
							</div>
							<div style="font-weight: 700; color: var(--color-primary-light); flex-shrink: 0;">{fmtMXN(p.total_venta)}</div>
						</div>
					{/each}
				</div>
			{/if}
			<div style="margin-top: 0.75rem; font-size: 0.9rem;">
				<div style="display: flex; justify-content: space-between;"><span style="color: var(--color-text-muted);">Subtotal</span><strong>{fmtMXN(tots.subtotal)}</strong></div>
				<div style="display: flex; justify-content: space-between;"><span style="color: var(--color-text-muted);">IVA 16%</span><strong>{fmtMXN(tots.iva)}</strong></div>
				<div style="display: flex; justify-content: space-between; font-size: 1.05rem;"><span>Total</span><strong style="color: var(--color-primary-light);">{fmtMXN(tots.total)}</strong></div>
			</div>
		</div>

		<div class="card" style="margin-bottom: 0.75rem;">
			<div class="card-title">🧾 Remisiones ({rems.length})</div>
			<p class="hint">Documento sin precios para entrega; el cliente lo firma en Field.</p>

			{#if mostrandoCrear}
				<div style="border: 1px solid var(--color-border, #334155); border-radius: 8px; padding: 0.6rem; margin-top: 0.5rem;">
					<p class="hint" style="margin-top: 0;">
						Edita cantidades y desmarca las partidas que NO van. Sin precios. Al crear queda inmutable (solo se puede borrar).
					</p>
					{#each remRows as row, i (row.partida)}
						<div style="display: flex; gap: 0.5rem; align-items: center; padding: 0.3rem 0; border-bottom: 1px solid rgba(148,163,184,0.15);">
							<input type="checkbox" bind:checked={row.incluida} aria-label="Incluir partida {row.partida}" />
							<span style="font-size: 0.75rem; color: var(--color-text-muted); width: 2.2rem;">#{row.partida}</span>
							<input type="number" class="input" min="1" step="1" style="width: 4.5rem;" bind:value={row.cantidad} disabled={!row.incluida} aria-label="Cantidad" />
							<span style="flex: 1; min-width: 0; font-size: 0.8rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{row.descripcion}</span>
						</div>
					{/each}
					<p class="hint" style="margin: 0.4rem 0;">Partidas incluidas: <strong>{remSelCount}</strong> de {remRows.length}</p>
					<div class="grid-2" style="margin-bottom: 0;">
						<button class="btn btn-secondary btn-block" on:click={cancelarCrearRemision} disabled={remBusy}>❌ Cancelar</button>
						<button class="btn btn-primary btn-block" on:click={crearRemision} disabled={remBusy || remSelCount === 0}>
							{remBusy ? 'Creando…' : '🧾 Crear remisión'}
						</button>
					</div>
				</div>
			{:else}
				{#if rems.length === 0}
					<p class="hint">Sin remisiones generadas aún.</p>
				{:else}
					<div class="list">
						{#each rems as r (r.id)}
							<div class="list-card" style="cursor: default; display: block;">
								<div style="display: flex; justify-content: space-between; gap: 0.5rem; flex-wrap: wrap;">
									<div style="min-width: 0;">
										<div style="font-weight: 700; font-size: 0.9rem;">{r.folio}</div>
										<div class="hint">Creado por: {r.creado_por} · {r.fecha}</div>
										{#if r.firmada}
											<div class="hint">✅ Firmada {r.fecha_firma}</div>
										{:else if r.asignado_nombre}
											<div class="hint">✍️ Firmará: <strong>{r.asignado_nombre}</strong></div>
										{:else}
											<div class="hint">👤 Sin asignar (Field)</div>
										{/if}
									</div>
									<div style="display: flex; gap: 0.35rem; flex-shrink: 0; align-items: flex-start;">
										<button class="btn btn-sm btn-secondary" on:click={() => descargarRemisionPdf(r)} disabled={remBusy} title="Descargar PDF">📥</button>
										<button class="btn btn-sm btn-secondary" on:click={() => abrirAsignar(r)} disabled={remBusy} title="Asignar usuario para firmar en Field">👤</button>
										<button class="btn btn-sm btn-danger" on:click={() => borrarRemision(r)} disabled={remBusy} title="Eliminar remisión">🗑️</button>
									</div>
								</div>
								{#if asignandoId === r.id}
									<div style="display: flex; gap: 0.4rem; margin-top: 0.5rem; align-items: center;">
										<select class="input" bind:value={asignSel} style="flex: 1;" aria-label="Usuario para firma">
											<option value="">-- Sin asignar --</option>
											{#each usuarios as u (u.id)}
												<option value={String(u.id)}>{u.nombre} ({u.email})</option>
											{/each}
										</select>
										<button class="btn btn-sm btn-primary" on:click={() => guardarAsignar(r)} disabled={remBusy}>💾</button>
									</div>
								{/if}
							</div>
						{/each}
					</div>
				{/if}
				<button class="btn btn-primary btn-block" style="margin-top: 0.6rem;" on:click={abrirCrearRemision} disabled={bloqueado || pendiente || remBusy || items.length === 0}>
					➕ Nueva remisión
				</button>
				{#if pendiente}
					<p class="hint" style="margin-top: 0.35rem;">⏳ Se habilita al sincronizar la cotización (necesita folio real).</p>
				{/if}
			{/if}
		</div>

		{#if error}
			<div class="msg err">{error}</div>
		{/if}
		{#if msg}
			<div class="msg ok">{msg}</div>
		{/if}

		<div class="grid-2" style="margin-bottom: 0.5rem;">
			<button class="btn btn-primary btn-block" on:click={() => navigate(`/cotizaciones/${clave}/pdf`)} disabled={busy}>👁️ Previsualizar PDF</button>
			<button class="btn btn-secondary btn-block" on:click={() => navigate(`/cotizaciones/${clave}/enviar`)} disabled={busy}>📧 Enviar</button>
		</div>
		<div class="grid-2" style="margin-bottom: 0.5rem;">
			<button class="btn btn-primary btn-block" on:click={() => navigate(`/cotizaciones/${clave}/partidas`)} disabled={bloqueado || busy}>📝 Partidas</button>
			<button class="btn btn-secondary btn-block" on:click={() => navigate(`/cotizaciones/${clave}/editar`)} disabled={bloqueado || busy}>✏️ Modificar</button>
		</div>
		<div class="grid-2" style="margin-bottom: 0.5rem;">
			<button class="btn btn-secondary btn-block" on:click={() => navigate(`/cotizaciones/${clave}/nota`)} disabled={busy}>📝 Nota</button>
			<button class="btn btn-secondary btn-block" on:click={onClonar} disabled={busy}>🐑 Clonar</button>
		</div>
		<button class="btn btn-secondary btn-block" style="margin-bottom: 0.5rem;" on:click={() => navigate(`/cotizaciones/${clave}/estatus`)} disabled={busy}>🚦 Cambiar estatus</button>
		<button class="btn btn-danger btn-block" on:click={onBorrar} disabled={bloqueado || busy}>🚨 Borrar cotización</button>
		{#if bloqueado}
			<p class="hint" style="margin-top: 0.5rem;">🔒 Bloqueada (lista para facturar / facturada).</p>
		{/if}
	{/if}
	{#if mostrandoHistorial}
		<div class="modal-overlay" on:click={() => mostrandoHistorial = false}>
			<div class="modal" on:click|stopPropagation>
				<div class="modal-header">
					<h3>📜 Historial de cambios</h3>
					<button class="btn btn-sm btn-secondary" on:click={() => mostrandoHistorial = false}>✕</button>
				</div>
				{#if cargandoHistorial}
					<div class="empty">Cargando historial…</div>
				{:else if historial.length === 0}
					<div class="empty">Sin cambios registrados.</div>
				{:else}
					<div class="historial-list">
						{#each historial as h (h.fecha)}
							<div class="historial-item">
								<div class="historial-meta">
									<span class="historial-user">{h.usuario}</span>
									<span class="historial-fecha">{h.fecha}</span>
								</div>
								<div class="historial-accion">{h.accion}</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		</div>
	{/if}

</div>

<style>
	.card-title { font-weight: 700; font-size: 1rem; margin-bottom: 0.25rem; }
	.msg { padding: 0.6rem 0.75rem; border-radius: 8px; font-size: 0.85rem; margin-bottom: 0.75rem; }
	.msg.err { background: rgba(239,68,68,0.1); color: #EF4444; }
	.msg.ok { background: rgba(34,197,94,0.1); color: #22C55E; }
	.hint { font-size: 0.8rem; color: var(--color-text-muted); }
	.card { margin-bottom: 0.75rem; }
	.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); backdrop-filter: blur(4px); z-index: 9999; display: flex; align-items: center; justify-content: center; padding: 1rem; }
	.modal { width: 90%; max-width: 600px; max-height: 80vh; background: #1e293b; border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; overflow: hidden; display: flex; flex-direction: column; }
	.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem 1.25rem; border-bottom: 1px solid rgba(255,255,255,0.1); }
	.modal-header h3 { margin: 0; font-size: 1.1rem; color: #f1f5f9; }
	.historial-list { padding: 1rem; overflow-y: auto; flex: 1; }
	.historial-item { padding: 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.05); }
	.historial-meta { display: flex; justify-content: space-between; margin-bottom: 0.25rem; }
	.historial-user { font-weight: 600; color: #FFAE00; font-size: 0.8rem; }
	.historial-fecha { font-size: 0.7rem; color: #64748b; }
	.historial-accion { font-size: 0.85rem; color: #e2e8f0; }
</style>
