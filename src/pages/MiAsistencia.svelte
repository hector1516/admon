<script lang="ts">
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { api } from '$lib/api';
	import { auth } from '$lib/stores/auth';
	let msg = $state('');
	import { online } from '$lib/stores/online';
	import { Clock, MapPin, HelpCircle, FileText, ArrowLeft, CheckCircle, XCircle, Loader2, Timer, Download } from 'lucide-svelte';

	let loading = $state(true);
	let marking = $state(false);
	let showHelp = $state(false);
	let error = $state('');

	let marcados = $state<any[]>([]);
	let horasExtras = $state<any>(null);
	let calculo = $state<any>(null);
	let loadingCalculo = $state(false);
	let generandoReporte = $state(false);
	let showOvertimeTable = $state(false);
	let showReportHistory = $state(false);
	let reportesGenerados = $state<any[]>([]);
	let loadingReportes = $state(false);

	let gpsLat = $state<number | null>(null);
	let gpsLon = $state<number | null>(null);
	let gpsPrecision = $state<number | null>(null);
	let gpsError = $state('');

	let timerActivo = $state(false);
	let horaEntradaActual = $state<Date | null>(null);
	let horasTrabajadas = $state('0.0');
	let fraseActual = $state('');
	let timerInterval: any;

	const frases = [
		{ min: 0, max: 1, text: 'Apenas calentando motores... ☕' },
		{ min: 1, max: 2, text: 'Todavía no es hora de quejarse... 😏' },
		{ min: 2, max: 3, text: 'Ya llevas un buen rato, ¿café? ☕' },
		{ min: 3, max: 4, text: 'El tiempo vuela cuando te diviertes... o cuando trabajas 😅' },
		{ min: 4, max: 5, text: 'Ya mereces un descanso, ¿no? 🛋️' },
		{ min: 5, max: 6, text: 'Esto ya es jornada completa, ¿eh? 💪' },
		{ min: 6, max: 7, text: 'Y todavía no terminas... 😤' },
		{ min: 7, max: 8, text: 'Jornada casi completa, ¡ánimo! 🎯' },
		{ min: 8, max: 9, text: 'Ya entraste en zona de horas extras... ⚠️' },
		{ min: 9, max: 10, text: 'Esto ya es sacrificio, ¿dónde está el pago? 💰' },
		{ min: 10, max: 12, text: '¿No tienes casa? 🏠' },
		{ min: 12, max: 24, text: 'Esto ya es heroico... o imprudente 🦸' },
	];

	function getFrase(horas: number): string {
		const h = frases.find(f => horas >= f.min && horas < f.max);
		return h ? h.text : '¡Leyenda del trabajo! 🏆';
	}

	function actualizarTimer() {
		if (!horaEntradaActual) return;
		const ahora = new Date();
		const diff = (ahora.getTime() - horaEntradaActual.getTime()) / 3600000;
		horasTrabajadas = diff.toFixed(1);
		fraseActual = getFrase(diff);
	}

	async function obtenerGPS() {
		if (!navigator.geolocation) return;
		try {
			const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
				navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 });
			});
			gpsLat = pos.coords.latitude;
			gpsLon = pos.coords.longitude;
			gpsPrecision = Math.round(pos.coords.accuracy);
		} catch {}
	}

	async function cargarDatos() {
		loading = true;
		error = '';
		try {
			const hist = await api.get('/mi-asistencia/historial?dias=30');
			marcados = hist.registros || [];
			const he = await api.get('/mi-asistencia/horas-extras');
			horasExtras = he;
			if (marcados.length > 0 && marcados[0].Tipo === 'Entrada') {
				const ultima = marcados[0];
				horaEntradaActual = new Date(ultima.Fecha + 'T' + ultima.Hora);
				timerActivo = true;
				actualizarTimer();
				timerInterval = setInterval(actualizarTimer, 60000);
			}
		} catch (e: any) {
			error = e.message || 'Error cargando datos';
		} finally {
			loading = false;
		}
	}

	async function cargarReportes() {
		loadingReportes = true;
		try {
			const res = await api.get('/mi-asistencia/horas-extras/reportes');
			reportesGenerados = res.reportes || [];
		} catch (e: any) {
			// silently fail
		} finally {
			loadingReportes = false;
		}
	}

	async function marcar() {
		marking = true;
		try {
			await obtenerGPS();
			const tipo = timerActivo ? 'Salida' : 'Entrada';
			const res = await api.post('/mi-asistencia/marcar', {
				tipo, latitud: gpsLat, longitud: gpsLon, precision: gpsPrecision,
				verificacion_facial: false, dispositivo: navigator.userAgent
			});
			msg = res.mensaje || `${tipo} registrada`;
			if (tipo === 'Entrada') {
				horaEntradaActual = new Date();
				timerActivo = true;
				actualizarTimer();
				timerInterval = setInterval(actualizarTimer, 60000);
			} else {
				timerActivo = false;
				clearInterval(timerInterval);
				horasTrabajadas = '0.0';
				fraseActual = '';
			}
			await cargarDatos();
		} catch (e: any) {
			error = e.message || 'Error al marcar';
		} finally {
			marking = false;
		}
	}

	async function cargarCalculo() {
		loadingCalculo = true;
		try {
			calculo = await api.get('/mi-asistencia/horas-extras/calculo');
		} catch (e: any) {
			error = e.message || 'Error cargando cálculo';
		} finally {
			loadingCalculo = false;
		}
	}

	async function abrirAyuda() {
		showHelp = true;
		if (!calculo) await cargarCalculo();
	}

	async function generarReporte() {
		generandoReporte = true;
		try {
			const hoy = new Date().toISOString().split('T')[0];
			const hace7 = new Date(Date.now() - 7 * 86400000).toISOString().split('T')[0];
			const res = await api.post('/mi-asistencia/horas-extras/generar-reporte', {
				periodo_inicio: hace7, periodo_fin: hoy, notas: ''
			});
			msg = `Reporte ${res.folio} generado. ${res.total_horas} horas quemadas.`;
			await cargarDatos();
			await cargarReportes();
		} catch (e: any) {
			error = e.message || 'Error generando reporte';
		} finally {
			generandoReporte = false;
		}
	}

	function verPdf(reporteId: number) {
		const token = (() => { try { return JSON.parse(localStorage.getItem('field_session') || '{}').token || ''; } catch { return ''; } })();
		window.open(`/api/mi-asistencia/horas-extras/reporte/${reporteId}/pdf?token=${encodeURIComponent(token)}`, '_blank');
	}

	onMount(() => {
		if (!$auth?.token) { navigate('/login'); return; }
		cargarDatos();
		cargarReportes();
		obtenerGPS();
		return () => { if (timerInterval) clearInterval(timerInterval); };
	});
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" onclick={() => navigate('/dashboard')}>
			<ArrowLeft size={16} />
		</button>
		<h1>Mi Asistencia</h1>
		<button class="btn btn-sm btn-secondary" onclick={abrirAyuda}>
			<HelpCircle size={16} />
		</button>
	</div>

	{#if msg}
		<div class="msg-box">{msg}</div>
	{/if}
	{#if error}
		<div class="error-box">{error}</div>
	{/if}

	{#if loading}
		<div class="loading">Cargando...</div>
	{:else}
		<!-- Check-in button -->
		<div class="checkin-section">
			<button class="checkin-btn {timerActivo ? 'checkout' : 'checkin'}" onclick={marcar} disabled={marking}>
				{#if marking}
					<Loader2 size={32} class="spin" />
				{:else if timerActivo}
					<XCircle size={48} />
					<span class="btn-label">CHECK OUT</span>
				{:else}
					<CheckCircle size={48} />
					<span class="btn-label">CHECK IN</span>
				{/if}
			</button>
			{#if timerActivo}
				<div class="timer-display">
					<Timer size={24} />
					<span class="timer-hours">{horasTrabajadas}</span>
					<span class="timer-unit">horas</span>
				</div>
				<div class="frase">{fraseActual}</div>
			{/if}
			{#if gpsLat}
				<div class="gps-info"><MapPin size={14} /> <span>±{gpsPrecision}m</span></div>
			{:else if gpsError}
				<div class="gps-error"><XCircle size={14} /> {gpsError}</div>
			{/if}
		</div>

		<!-- Overtime hours summary -->
		{#if horasExtras && (horasExtras.total_horas || 0) > 0}
			<div class="card">
				<h2>Horas Extras Pendientes</h2>
				<div class="stat-row"><span class="stat-label">Total acumulado:</span><span class="stat-value">{horasExtras.total_horas} hrs</span></div>
				<div class="stat-row"><span class="stat-label">Registros pendientes:</span><span class="stat-value">{horasExtras.total_registros}</span></div>
				<button class="btn btn-primary btn-sm" onclick={generarReporte} disabled={generandoReporte} style="margin-top: 0.75rem;">
					{#if generandoReporte}<Loader2 size={16} class="spin" />{:else}<FileText size={16} />{/if}
					Generar Reporte de Horas
				</button>
			</div>
		{/if}

		<!-- Overtime records table (all fields from Excel) -->
		{#if horasExtras && horasExtras.registros && horasExtras.registros.length > 0}
			<div class="card">
				<h2>Horas Extras (Detalle)</h2>
				<div class="table-wrapper">
					<table class="he-table">
						<thead>
							<tr>
								<th>Fecha</th><th>Entrada</th><th>Salida</th><th>Comida</th><th>Viaje</th><th>Hrs Extra</th><th>Cliente</th>
							</tr>
						</thead>
						<tbody>
							{#each horasExtras.registros as r}
								<tr>
									<td>{r.Fecha}</td>
									<td>{r.HoraEntrada || '-'}</td>
									<td>{r.HoraSalida || '-'}</td>
									<td>{r.HorasComida ?? '-'}</td>
									<td>{r.HorasTraslado ?? '-'}</td>
									<td class="bold">{r.HorasExtrasCalculadas}</td>
									<td>{r.Cliente || '-'}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{/if}

		<!-- Recent markings -->
		<div class="card">
			<h2>Últimos Marcados</h2>
			{#if marcados.length === 0}
				<p class="empty">Sin marcados recientes</p>
			{:else}
				<div class="marking-list">
					{#each marcados.slice(0, 10) as m}
						<div class="marking-item">
							<span class="marking-tipo {m.Tipo === 'Entrada' ? 'entrada' : 'salida'}">{m.Tipo}</span>
							<span class="marking-fecha">{m.Fecha}</span>
							<span class="marking-hora">{m.Hora}</span>
							{#if m.Latitud}<span class="marking-gps"><MapPin size={12} /></span>{/if}
						</div>
					{/each}
				</div>
			{/if}
		</div>

		<!-- Generated reports history -->
		{#if reportesGenerados.length > 0}
			<div class="card">
				<h2>Reportes Generados</h2>
				<div class="reportes-list">
					{#each reportesGenerados as r}
						<div class="reporte-item">
							<div class="reporte-info">
								<strong>{r.Folio}</strong>
								<span>{r.PeriodoInicio} - {r.PeriodoFin}</span>
								<span>{r.TotalHorasExtras} hrs</span>
								<span class="badge {r.Estatus}">{r.Estatus}</span>
							</div>
							<button class="btn btn-sm btn-secondary" onclick={() => verPdf(r.Id)}>
								<Download size={14} /> PDF
							</button>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	{/if}

	<!-- Help modal -->
	{#if showHelp}
		<div class="modal-overlay" onclick={() => showHelp = false}>
			<div class="modal" onclick={(e) => e.stopPropagation()}>
				<div class="modal-header">
					<h2>Cálculo de Horas Extras (LFT)</h2>
					<button class="btn btn-sm btn-secondary" onclick={() => showHelp = false}>✕</button>
				</div>
				<div class="modal-body">
					{#if loadingCalculo}
						<div class="loading">Cargando...</div>
					{:else if calculo}
						<div class="calc-section">
							<h3>Sueldo (informativo)</h3>
							<div class="calc-row"><span>Semanal:</span><span>${calculo.sueldo_semanal}</span></div>
							<div class="calc-row"><span>Diario:</span><span>${calculo.sueldo_diario}</span></div>
							<div class="calc-row"><span>Por hora:</span><span>${calculo.sueldo_hora}</span></div>
							<div class="calc-row"><span>Mensual:</span><span>${calculo.sueldo_mensual}</span></div>
							<div class="calc-row"><span>Anual:</span><span>${calculo.sueldo_anual}</span></div>
						</div>
						<div class="calc-section">
							<h3>Horas Extras Pendientes</h3>
							<div class="calc-row"><span>Total:</span><span>{calculo.horas_extras_pendientes} hrs</span></div>
							<div class="calc-row"><span>Dobles (2x):</span><span>{calculo.horas_extras_dobles} hrs</span></div>
							<div class="calc-row"><span>Triples (3x):</span><span>{calculo.horas_extras_triples} hrs</span></div>
						</div>
						<div class="calc-section">
							<h3>Configuración LFT ({calculo.config_lft?.anio})</h3>
							<div class="calc-row"><span>Jornada diurna máx:</span><span>{calculo.config_lft?.jornada_diurna_max}h</span></div>
							<div class="calc-row"><span>Jornada nocturna máx:</span><span>{calculo.config_lft?.jornada_nocturna_max}h</span></div>
							<div class="calc-row"><span>Horas extras dobles máx:</span><span>{calculo.config_lft?.horas_extras_dobles_max}h/semana</span></div>
							<div class="calc-row"><span>Límite HE/día:</span><span>{calculo.config_lft?.limite_he_dia}h</span></div>
							<div class="calc-row"><span>Límite HE/semana:</span><span>{calculo.config_lft?.limite_he_semana} veces</span></div>
							<div class="calc-row"><span>Prima dominical:</span><span>{(calculo.config_lft?.prima_dominical * 100)}%</span></div>
						</div>
						<div class="calc-note">
							<p><strong>Conforme a LFT vigente.</strong> {calculo.nota}</p>
							<p>Fecha de vigencia de la ley: {calculo.config_lft?.fecha_vigencia_ley}</p>
						</div>
					{/if}
				</div>
			</div>
		</div>
	{/if}
</div>

<style>
	.page { padding: 1rem; max-width: 600px; margin: 0 auto; }
	.header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
	.header h1 { font-size: 1.25rem; font-weight: 700; flex: 1; }
	.card { background: white; border-radius: 0.75rem; padding: 1rem; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
	.card h2 { font-size: 1rem; font-weight: 600; margin-bottom: 0.75rem; color: #1e293b; }
	.checkin-section { display: flex; flex-direction: column; align-items: center; gap: 1rem; padding: 1.5rem 0; }
	.checkin-btn { width: 200px; height: 200px; border-radius: 50%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.5rem; font-size: 1.25rem; font-weight: 800; cursor: pointer; border: none; transition: all 0.3s; box-shadow: 0 4px 20px rgba(0,0,0,0.15); }
	.checkin-btn.checkin { background: linear-gradient(135deg, #22c55e, #16a34a); color: white; }
	.checkin-btn.checkin:hover { transform: scale(1.05); box-shadow: 0 6px 25px rgba(34,197,94,0.4); }
	.checkin-btn.checkout { background: linear-gradient(135deg, #ef4444, #dc2626); color: white; }
	.checkin-btn.checkout:hover { transform: scale(1.05); box-shadow: 0 6px 25px rgba(239,68,68,0.4); }
	.checkin-btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
	.btn-label { font-size: 1.1rem; letter-spacing: 0.05em; }
	.timer-display { display: flex; align-items: baseline; gap: 0.5rem; }
	.timer-hours { font-size: 3.5rem; font-weight: 800; color: #1e293b; }
	.timer-unit { font-size: 1.2rem; color: #64748b; }
	.frase { font-size: 1rem; color: #64748b; font-style: italic; text-align: center; max-width: 320px; padding: 0.5rem; }
	.gps-info { display: flex; align-items: center; gap: 0.25rem; font-size: 0.75rem; color: #64748b; }
	.gps-error { display: flex; align-items: center; gap: 0.25rem; font-size: 0.75rem; color: #ef4444; }
	.stat-row { display: flex; justify-content: space-between; padding: 0.25rem 0; font-size: 0.875rem; }
	.stat-label { color: #64748b; }
	.stat-value { font-weight: 600; color: #1e293b; }
	.marking-list { display: flex; flex-direction: column; gap: 0.5rem; }
	.marking-item { display: flex; gap: 0.5rem; align-items: center; font-size: 0.8rem; padding: 0.25rem 0; border-bottom: 1px solid #f1f5f9; }
	.marking-tipo { font-weight: 600; padding: 0.125rem 0.5rem; border-radius: 0.25rem; font-size: 0.75rem; }
	.marking-tipo.entrada { background: #dcfce7; color: #166534; }
	.marking-tipo.salida { background: #fee2e2; color: #991b1b; }
	.marking-fecha { color: #64748b; }
	.marking-hora { font-weight: 500; }
	.marking-gps { color: #3b82f6; }
	.empty { color: #94a3b8; font-size: 0.875rem; text-align: center; padding: 1rem; }
	.error-box { background: #fee2e2; color: #991b1b; padding: 0.75rem; border-radius: 0.5rem; margin-bottom: 1rem; }
	.msg-box { background: #dcfce7; color: #166534; padding: 0.75rem; border-radius: 0.5rem; margin-bottom: 1rem; }
	.btn { display: inline-flex; align-items: center; gap: 0.375rem; padding: 0.5rem 1rem; border-radius: 0.5rem; font-weight: 500; cursor: pointer; border: none; font-size: 0.875rem; }
	.btn-primary { background: #3b82f6; color: white; }
	.btn-secondary { background: #e2e8f0; color: #334155; }
	.btn-sm { padding: 0.375rem 0.75rem; font-size: 0.8rem; }
	.btn:disabled { opacity: 0.5; cursor: not-allowed; }
	.loading { text-align: center; padding: 2rem; color: #94a3b8; }
	.spin { animation: spin 1s linear infinite; }
	@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
	.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 1rem; }
	.modal { background: white; border-radius: 0.75rem; max-width: 500px; width: 100%; max-height: 80vh; overflow-y: auto; }
	.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem; border-bottom: 1px solid #e2e8f0; }
	.modal-header h2 { font-size: 1.1rem; font-weight: 600; }
	.modal-body { padding: 1rem; }
	.calc-section { margin-bottom: 1rem; }
	.calc-section h3 { font-size: 0.875rem; font-weight: 600; color: #3b82f6; margin-bottom: 0.5rem; }
	.calc-row { display: flex; justify-content: space-between; font-size: 0.8rem; padding: 0.125rem 0; }
	.calc-note { font-size: 0.75rem; color: #64748b; margin-top: 0.5rem; border-top: 1px solid #e2e8f0; padding-top: 0.5rem; }
	.table-wrapper { overflow-x: auto; }
	.he-table { width: 100%; border-collapse: collapse; font-size: 0.75rem; }
	.he-table th, .he-table td { padding: 0.375rem 0.5rem; border-bottom: 1px solid #e2e8f0; text-align: left; white-space: nowrap; }
	.he-table th { background: #f8fafc; font-weight: 600; color: #475569; }
	.he-table .bold { font-weight: 600; }
	.reportes-list { display: flex; flex-direction: column; gap: 0.5rem; }
	.reporte-item { display: flex; justify-content: space-between; align-items: center; padding: 0.5rem; border-bottom: 1px solid #f1f5f9; font-size: 0.8rem; }
	.reporte-info { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
	.badge { padding: 0.125rem 0.5rem; border-radius: 0.25rem; font-size: 0.7rem; font-weight: 600; }
	.badge.Generado { background: #dbeafe; color: #1e40af; }
	.badge.Pagado { background: #dcfce7; color: #166534; }
	.badge.Cancelado { background: #fee2e2; color: #991b1b; }
</style>
