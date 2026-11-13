<script>
	import { onMount } from 'svelte';
	import { api } from '$lib/api.js';
	import { auth } from '$lib/stores/auth.js';
	// Admon no tiene toasts store; se usa alert()
	import { navigate } from '$lib/router.js';
	import ActionsBar from '$lib/components/ActionsBar.svelte';

	let { onSalir = null } = $props();

	let servicios = $state([]);
	let resumenData = $state(null);
	let cargando = $state(true);
	let error = $state('');
	let servicioSeleccionado = $state(null);
	let detalle = $state(null);
	let cargandoDetalle = $state(false);
	let autoRefresh = $state(true);
	let intervalo = null;

	const COLORES = {
		verde: '#22c55e',
		amarillo: '#eab308',
		rojo: '#ef4444',
		gris: '#6b7280',
	};

	const ICONOS_ESTATUS = {
		verde: '🟢',
		amarillo: '🟡',
		rojo: '🔴',
		gris: '⚪',
	};

	onMount(async () => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
		await cargar();
		if (autoRefresh) {
			intervalo = setInterval(cargar, 60000);
		}
		return () => {
			if (intervalo) clearInterval(intervalo);
		};
	});

	async function cargar() {
		try {
			const [servs, res] = await Promise.all([
				api.get('/estatus-servicios'),
				api.get('/estatus-servicios/resumen'),
			]);
			servicios = servs || [];
			resumenData = res;
			error = '';
		} catch (e) {
			error = e.message || 'Error al cargar servicios.';
		} finally {
			cargando = false;
		}
	}

	async function verDetalle(svc) {
		servicioSeleccionado = svc;
		cargandoDetalle = true;
		detalle = null;
		try {
			detalle = await api.get(`/estatus-servicios/${svc.id}`);
		} catch (e) {
			alert(e.message || 'Error al cargar detalle');
		} finally {
			cargandoDetalle = false;
		}
	}

	async function verificarAhora() {
		try {
			await api.post('/estatus-servicios/verificar');
			await cargar();
			if (servicioSeleccionado && detalle) {
				detalle = await api.get(`/estatus-servicios/${servicioSeleccionado.id}`);
			}
			alert('Verificación completada');
		} catch (e) {
			alert(e.message || 'Error');
		}
	}

	async function verificarUno(id) {
		try {
			const r = await api.post(`/estatus-servicios/verificar/${id}`);
			await cargar();
			if (servicioSeleccionado && servicioSeleccionado.id === id) {
				detalle = await api.get(`/estatus-servicios/${id}`);
			}
			alert(`Estatus: ${r.estatus}`);
		} catch (e) {
			alert(e.message || 'Error');
		}
	}

	function cerrarDetalle() {
		servicioSeleccionado = null;
		detalle = null;
	}

	function formatearTiempo(ms) {
		if (ms == null) return '—';
		if (ms < 1000) return `${ms}ms`;
		return `${(ms / 1000).toFixed(1)}s`;
	}
</script>

<div class="page">
	<div class="header">
		<div class="brand-col" style="display: flex; align-items: center; gap: 0.5rem;">
			<button class="btn btn-sm btn-secondary" onclick={() => navigate('/dashboard')} title="Volver">
				Volver
			</button>
			<h1 class="brand">📊 Estatus de Servicios</h1>
		</div>
		<ActionsBar onlogout={onSalir} />
	</div>

	{#if error}
		<div class="alert alert-warning">
			<span>{error}</span>
			<button class="btn btn-sm" onclick={cargar}>Reintentar</button>
		</div>
	{/if}

	<!-- Resumen global -->
	{#if resumenData}
		<div class="resumen-bar">
			<div class="resumen-item" style="color: {COLORES.verde}">
				<span class="resumen-num">{resumenData.verdes}</span>
				<span class="resumen-label">Operativos</span>
			</div>
			<div class="resumen-item" style="color: {COLORES.amarillo}">
				<span class="resumen-num">{resumenData.amarillos}</span>
				<span class="resumen-label">Degradados</span>
			</div>
			<div class="resumen-item" style="color: {COLORES.rojo}">
				<span class="resumen-num">{resumenData.rojos}</span>
				<span class="resumen-label">Caídos</span>
			</div>
			<div class="resumen-item" style="color: {COLORES.gris}">
				<span class="resumen-num">{resumenData.grises}</span>
				<span class="resumen-label">Sin datos</span>
			</div>
			<div class="resumen-actions">
				<button class="btn btn-sm btn-primary" onclick={verificarAhora} disabled={cargando}>
					{cargando ? 'Verificando...' : '🔄 Verificar todo'}
				</button>
				<label class="toggle-auto">
					<input type="checkbox" bind:checked={autoRefresh} />
					Auto 60s
				</label>
			</div>
		</div>
	{/if}

	{#if cargando && servicios.length === 0}
		<div class="empty">
			<div class="mb-spinner"></div>
			<p>Cargando servicios...</p>
		</div>
	{:else}
		<!-- Grid de tarjetas -->
		<div class="servicios-grid">
			{#each servicios as svc (svc.id)}
				<button class="servicio-card" onclick={() => verDetalle(svc)}
					style="border-left: 4px solid {COLORES[svc.estatus] || COLORES.gris}">
					<div class="svc-header">
						<span class="svc-icono">{svc.icono || '🔧'}</span>
						<span class="svc-estatus">{ICONOS_ESTATUS[svc.estatus] || '⚪'}</span>
					</div>
					<div class="svc-nombre">{svc.nombre}</div>
					<div class="svc-detalle">{svc.detalle || 'Sin datos'}</div>
					<div class="svc-footer">
						<span class="svc-tipo">{svc.tipo === 'externo' ? 'Externo' : 'Interno'}</span>
						{#if svc.tiempo_respuesta_ms}
							<span class="svc-ms">{formatearTiempo(svc.tiempo_respuesta_ms)}</span>
						{/if}
					</div>
				</button>
			{/each}
		</div>
	{/if}

	<!-- Modal de detalle -->
	{#if servicioSeleccionado}
		<div class="modal-overlay" onclick={cerrarDetalle}>
			<div class="modal-card" onclick={(e) => e.stopPropagation()}>
				<div class="modal-header">
					<h2>{servicioSeleccionado.icono} {servicioSeleccionado.nombre}</h2>
					<button class="btn-close" onclick={cerrarDetalle}>✕</button>
				</div>

				{#if cargandoDetalle}
					<div class="empty">
						<div class="mb-spinner"></div>
						<p>Cargando detalle...</p>
					</div>
				{:else if detalle}
					<!-- Estatus actual -->
					<div class="detalle-estatus" style="background: {COLORES[detalle.estatus]}20; border: 1px solid {COLORES[detalle.estatus]}">
						<span class="detalle-icono">{ICONOS_ESTATUS[detalle.estatus]}</span>
						<div>
							<div class="detalle-label">{detalle.estatus.toUpperCase()}</div>
							<div class="detalle-texto">{detalle.detalle}</div>
							<div class="detalle-meta">
								Último check: {detalle.ultimo_check || 'Nunca'} · 
								Tiempo: {formatearTiempo(detalle.tiempo_respuesta_ms)}
							</div>
						</div>
					</div>

					<!-- Botón verificar -->
					<div style="margin: 0.75rem 0;">
						<button class="btn btn-sm btn-primary" onclick={() => verificarUno(detalle.id)}>
							🔄 Verificar ahora
						</button>
						{#if detalle.url_status}
							<a class="btn btn-sm btn-secondary" href={detalle.url_status} target="_blank" rel="noopener">
								🔗 Página de status
							</a>
						{/if}
					</div>

					<!-- Incidencias activas -->
					{#if detalle.incidencias.filter(i => i.estatus === 'activa').length > 0}
						<h3 class="section-title">⚠️ Incidencias activas</h3>
						{#each detalle.incidencias.filter(i => i.estatus === 'activa') as inc}
							<div class="incidencia-card incidencia-activa">
								<div class="inc-titulo">{inc.titulo}</div>
								<div class="inc-desc">{inc.descripcion}</div>
								<div class="inc-meta">
									Inicio: {inc.fecha_inicio} · Fuente: {inc.fuente}
								</div>
							</div>
						{/each}
					{/if}

					<!-- Historial de checks -->
					<h3 class="section-title">📋 Historial (últimas 24h)</h3>
					<div class="historial-list">
						{#each detalle.historial.slice(0, 20) as h}
							<div class="historial-row">
								<span class="hist-icono">{ICONOS_ESTATUS[h.estatus]}</span>
								<span class="hist-fecha">{h.fecha}</span>
								<span class="hist-detalle">{h.detalle}</span>
								<span class="hist-ms">{formatearTiempo(h.tiempo_respuesta_ms)}</span>
							</div>
						{/each}
						{#if detalle.historial.length === 0}
							<p class="empty-text">Sin historial todavía</p>
						{/if}
					</div>

					<!-- Incidencias resueltas -->
					{#if detalle.incidencias.filter(i => i.estatus === 'resuelta').length > 0}
						<h3 class="section-title">✅ Incidencias resueltas</h3>
						{#each detalle.incidencias.filter(i => i.estatus === 'resuelta').slice(0, 10) as inc}
							<div class="incidencia-card incidencia-resuelta">
								<div class="inc-titulo">{inc.titulo}</div>
								<div class="inc-desc">{inc.descripcion}</div>
								<div class="inc-meta">
									Inicio: {inc.fecha_inicio} → Resuelta: {inc.fecha_resolucion}
								</div>
							</div>
						{/each}
					{/if}
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.brand-col { display: flex; flex-direction: column; gap: 0; }
	.brand { display: flex; align-items: center; gap: 0.5rem; margin: 0; font-size: 1.2rem; }

	.mb-spinner {
		width: 28px; height: 28px; margin: 0 auto 0.75rem;
		border: 3px solid var(--color-surface-2);
		border-top-color: var(--color-primary);
		border-radius: 50%;
		animation: mb-spin 0.8s linear infinite;
	}
	@keyframes mb-spin { to { transform: rotate(360deg); } }

	.alert { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.85rem 1rem; border-radius: var(--radius-sm); font-size: 0.85rem; margin-bottom: 1rem; }
	.alert-warning { background: rgba(234, 179, 8, 0.15); color: var(--color-warning, #eab308); }

	.resumen-bar {
		display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;
		padding: 0.75rem 1rem; margin-bottom: 1rem;
		background: var(--color-surface-1, #1e293b); border-radius: var(--radius-sm);
	}
	.resumen-item { display: flex; flex-direction: column; align-items: center; }
	.resumen-num { font-size: 1.5rem; font-weight: 700; }
	.resumen-label { font-size: 0.7rem; color: var(--color-text-muted); }
	.resumen-actions { margin-left: auto; display: flex; align-items: center; gap: 0.75rem; }
	.toggle-auto { font-size: 0.8rem; display: flex; align-items: center; gap: 0.3rem; }

	.servicios-grid {
		display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: 0.75rem;
	}
	.servicio-card {
		background: var(--color-surface-1, #1e293b);
		border-radius: var(--radius-sm, 8px);
		padding: 0.85rem; text-align: left; cursor: pointer;
		transition: transform 0.15s, box-shadow 0.15s;
		border: none;
	}
	.servicio-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
	.svc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem; }
	.svc-icono { font-size: 1.5rem; }
	.svc-estatus { font-size: 1.2rem; }
	.svc-nombre { font-weight: 600; font-size: 0.95rem; margin-bottom: 0.25rem; }
	.svc-detalle { font-size: 0.75rem; color: var(--color-text-muted); margin-bottom: 0.4rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.svc-footer { display: flex; justify-content: space-between; font-size: 0.7rem; color: var(--color-text-muted); }
	.svc-tipo { text-transform: capitalize; }
	.svc-ms { font-family: monospace; }

	.modal-overlay {
		position: fixed; inset: 0; background: rgba(0,0,0,0.6);
		display: flex; align-items: center; justify-content: center;
		z-index: 1000; padding: 1rem;
	}
	.modal-card {
		background: var(--color-surface-0, #0f172a);
		border-radius: 12px; padding: 1.25rem;
		max-width: 600px; width: 100%; max-height: 85vh; overflow-y: auto;
	}
	.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
	.modal-header h2 { margin: 0; font-size: 1.1rem; }
	.btn-close { background: none; border: none; font-size: 1.2rem; cursor: pointer; color: var(--color-text-muted); }

	.detalle-estatus {
		display: flex; gap: 0.75rem; align-items: center;
		padding: 0.75rem; border-radius: 8px; margin-bottom: 0.75rem;
	}
	.detalle-icono { font-size: 2rem; }
	.detalle-label { font-weight: 700; font-size: 1rem; }
	.detalle-texto { font-size: 0.85rem; color: var(--color-text-muted); }
	.detalle-meta { font-size: 0.75rem; color: var(--color-text-muted); margin-top: 0.25rem; }

	.section-title { font-size: 0.9rem; font-weight: 600; margin: 1rem 0 0.5rem; }

	.incidencia-card { padding: 0.6rem 0.75rem; border-radius: 6px; margin-bottom: 0.5rem; font-size: 0.85rem; }
	.incidencia-activa { background: rgba(239, 68, 68, 0.1); border: 1px solid #ef4444; }
	.incidencia-resuelta { background: rgba(34, 197, 94, 0.1); border: 1px solid #22c55e; }
	.inc-titulo { font-weight: 600; margin-bottom: 0.2rem; }
	.inc-desc { color: var(--color-text-muted); font-size: 0.8rem; }
	.inc-meta { font-size: 0.7rem; color: var(--color-text-muted); margin-top: 0.25rem; }

	.historial-list { max-height: 300px; overflow-y: auto; }
	.historial-row {
		display: flex; gap: 0.5rem; align-items: center;
		padding: 0.35rem 0; border-bottom: 1px solid var(--color-border, #334155);
		font-size: 0.8rem;
	}
	.hist-icono { font-size: 0.9rem; }
	.hist-fecha { font-family: monospace; font-size: 0.75rem; color: var(--color-text-muted); min-width: 110px; }
	.hist-detalle { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.hist-ms { font-family: monospace; font-size: 0.75rem; color: var(--color-text-muted); }

	.empty { text-align: center; padding: 2rem; color: var(--color-text-muted); }
	.empty-text { color: var(--color-text-muted); font-size: 0.85rem; }

	.btn { padding: 0.4rem 0.75rem; border-radius: 6px; border: none; cursor: pointer; font-size: 0.85rem; }
	.btn-primary { background: var(--color-primary, #3b82f6); color: white; }
	.btn-secondary { background: var(--color-surface-2, #334155); color: white; }
	.btn-sm { padding: 0.25rem 0.5rem; font-size: 0.8rem; }
	.btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>