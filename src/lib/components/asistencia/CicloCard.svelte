<!-- CicloCard — un ciclo completo de Mi Asistencia (entrada + salida).
     Una sola tarjeta por ciclo, con los datos de ese ciclo: horas, ubicación,
     horas extra según la LFT y cómo se verificó (rostro, passkey, GPS).
     Recibe un ciclo ya armado por `agruparCiclos()` (ciclos.js). -->
<script>
	import { LogIn, LogOut, MapPin, ShieldCheck, ShieldAlert, Fingerprint, Clock, TriangleAlert } from 'lucide-svelte';
	import MiniMapa from './MiniMapa.svelte';
	import { formatoHoras, HORAS_JORNADA } from './ciclos.js';

	let { ciclo = {}, horasJornada = HORAS_JORNADA } = $props();

	const entrada = $derived(ciclo?.entrada || null);
	const salida = $derived(ciclo?.salida || null);
	const abierto = $derived(!!ciclo?.abierto);
	const olvidado = $derived(!!ciclo?.olvidado);
	const sinEntrada = $derived(!!ciclo?.sinEntrada);
	const tieneGps = $derived(!!ciclo?.ubicacion);
	const rostro = $derived(!!(entrada?.VerificacionFacial || salida?.VerificacionFacial));
	const passkey = $derived(!!(entrada?.PasskeyCredentialId || salida?.PasskeyCredentialId));
	const estado = $derived(salida?.Estado || entrada?.Estado || 'Valido');
	const dispositivo = $derived(
		entrada?.Dispositivo || salida?.Dispositivo
			? String(entrada?.Dispositivo || salida?.Dispositivo).slice(0, 48)
			: null
	);

	const fecha = $derived(
		ciclo?.inicio
			? new Intl.DateTimeFormat('es-MX', {
					weekday: 'short',
					day: 'numeric',
					month: 'short'
				}).format(ciclo.inicio)
			: ''
	);
</script>

<div class="ciclo-card" class:abierto class:olvidado>
	<div class="ciclo-fecha">
		<span>{fecha}</span>
		{#if abierto}
			<span class="estado-chip en-curso">{olvidado ? 'Sin salida' : 'En curso'}</span>
		{:else if sinEntrada}
			<span class="estado-chip revisar">Salida sin entrada</span>
		{:else}
			<span class="estado-chip" class:revisar={estado !== 'Valido'}>{estado}</span>
		{/if}
	</div>

	<div class="ciclo-horas">
		<div class="tramo">
			<span class="tramo-titulo"><LogIn size={14} /> Entrada</span>
			<span class="tramo-hora">{entrada?.Hora ? String(entrada.Hora).slice(0, 5) : '—'}</span>
		</div>
		<div class="flecha">→</div>
		<div class="tramo salida">
			<span class="tramo-titulo"><LogOut size={14} /> Salida</span>
			<span class="tramo-hora">{salida?.Hora ? String(salida.Hora).slice(0, 5) : '—'}</span>
		</div>
	</div>

	<div class="ciclo-totales">
		<span class="total">
			<Clock size={14} /> {formatoHoras(ciclo?.horas)}
		</span>
		<span class="jornada">de {formatoHoras(horasJornada)} de jornada</span>
		{#if ciclo?.extras > 0}
			<span class="extras" class:excedido={ciclo.excede_limite_dia}>
				{#if ciclo.excede_limite_dia}
					<TriangleAlert size={14} />
				{:else}
					<Clock size={14} />
				{/if}
				{formatoHoras(ciclo.extras)} extra
				{#if ciclo.dobles > 0}<span class="tarifa">dobles {formatoHoras(ciclo.dobles)}</span>{/if}
				{#if ciclo.triples > 0}<span class="tarifa">triples {formatoHoras(ciclo.triples)}</span>{/if}
			</span>
		{/if}
	</div>

	{#if ciclo?.excede_limite_dia}
		<p class="aviso">Supera el máximo de 3 h extra al día (LFT art. 66).</p>
	{/if}

	<div class="ciclo-chips">
		<span class="chip" class:ok={rostro}>
			{#if rostro}<ShieldCheck size={13} /> Rostro{:else}<ShieldAlert size={13} /> Sin rostro{/if}
		</span>
		<span class="chip" class:ok={passkey}>
			<Fingerprint size={13} /> {passkey ? 'Passkey' : 'Sin passkey'}
		</span>
		{#if tieneGps}
			<span class="chip"><MapPin size={13} /> {ciclo.ubicacion.precision != null ? `±${ciclo.ubicacion.precision} m` : 'GPS'}</span>
		{/if}
	</div>

	{#if tieneGps}
		<MiniMapa lat={ciclo.ubicacion.lat} lon={ciclo.ubicacion.lon} />
	{/if}

	{#if dispositivo}
		<div class="ciclo-meta" title={dispositivo}>{dispositivo}…</div>
	{/if}
</div>

<style>
	.ciclo-card {
		background: var(--color-surface);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-sm);
		padding: 0.7rem 0.8rem;
		margin-bottom: 0.6rem;
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
		text-transform: capitalize;
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
		letter-spacing: 0.02em;
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
	.ciclo-totales {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.45rem;
		margin-top: 0.5rem;
		font-size: var(--font-size-sm);
	}
	.total {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-weight: 700;
	}
	.jornada {
		color: var(--color-text-dim);
		font-size: var(--font-size-xs);
	}
	.extras {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: var(--font-size-xs);
		color: var(--color-info);
	}
	.extras.excedido {
		color: var(--color-warning);
	}
	.tarifa {
		opacity: 0.75;
	}
	.aviso {
		margin: 0.35rem 0 0;
		font-size: var(--font-size-2xs);
		color: var(--color-warning);
	}
	.ciclo-chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-top: 0.5rem;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: var(--font-size-xs);
		color: var(--color-text-dim);
		background: var(--color-surface-2);
		border-radius: 999px;
		padding: 0.15rem 0.5rem;
	}
	.chip.ok {
		color: var(--color-success-light);
	}
	.ciclo-meta {
		margin-top: 0.4rem;
		font-size: var(--font-size-2xs);
		color: var(--color-text-dim);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
</style>
