<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { api } from '$lib/api.js';
	import { FileText, Settings, Clock, CalendarDays, ArrowLeft } from 'lucide-svelte';
	import AsistenciaReportes from './AsistenciaReportes.svelte';
	import AsistenciaHorarios from './AsistenciaHorarios.svelte';

	let loading = $state(true);
	let error = $state('');
	let reportes = $state([]);
	let configs = $state([]);
	let activeTab = $state('asistencias');

	const PESTANAS = [
		{ id: 'asistencias', texto: 'Asistencias', icono: CalendarDays },
		{ id: 'horarios', texto: 'Horarios', icono: Clock },
		{ id: 'reportes', texto: 'Horas extras', icono: FileText },
		{ id: 'config', texto: 'Config LFT', icono: Settings }
	];

	async function cargar() {
		loading = true;
		error = '';
		try {
			const [r, c] = await Promise.all([
				api.get('/mi-asistencia/admin/reportes'),
				api.get('/mi-asistencia/admin/config-lft')
			]);
			reportes = r.reportes || [];
			configs = c.configs || [];
		} catch (e) {
			error = e?.message || 'Error cargando datos';
		} finally {
			loading = false;
		}
	}

	function verPdf(id) {
		const token = auth.getToken ? auth.getToken() : '';
		window.open(
			`/api/mi-asistencia/horas-extras/reporte/${id}/pdf?token=${encodeURIComponent(token)}`,
			'_blank'
		);
	}

	onMount(() => {
		if (!$auth.user || !$auth.user.acceso_usuarios) {
			navigate('/login');
			return;
		}
		cargar();
	});
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" onclick={() => navigate('/dashboard')} aria-label="Volver">
			<ArrowLeft size={16} />
		</button>
		<h1><Clock size={20} /> Asistencia</h1>
	</div>

	<div class="tabs">
		{#each PESTANAS as t (t.id)}
			<button
				class="tab"
				class:active={activeTab === t.id}
				onclick={() => (activeTab = t.id)}
			>
				<t.icono size={15} /> {t.texto}
			</button>
		{/each}
	</div>

	{#if activeTab === 'asistencias'}
		<AsistenciaReportes />
	{:else if activeTab === 'horarios'}
		<AsistenciaHorarios />
	{:else if loading}
		<div class="card"><p class="dim">Cargando…</p></div>
	{:else if error}
		<div class="card"><p class="err">{error}</p></div>
	{:else if activeTab === 'reportes'}
		<div class="card">
			<h2>Reportes de horas extras</h2>
			{#if reportes.length === 0}
				<p class="dim">No hay reportes de horas extras.</p>
			{:else}
				<div class="lista">
					{#each reportes as r (r.Id)}
						<div class="fila">
							<div class="info">
								<strong>{r.Folio}</strong>
								<span class="dim">{r.Nombre || 'Usuario ' + r.IdUsuario}</span>
								<span class="periodo">{r.PeriodoInicio} – {r.PeriodoFin}</span>
								<span class="horas">{r.TotalHorasExtras} h</span>
								<span class="badge" class:pagado={r.Estatus === 'Pagado'} class:cancelado={r.Estatus === 'Cancelado'}>
									{r.Estatus}
								</span>
							</div>
							<button class="btn btn-sm btn-secondary" onclick={() => verPdf(r.Id)}>
								<FileText size={14} /> PDF
							</button>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{:else if activeTab === 'config'}
		{#each configs as c (c.Anio)}
			<div class="card">
				<h2>LFT {c.Anio}</h2>
				<div class="config">
					{#each [
						['Jornada diurna máx', c.JornadaDiurnaMax + ' h'],
						['Jornada nocturna máx', c.JornadaNocturnaMax + ' h'],
						['Jornada mixta máx', c.JornadaMixtaMax + ' h'],
						['HE dobles máx', c.HorasExtrasDoblesMax + ' h/semana'],
						['Límite HE al día', c.LimiteHorasExtrasDia + ' h'],
						['Límite HE por semana', c.LimiteHorasExtrasSemana + ' veces'],
						['Prima dominical', c.PrimaDominical * 100 + ' %'],
						['Días de trabajo por semana', c.DiasTrabajoSemana],
						['Horas de jornada', c.HorasJornada + ' h'],
						['Semanas por mes', c.SemanasPorMes],
						['Vigencia de la ley', c.FechaVigenciaLey]
					] as par}
						<div class="config-row"><span>{par[0]}</span><span>{par[1]}</span></div>
					{/each}
				</div>
			</div>
		{/each}
	{/if}
</div>

<style>
	.page {
		padding: 1rem;
		max-width: 900px;
		margin: 0 auto;
		padding-bottom: calc(var(--nav-h, 64px) + 1.5rem);
	}
	.header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 1rem;
	}
	.header h1 {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		font-size: var(--font-size-xl);
		font-weight: 700;
		flex: 1;
		margin: 0;
	}
	.tabs {
		display: flex;
		gap: 0.4rem;
		margin-bottom: 1rem;
		overflow-x: auto;
		padding-bottom: 0.15rem;
	}
	.tab {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0.45rem 0.75rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-2);
		color: var(--color-text-dim);
		border-radius: 999px;
		cursor: pointer;
		font-size: var(--font-size-xs);
		font-weight: 600;
		white-space: nowrap;
	}
	.tab.active {
		background: var(--color-info);
		border-color: var(--color-info);
		color: var(--color-ink);
	}
	.lista {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.fila {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
		padding-bottom: 0.5rem;
		border-bottom: 1px solid var(--color-line);
	}
	.fila:last-child {
		border-bottom: none;
		padding-bottom: 0;
	}
	.info {
		display: flex;
		gap: 0.6rem;
		align-items: baseline;
		flex-wrap: wrap;
		font-size: var(--font-size-sm);
	}
	.dim {
		color: var(--color-text-dim);
		font-size: var(--font-size-xs);
	}
	.periodo {
		color: var(--color-text-muted);
		font-size: var(--font-size-xs);
	}
	.horas {
		font-weight: 700;
		color: var(--color-text-strong);
	}
	.badge {
		padding: 0.1rem 0.45rem;
		border-radius: 999px;
		font-size: var(--font-size-2xs);
		font-weight: 700;
		background: color-mix(in srgb, var(--color-info) 18%, transparent);
		color: var(--color-info);
	}
	.badge.pagado {
		background: color-mix(in srgb, var(--color-success) 18%, transparent);
		color: var(--color-success-light);
	}
	.badge.cancelado {
		background: color-mix(in srgb, var(--color-danger) 18%, transparent);
		color: var(--color-danger);
	}
	.config {
		display: flex;
		flex-direction: column;
	}
	.config-row {
		display: flex;
		justify-content: space-between;
		gap: 0.5rem;
		font-size: var(--font-size-sm);
		padding: 0.3rem 0;
		border-bottom: 1px solid var(--color-line);
		color: var(--color-text-soft);
	}
	.config-row:last-child {
		border-bottom: none;
	}
	.config-row span:last-child {
		font-weight: 600;
		color: var(--color-text-strong);
	}
	.err {
		color: var(--color-danger);
		font-size: var(--font-size-sm);
	}
</style>
