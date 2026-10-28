<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { api } from '$lib/api.js';
	import OfflineNotice from '$lib/components/OfflineNotice.svelte';

	// Módulo Kilómetros — dos pestañas:
	//  1) Consumo: por automóvil, km de la semana (último registro − primero) y
	//     vales consumidos (tickets de Field) con su monto (todos son $500).
	//  2) Captura: odómetro por automóvil con fecha y hora (1 registro por día).
	// Los datos salen de HUB_RegistroKilometros, la MISMA tabla que escribe el
	// HUB y Field: lo que se captura en cualquiera de las apps se ve aquí.
	// Las tarjetas usan el mismo lenguaje visual que Tickets de OxxoGas.

	let tab = $state('consumo');
	let loading = $state(true);
	let error = $state('');
	let msg = $state('');

	// ── Consumo ───────────────────────────────────────────────────────────────
	let consumo = $state(null);
	let vehiculos = $state([]);
	let recientes = $state([]);

	// El detalle del vehículo NO es popup: la tarjeta navega a la página
	// /kilometros/vehiculo/:id (ver src/pages/KilometroVehiculo.svelte).

	// ── Captura ───────────────────────────────────────────────────────────────
	let selVehiculo = $state('');
	let km = $state(null);
	let fechaHora = $state('');
	let busy = $state(false);

	function tieneAcceso() {
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && u.acceso_registro_kilometros);
		} catch {
			return false;
		}
	}

	function fmtNum(v) {
		return Number(v || 0).toLocaleString('es-MX');
	}

	function fmtMXN(v) {
		return '$' + Number(v || 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	}

	// 'YYYY-MM-DDTHH:MM' SIEMPRE en hora de México (fijo UTC−6), sin importar
	// la zona del dispositivo: si se usara la hora local de un navegador en UTC
	// el registro quedaría guardado 6 horas adelantado.
	function ahoraLocalInput() {
		const f = new Intl.DateTimeFormat('en-CA', {
			timeZone: 'America/Mexico_City',
			year: 'numeric', month: '2-digit', day: '2-digit',
			hour: '2-digit', minute: '2-digit', hour12: false
		});
		const g = {};
		for (const p of f.formatToParts(new Date())) g[p.type] = p.value;
		return `${g.year}-${g.month}-${g.day}T${g.hour === '24' ? '00' : g.hour}:${g.minute}`;
	}

	// La BD guarda hora de México SIN offset. Se renderiza tal cual (componentes
	// del string) para que la hora se vea igual en cualquier dispositivo.
	function fmtFecha(iso) {
		if (!iso) return '—';
		const s = String(iso);
		const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
		if (m) return `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}`;
		const d = new Date(s);
		if (isNaN(d.getTime())) return '—';
		const p = (x) => String(x).padStart(2, '0');
		return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
	}

	let vehiculoSel = $derived(vehiculos.find((v) => String(v.id) === String(selVehiculo)) || null);

	// Semana ISO de una fecha (algoritmo estándar: el jueves define el año).
	function isoWeekOf(date) {
		const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
		const dia = d.getUTCDay() || 7;
		d.setUTCDate(d.getUTCDate() + 4 - dia);
		const inicioAnio = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
		return { anio: d.getUTCFullYear(), semana: Math.ceil(((d - inicioAnio) / 86400000 + 1) / 7) };
	}

	async function cargarTodo() {
		loading = true;
		error = '';
		try {
			// api.get: red -> IndexedDB -> copia local (el consumo también abre sin red).
			consumo = await api.get('/kilometros/consumo');
			vehiculos = (await api.get('/kilometros/vehiculos')) || [];
			recientes = (await api.get('/kilometros/recientes?n=15')) || [];
			if (!selVehiculo && vehiculos.length) {
				selVehiculo = String(vehiculos[0].id);
				km = vehiculos[0].km_actuales;
			}
		} catch (e) {
			error = e.message === 'Sesión expirada' ? e.message : e.message || 'No se pudo cargar.';
		} finally {
			loading = false;
		}
	}

	// Mover el rango de la semana. OJO: `semana.inicio` YA viene en ISO
	// ("2026-09-28T00:00:00"); concatenarle otro 'T00:00:00' producía una fecha
	// inválida y la petición salía como ?anio=NaN&semana=NaN (422).
	async function moverSemana(delta) {
		busy = true;
		error = '';
		try {
			const s = consumo?.semana;
			if (!s) return;
			const d = new Date(s.inicio);
			if (isNaN(d.getTime())) {
				error = 'No se pudo leer la semana actual.';
				return;
			}
			d.setDate(d.getDate() + delta * 7);
			const { anio, semana } = isoWeekOf(d);
			consumo = await api.get(`/kilometros/consumo?anio=${anio}&semana=${semana}`);
		} catch (e) {
			error = e.message || 'No se pudo cambiar de semana.';
		} finally {
			busy = false;
		}
	}

	function volverACurrent() {
		busy = true;
		api.get('/kilometros/consumo')
			.then((c) => (consumo = c))
			.catch((e) => (error = e.message))
			.finally(() => (busy = false));
	}

	function alElegirVehiculo() {
		// El odómetro nunca puede bajar: el mínimo es la última lectura.
		km = vehiculoSel ? vehiculoSel.km_actuales : null;
	}

	async function registrar() {
		error = '';
		msg = '';
		if (!selVehiculo) {
			error = 'Elige un automóvil.';
			return;
		}
		const valor = Number(km);
		if (km === null || km === undefined || km === '' || !Number.isFinite(valor)) {
			error = 'Escribe los kilómetros del odómetro.';
			return;
		}
		busy = true;
		try {
			const r = await api.post('/kilometros/registro', {
				id_automovil: Number(selVehiculo),
				kilometros: valor,
				fecha_hora: fechaHora || ahoraLocalInput()
			});
			msg = `✅ Kilometraje registrado: ${fmtNum(r.kilometros)} km — ${r.vehiculo}`;
			await cargarTodo();
		} catch (e) {
			error = e.message || 'No se pudo registrar.';
		} finally {
			busy = false;
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
		fechaHora = ahoraLocalInput();
		await cargarTodo();
	});
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" onclick={() => navigate('/dashboard')} title="Volver">⬅️</button>
		<h1>🛣️ Kilómetros</h1>
		<div style="flex:1"></div>
		<span class="count">{consumo ? consumo.vehiculos.length : 0} vehículos</span>
	</div>

	<OfflineNotice />

	<div class="tabs">
		<button class="tab" class:active={tab === 'consumo'} onclick={() => (tab = 'consumo')}>📊 Consumo semanal</button>
		<button class="tab" class:active={tab === 'captura'} onclick={() => (tab = 'captura')}>✍️ Capturar kilómetros</button>
	</div>

	{#if error}<div class="msg err">⚠️ {error}</div>{/if}
	{#if msg}<div class="msg ok">{msg}</div>{/if}

	{#if loading}
		<div class="state">⏳ Cargando…</div>
	{:else if tab === 'consumo'}
		<!-- ═══ CONSUMO ═══ -->
		{#if !consumo}
			<div class="state">Sin datos de consumo.</div>
		{:else}
			{@const r = consumo.resumen}
			<div class="semana-bar">
				<button class="btn btn-sm btn-secondary" onclick={() => moverSemana(-1)} disabled={busy} title="Semana anterior">◀</button>
				<div class="semana-txt">
					<div class="semana-lbl">Semana {consumo.semana.num} del {consumo.semana.anio}</div>
					<div class="semana-rango">{consumo.semana.etiqueta}</div>
				</div>
				<button class="btn btn-sm btn-secondary" onclick={() => moverSemana(1)} disabled={busy} title="Semana siguiente">▶</button>
				<button class="btn btn-sm btn-ghost" onclick={volverACurrent} disabled={busy}>Esta semana</button>
			</div>

			<div class="kpis">
				<div class="kpi">
					<div class="kpi-lbl">Consumo de la flota</div>
					<div class="kpi-val">{fmtNum(r.consumo_km)} <span class="kpi-unit">km</span></div>
					<div class="kpi-sub" class:subio={r.consumo_km > r.consumo_ant} class:bajo={r.consumo_km < r.consumo_ant}>
						{#if r.consumo_ant > 0}
							{r.consumo_km >= r.consumo_ant ? '▲' : '▼'} {fmtNum(Math.abs(r.consumo_km - r.consumo_ant))} km vs. semana anterior
						{:else}
							sin referencia de la semana anterior
						{/if}
					</div>
				</div>
				<div class="kpi">
					<div class="kpi-lbl">Vales consumidos</div>
					<div class="kpi-val">{fmtNum(r.vales)}</div>
					<div class="kpi-sub">{fmtMXN(r.monto_vales)} · {fmtMXN(consumo.monto_vale)} c/u</div>
				</div>
				<div class="kpi">
					<div class="kpi-lbl">Con lectura esta semana</div>
					<div class="kpi-val">{r.con_registro}<span class="kpi-unit">/{r.vehiculos}</span></div>
				</div>
			</div>

			<p class="hint">
				Consumo = último registro de la semana − primero. Con una sola lectura no hay diferencia
				posible, por eso la tarjeta marca “1 lectura”. Vales = tickets de gasolina capturados en Field
				(x {fmtMXN(consumo.monto_vale)} cada uno).
			</p>

			<!-- Tarjetas por automóvil (mismo estilo que Tickets de OxxoGas).
			     Solo los que tienen kilómetros registrados alguna vez. -->
			<div class="grid">
				{#each consumo.vehiculos.filter((v) => v.tiene_registros) as v (v.id)}
					{@const delta = v.consumo_km - v.consumo_ant}
					<button class="card-auto" class:sin-lectura={v.registros === 0}
						onclick={() => navigate(`/kilometros/vehiculo/${v.id}`)} title="Ver detalle del vehículo">
						<div class="body">
							<div class="folio">{v.placas || 'SIN PLACAS'}</div>
							<div class="fecha">{v.marca_modelo || '—'}</div>

							<div class="consumo">
								{#if v.comparable}
									<span class="consumo-num">{fmtNum(v.consumo_km)}</span><span class="consumo-unit">km esta semana</span>
								{:else}
									<span class="consumo-num apagado">—</span><span class="consumo-unit">sin lectura esta semana</span>
								{/if}
							</div>

							<div class="chips">
								<span class="chip vale">🎫 {v.vales} {v.vales === 1 ? 'ticket' : 'tickets'}</span>
								{#if v.registros > 0}
									<span class="chip ok">{v.registros} {v.registros === 1 ? 'lectura' : 'lecturas'}</span>
								{:else}
									<span class="chip pend">sin lectura esta semana</span>
								{/if}
								{#if v.consumo_ant > 0}
									<span class="chip" class:subio={delta > 0} class:bajo={delta < 0}>
										{delta > 0 ? '▲' : delta < 0 ? '▼' : '='} {fmtNum(Math.abs(delta))} vs. semana pasada
									</span>
								{/if}
								{#if v.requiere_servicio}
									<span class="chip warn">🔧 Requiere servicio</span>
								{/if}
							</div>

							{#if v.conductor}<div class="row">👤 {v.conductor}</div>{/if}
							<div class="row">🛞 Odómetro: {fmtNum(v.km_actuales)} km</div>
							{#if v.comparable}
								<div class="row">↔️ {fmtNum(v.ultimo_km_pasada)} → {fmtNum(v.ultimo_km)} (sem. pasada → esta)</div>
							{/if}
							{#if v.kms_desde_servicio !== null}
								<div class="row">🔧 {fmtNum(v.kms_desde_servicio)} km desde el último servicio</div>
							{/if}
							<div class="row ver">👆 Toca para ver lecturas y tickets</div>
						</div>
					</button>
				{/each}
			</div>

			{#if recientes.length}
				<h2 class="sub">🕐 Últimas capturas</h2>
				<div class="grid grid-chicas">
					{#each recientes as k (k.id)}
						<div class="card-auto">
							<div class="body">
								<div class="folio pequeno">{fmtNum(k.kilometros)} <span class="consumo-unit">km</span></div>
								<div class="fecha">{k.marca_modelo} · {k.placas}</div>
								<div class="chips">
									<span class="chip">{fmtFecha(k.fecha_hora)}</span>
									{#if k.usuario}<span class="chip">{k.usuario}</span>{/if}
								</div>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		{/if}
	{:else}
		<!-- ═══ CAPTURA ═══ -->
		<div class="card">
			<div class="card-title">✍️ Registrar odómetro</div>
			<div class="field">
				<label for="km-veh">Automóvil:</label>
				<select id="km-veh" class="input" bind:value={selVehiculo} onchange={alElegirVehiculo}>
					{#each vehiculos as v (v.id)}
						<option value={String(v.id)}>
							{v.marca_modelo} · {v.placas} — {fmtNum(v.km_actuales)} km{v.conductor ? ` (${v.conductor})` : ''}
						</option>
					{/each}
				</select>
				{#if vehiculoSel}
					<p class="hint" style="margin: 0.35rem 0 0;">
						Última lectura: <strong>{fmtNum(vehiculoSel.km_actuales)} km</strong>
						{vehiculoSel.ultima_lectura ? `(${fmtFecha(vehiculoSel.ultima_lectura)})` : '(sin registros)'} ·
						mínimo {fmtNum(vehiculoSel.km_actuales)} km
					</p>
				{/if}
			</div>
			<div class="grid-2">
				<div class="field">
					<label for="km-valor">Kilómetros del odómetro:</label>
					<input id="km-valor" class="input" type="number" min={vehiculoSel ? vehiculoSel.km_actuales : 0} step="1"
						bind:value={km} placeholder="Odómetro actual" />
				</div>
				<div class="field">
					<label for="km-fecha">Fecha y hora:</label>
					<input id="km-fecha" class="input" type="datetime-local" bind:value={fechaHora} />
				</div>
			</div>
			<button class="btn btn-primary btn-block" onclick={registrar} disabled={busy || !selVehiculo}>
				{busy ? 'Guardando…' : '💾 Registrar kilómetros'}
			</button>
			<p class="hint" style="margin: 0.6rem 0 0;">
				Un registro por automóvil por día. Lo capturado aquí o en el HUB aparece en la pestaña de consumo.
			</p>
		</div>
	{/if}
</div>

<style>
	.page { max-width: 1200px; margin: 0 auto; padding: 1rem; }
	.header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
	.header h1 { font-size: 1.25rem; margin: 0; color: #f1f5f9; }
	.count { font-size: 0.8rem; color: #94a3b8; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 999px; padding: 0.25rem 0.7rem; }
	.tabs { display: flex; gap: 0.25rem; border-bottom: 1px solid var(--color-border); margin-bottom: 1rem; }
	.tab { background: transparent; border: 0; border-bottom: 2px solid transparent; color: var(--color-text-muted);
		padding: 0.6rem 0.9rem; font: inherit; cursor: pointer; font-weight: 600; }
	.tab.active { color: #FFAE00; border-bottom-color: #FF6B00; }
	.tab:hover { color: #f1f5f9; }

	.msg { padding: 0.6rem 0.75rem; border-radius: 8px; font-size: 0.85rem; margin-bottom: 0.75rem; }
	.msg.err { background: rgba(239, 68, 68, 0.1); color: #f87171; }
	.msg.ok { background: rgba(34, 197, 94, 0.1); color: #4ade80; }
	.state { text-align: center; color: #94a3b8; padding: 3rem 1rem; font-size: 0.9rem; }
	.hint { font-size: 0.75rem; color: #64748b; margin: 0 0 0.9rem; }
	.hint strong { color: #FFAE00; }
	.sub { font-size: 0.95rem; color: #f1f5f9; margin: 1.4rem 0 0.6rem; }

	/* Barra de semana */
	.semana-bar { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.9rem; flex-wrap: wrap; }
	.semana-txt { text-align: center; min-width: 190px; }
	.semana-lbl { font-weight: 700; color: #f1f5f9; font-size: 0.9rem; }
	.semana-rango { font-size: 0.75rem; color: var(--color-text-muted); }
	.btn-ghost { background: transparent; border: 1px solid var(--color-border); color: var(--color-text-muted); }
	.btn-ghost:hover { color: #f1f5f9; }

	/* KPIs */
	.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 0.75rem; margin-bottom: 1rem; }
	.kpi { background: #1e293b; border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 14px; padding: 0.85rem 1rem; }
	.kpi-lbl { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: #94a3b8; font-weight: 700; }
	.kpi-val { font-size: 1.7rem; font-weight: 800; color: #f1f5f9; line-height: 1.2; }
	.kpi-unit { font-size: 0.9rem; color: #94a3b8; font-weight: 600; }
	.kpi-sub { font-size: 0.72rem; color: var(--color-text-muted); }
	.kpi-sub.subio { color: #fbbf24; }
	.kpi-sub.bajo { color: #4ade80; }

	/* Tarjetas (mismo estilo visual que Tickets de OxxoGas) */
	.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 0.9rem; }
	.grid-chicas { grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); }
	.card-auto { text-align: left; background: #1e293b; border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 14px;
		overflow: hidden; padding: 0; color: inherit; font: inherit; transition: transform 0.15s, border-color 0.15s; }
	.card-auto:hover { transform: translateY(-3px); border-color: rgba(255, 107, 0, 0.5); }
	.card-auto.sin-lectura { opacity: 0.72; }
	.body { padding: 0.75rem 0.85rem 0.9rem; }
	.folio { font-family: ui-monospace, 'Cascadia Mono', monospace; font-weight: 800; font-size: 1.05rem; color: #FFAE00; letter-spacing: 0.5px; }
	.folio.pequeno { font-size: 0.95rem; }
	.fecha { font-size: 0.72rem; color: #94a3b8; margin-top: 0.15rem; }
	.consumo { margin-top: 0.5rem; display: flex; align-items: baseline; gap: 0.3rem; }
	.consumo-num { font-size: 1.7rem; font-weight: 800; color: #f1f5f9; line-height: 1.1; }
	.consumo-num.apagado { color: #64748b; }
	.consumo-unit { font-size: 0.72rem; color: #94a3b8; font-weight: 600; }
	.chips { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.55rem; }
	.chip { font-size: 0.68rem; font-weight: 700; border-radius: 999px; padding: 0.22rem 0.6rem; border: 1px solid transparent;
		background: rgba(255, 255, 255, 0.06); color: #cbd5e1; }
	.chip.ok { color: #4ade80; background: rgba(74, 222, 128, 0.1); border-color: rgba(74, 222, 128, 0.25); }
	.chip.pend { color: #fbbf24; background: rgba(251, 191, 36, 0.1); border-color: rgba(251, 191, 36, 0.3); }
	.chip.vale { color: #93c5fd; background: rgba(147, 197, 253, 0.1); border-color: rgba(147, 197, 253, 0.25); }
	.chip.warn { color: #fca5a5; background: rgba(239, 68, 68, 0.12); border-color: rgba(239, 68, 68, 0.3); }
	.chip.subio { color: #fbbf24; background: rgba(251, 191, 36, 0.1); }
	.chip.bajo { color: #4ade80; background: rgba(74, 222, 128, 0.1); }
	.row { font-size: 0.75rem; color: #cbd5e1; margin-top: 0.4rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.row.ver { color: #64748b; font-size: 0.7rem; margin-top: 0.55rem; }
	.card-auto { cursor: pointer; }


	/* Captura */
	.card { background: #1e293b; border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 14px; padding: 1rem; }
	.card-title { font-weight: 700; color: #f1f5f9; margin-bottom: 0.75rem; }
	.field { margin-bottom: 0.75rem; }
	.field label { display: block; font-size: 0.78rem; color: #cbd5e1; margin-bottom: 0.3rem; }
	.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
	@media (max-width: 640px) { .grid-2 { grid-template-columns: 1fr; } }
</style>
