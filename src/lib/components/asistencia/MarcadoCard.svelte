<!-- MarcadoCard — tarjeta de un marcado de Mi Asistencia (Field + Admon).
     Muestra tipo, fecha/hora, rostro, passkey, GPS con enlace y un fragmento
     de mapa. Se alimenta tal cual con una fila de `HUB_AsistenciaMarcado`. -->
<script>
	import { MapPin, ShieldCheck, ShieldAlert, Fingerprint, LogIn, LogOut } from 'lucide-svelte';
	import MiniMapa from './MiniMapa.svelte';

	let { marcado = {} } = $props();

	const esEntrada = $derived(marcado?.Tipo === 'Entrada');
	const tieneGps = $derived(marcado?.Latitud != null && marcado?.Longitud != null);
	const precision = $derived(
		marcado?.Precision != null ? `±${marcado.Precision} m` : null
	);
	const estado = $derived(marcado?.Estado || 'Valido');
	const dispositivo = $derived(
		marcado?.Dispositivo ? String(marcado.Dispositivo).slice(0, 48) : null
	);
</script>

<div class="marcado-card">
	<div class="marcado-head">
		<span class="tipo" class:entrada={esEntrada}>
			{#if esEntrada}<LogIn size={14} />{:else}<LogOut size={14} />{/if}
			{marcado?.Tipo || 'Marcado'}
		</span>
		<span class="fecha">{marcado?.Fecha}</span>
		<span class="hora">{marcado?.Hora}</span>
	</div>

	<div class="marcado-chips">
		<span class="chip" class:ok={marcado?.VerificacionFacial}>
			{#if marcado?.VerificacionFacial}
				<ShieldCheck size={13} /> Rostro
			{:else}
				<ShieldAlert size={13} /> Sin rostro
			{/if}
		</span>
		<span class="chip" class:ok={!!marcado?.PasskeyCredentialId}>
			<Fingerprint size={13} />
			{marcado?.PasskeyCredentialId ? 'Passkey' : 'Sin passkey'}
		</span>
		{#if tieneGps}
			<span class="chip"><MapPin size={13} /> {precision || 'GPS'}</span>
		{/if}
	</div>

	{#if tieneGps}
		<MiniMapa lat={marcado.Latitud} lon={marcado.Longitud} />
	{/if}

	<div class="marcado-meta">
		<span class="estado" class:revisar={estado !== 'Valido'}>{estado}</span>
		{#if dispositivo}
			<span class="dispositivo" title={marcado.Dispositivo}>{dispositivo}…</span>
		{/if}
	</div>
</div>

<style>
	.marcado-card {
		background: var(--color-surface);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-sm);
		padding: 0.7rem 0.8rem;
		margin-bottom: 0.6rem;
	}
	.marcado-head {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		font-size: var(--font-size-sm);
	}
	.tipo {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		font-weight: 700;
		color: var(--color-text-muted);
	}
	.tipo.entrada {
		color: var(--color-success);
	}
	.fecha {
		color: var(--color-text-soft);
	}
	.hora {
		margin-left: auto;
		font-variant-numeric: tabular-nums;
		font-weight: 600;
	}
	.marcado-chips {
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
	.marcado-meta {
		display: flex;
		justify-content: space-between;
		gap: 0.5rem;
		margin-top: 0.5rem;
		font-size: var(--font-size-2xs);
		color: var(--color-text-dim);
	}
	.estado {
		font-weight: 600;
	}
	.estado.revisar {
		color: var(--color-warning);
	}
	.dispositivo {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
</style>
