<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { fechaLocal } from '$lib/fechas';
	import { navigate } from '$lib/router.js';
	import { api } from '$lib/api';
	import { auth } from '$lib/stores/auth';
	let msg = $state('');
	import { online } from '$lib/stores/online';
	import { Clock, MapPin, HelpCircle, FileText, ArrowLeft, CheckCircle, XCircle, Loader2, Timer, Download } from 'lucide-svelte';
	import CicloCard from '$lib/components/asistencia/CicloCard.svelte';
	import { agruparCiclos, resumenViatico } from '$lib/components/asistencia/ciclos.js';
	import { pasoAsistencia, registerPasskey, randomDeviceName } from '$lib/passkey.js';

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

	// Se sabe al cargar la página para no preguntarlo en medio del gesto del
	// botón: si falta, la passkey se crea ahí mismo con la huella o Face ID.
	let passkeyOk = $state<boolean | null>(null);
	let horarioDias = $state<any>(null);

	// Tarjetas por ciclo (entrada + salida) con horas extra según la LFT.
	let configLft = $state({ horas_jornada: 8, extras_max_dia: 3, extras_dobles_semana: 9 });
	// Oficina y umbral de viáticos: llegan de la API (HUB_Config) y aquí solo
	// se usan; los valores de arriba son el respaldo si la API no los manda.
	let oficina = $state({ lat: 25.662117, lon: -100.280684, viaticos_km: 50 });
	let relojMs = $state(Date.now());
	let ciclos = $derived(
		agruparCiclos(marcados, {
			horasJornada: Number(configLft.horas_jornada) || 8,
			extrasMaxDia: Number(configLft.extras_max_dia) || 3,
			extrasDoblesSemana: Number(configLft.extras_dobles_semana) || 9,
			ahora: new Date(relojMs),
			horario: horarioDias
		})
	);
	// Viáticos del día: la mayor distancia a la oficina entre los marcados con
	// GPS, contra el umbral (50 km por LISR art. 28-V).
	let viatico = $derived(
		resumenViatico(ciclos, { oficina, umbralKm: Number(oficina.viaticos_km) || 50 })
	);

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
		relojMs = Date.now();
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


	// Horario asignado: manda en las horas extra (solo el tiempo fuera de la
	// ventana del horario). Si no tiene, se cae al cálculo de la jornada.
	async function cargarHorario() {
		try {
			const r = await api.get('/mi-asistencia/horario');
			const dias = r?.dias || {};
			horarioDias = Object.fromEntries(
				Object.entries(dias).map(([k, v]) => [Number(k), v])
			);
		} catch {
			horarioDias = null;
		}
	}

	/** Deja `passkeyOk` resuelto antes de que el usuario toque el botón. */
	async function verificarPasskey() {
		try {
			const pks = await api.get('/passkeys/mine');
			passkeyOk = !!pks?.passkeys?.length;
		} catch {
			passkeyOk = null;
		}
	}

	async function cargarDatos() {
		loading = true;
		error = '';
		try {
			// En paralelo: son dos consultas independientes y el SQL está lento.
			const [hist, he] = await Promise.all([
				api.get('/mi-asistencia/historial?dias=30'),
				api.get('/mi-asistencia/horas-extras').catch(() => null)
			]);
			marcados = hist.registros || [];
			if (hist.config_lft) configLft = hist.config_lft;
			if (hist.oficina) oficina = hist.oficina;
			if (he) horasExtras = he;
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

	/** Pide la cámara DENTRO del gesto del usuario y reusa la misma promesa. */
	/**
	 * Deja una passkey lista. Si el usuario no tiene ninguna, se la crea aquí
	 * mismo: mandarlo a Configuración en medio del marcado no tiene sentido.
	 */
	async function asegurarPasskey(): Promise<boolean> {
		if (passkeyOk === true) return true;
		try {
			const pks = await api.get('/passkeys/mine');
			passkeyOk = !!pks?.passkeys?.length;
		} catch {
			error = 'No se pudo comprobar tu passkey. Revisa tu conexión.';
			return false;
		}
		if (passkeyOk) return true;

		msg = 'Crea tu passkey con la huella o Face ID del teléfono…';
		try {
			await registerPasskey(randomDeviceName());
			passkeyOk = true;
			msg = '';
			return true;
		} catch (e: any) {
			error = e?.message || 'No se pudo crear la passkey. Vuelve a intentar.';
			return false;
		}
	}

	async function marcar() {
		if (marking) return;
		marking = true;
		error = '';
		try {
			if (!(await asegurarPasskey())) return;
			try {
				await obtenerGPS();
			} catch {}

			// La passkey se firma ahora: así nadie marca por otro.
			const stepup_token = await pasoAsistencia();
			const tipo = timerActivo ? 'Salida' : 'Entrada';
			const res = await api.post('/mi-asistencia/marcar', {
				tipo, latitud: gpsLat, longitud: gpsLon, precision: gpsPrecision,
				verificacion_facial: false, stepup_token, dispositivo: navigator.userAgent
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
			error = e?.message || 'Error al marcar';
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
			const hoy = fechaLocal();
			const hace7 = fechaLocal(new Date(Date.now() - 7 * 86400000));
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
		verificarPasskey();
		cargarHorario();
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
			{#if ciclos.length === 0}
				<p class="empty">Sin marcados recientes</p>
			{:else}
				{#if !viatico.sinGps}
					<div class="chip-viatico" class:si={viatico.aplica}>
						<MapPin size={16} />
						<span>
							{viatico.aplica ? 'Viáticos posibles' : 'Sin viáticos'}
							· {viatico.maxKm.toFixed(1)} km de la oficina
						</span>
					</div>
				{/if}
				<div class="marking-list">
					{#each ciclos.slice(0, 10) as ciclo}
						<CicloCard {ciclo} horasJornada={Number(configLft.horas_jornada) || 8} {oficina} />
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
	.page { padding: 1rem; max-width: 600px; margin: 0 auto; 	padding-bottom: calc(var(--nav-h, 64px) + 1.5rem);
	}
	.header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
	.header h1 { font-size: var(--font-size-xl); font-weight: 700; flex: 1; }
	.card { background: var(--color-surface); border: 1px solid var(--color-line); border-radius: var(--radius-sm); padding: 1rem; margin-bottom: 1rem; }
	.card h2 { font-size: var(--font-size-base); font-weight: 600; margin-bottom: 0.75rem; color: var(--color-text-strong); }
	.checkin-section { display: flex; flex-direction: column; align-items: center; gap: 1rem; padding: 1.5rem 0; }
	.checkin-btn { width: 200px; height: 200px; border-radius: 50%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.5rem; font-size: var(--font-size-xl); font-weight: 800; cursor: pointer; border: none; transition: all 0.3s; box-shadow: 0 4px 20px rgba(0,0,0,0.15); }
	.checkin-btn.checkin { background: linear-gradient(135deg, var(--color-success), #16a34a); color: white; }
	.checkin-btn.checkin:hover { transform: scale(1.05); box-shadow: 0 6px 25px rgba(34,197,94,0.4); }
	.checkin-btn.checkout { background: linear-gradient(135deg, var(--color-danger), #dc2626); color: white; }
	.checkin-btn.checkout:hover { transform: scale(1.05); box-shadow: 0 6px 25px rgba(239,68,68,0.4); }
	.checkin-btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
	.btn-label { font-size: var(--font-size-lg); letter-spacing: 0.05em; }
	.timer-display { display: flex; align-items: baseline; gap: 0.5rem; }
	.timer-hours { font-size: 3.5rem; font-weight: 800; color: var(--color-surface); }
	.timer-unit { font-size: var(--font-size-xl); color: var(--color-text-dim); }
	.frase { font-size: var(--font-size-base); color: var(--color-text-dim); font-style: italic; text-align: center; max-width: 320px; padding: 0.5rem; }
	.gps-info { display: flex; align-items: center; gap: 0.25rem; font-size: var(--font-size-xs); color: var(--color-text-dim); }
	.gps-error { display: flex; align-items: center; gap: 0.25rem; font-size: var(--font-size-xs); color: var(--color-danger); }
	.stat-row { display: flex; justify-content: space-between; padding: 0.25rem 0; font-size: var(--font-size-sm); }
	.stat-label { color: var(--color-text-dim); }
	.stat-value { font-weight: 600; color: var(--color-surface); }
	.marking-list { display: flex; flex-direction: column; gap: 0.5rem; }
	.marking-item { display: flex; gap: 0.5rem; align-items: center; font-size: var(--font-size-xs); padding: 0.25rem 0; border-bottom: 1px solid var(--color-text-strong); }
	.marking-tipo { font-weight: 600; padding: 0.125rem 0.5rem; border-radius: 0.25rem; font-size: var(--font-size-xs); }
	.marking-tipo.entrada { background: var(--color-success-soft); color: #166534; }
	.marking-tipo.salida { background: var(--color-danger-soft); color: var(--color-danger-dark); }
	.marking-fecha { color: var(--color-text-dim); }
	.marking-hora { font-weight: 500; }
	.marking-gps { color: var(--color-info); }
	.empty { color: var(--color-text-muted); font-size: var(--font-size-sm); text-align: center; padding: 1rem; }
	.error-box { background: var(--color-danger-soft); color: var(--color-danger-dark); padding: 0.75rem; border-radius: 0.5rem; margin-bottom: 1rem; }
	.msg-box { background: var(--color-success-soft); color: #166534; padding: 0.75rem; border-radius: 0.5rem; margin-bottom: 1rem; }
	.loading { text-align: center; padding: 2rem; color: var(--color-text-muted); }
	.spin { animation: spin 1s linear infinite; }
	@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
	.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 1rem; }
	.modal { background: var(--color-surface); border: 1px solid var(--color-line); border-radius: var(--radius-sm); max-width: 500px; width: 100%; max-height: 80vh; overflow-y: auto; }
	.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem; border-bottom: 1px solid var(--color-text-soft); }
	.modal-header h2 { font-size: var(--font-size-lg); font-weight: 600; }
	.modal-body { padding: 1rem; }
	.calc-section { margin-bottom: 1rem; }
	.calc-section h3 { font-size: var(--font-size-sm); font-weight: 600; color: var(--color-info); margin-bottom: 0.5rem; }
	.calc-row { display: flex; justify-content: space-between; font-size: var(--font-size-xs); padding: 0.125rem 0; }
	.calc-note { font-size: var(--font-size-xs); color: var(--color-text-dim); margin-top: 0.5rem; border-top: 1px solid var(--color-text-soft); padding-top: 0.5rem; }
	.table-wrapper { overflow-x: auto; }
	.he-table { width: 100%; border-collapse: collapse; font-size: var(--font-size-xs); }
	.he-table th, .he-table td { padding: 0.375rem 0.5rem; border-bottom: 1px solid var(--color-text-soft); text-align: left; white-space: nowrap; }
	.he-table th { background: var(--color-text); font-weight: 600; color: var(--color-border); }
	.he-table .bold { font-weight: 600; }
	.reportes-list { display: flex; flex-direction: column; gap: 0.5rem; }
	.reporte-item { display: flex; justify-content: space-between; align-items: center; padding: 0.5rem; border-bottom: 1px solid var(--color-text-strong); font-size: var(--font-size-xs); }
	.reporte-info { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
	.badge { padding: 0.125rem 0.5rem; border-radius: 0.25rem; font-size: var(--font-size-2xs); font-weight: 600; }
	.badge.Generado { background: #dbeafe; color: #1e40af; }
	.badge.Pagado { background: var(--color-success-soft); color: #166534; }
	.badge.Cancelado { background: var(--color-danger-soft); color: var(--color-danger-dark); }
	/* Indicador de viáticos del día: informativo, no es un botón. */
	.chip-viatico {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		margin: 0 0 0.7rem;
		padding: 0.55rem 0.8rem;
		border-radius: var(--radius-sm);
		font-size: var(--font-size-sm);
		color: var(--color-text-muted);
		background: rgba(148, 163, 184, 0.12);
		border: 1px solid var(--color-line);
	}
	.chip-viatico.si {
		color: var(--color-warning);
		background: rgba(251, 191, 36, 0.10);
		border-color: rgba(251, 191, 36, 0.35);
	}
</style>
