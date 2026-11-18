<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	let msg = $state('');
	import { api } from '$lib/api.js';
	import { FileText, Download, Settings, Clock, Users, ArrowLeft } from 'lucide-svelte';

	let loading = $state(true);
	let error = $state('');
	let reportes = $state([]);
	let configs = $state([]);
	let activeTab = $state('reportes');

	async function cargar() {
		loading = true;
		error = '';
		try {
			const r = await api.get('/mi-asistencia/admin/reportes');
			reportes = r.reportes || [];
			const c = await api.get('/mi-asistencia/admin/config-lft');
			configs = c.configs || [];
		} catch (e) {
			error = e.message || 'Error cargando datos';
		} finally {
			loading = false;
		}
	}

	function verPdf(id) {
		const token = auth.getToken ? auth.getToken() : '';
		window.open(`/api/mi-asistencia/horas-extras/reporte/${id}/pdf?token=${encodeURIComponent(token)}`, '_blank');
	}

	onMount(() => {
		if (!$auth.user || !$auth.user.acceso_usuarios) { navigate('/login'); return; }
		cargar();
	});
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" onclick={() => navigate('/dashboard')}>
			<ArrowLeft size={16} />
		</button>
		<h1>Asistencia - Horas Extras</h1>
	</div>

	<div class="tabs">
		<button class="tab" class:active={activeTab === 'reportes'} onclick={() => activeTab = 'reportes'}>Reportes</button>
		<button class="tab" class:active={activeTab === 'config'} onclick={() => activeTab = 'config'}>Config LFT</button>
	</div>

	{#if loading}
		<p class="loading">Cargando...</p>
	{:else if error}
		<div class="error-box">{error}</div>
	{:else}
		{#if activeTab === 'reportes'}
			{#if reportes.length === 0}
				<p class="empty">No hay reportes de horas extras.</p>
			{:else}
				<div class="reportes-list">
					{#each reportes as r}
						<div class="reporte-card">
							<div class="reporte-info">
								<strong>{r.Folio}</strong>
								<span class="reporte-user">{r.Nombre || 'Usuario ' + r.IdUsuario}</span>
								<span class="reporte-periodo">{r.PeriodoInicio} - {r.PeriodoFin}</span>
								<span class="reporte-horas">{r.TotalHorasExtras} hrs</span>
								<span class="badge {r.Estatus}">{r.Estatus}</span>
							</div>
							<button class="btn btn-sm btn-secondary" onclick={() => verPdf(r.Id)}>
								<FileText size={14} /> PDF
							</button>
						</div>
					{/each}
				</div>
			{/if}
		{:else if activeTab === 'config'}
			{#each configs as c}
				<div class="config-card">
					<h3>LFT {c.Anio}</h3>
					<div class="config-row"><span>Jornada diurna máx:</span><span>{c.JornadaDiurnaMax}h</span></div>
					<div class="config-row"><span>Jornada nocturna máx:</span><span>{c.JornadaNocturnaMax}h</span></div>
					<div class="config-row"><span>Jornada mixta máx:</span><span>{c.JornadaMixtaMax}h</span></div>
					<div class="config-row"><span>HE dobles máx:</span><span>{c.HorasExtrasDoblesMax}h/sem</span></div>
					<div class="config-row"><span>Límite HE/día:</span><span>{c.LimiteHorasExtrasDia}h</span></div>
					<div class="config-row"><span>Límite HE/semana:</span><span>{c.LimiteHorasExtrasSemana} veces</span></div>
					<div class="config-row"><span>Prima dominical:</span><span>{(c.PrimaDominical * 100)}%</span></div>
					<div class="config-row"><span>Días trabajo/sem:</span><span>{c.DiasTrabajoSemana}</span></div>
					<div class="config-row"><span>Horas jornada:</span><span>{c.HorasJornada}h</span></div>
					<div class="config-row"><span>Semanas/mes:</span><span>{c.SemanasPorMes}</span></div>
					<div class="config-row"><span>Vigencia ley:</span><span>{c.FechaVigenciaLey}</span></div>
				</div>
			{/each}
		{/if}
	{/if}
</div>

<style>
	.page { padding: 1rem; max-width: 900px; margin: 0 auto; }
	.header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
	.header h1 { font-size: 1.25rem; font-weight: 700; flex: 1; }
	.tabs { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
	.tab { padding: 0.5rem 1rem; border: none; background: #e2e8f0; border-radius: 0.5rem; cursor: pointer; font-weight: 500; }
	.tab.active { background: #3b82f6; color: white; }
	.reportes-list { display: flex; flex-direction: column; gap: 0.5rem; }
	.reporte-card { display: flex; justify-content: space-between; align-items: center; background: white; border-radius: 0.5rem; padding: 0.75rem 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
	.reporte-info { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; font-size: 0.85rem; }
	.reporte-user { color: #64748b; }
	.reporte-periodo { color: #94a3b8; font-size: 0.8rem; }
	.reporte-horas { font-weight: 600; color: #1e293b; }
	.badge { padding: 0.125rem 0.5rem; border-radius: 0.25rem; font-size: 0.75rem; font-weight: 600; }
	.badge.Generado { background: #dbeafe; color: #1e40af; }
	.badge.Pagado { background: #dcfce7; color: #166534; }
	.badge.Cancelado { background: #fee2e2; color: #991b1b; }
	.config-card { background: white; border-radius: 0.75rem; padding: 1rem; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
	.config-card h3 { font-size: 1rem; font-weight: 600; margin-bottom: 0.75rem; color: #3b82f6; }
	.config-row { display: flex; justify-content: space-between; font-size: 0.85rem; padding: 0.25rem 0; border-bottom: 1px solid #f1f5f9; }
	.empty { text-align: center; color: #94a3b8; padding: 2rem; }
	.error-box { background: #fee2e2; color: #991b1b; padding: 0.75rem; border-radius: 0.5rem; }
	.loading { text-align: center; padding: 2rem; color: #94a3b8; }
	.btn { display: inline-flex; align-items: center; gap: 0.375rem; padding: 0.5rem 1rem; border-radius: 0.5rem; font-weight: 500; cursor: pointer; border: none; font-size: 0.875rem; }
	.btn-secondary { background: #e2e8f0; color: #334155; }
	.btn-sm { padding: 0.375rem 0.75rem; font-size: 0.8rem; }
</style>
