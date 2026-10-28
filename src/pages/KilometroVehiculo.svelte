<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { api } from '$lib/api.js';
	import OfflineNotice from '$lib/components/OfflineNotice.svelte';

	// Detalle de un vehículo como PÁGINA COMPLETA (ruta /kilometros/vehiculo/:id),
	// en lugar de un popup/overlay: patrón igual que TicketOxxoGasDetalle.
	// Muestra el odómetro, las últimas lecturas de kilometraje y los tickets
	// de OxxoGas del vehículo.

	let { id } = $props();

	let d = $state(null);
	let loading = $state(true);
	let error = $state('');

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

	// La BD guarda hora de México SIN offset ("YYYY-MM-DDTHH:MM:SS").
	// Se renderiza tal cual (componentes del string) para que la hora se vea
	// igual en cualquier dispositivo, sin pasar por la zona local del navegador.
	function fmtFecha(iso) {
		if (!iso) return '—';
		const s = String(iso);
		const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
		if (m) return `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}`;
		const d = new Date(s);
		if (isNaN(d.getTime())) return '—';
		const p = (n) => String(n).padStart(2, '0');
		return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
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
		try {
			d = await api.get(`/kilometros/vehiculo/${id}?n=40`);
		} catch (e) {
			error = e.message === 'Sesión expirada' ? e.message : e.message || 'No se pudo cargar el vehículo.';
		} finally {
			loading = false;
		}
	});
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" onclick={() => navigate('/kilometros')} title="Volver al módulo">⬅️</button>
		<h1>🛞 {d ? d.vehiculo.placas || 'SIN PLACAS' : 'Detalle del vehículo'}</h1>
		<div style="flex:1"></div>
		{#if d}<span class="count">{d.vehiculo.marca_modelo || '—'}</span>{/if}
	</div>

	<OfflineNotice />

	{#if loading}
		<div class="state">⏳ Cargando detalle…</div>
	{:else if error}
		<div class="state err">⚠️ {error}</div>
	{:else if d}
		{@const v = d.vehiculo}
		<div class="folio grande">{v.placas || 'SIN PLACAS'}</div>
		<div class="sub-modelo">{v.marca_modelo || '—'}{v.conductor ? ` · ${v.conductor}` : ''}</div>

		<div class="mini-kpis">
			<div class="mini"><div class="mini-lbl">Odómetro</div><div class="mini-val">{fmtNum(v.km_actuales)} km</div></div>
			<div class="mini"><div class="mini-lbl">Lecturas</div><div class="mini-val">{v.total_registros}</div></div>
			<div class="mini"><div class="mini-lbl">Tickets</div><div class="mini-val">{v.total_tickets}</div></div>
		</div>
		{#if v.kms_desde_servicio !== null}
			<p class="hint" style="margin: 0.4rem 0 0;">
				🔧 {fmtNum(v.kms_desde_servicio)} km desde el último servicio
				{#if v.requiere_servicio}<span class="chip warn" style="margin-left:.4rem;">requiere servicio</span>{/if}
				{#if v.poliza} · Póliza {v.poliza}{/if}
			</p>
		{/if}

		<h3 class="sub">🛞 Kilómetros registrados {#if v.total_registros > d.lecturas.length}({v.total_registros} en total, últimas {d.lecturas.length}){/if}</h3>
		{#if d.lecturas.length === 0}
			<p class="hint">Sin lecturas registradas.</p>
		{:else}
			<div class="lista">
				{#each d.lecturas as k (k.id)}
					<div class="item">
						<span class="item-fecha mono">{fmtFecha(k.fecha_hora)}</span>
						<span class="item-valor mono">{fmtNum(k.kilometros)} km</span>
						{#if k.usuario}<span class="item-extra">{k.usuario}</span>{/if}
					</div>
				{/each}
			</div>
		{/if}

		<h3 class="sub">🎫 Tickets registrados ({d.tickets.length})</h3>
		{#if d.tickets.length === 0}
			<p class="hint">Sin tickets registrados para este vehículo.</p>
		{:else}
			<div class="lista">
				{#each d.tickets as t (t.id)}
					<div class="item">
						<span class="item-fecha mono">{fmtFecha(t.fecha)}</span>
						<span class="item-valor mono">#{t.folio || '—'}</span>
						<span class="item-extra">{t.estacion || t.descripcion || t.cliente || '—'}</span>
					</div>
				{/each}
			</div>
		{/if}

		<button class="btn btn-secondary btn-back" onclick={() => navigate('/kilometros')}>⬅️ Volver al módulo de Kilómetros</button>
	{/if}
</div>

<style>
	.page { max-width: 860px; margin: 0 auto; padding: 1rem; }
	.header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
	.header h1 { font-size: 1.25rem; margin: 0; color: #f1f5f9; }
	.count { font-size: 0.8rem; color: #94a3b8; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 999px; padding: 0.25rem 0.7rem; }
	.state { text-align: center; color: #94a3b8; padding: 3rem 1rem; font-size: 0.9rem; }
	.state.err { color: #f87171; }
	.hint { font-size: 0.75rem; color: #64748b; margin: 0 0 0.9rem; }
	.sub { font-size: 0.95rem; color: #f1f5f9; margin: 1.4rem 0 0.6rem; }

	.folio { font-family: ui-monospace, 'Cascadia Mono', monospace; font-weight: 800; color: #FFAE00; letter-spacing: 0.5px; }
	.folio.grande { font-size: 1.3rem; }
	.sub-modelo { font-size: 0.8rem; color: #94a3b8; margin-top: 0.15rem; }

	.mini-kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; margin: 0.8rem 0 0.4rem; }
	.mini { background: #1e293b; border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 10px; padding: 0.5rem 0.6rem; }
	.mini-lbl { font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.05em; color: #94a3b8; font-weight: 700; }
	.mini-val { font-size: 1.05rem; font-weight: 800; color: #f1f5f9; }

	.chip { font-size: 0.68rem; font-weight: 700; border-radius: 999px; padding: 0.22rem 0.6rem; border: 1px solid transparent;
		background: rgba(255, 255, 255, 0.06); color: #cbd5e1; }
	.chip.warn { color: #fca5a5; background: rgba(239, 68, 68, 0.12); border-color: rgba(239, 68, 68, 0.3); }

	.lista { display: flex; flex-direction: column; gap: 0.3rem; }
	.item { display: flex; align-items: baseline; gap: 0.6rem; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 8px; padding: 0.4rem 0.6rem; font-size: 0.78rem; }
	.item-fecha { color: #94a3b8; min-width: 120px; }
	.item-valor { color: #FFAE00; font-weight: 700; min-width: 96px; text-align: right; }
	.item-extra { color: #cbd5e1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

	.btn-back { width: 100%; margin-top: 1.4rem; }
</style>
