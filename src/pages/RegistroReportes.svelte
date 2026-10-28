<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { api } from '$lib/api.js';
	import OfflineNotice from '$lib/components/OfflineNotice.svelte';
	import Paginacion from '$lib/components/Paginacion.svelte';

	// REGISTRO DE REPORTES (Admin) — clon del HUB views/registro_reportes.py
	// Lista global con pestañas: Firmados / 📊 Excel (exportación) / Papelera
	// Permiso: acceso_registro_reportes

	let lista = $state([]);
	let pagina = $state(1);
	let loading = $state(true);
	let error = $state('');
	let msg = $state('');
	let busqueda = $state('');
	let busy = $state(false);
	let tab = $state('firmados'); // 'firmados' | 'excel' | 'papelera'
	// IdReporte seleccionados en la pestaña Excel (la selección NO se mezcla
	// entre pestañas: cambiarTab la limpia).
	let seleccion = $state([]);
	let busyExcel = $state(false);

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

	let filtrados = $derived(
		lista.filter((r) => {
			const q = busqueda.trim().toLowerCase();
			if (!q) return true;
			return String(r.Folio || '').toLowerCase().includes(q) ||
				   String(r.Cliente || '').toLowerCase().includes(q) ||
				   String(r.Tecnico || '').toLowerCase().includes(q) ||
				   String(r.Contacto || '').toLowerCase().includes(q) ||
				   String(r.Cotizacion || '').toLowerCase().includes(q);
		})
	);

	// Tab firmados: solo firmados (FirmaConformidad no vacío) y no eliminados
	let firmados = $derived(filtrados.filter(r => 
		r.FirmaConformidad && String(r.FirmaConformidad).trim() !== '' && 
		(r.Eliminado === 0 || r.Eliminado === false || r.Eliminado === null || r.Eliminado === undefined)
	));

	// Tab papelera: eliminados (Eliminado = 1)
	let papelera = $derived(filtrados.filter(r => r.Eliminado === 1 || r.Eliminado === true));

	// Lista visible: la pestaña Excel exporta los MISMOS reportes firmados,
	// así que reutiliza la lista de la pestaña 🟢 Firmados.
	let listaTab = $derived(tab === 'papelera' ? papelera : firmados);

	const POR_PAGINA = 100;
	const pagActual = $derived(listaTab.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA));

	// Buscar o cambiar de pestaña deja al usuario en la primera página; si no,
	// puede quedarse viendo una página vacía de la lista ya filtrada.
	$effect(() => {
		busqueda;
		tab;
		pagina = 1;
	});

	// Total de horas de un reporte: (Fin − Inicio) + TiempoTraslado.
	// Misma fórmula que usa el backend para la columna B del Excel (2 cifras).
	function horasReporte(r) {
		if (!r || !r.FechaHoraInicio || !r.FechaHoraFin) return null;
		const h = (new Date(r.FechaHoraFin) - new Date(r.FechaHoraInicio)) / 3600000
			+ Number(r.TiempoTraslado || 0);
		return Math.round(h * 100) / 100;
	}

	// Cliente de la selección: lo fija el PRIMER reporte marcado; el resto
	// debe coincidir (el Excel solo admite reportes de un mismo cliente).
	let clienteSel = $derived(
		seleccion.length
			? String(lista.find(x => x.IdReporte === seleccion[0])?.Cliente || '').trim()
			: ''
	);

	let horasSel = $derived(
		seleccion.reduce((s, id) => s + (horasReporte(lista.find(x => x.IdReporte === id)) || 0), 0)
	);

	// Click en el checkbox de una card (pestaña Excel). Se decide ANTES de que
	// el navegador alterne `checked`: si no se permite, preventDefault() deja
	// la casilla como estaba; si se permite, se actualiza `seleccion` para que
	// coincida con el toggle nativo.
	function clicCheckbox(e, r) {
		e.stopPropagation();
		if (seleccion.includes(r.IdReporte)) {
			seleccion = seleccion.filter(x => x !== r.IdReporte);
			return;
		}
		if (horasReporte(r) === null) {
			e.preventDefault();
			error = `${r.Folio}: falta la hora de inicio o fin, no puede exportarse.`;
			msg = '';
			return;
		}
		const cli = String(r.Cliente || '').trim();
		if (seleccion.length && cli !== clienteSel) {
			e.preventDefault();
			error = `Solo reportes del mismo cliente. La selección es de: ${clienteSel}`;
			msg = '';
			return;
		}
		error = '';
		seleccion = [...seleccion, r.IdReporte];
	}

	function limpiarSeleccion() {
		seleccion = [];
		error = '';
		msg = '';
	}

	// Descarga el XLSX generado por /api/reportes/excel y lo guarda con el
	// nombre que trae el Content-Disposition (Reportes_<Cliente>_AAAA-MM-DD).
	async function descargarExcel() {
		if (!seleccion.length || busyExcel) return;
		error = '';
		msg = '';
		busyExcel = true;
		try {
			const res = await fetch(`/api/reportes/excel?ids=${seleccion.join(',')}`, {
				headers: auth.authHeader()
			});
			if (!res.ok) {
				const d = await res.json().catch(() => ({}));
				throw new Error(d.detail || 'No se pudo generar el Excel.');
			}
			const blob = await res.blob();
			const cd = res.headers.get('Content-Disposition') || '';
			const m = cd.match(/filename="?([^";]+)"?/);
			const nombre = (m && m[1]) || 'Reportes.xlsx';
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = nombre;
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			URL.revokeObjectURL(url);
			msg = `✅ ${seleccion.length} reportes exportados a ${nombre}.`;
			seleccion = [];
		} catch (e) {
			error = e.message || 'No se pudo generar el Excel.';
		} finally {
			busyExcel = false;
		}
	}

	async function cargar() {
		loading = true;
		error = '';
		try {
			const params = new URLSearchParams();
			if (tab === 'papelera') params.set('eliminados', 'true');
			// Lista con caché offline: red primero; sin red sirve la última
			// lista cacheada por el prefetch (mismo path/llave `?`).
			lista = (await api.get(`/reportes?${params}`)) || [];
			// Si se refrescó mientras había selección de Excel, descarta los ids
			// que ya no existan en la lista (evita 404 en la exportación).
			if (seleccion.length) {
				const validos = new Set(lista.map(x => x.IdReporte));
				seleccion = seleccion.filter(id => validos.has(id));
			}
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

	function formatearFecha(val) {
		if (!val) return 'Sin registrar';
		const d = new Date(val);
		if (isNaN(d)) return String(val);
		return d.toLocaleString('es-MX', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
	}

	function estatusHtml(est) {
		const v = String(est || 'Borrador');
		if (v === 'Borrador') return `<span class="badge" style="background:#475569;">📝 Borrador</span>`;
		if (v === 'Completado') return `<span class="badge" style="background:#0EA5E9;">🔵 Completado</span>`;
		if (v === 'Firmado') return `<span class="badge" style="background:#10B981;">🟢 Firmado</span>`;
		if (v === 'Cancelado') return `<span class="badge" style="background:#EF4444;">🔴 Cancelado</span>`;
		return `<span class="badge">${v}</span>`;
	}

	function verDetalle(r) {
		navigate(`/registro_reportes/${r.IdReporte}`);
	}

	async function moverAPapelera(r) {
		const folio = r.Folio;
		if (!confirm(`¿Mover a PAPELERA el reporte ${folio}?\n\nSe ocultará de la lista principal pero se podrá restaurar desde la pestaña "Papelera".\n\n¿Continuar?`)) return;
		error = '';
		msg = '';
		busy = true;
		try {
			const res = await fetch(`/api/reportes/${r.IdReporte}`, { method: 'DELETE', headers: auth.authHeader() });
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al mover a papelera.');
			msg = `🗑️ ${folio} movido a papelera.`;
			await cargar();
		} catch (e) {
			error = e.message || 'Error al mover a papelera.';
		} finally {
			busy = false;
		}
	}

	async function restaurar(r) {
		const folio = r.Folio;
		if (!confirm(`¿RESTAURAR el reporte ${folio}?\n\nVolverá a la lista de "Firmados".`)) return;
		error = '';
		msg = '';
		busy = true;
		try {
			const res = await fetch(`/api/reportes/${r.IdReporte}/restaurar`, { method: 'POST', headers: auth.authHeader() });
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al restaurar.');
			msg = `✅ ${folio} restaurado.`;
			await cargar();
		} catch (e) {
			error = e.message || 'Error al restaurar.';
		} finally {
			busy = false;
		}
	}

	async function eliminarDefinitivo(r) {
		const folio = r.Folio;
		if (!confirm(`⚠️ ELIMINACIÓN PERMANENTE ⚠️\n\n¿Borrar DEFINITIVAMENTE el reporte ${folio}?\n\n❌ NO SE PUEDE DESHACER\n❌ Se borran fotos, técnicos y todo el historial\n\nEscribe "ELIMINAR" para confirmar:`)) return;
		const input = prompt('Escribe "ELIMINAR" para confirmar borrado permanente:');
		if (input !== 'ELIMINAR') return;
		error = '';
		msg = '';
		busy = true;
		try {
			const res = await fetch(`/api/reportes/${r.IdReporte}/purge`, { method: 'DELETE', headers: auth.authHeader() });
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al eliminar permanentemente.');
			msg = `💀 ${folio} eliminado permanentemente.`;
			await cargar();
		} catch (e) {
			error = e.message || 'Error al eliminar permanentemente.';
		} finally {
			busy = false;
		}
	}

	function cambiarTab(nuevoTab) {
		tab = nuevoTab;
		// La selección de la pestaña Excel no debe cruzarse de pestaña.
		seleccion = [];
		error = '';
		msg = '';
		cargar();
	}
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" on:click={() => navigate('/dashboard')} title="Volver">⬅️</button>
		<h1>📋 Registro de Reportes</h1>
		<p class="subtitle">Visualización global de reportes de servicio técnico de todos los ingenieros.</p>
		<div style="flex:1"></div>
		<button class="btn btn-sm btn-secondary" on:click={cargar} title="Sincronizar">🔄</button>
	</div>

	<input class="input" placeholder="Buscar por cliente, folio, técnico, contacto, cotización…" bind:value={busqueda} style="margin-bottom: 0.75rem;" />

	<OfflineNotice />

	<!-- Tabs -->
	<div class="tabs" style="margin-bottom: 0.75rem; display: flex; gap: 0.25rem; border-bottom: 1px solid var(--color-border);">
		<button 
			class="tab-btn" 
			class:active={tab === 'firmados'}
			on:click={() => cambiarTab('firmados')}
			style="padding: 0.5rem 1rem; border: none; background: transparent; color: var(--color-text); font-weight: 600; border-bottom: 2px solid transparent; cursor: pointer;"
		>
			🟢 Firmados ({firmados.length})
		</button>
		<button 
			class="tab-btn" 
			class:active={tab === 'excel'}
			on:click={() => cambiarTab('excel')}
			style="padding: 0.5rem 1rem; border: none; background: transparent; color: var(--color-text); font-weight: 600; border-bottom: 2px solid transparent; cursor: pointer;"
		>
			📊 Excel ({firmados.length})
		</button>
		<button 
			class="tab-btn" 
			class:active={tab === 'papelera'}
			on:click={() => cambiarTab('papelera')}
			style="padding: 0.5rem 1rem; border: none; background: transparent; color: var(--color-text); font-weight: 600; border-bottom: 2px solid transparent; cursor: pointer;"
		>
			🗑️ Papelera ({papelera.length})
		</button>
	</div>

	<!-- Pestaña Excel: barra de selección + descarga del formato -->
	{#if tab === 'excel' && !loading}
		<div class="excel-bar">
			{#if clienteSel}
				<span class="chip" title="Cliente de la selección">
					👤 {clienteSel}
					<button class="chip-x" on:click={limpiarSeleccion} title="Vaciar selección">✕</button>
				</span>
			{/if}
			<span class="excel-cuenta">
				<strong>{seleccion.length}</strong> seleccionado{seleccion.length === 1 ? '' : 's'}
				· {horasSel.toFixed(2)} h
			</span>
			<div style="flex: 1"></div>
			<button
				class="btn btn-sm btn-primary"
				on:click={descargarExcel}
				disabled={busyExcel || seleccion.length === 0}
			>
				{busyExcel ? '⏳ Generando…' : `⬇️ Descargar Excel${seleccion.length ? ` (${seleccion.length})` : ''}`}
			</button>
		</div>
		<p class="excel-hint">
			Selecciona reportes del <strong>mismo cliente</strong> (solo 🟢 Firmados): cada uno se exporta en una
			fila con su consecutivo, horas totales (fin − inicio + traslado) y la descripción del servicio.
		</p>
	{/if}

	{#if loading}
		<div class="empty">Cargando…</div>
	{:else if listaTab.length === 0}
		<div class="empty">
			{#if tab === 'papelera'}
				Papelera vacía.
			{:else}
				No hay reportes firmados registrados.
			{/if}
		</div>
	{:else}
		<p style="color: var(--color-text-muted); font-size: 0.8rem; margin-bottom: 0.5rem;">
			Mostrando <strong>{listaTab.length}</strong> de <strong>{lista.length}</strong> reportes globales.
		</p>

		<!-- Contenido de la card (folio/estatus/cliente/datos): compartido por
		     la lista normal (botón → detalle) y la de Excel (label + checkbox). -->
		{#snippet cuerpo(r)}
			<div style="flex: 1;">
				<div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
					<span style="font-weight: 800; color: var(--color-primary-light);">{r.Folio}</span>
					{@html estatusHtml(r.Estatus)}
					{#if r.Eliminado === 1 || r.Eliminado === true}
						<span class="badge" style="background:#EF4444;">🗑️ Papelera</span>
					{/if}
				</div>
				<div style="font-size: 0.9rem; margin-top: 0.15rem;">{r.Cliente}</div>
				<div style="font-size: 0.75rem; color: var(--color-text-muted);">
					{r.Tecnico} · {formatearFecha(r.FechaHoraInicio)} · {r.MaquinaLinea || '—'}
				</div>
			</div>
			<div style="text-align: right; font-size: 0.75rem; color: var(--color-text-muted);">
				Cot: {r.Cotizacion || '—'}
				{#if tab === 'excel'}
					<div class="horas">{horasReporte(r) ?? '⚠️'}{horasReporte(r) != null ? ' h' : ' sin horas'}</div>
				{/if}
			</div>
		{/snippet}

		<div class="list">
			{#each pagActual as r (r.IdReporte)}
				{#if tab === 'excel'}
					<label class="list-card">
						<input
							type="checkbox"
							class="chk"
							checked={seleccion.includes(r.IdReporte)}
							on:click={(e) => clicCheckbox(e, r)}
						/>
						{@render cuerpo(r)}
					</label>
				{:else}
					<button class="list-card" on:click={() => verDetalle(r)}>
						{@render cuerpo(r)}
					</button>
				{/if}
			{/each}
			<Paginacion total={listaTab.length} bind:pagina porPagina={POR_PAGINA} etiqueta="reportes" />
		</div>
	{/if}

	{#if error}
		<div class="msg err">{error}</div>
	{/if}
	{#if msg}
		<div class="msg ok">{msg}</div>
	{/if}
</div>

<style>
	.subtitle { color: #94A3B8; font-size: 0.9rem; font-weight: 400; margin: 0; }
	.msg { padding: 0.6rem 0.75rem; border-radius: 8px; font-size: 0.85rem; margin-bottom: 0.75rem; }
	.msg.err { background: rgba(239,68,68,0.1); color: #EF4444; }
	.msg.ok { background: rgba(34,197,94,0.1); color: #22C55E; }
	.badge { padding: 0.1rem 0.5rem; border-radius: 12px; font-weight: 600; font-size: 0.7rem; color: #fff; }
	.tab-btn.active { color: var(--color-primary-light); border-bottom-color: var(--color-primary-light); }
	.tab-btn:hover:not(.active) { color: var(--color-text-muted); }

	/* ── Pestaña 📊 Excel: barra de selección, chips y ayudas ─────────── */
	.excel-bar {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
		padding: 0.65rem 0.75rem;
		background: var(--color-surface);
		border: 1px solid rgba(255, 255, 255, 0.06);
		border-radius: var(--radius);
		margin-bottom: 0.5rem;
	}
	.excel-cuenta { font-size: 0.85rem; color: var(--color-text-muted); }
	.excel-cuenta strong { color: var(--color-primary-light); }
	.excel-hint {
		font-size: 0.78rem;
		color: var(--color-text-muted);
		margin: 0 0 0.75rem;
		line-height: 1.45;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		background: rgba(255, 107, 0, 0.12);
		border: 1px solid rgba(255, 107, 0, 0.35);
		color: var(--color-primary-light);
		border-radius: 999px;
		padding: 0.15rem 0.65rem;
		font-size: 0.78rem;
		font-weight: 600;
	}
	.chip-x {
		background: transparent;
		border: none;
		color: inherit;
		cursor: pointer;
		font-size: 0.75rem;
		padding: 0 0.15rem;
		line-height: 1;
	}
	.chk {
		width: 1.25rem;
		height: 1.25rem;
		flex-shrink: 0;
		margin-right: 0.85rem;
		accent-color: var(--color-primary);
		cursor: pointer;
	}
	.horas {
		margin-top: 0.2rem;
		font-weight: 700;
		color: var(--color-primary-light);
		font-size: 0.78rem;
	}
</style>