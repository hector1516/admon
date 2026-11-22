<!-- Horarios de asistencia: catálogo con nombre + asignación por usuario.
     Se muestra dentro del módulo de Asistencia de Admon. -->
<script>
	import { onMount } from 'svelte';
	import { Loader2, Plus, Save, Trash2, Clock } from 'lucide-svelte';
	import { api } from '$lib/api';

	const DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

	let cargando = $state(true);
	let guardando = $state(0);
	let error = $state('');
	let aviso = $state('');
	let horarios = $state([]);
	let usuarios = $state([]);
	let lft = $state({ horas_jornada: 8, dias_semana: 6, tope_semana: 48 });
	let nuevoNombre = $state('');

	const horas = (h) => (h == null ? '—' : `${Math.round(h * 100) / 100} h`);

	function diasCompletos(dias) {
		// siete filas siempre, para poder editar el horario entero
		const porDia = {};
		for (const d of dias || []) porDia[d.dia] = d;
		return DIAS.map((_, i) => {
			const dia = i + 1;
			return (
				porDia[dia] || { dia, entrada: '09:00', salida: '18:00', comida: 60, descanso: dia >= 6 }
			);
		});
	}

	async function cargar() {
		cargando = true;
		error = '';
		try {
			const [h, u] = await Promise.all([
				api.get('/mi-asistencia/admin/horarios'),
				api.get('/mi-asistencia/admin/horarios/usuarios')
			]);
			horarios = (h.horarios || []).map((x) => ({ ...x, dias: diasCompletos(x.dias) }));
			lft = h.lft || lft;
			usuarios = u.usuarios || [];
		} catch (e) {
			error = e?.message || 'No se pudieron cargar los horarios';
		} finally {
			cargando = false;
		}
	}

	onMount(cargar);

	async function guardar(h) {
		guardando = h.id || -1;
		error = '';
		aviso = '';
		try {
			const cuerpo = {
				nombre: h.nombre,
				dias: h.dias.map((d) => ({
					dia: d.dia,
					entrada: d.descanso ? null : d.entrada,
					salida: d.descanso ? null : d.salida,
					comida: Number(d.comida) || 0,
					descanso: !!d.descanso
				}))
			};
			if (h.id) await api.put(`/mi-asistencia/admin/horarios/${h.id}`, cuerpo);
			else await api.post('/mi-asistencia/admin/horarios', cuerpo);
			aviso = `Horario «${h.nombre}» guardado`;
			await cargar();
		} catch (e) {
			error = e?.message || 'No se pudo guardar el horario';
		} finally {
			guardando = 0;
		}
	}

	async function borrar(h) {
		if (!confirm(`¿Eliminar el horario «${h.nombre}»?`)) return;
		try {
			await api.delete(`/mi-asistencia/admin/horarios/${h.id}`);
			aviso = 'Horario eliminado';
			await cargar();
		} catch (e) {
			error = e?.message || 'No se pudo eliminar';
		}
	}

	function agregar() {
		const nombre = nuevoNombre.trim();
		if (!nombre) return;
		horarios = [
			...horarios,
			{ id: null, nombre, activo: true, dias: diasCompletos([]), horas_semana: 0, nueva: true }
		];
		nuevoNombre = '';
	}

	async function asignar(idUsuario, valor) {
		try {
			await api.put(`/mi-asistencia/admin/horarios/usuario/${idUsuario}`, {
				id_horario: valor ? Number(valor) : null
			});
			const u = usuarios.find((x) => x.Id === idUsuario);
			if (u) {
				u.IdHorario = valor ? Number(valor) : null;
				u.Horario = valor ? horarios.find((h) => h.id === Number(valor))?.nombre : null;
			}
			aviso = 'Horario asignado';
		} catch (e) {
			error = e?.message || 'No se pudo asignar';
		}
	}
</script>

<div class="card">
	<div class="fila-titulo">
		<h2><Clock size={20} /> Horarios</h2>
		{#if lft}
			<span class="lft">LFT: {lft.tope_semana} h/semana ({lft.horas_jornada} × {lft.dias_semana})</span>
		{/if}
	</div>

	{#if error}<p class="err">{error}</p>{/if}
	{#if aviso}<p class="ok">{aviso}</p>{/if}

	{#if cargando}
		<p class="dim"><Loader2 size={16} class="spin" /> Cargando horarios…</p>
	{:else}
		{#if horarios.length === 0}
			<p class="dim">Todavía no hay horarios. Crea el primero abajo.</p>
		{/if}

		{#each horarios as h (h.id ?? h.nombre)}
			<div class="horario">
				<div class="horario-head">
					<input class="nombre" bind:value={h.nombre} aria-label="Nombre del horario" />
					<span class="total" class:excede={(h.horas_semana || 0) > lft.tope_semana}>
						{horas(h.horas_semana || 0)} / semana
					</span>
					<button class="btn btn-sm btn-primary" onclick={() => guardar(h)} disabled={guardando === h.id}>
						{#if guardando === h.id}<Loader2 size={14} class="spin" />{:else}<Save size={14} />{/if}
						Guardar
					</button>
					{#if h.id}
						<button class="btn btn-sm btn-secondary" onclick={() => borrar(h)} aria-label="Eliminar">
							<Trash2 size={14} />
						</button>
					{/if}
				</div>

				<div class="rejilla">
					{#each h.dias as d, i (d.dia)}
						<div class="dia" class:descanso={d.descanso}>
							<span class="dia-nombre">{DIAS[i]}</span>
							{#if d.descanso}
								<span class="descanso-txt">Descanso</span>
							{:else}
								<input type="time" bind:value={d.entrada} aria-label="Entrada {DIAS[i]}" />
								<input type="time" bind:value={d.salida} aria-label="Salida {DIAS[i]}" />
								<input
									class="comida"
									type="number"
									min="0"
									max="240"
									step="15"
									bind:value={d.comida}
									aria-label="Comida {DIAS[i]}"
								/>
								<span class="comida-txt">min comida</span>
							{/if}
							<label class="chk">
								<input type="checkbox" bind:checked={d.descanso} /> descanso
							</label>
						</div>
					{/each}
				</div>
			</div>
		{/each}

		<div class="nuevo">
			<input placeholder="Nombre del horario nuevo (ej. Operativo)" bind:value={nuevoNombre} />
			<button class="btn btn-sm btn-secondary" onclick={agregar} disabled={!nuevoNombre.trim()}>
				<Plus size={14} /> Agregar horario
			</button>
		</div>

		<h3>Asignación por usuario</h3>
		{#if usuarios.length === 0}
			<p class="dim">Sin usuarios.</p>
		{:else}
			<div class="tabla">
				<div class="th"><span>Usuario</span><span>Horario</span></div>
				{#each usuarios as u (u.Id)}
					<div class="tr">
						<span class="usuario">{u.Nombre}</span>
						<select
							value={u.IdHorario ?? ''}
							onchange={(e) => asignar(u.Id, e.currentTarget.value)}
						>
							<option value="">Sin horario</option>
							{#each horarios.filter((h) => h.id) as h (h.id)}
								<option value={h.id}>{h.nombre}</option>
							{/each}
						</select>
					</div>
				{/each}
			</div>
		{/if}
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
	h3 {
		margin: 1.25rem 0 0.5rem;
		font-size: var(--font-size-md);
	}
	.lft {
		font-size: var(--font-size-xs);
		color: var(--color-text-dim);
	}
	.err {
		color: var(--color-danger);
		font-size: var(--font-size-sm);
	}
	.ok {
		color: var(--color-success-light);
		font-size: var(--font-size-sm);
	}
	.dim {
		color: var(--color-text-dim);
		font-size: var(--font-size-sm);
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}
	.horario {
		border: 1px solid var(--color-line);
		border-radius: var(--radius-sm);
		padding: 0.7rem;
		margin-top: 0.75rem;
	}
	.horario-head {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
	.nombre {
		font-weight: 700;
		font-size: var(--font-size-md);
		background: transparent;
		border: 1px solid transparent;
		color: var(--color-text-strong);
		border-radius: var(--radius-xs);
		padding: 0.2rem 0.35rem;
		flex: 1;
		min-width: 8rem;
	}
	.nombre:hover,
	.nombre:focus {
		border-color: var(--color-line);
	}
	.total {
		font-size: var(--font-size-xs);
		color: var(--color-text-dim);
	}
	.total.excede {
		color: var(--color-warning);
		font-weight: 700;
	}
	.rejilla {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(7.5rem, 1fr));
		gap: 0.4rem;
		margin-top: 0.6rem;
	}
	.dia {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		background: var(--color-surface-2);
		border-radius: var(--radius-xs);
		padding: 0.4rem;
	}
	.dia.descanso {
		opacity: 0.75;
	}
	.dia-nombre {
		font-size: var(--font-size-2xs);
		font-weight: 700;
		text-transform: uppercase;
		color: var(--color-text-dim);
	}
	.dia input[type='time'],
	.dia input[type='number'],
	.nuevo input,
	select {
		background: var(--color-surface);
		border: 1px solid var(--color-line);
		color: var(--color-text-strong);
		border-radius: var(--radius-xs);
		padding: 0.2rem 0.3rem;
		font-size: var(--font-size-xs);
		width: 100%;
	}
	.comida-txt,
	.descanso-txt {
		font-size: var(--font-size-2xs);
		color: var(--color-text-dim);
	}
	.chk {
		font-size: var(--font-size-2xs);
		color: var(--color-text-dim);
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}
	.nuevo {
		display: flex;
		gap: 0.5rem;
		margin-top: 1rem;
		align-items: center;
	}
	.nuevo input {
		max-width: 20rem;
	}
	.tabla {
		border: 1px solid var(--color-line);
		border-radius: var(--radius-sm);
		overflow: hidden;
	}
	.th,
	.tr {
		display: grid;
		grid-template-columns: 1fr 14rem;
		gap: 0.5rem;
		padding: 0.4rem 0.6rem;
		align-items: center;
	}
	.th {
		background: var(--color-surface-2);
		font-size: var(--font-size-2xs);
		text-transform: uppercase;
		color: var(--color-text-dim);
	}
	.tr + .tr {
		border-top: 1px solid var(--color-line);
	}
	.usuario {
		font-size: var(--font-size-sm);
	}
	.spin {
		animation: girar 1s linear infinite;
	}
	@keyframes girar {
		to {
			transform: rotate(360deg);
		}
	}
</style>
