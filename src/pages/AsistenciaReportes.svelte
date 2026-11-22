<!-- Asistencias por usuario y reportes semanales en PDF.
     Vive dentro del módulo de Asistencia de Admon. -->
<script>
	import { onMount } from 'svelte';
	import { Loader2, FileText, Download, CalendarDays } from 'lucide-svelte';
	import { api } from '$lib/api';
	import { auth } from '$lib/stores/auth';
	import { fechaLocal } from '$lib/fechas';

	const hoy = new Date();
	const lunes = new Date(hoy);
	lunes.setDate(hoy.getDate() - ((hoy.getDay() + 6) % 7));
	const domingo = new Date(lunes);
	domingo.setDate(lunes.getDate() + 6);

	let desde = $state(fechaLocal(lunes));
	let hasta = $state(fechaLocal(domingo));
	let cargando = $state(true);
	let bajando = $state('');
	let error = $state('');
	let usuarios = $state([]);
	let elegido = $state('');
	let abierto = $state(-1);

	async function cargar() {
		cargando = true;
		error = '';
		try {
			const r = await api.get(
				`/mi-asistencia/admin/asistencias?desde=${desde}&hasta=${hasta}`
			);
			usuarios = r.usuarios || [];
			if (!elegido && usuarios.length) elegido = usuarios[0].usuario;
		} catch (e) {
			error = e?.message || 'No se pudieron cargar las asistencias';
		} finally {
			cargando = false;
		}
	}

	onMount(cargar);

	async function descargar(idUsuario) {
		bajando = idUsuario ? `u${idUsuario}` : 'general';
		error = '';
		try {
			const q = new URLSearchParams({ desde, hasta });
			if (idUsuario) q.set('id_usuario', idUsuario);
			const res = await fetch(`/api/mi-asistencia/admin/asistencia/reporte?${q}`, {
				headers: auth.authHeader()
			});
			if (!res.ok) {
				const d = await res.json().catch(() => ({}));
				throw new Error(d.detail || 'No se pudo generar el PDF');
			}
			const blob = await res.blob();
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = `asistencia_${desde}_${hasta}${idUsuario ? '_usuario' : '_general'}.pdf`;
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			setTimeout(() => URL.revokeObjectURL(url), 10000);
		} catch (e) {
			error = e?.message || 'No se pudo descargar el PDF';
		} finally {
			bajando = '';
		}
	}

	function idDe(nombre) {
		// el endpoint espera el Id; la lista solo trae el nombre, así que se
		// resuelve por nombre contra los usuarios asignados del horario
		return usuarios.find((u) => u.usuario === nombre)?.id_usuario || null;
	}
</script>

<div class="card">
	<div class="fila-titulo">
		<h2><CalendarDays size={20} /> Asistencias y reportes</h2>
		<div class="rango">
			<input type="date" bind:value={desde} onchange={cargar} aria-label="Desde" />
			<span>→</span>
			<input type="date" bind:value={hasta} onchange={cargar} aria-label="Hasta" />
			<button class="btn btn-sm btn-secondary" onclick={cargar} disabled={cargando}>
				{cargando ? 'Buscando…' : 'Ver'}
			</button>
		</div>
	</div>

	{#if error}<p class="err">{error}</p>{/if}

	{#if cargando}
		<p class="dim"><Loader2 size={16} /> Cargando asistencias…</p>
	{:else if usuarios.length === 0}
		<p class="dim">Sin asistencias en ese periodo.</p>
	{:else}
		<div class="usuarios">
			{#each usuarios as u, i (u.usuario)}
				<div class="usuario">
					<button class="cabecera" onclick={() => (abierto = abierto === i ? -1 : i)}>
						<span class="nombre">{u.usuario}</span>
						<span class="total">{u.total} h</span>
					</button>
					{#if abierto === i}
						<div class="dias">
							{#each u.dias as d (d.fecha)}
								<div class="dia">
									<span>{d.fecha}</span>
									<span>{d.entrada || '—'}</span>
									<span>{d.salida || '—'}</span>
									<span class="h">{d.horas != null ? `${d.horas} h` : '—'}</span>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			{/each}
		</div>

		<div class="acciones">
			<select bind:value={elegido} aria-label="Usuario para el reporte">
				{#each usuarios as u (u.usuario)}
					<option value={u.usuario}>{u.usuario}</option>
				{/each}
			</select>
			<button class="btn btn-sm btn-primary" onclick={() => descargar(idDe(elegido))} disabled={bajando !== ''}>
				{#if bajando === `u${idDe(elegido)}`}<Loader2 size={14} />{:else}<Download size={14} />{/if}
				PDF del usuario
			</button>
			<button class="btn btn-sm btn-secondary" onclick={() => descargar(null)} disabled={bajando !== ''}>
				{#if bajando === 'general'}<Loader2 size={14} />{:else}<FileText size={14} />{/if}
				PDF general
			</button>
		</div>
	{/if}
</div>

<style>
	.fila-titulo {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
	h2 {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		margin: 0;
		font-size: var(--font-size-lg);
	}
	.rango {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		flex-wrap: wrap;
	}
	.rango input,
	select {
		background: var(--color-surface-2);
		border: 1px solid var(--color-line);
		color: var(--color-text-strong);
		border-radius: var(--radius-xs);
		padding: 0.25rem 0.4rem;
		font-size: var(--font-size-xs);
	}
	.err {
		color: var(--color-danger);
		font-size: var(--font-size-sm);
	}
	.dim {
		color: var(--color-text-dim);
		font-size: var(--font-size-sm);
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}
	.usuarios {
		margin-top: 0.75rem;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}
	.usuario {
		border: 1px solid var(--color-line);
		border-radius: var(--radius-xs);
		overflow: hidden;
	}
	.cabecera {
		width: 100%;
		display: flex;
		justify-content: space-between;
		gap: 0.5rem;
		padding: 0.45rem 0.6rem;
		background: var(--color-surface-2);
		border: 0;
		color: var(--color-text-strong);
		cursor: pointer;
		font-size: var(--font-size-sm);
	}
	.nombre {
		font-weight: 600;
	}
	.total {
		color: var(--color-text-dim);
		font-variant-numeric: tabular-nums;
	}
	.dias {
		padding: 0.35rem 0.6rem 0.5rem;
	}
	.dia {
		display: grid;
		grid-template-columns: 6.5rem 1fr 1fr 3.5rem;
		gap: 0.4rem;
		font-size: var(--font-size-xs);
		color: var(--color-text-dim);
		padding: 0.12rem 0;
		font-variant-numeric: tabular-nums;
	}
	.dia .h {
		text-align: right;
		color: var(--color-text-strong);
	}
	.acciones {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
		margin-top: 0.9rem;
	}
</style>
