<!-- CicloCard — un ciclo completo de Mi Asistencia (entrada + salida).
     La tarjeta es solo el resumen: al tocarla se abre el detalle del día con
     los dos marcados, sus mini mapas y el desglose de horas extra. -->
<script>
	import { LogIn, LogOut, MapPin, ShieldCheck, ShieldAlert, Fingerprint, ChevronRight, X } from 'lucide-svelte';
	import MiniMapa from './MiniMapa.svelte';
	import { formatoHoras, HORAS_JORNADA } from './ciclos.js';

	let { ciclo = {}, horasJornada = HORAS_JORNADA } = $props();

	const entrada = $derived(ciclo?.entrada || null);
	const salida = $derived(ciclo?.salida || null);
	const abierto = $derived(!!ciclo?.abierto);
	const olvidado = $derived(!!ciclo?.olvidado);
	const sinEntrada = $derived(!!ciclo?.sinEntrada);
	const rostro = $derived(!!(entrada?.VerificacionFacial || salida?.VerificacionFacial));
	const passkey = $derived(!!(entrada?.PasskeyCredentialId || salida?.PasskeyCredentialId));
	const estado = $derived(salida?.Estado || entrada?.Estado || 'Valido');

	const fecha = $derived(
		ciclo?.inicio
			? new Intl.DateTimeFormat('es-MX', { weekday: 'long', day: 'numeric', month: 'long' }).format(ciclo.inicio)
			: ''
	);

	let detalle = $state(false);
	const hora = (m) => (m?.Hora ? String(m.Hora).slice(0, 5) : '—');
	const tieneGps = (m) => m != null && m.Latitud != null && m.Longitud != null;
</script>

<div
	class="card ciclo-card"
	class:abierto
	class:olvidado
	role="button"
	tabindex="0"
	onclick={() => (detalle = true)}
	onkeydown={(e) => {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			detalle = true;
		}
	}}
	aria-label="Ver el detalle del {fecha}"
>
	<div class="ciclo-fecha">
		<span>{fecha}</span>
		<span class="estado-chip" class:en-curso={abierto} class:revisar={olvidado || estado !== 'Valido'}>
			{abierto ? (olvidado ? 'Sin salida' : 'En curso') : sinEntrada ? 'Salida sin entrada' : estado}
		</span>
	</div>

	<div class="ciclo-horas">
		<div class="tramo">
			<span class="tramo-titulo"><LogIn size={14} /> Entrada</span>
			<span class="tramo-hora">{hora(entrada)}</span>
		</div>
		<div class="flecha">→</div>
		<div class="tramo salida">
			<span class="tramo-titulo"><LogOut size={14} /> Salida</span>
			<span class="tramo-hora">{hora(salida)}</span>
		</div>
		<ChevronRight size={16} class="chevron" />
	</div>

	<div class="ciclo-totales">
		<span class="total">{formatoHoras(ciclo?.horas)}</span>
		<span class="jornada">de {formatoHoras(horasJornada)}</span>
		{#if ciclo?.extras > 0}
			<span class="extras">{formatoHoras(ciclo.extras)} extra</span>
		{/if}
	</div>
</div>

{#if detalle}
	<div class="modal-overlay" onclick={() => (detalle = false)} role="presentation">
		<div class="modal ciclo-modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
			<div class="modal-header">
				<h2>{fecha}</h2>
				<button class="btn btn-sm btn-secondary" onclick={() => (detalle = false)} aria-label="Cerrar">
					<X size={16} />
				</button>
			</div>

			<div class="detalle">
				{#each [{ m: entrada, t: 'Entrada' }, { m: salida, t: 'Salida' }] as par}
					<div class="marcado">
						<div class="marcado-head">
							<strong>{par.t}</strong>
							<span class="marcado-hora">{hora(par.m)}</span>
						</div>
						{#if par.m}
							<div class="chips">
								<span class="chip">
									<Fingerprint size={13} /> {par.m.PasskeyCredentialId ? 'Con passkey' : 'Sin passkey'}
								</span>
								{#if tieneGps(par.m)}
									<span class="chip"><MapPin size={13} /> ±{par.m.Precision ?? '?'} m</span>
								{:else}
									<span class="chip">Sin GPS</span>
								{/if}
								{#if par.m.Dispositivo}
									<span class="chip" title={par.m.Dispositivo}>
										{String(par.m.Dispositivo).slice(0, 26)}…
									</span>
								{/if}
							</div>
							{#if tieneGps(par.m)}
								<MiniMapa lat={par.m.Latitud} lon={par.m.Longitud} />
							{:else}
								<p class="sin-gps">Ese marcado no guardó ubicación.</p>
							{/if}
						{:else}
							<p class="sin-gps">Sin marcado.</p>
						{/if}
					</div>
				{/each}

				<div class="resumen">
					<div class="linea"><span>Horas trabajadas</span><strong>{formatoHoras(ciclo?.horas)}</strong></div>
					<div class="linea"><span>Jornada</span><span>{formatoHoras(horasJornada)}</span></div>
					{#if ciclo?.extras > 0}
						<div class="linea"><span>Horas extra</span><strong>{formatoHoras(ciclo.extras)}</strong></div>
						{#if ciclo?.dobles > 0}
							<div class="linea"><span>Dobles (LFT)</span><span>{formatoHoras(ciclo.dobles)}</span></div>
						{/if}
						{#if ciclo?.triples > 0}
							<div class="linea"><span>Triples (LFT)</span><span>{formatoHoras(ciclo.triples)}</span></div>
						{/if}
						{#if ciclo?.excede_limite_dia}
							<div class="linea aviso-lft"><span>Excede 3 h extra al día</span><span>LFT art. 66</span></div>
						{/if}
					{/if}
					<div class="linea">
						<span>Verificación</span>
						<span class="verif">
							{#if rostro}<ShieldCheck size={13} /> rostro{/if}
							{#if passkey}<Fingerprint size={13} /> passkey{/if}
							{#if !rostro && !passkey}<ShieldAlert size={13} /> sin verificar{/if}
						</span>
					</div>
				</div>
			</div>
		</div>
	</div>
{/if}

<style>
	.ciclo-card {
		cursor: pointer;
		margin-bottom: 0.6rem;
		transition: border-color 0.15s ease;
	}
	/* El popup se pinta solo: ni .modal-overlay ni .modal existen en todas
	   las apps, y sin position:fixed el detalle aparecía al final de la página
	   en vez de encima. */
	.modal-overlay {
		position: fixed;
		inset: 0;
		background: color-mix(in srgb, var(--color-ink) 72%, transparent);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
		z-index: 400;
		backdrop-filter: blur(2px);
	}
	/* El popup del detalle, con la superficie del tema: la clase .modal de cada
	   app se pintaba clara y en Mi Asistencia se veía un bloque blanco. */
	.ciclo-modal {
		background: var(--color-surface);
		color: var(--color-text-strong);
		border: 1px solid var(--color-line);
		width: calc(100% - 2rem);
		max-width: 26rem;
		max-height: 84vh;
		overflow-y: auto;
		padding: 1rem 1.1rem 1.1rem;
		border-radius: var(--radius-sm);
		font: inherit;
		box-shadow: 0 12px 40px color-mix(in srgb, var(--color-ink) 60%, transparent);
	}
	.ciclo-modal .modal-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}
	.ciclo-modal h2 {
		color: var(--color-text-strong);
		font-size: var(--font-size-lg);
		margin: 0;
	}
	.ciclo-card:hover {
		border-color: var(--color-text-dim);
	}
	.ciclo-card.abierto {
		border-color: var(--color-success);
	}
	.ciclo-card.olvidado {
		border-color: var(--color-warning);
	}
	.ciclo-fecha {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		font-size: var(--font-size-xs);
		color: var(--color-text-soft);
	}
	.ciclo-fecha > span:first-child::first-letter {
		text-transform: uppercase;
	}
	.estado-chip {
		font-size: var(--font-size-2xs);
		font-weight: 700;
		border-radius: 999px;
		padding: 0.1rem 0.45rem;
		background: var(--color-surface-2);
		color: var(--color-text-dim);
		text-transform: none;
	}
	.estado-chip.en-curso {
		background: color-mix(in srgb, var(--color-success) 18%, transparent);
		color: var(--color-success-light);
	}
	.estado-chip.revisar {
		background: color-mix(in srgb, var(--color-warning) 18%, transparent);
		color: var(--color-warning);
	}
	.ciclo-horas {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-top: 0.45rem;
	}
	.tramo {
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
	}
	.tramo.salida {
		text-align: right;
	}
	.tramo-titulo {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: var(--font-size-2xs);
		color: var(--color-text-dim);
		text-transform: uppercase;
	}
	.tramo.salida .tramo-titulo {
		justify-content: flex-end;
	}
	.tramo-hora {
		font-size: var(--font-size-lg);
		font-weight: 700;
		font-variant-numeric: tabular-nums;
	}
	.flecha {
		flex: 1;
		text-align: center;
		color: var(--color-text-dim);
	}
	.chevron {
		color: var(--color-text-dim);
		flex-shrink: 0;
	}
	.ciclo-totales {
		display: flex;
		align-items: baseline;
		gap: 0.45rem;
		margin-top: 0.5rem;
		font-size: var(--font-size-sm);
	}
	.total {
		font-weight: 700;
	}
	.jornada {
		color: var(--color-text-dim);
		font-size: var(--font-size-xs);
	}
	.extras {
		font-size: var(--font-size-xs);
		color: var(--color-info);
	}
	.detalle {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	.marcado {
		border-bottom: 1px solid var(--color-line);
		padding-bottom: 0.85rem;
	}
	.marcado:last-of-type {
		border-bottom: none;
		padding-bottom: 0;
	}
	.marcado-head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		font-size: var(--font-size-sm);
	}
	.marcado-hora {
		font-size: var(--font-size-lg);
		font-weight: 700;
		font-variant-numeric: tabular-nums;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
		margin-top: 0.35rem;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: var(--font-size-2xs);
		color: var(--color-text-dim);
		background: var(--color-surface-2);
		border-radius: 999px;
		padding: 0.15rem 0.5rem;
	}
	.sin-gps {
		margin: 0.35rem 0 0;
		font-size: var(--font-size-xs);
		color: var(--color-text-dim);
	}
	.resumen {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		font-size: var(--font-size-sm);
	}
	.linea {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 0.5rem;
		color: var(--color-text-soft);
	}
	.linea strong {
		color: var(--color-text-strong);
	}
	.aviso-lft {
		color: var(--color-warning);
	}
	.verif {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
	}
</style>
