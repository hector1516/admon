<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { api } from '$lib/api.js';
	import { auth } from '$lib/stores/auth.js';
	import db from '$lib/db/admonDb.js';

	const user = $derived($auth.user);

	let data = $state(null);
	let loading = $state(true);
	let error = $state('');
	let tab = $state('ranking');

	const yo = $derived(data?.usuario ?? null);
	const ranking = $derived(data?.ranking ?? []);
	const logros = $derived(data?.logros ?? []);
	const guia = $derived(data?.guia ?? []);
	const positivas = $derived(guia.filter((g) => g.tipo !== 'negativo'));
	const negativas = $derived(guia.filter((g) => g.tipo === 'negativo'));
	const miSemana = $derived(data?.mi_semana ?? null);
	const historial = $derived(data?.historial ?? []);
	const niveles = $derived(data?.niveles ?? []);
	const maxDia = $derived(
		Math.max(1, ...(miSemana?.por_dia ?? []).map((d) => Math.abs(Number(d.puntos) || 0)))
	);

	const fmt = new Intl.NumberFormat('es-MX', { maximumFractionDigits: 0 });
	const n = (v) => fmt.format(Number(v) || 0);

	function initials(nombre) {
		return (nombre || '?')
			.split(/\s+/)
			.filter(Boolean)
			.slice(0, 2)
			.map((p) => p[0]?.toUpperCase() || '')
			.join('');
	}

	function fecha(iso) {
		if (!iso) return '';
		// Las fechas de la API vienen como YYYY-MM-DD (sin hora). `new Date` las
		// interpreta en UTC y en México se verían un día antes.
		const texto = String(iso);
		const d = new Date(texto.length <= 10 ? texto + 'T00:00:00' : texto);
		if (Number.isNaN(d.getTime())) return texto.slice(0, 10);
		return d.toLocaleDateString('es-MX', { day: 'numeric', month: 'short' });
	}

	function fechaHora(iso) {
		if (!iso) return '';
		const d = new Date(iso);
		if (Number.isNaN(d.getTime())) return String(iso).replace('T', ' ').slice(0, 16);
		return d.toLocaleString('es-MX', {
			day: 'numeric',
			month: 'short',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function diasReset(seg) {
		const dias = Math.ceil((Number(seg) || 0) / 86400);
		if (dias <= 0) return 'hoy';
		return `${dias} día${dias === 1 ? '' : 's'}`;
	}

	function nivelClass(nombre) {
		return 'lvl lvl-' + String(nombre || '').toLowerCase();
	}

	async function load() {
		loading = true;
		error = '';
		try {
			data = await api.get('/legends/overview');
			try {
				await db.legendsCache.put({ id: 'overview', data, ts: Date.now() });
			} catch {
				/* IndexedDB puede fallar en modo privado; no es crítico */
			}
		} catch (e) {
			try {
				const cache = await db.legendsCache.get('overview');
				if (cache?.data) {
					data = cache.data;
					error = 'Sin conexión: mostrando la última foto guardada.';
				} else {
					error = e?.message || 'No se pudo cargar Legends.';
				}
			} catch {
				error = e?.message || 'No se pudo cargar Legends.';
			}
		} finally {
			loading = false;
		}
	}

	onMount(load);
</script>

<svelte:head>
	<title>Legends · Admon</title>
</svelte:head>

<div class="legends">
	<header class="head">
		<button class="btn btn-sm btn-secondary" onclick={() => navigate('/dashboard')} title="Volver">←</button>
		<div>
			<p class="kicker">ECCSA LEGENDS</p>
			<h1>Competencia semanal</h1>
			<p class="sub">
				{#if data}
					{fecha(data.semana.inicio)} → {fecha(data.semana.fin)}
					· cierra en {diasReset(data.semana.reset_en_segundos)}
				{:else}
					Tu semana, tus logros y la tabla general
				{/if}
			</p>
		</div>
		<button class="refresh" type="button" onclick={load} disabled={loading} title="Actualizar">
			{loading ? '…' : '↻'}
		</button>
	</header>

	{#if error}
		<div class="notice" class:soft={!!data}>{error}</div>
	{/if}

	{#if loading && !data}
		<div class="skeleton">
			<div class="sk sk-hero"></div>
			<div class="sk sk-row"></div>
			<div class="sk sk-row"></div>
			<div class="sk sk-row"></div>
		</div>
	{:else if !data}
		<div class="empty">
			<p>No se pudo cargar Legends.</p>
			<button class="btn" onclick={load}>Reintentar</button>
		</div>
	{:else}
		<section class="hero">
			<div class="identity">
				<div class="avatar">
					{#if yo?.avatar}
						<img src={yo.avatar} alt={yo.nombre} />
					{:else}
						{initials(yo?.nickname || yo?.nombre || user?.nombre || '')}
					{/if}
				</div>
				<div class="identity-text">
					<p class="name">{yo?.nickname || yo?.nombre || user?.nombre}</p>
					<p class="level-line">
						<span class={nivelClass(yo?.nivel)}>{yo?.icono_nivel} {yo?.nivel}</span>
						<span class="dot">·</span>
						<span>{data.temporada.corto}</span>
					</p>
					{#if yo?.elegible === false}
						<p class="warn">Completa tu nickname y registra tu passkey para entrar al ranking.</p>
					{/if}
				</div>
			</div>

			<div class="numbers">
				<div>
					<b>{n(yo?.puntos_semana)}</b>
					<span>esta semana</span>
				</div>
				<div>
					<b>#{yo?.posicion ?? '—'}</b>
					<span>posición</span>
				</div>
				<div>
					<b>🔥 {n(yo?.racha_dias)}</b>
					<span>racha</span>
				</div>
			</div>

			<div class="season">
				<div class="season-head">
					<span>{data.temporada.nombre}</span>
					<span>{n(yo?.puntos_temporada)} pts</span>
				</div>
				<div class="track">
					<i style={`width:${Math.max(0, Math.min(100, Number(yo?.progreso_nivel?.pct) || 0))}%`}></i>
				</div>
				<p class="season-foot">
					{#if yo?.progreso_nivel?.siguiente}
						Te faltan <b>{n(yo.progreso_nivel.faltan)}</b> pts para
						{yo.progreso_nivel.siguiente.icono} {yo.progreso_nivel.siguiente.nombre}
					{:else}
						Ya estás en el nivel máximo de la temporada.
					{/if}
					<span>· {n(yo?.logros_desbloqueados)}/{n(yo?.logros_total)} logros</span>
				</p>
			</div>

			<div class="levels" aria-label="Niveles de la temporada">
				{#each niveles as nivel}
					<span class:active={nivel.nombre === yo?.nivel}>
						{nivel.icono} {nivel.nombre}
						<small>{n(nivel.min)}+</small>
					</span>
				{/each}
			</div>
		</section>

		<div class="rule">
			<span>💡</span>
			<p>
				La regla es simple: <b>si le haces ganar dinero a ECCSA, ganas puntos; si le haces
				perder dinero, pierdes puntos.</b> Las cotizaciones pagadas valen más que cualquier otra
				acción.
			</p>
		</div>

		<nav class="tabs" aria-label="Secciones de Legends">
			<button class:active={tab === 'ranking'} onclick={() => (tab = 'ranking')}>🏆 Ranking</button>
			<button class:active={tab === 'logros'} onclick={() => (tab = 'logros')}>
				🎖️ Logros <small>{yo?.logros_desbloqueados}/{yo?.logros_total}</small>
			</button>
			<button class:active={tab === 'guia'} onclick={() => (tab = 'guia')}>📋 Cómo ganar</button>
			<button class:active={tab === 'semana'} onclick={() => (tab = 'semana')}>📅 Mi semana</button>
		</nav>

		{#if tab === 'ranking'}
			{#if data.ganador_semana}
				<section class="winner">
					<span class="winner-icon">🏆</span>
					<div>
						<p class="eyebrow">Ganador de la semana pasada</p>
						<p class="winner-name">{data.ganador_semana.nombre}</p>
					</div>
					<b>{n(data.ganador_semana.puntos)} pts</b>
				</section>
			{/if}

			<section class="panel">
				<div class="panel-head">
					<h2>Tabla de la semana</h2>
					<span>{ranking.length} participantes</span>
				</div>
				<div class="ranking">
					{#each ranking as r (r.id_usuario)}
						<div
							class="rank-row"
							class:me={r.es_yo}
							class:top={r.posicion <= 3}
							class:ineligible={!r.elegible}
						>
							<span class="pos" data-pos={r.posicion}>{r.posicion}</span>
							<div class="mini-avatar">
								{#if r.avatar}
									<img src={r.avatar} alt={r.nombre} />
								{:else}
									{initials(r.nickname || r.nombre)}
								{/if}
							</div>
							<div class="who">
								<strong>
									{r.nickname || r.nombre}
									{#if r.es_yo}<em>tú</em>{/if}
								</strong>
								<small>
									{r.icono_nivel} {r.nivel}
									{#if !r.elegible}· sin perfil{/if}
								</small>
							</div>
							<div class="rpoints">
								<b>{n(r.puntos_semana)}</b>
								<small>sem</small>
							</div>
						</div>
					{/each}
				</div>
			</section>

			{#if historial.length}
				<section class="panel">
					<div class="panel-head">
						<h2>Ganadores anteriores</h2>
						<span>Últimas semanas</span>
					</div>
					<div class="history">
						{#each historial.slice(0, 6) as h}
							<div class="history-row">
								<span>🏆</span>
								<strong>{h.nombre}</strong>
								<small>{fecha(h.fecha_inicio)} – {fecha(h.fecha_fin)}</small>
								<b>{n(h.puntos)} pts</b>
							</div>
						{/each}
					</div>
				</section>
			{/if}
		{:else if tab === 'logros'}
			<section class="panel">
				<div class="panel-head">
					<h2>Logros</h2>
					<span>{yo?.logros_desbloqueados} de {yo?.logros_total} desbloqueados</span>
				</div>
				<div class="achievements">
					{#each logros as l (l.id)}
						<article class="ach" class:done={l.desbloqueado} class:ready={!l.desbloqueado && l.completado}>
							<div class="ach-icon">{l.icono}</div>
							<div class="ach-body">
								<div class="ach-title">
									<strong>{l.nombre}</strong>
									<span class="bonus">+{n(l.bonus)}</span>
								</div>
								<p>{l.descripcion}</p>
								<div class="ach-track"><i style={`width:${Math.max(0, Math.min(100, l.pct || 0))}%`}></i></div>
								<small>
									{l.progreso}/{l.meta}
									{#if l.desbloqueado}
										· ✅ desbloqueado {l.fecha_obtenido ? `el ${fecha(l.fecha_obtenido)}` : ''}
									{:else if l.completado}
										· listo, el auditor lo paga en la próxima pasada
									{:else}
										· {Math.max(0, l.meta - l.progreso)} por lograr
									{/if}
								</small>
							</div>
						</article>
					{/each}
				</div>
			</section>
		{:else if tab === 'guia'}
			<section class="panel">
				<div class="panel-head">
					<h2>Acciones que suman</h2>
					<span>Se acredita una vez por evento</span>
				</div>
				<div class="guide">
					{#each positivas as g}
						<div class="guide-row">
							<span class="guide-icon">{g.icono}</span>
							<div>
								<strong>{g.nombre}</strong>
								<p>{g.como}</p>
							</div>
							<span class="guide-pts">{g.puntos_texto}</span>
						</div>
					{/each}
				</div>
			</section>

			<section class="panel negative">
				<div class="panel-head">
					<h2>Acciones que restan</h2>
					<span>Protege el margen</span>
				</div>
				<div class="guide">
					{#each negativas as g}
						<div class="guide-row neg">
							<span class="guide-icon">{g.icono}</span>
							<div>
								<strong>{g.nombre}</strong>
								<p>{g.como}</p>
							</div>
							<span class="guide-pts">{g.puntos_texto}</span>
						</div>
					{/each}
				</div>
			</section>

			<section class="panel">
				<div class="panel-head">
					<h2>Cómo funciona la temporada</h2>
				</div>
				<div class="explain">
					<p>
						La competencia se reinicia cada <b>domingo a las 00:00</b> (hora de México) y el
						ganador se publica a las 03:00. Los puntos de la semana se reinician, pero tu
						<b>temporada</b> conserva el avance: así el nivel no se pierde cada domingo.
					</p>
					<p>
						Los logros se pagan <b>una sola vez</b> y no se pueden perder. La racha suma
						+2 por día con actividad positiva.
					</p>
				</div>
			</section>
		{:else if tab === 'semana'}
			<section class="panel">
				<div class="panel-head">
					<h2>Mi semana</h2>
					<span>{n(miSemana?.total)} pts en total</span>
				</div>
				<div class="days">
					{#each miSemana?.por_dia ?? [] as d}
						<div class="day" class:today={d.hoy} class:future={d.futuro}>
							<span class="day-name">{d.dia}</span>
							<div class="day-bar">
								<i
									class:neg={Number(d.puntos) < 0}
									style={`height:${Math.max(4, Math.round((Math.abs(Number(d.puntos)) / maxDia) * 100))}%`}
								></i>
							</div>
							<span class="day-pts" class:neg={Number(d.puntos) < 0}>{n(d.puntos)}</span>
						</div>
					{/each}
				</div>
			</section>

			<section class="panel">
				<div class="panel-head">
					<h2>Movimientos</h2>
					<span>{miSemana?.eventos?.length ?? 0} eventos</span>
				</div>
				{#if miSemana?.eventos?.length}
					<div class="events">
						{#each miSemana.eventos as e}
							<div class="event" class:neg={Number(e.puntos) < 0}>
								<span class="event-icon">{e.icono}</span>
								<div>
									<strong>{e.nombre}</strong>
									<small>{fechaHora(e.fecha)}</small>
								</div>
								<b class:neg={Number(e.puntos) < 0}>
									{Number(e.puntos) > 0 ? '+' : ''}{n(e.puntos)}
								</b>
							</div>
						{/each}
					</div>
				{:else}
					<div class="empty-inline">
						Todavía no hay movimientos esta semana. Un reporte firmado o un ticket ya suman.
					</div>
				{/if}
			</section>
		{/if}
	{/if}
</div>

<style>
	.legends {
		max-width: 980px;
		margin: 0 auto;
		padding: 1rem 1rem 3rem;
		color: var(--color-text, #f8fafc);
	}

	.head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		margin: 0.25rem 0 1rem;
	}

	.kicker {
		margin: 0 0 0.2rem;
		font-size: 0.7rem;
		font-weight: 800;
		letter-spacing: 0.16em;
		color: var(--color-primary, #ff6b00);
	}

	h1 {
		margin: 0;
		font-size: clamp(1.55rem, 4vw, 2.1rem);
		line-height: 1.1;
	}

	.sub {
		margin: 0.35rem 0 0;
		color: var(--color-text-muted, #94a3b8);
		font-size: 0.84rem;
	}

	.refresh {
		flex: none;
		width: 2.9rem;
		height: 2.9rem;
		border-radius: 0.9rem;
		border: 1px solid var(--color-line, rgba(255, 255, 255, 0.1));
		background: var(--color-surface, #1e293b);
		color: var(--color-text);
		font-size: 1.15rem;
		cursor: pointer;
	}

	.refresh:disabled {
		opacity: 0.55;
	}

	.notice {
		margin: 0 0 1rem;
		padding: 0.7rem 0.9rem;
		border-radius: 0.8rem;
		background: rgba(239, 68, 68, 0.12);
		border: 1px solid rgba(239, 68, 68, 0.35);
		color: #fecaca;
		font-size: 0.85rem;
	}

	.notice.soft {
		background: rgba(245, 158, 11, 0.1);
		border-color: rgba(245, 158, 11, 0.35);
		color: #fde68a;
	}

	.hero,
	.panel,
	.winner,
	.rule {
		background: var(--color-surface, #1e293b);
		border: 1px solid var(--color-line, rgba(255, 255, 255, 0.08));
		border-radius: 1.1rem;
	}

	.hero {
		padding: 1rem;
		display: grid;
		gap: 1rem;
		background:
			radial-gradient(700px 220px at 0% 0%, rgba(255, 107, 0, 0.16), transparent 62%),
			var(--color-surface, #1e293b);
	}

	.identity {
		display: flex;
		align-items: center;
		gap: 0.8rem;
	}

	.avatar,
	.mini-avatar {
		border-radius: 50%;
		overflow: hidden;
		display: grid;
		place-items: center;
		background: linear-gradient(145deg, #ff6b00, #ffae00);
		color: #0f172a;
		font-weight: 900;
	}

	.avatar {
		width: 3.4rem;
		height: 3.4rem;
		flex: none;
		font-size: 1.05rem;
	}

	.avatar img,
	.mini-avatar img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	.identity-text {
		min-width: 0;
	}

	.name {
		margin: 0;
		font-size: 1.15rem;
		font-weight: 800;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.level-line {
		margin: 0.2rem 0 0;
		display: flex;
		align-items: center;
		gap: 0.35rem;
		flex-wrap: wrap;
		color: var(--color-text-muted, #94a3b8);
		font-size: 0.82rem;
	}

	.dot {
		opacity: 0.5;
	}

	.lvl {
		font-weight: 700;
		color: var(--color-text, #f8fafc);
	}

	.lvl-plata {
		color: #d7dde8;
	}

	.lvl-oro {
		color: #ffd54a;
	}

	.lvl-diamante {
		color: #67e8f9;
	}

	.lvl-leyenda {
		color: #d8b4fe;
	}

	.warn {
		margin: 0.35rem 0 0;
		color: #fbbf24;
		font-size: 0.8rem;
	}

	.numbers {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 0.5rem;
	}

	.numbers > div {
		padding: 0.7rem 0.55rem;
		border-radius: 0.8rem;
		background: rgba(255, 255, 255, 0.035);
		border: 1px solid rgba(255, 255, 255, 0.05);
		display: flex;
		flex-direction: column;
		align-items: center;
	}

	.numbers b {
		font-size: 1.35rem;
		line-height: 1.1;
	}

	.numbers span {
		margin-top: 0.15rem;
		font-size: 0.7rem;
		color: var(--color-text-muted, #94a3b8);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.season-head,
	.season-foot {
		display: flex;
		justify-content: space-between;
		gap: 0.75rem;
		flex-wrap: wrap;
		font-size: 0.8rem;
	}

	.season-head {
		margin-bottom: 0.4rem;
		color: var(--color-text-muted, #94a3b8);
	}

	.season-foot {
		margin: 0.45rem 0 0;
		color: var(--color-text-muted, #94a3b8);
	}

	.season-foot b {
		color: var(--color-primary-light, #ffae00);
	}

	.track {
		height: 0.55rem;
		border-radius: 999px;
		overflow: hidden;
		background: rgba(255, 255, 255, 0.08);
	}

	.track i {
		display: block;
		height: 100%;
		border-radius: inherit;
		background: linear-gradient(90deg, #ff6b00, #ffae00);
		transition: width 0.4s ease;
	}

	.levels {
		display: flex;
		gap: 0.4rem;
		overflow-x: auto;
		padding-bottom: 0.15rem;
		scrollbar-width: none;
	}

	.levels::-webkit-scrollbar {
		display: none;
	}

	.levels span {
		flex: none;
		padding: 0.3rem 0.55rem;
		border-radius: 999px;
		border: 1px solid rgba(255, 255, 255, 0.08);
		color: var(--color-text-muted, #94a3b8);
		font-size: 0.7rem;
	}

	.levels span.active {
		color: #0f172a;
		background: linear-gradient(90deg, #ff6b00, #ffae00);
		border-color: transparent;
		font-weight: 800;
	}

	.levels small {
		opacity: 0.7;
	}

	.rule {
		margin: 0.85rem 0;
		padding: 0.75rem 0.9rem;
		display: flex;
		gap: 0.65rem;
		align-items: flex-start;
		background: rgba(255, 174, 0, 0.07);
		border-color: rgba(255, 174, 0, 0.22);
	}

	.rule p {
		margin: 0;
		font-size: 0.82rem;
		line-height: 1.45;
		color: #fde68a;
	}

	.tabs {
		display: flex;
		gap: 0.35rem;
		overflow-x: auto;
		padding: 0.15rem 0 0.85rem;
		scrollbar-width: none;
	}

	.tabs::-webkit-scrollbar {
		display: none;
	}

	.tabs button {
		flex: none;
		border: 1px solid var(--color-line, rgba(255, 255, 255, 0.1));
		background: transparent;
		color: var(--color-text-muted, #94a3b8);
		padding: 0.55rem 0.75rem;
		border-radius: 999px;
		font-size: 0.8rem;
		font-weight: 700;
		cursor: pointer;
	}

	.tabs button.active {
		background: rgba(255, 107, 0, 0.14);
		border-color: rgba(255, 107, 0, 0.45);
		color: #ffd7b0;
	}

	.tabs small {
		opacity: 0.7;
		font-weight: 600;
	}

	.winner {
		margin-bottom: 0.75rem;
		padding: 0.8rem 0.9rem;
		display: flex;
		align-items: center;
		gap: 0.7rem;
		background: linear-gradient(120deg, rgba(255, 174, 0, 0.12), rgba(30, 41, 59, 1) 60%);
		border-color: rgba(255, 174, 0, 0.28);
	}

	.winner-icon {
		font-size: 1.6rem;
	}

	.winner > div {
		min-width: 0;
		flex: 1;
	}

	.eyebrow {
		margin: 0;
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: #fbbf24;
	}

	.winner-name {
		margin: 0.1rem 0 0;
		font-weight: 800;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.winner > b {
		color: #ffd54a;
		font-size: 1.05rem;
	}

	.panel {
		margin-bottom: 0.85rem;
		overflow: hidden;
	}

	.panel-head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.85rem 0.95rem 0.6rem;
	}

	.panel-head h2 {
		margin: 0;
		font-size: 0.98rem;
	}

	.panel-head span {
		color: var(--color-text-muted, #94a3b8);
		font-size: 0.72rem;
	}

	.ranking,
	.history,
	.events,
	.guide {
		padding: 0 0.55rem 0.55rem;
	}

	.rank-row {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.55rem 0.45rem;
		border-radius: 0.75rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.04);
	}

	.rank-row:last-child {
		border-bottom: 0;
	}

	.rank-row.me {
		background: rgba(255, 107, 0, 0.12);
		border-bottom-color: transparent;
	}

	.rank-row.ineligible {
		opacity: 0.55;
	}

	.pos {
		width: 1.65rem;
		text-align: center;
		font-size: 0.8rem;
		font-weight: 800;
		color: var(--color-text-muted, #94a3b8);
		flex: none;
	}

	.rank-row.top .pos {
		color: #ffd54a;
	}

	.rank-row .pos[data-pos='1'] {
		font-size: 1rem;
	}

	.mini-avatar {
		width: 2.1rem;
		height: 2.1rem;
		flex: none;
		font-size: 0.7rem;
	}

	.who {
		flex: 1;
		min-width: 0;
	}

	.who strong {
		display: block;
		font-size: 0.86rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.who em {
		font-style: normal;
		font-size: 0.62rem;
		margin-left: 0.3rem;
		padding: 0.08rem 0.3rem;
		border-radius: 999px;
		background: rgba(255, 107, 0, 0.25);
		color: #ffd7b0;
	}

	.who small {
		display: block;
		margin-top: 0.12rem;
		font-size: 0.7rem;
		color: var(--color-text-muted, #94a3b8);
	}

	.rpoints {
		text-align: right;
		flex: none;
	}

	.rpoints b {
		display: block;
		font-size: 0.95rem;
	}

	.rpoints small {
		font-size: 0.62rem;
		color: var(--color-text-muted, #94a3b8);
		text-transform: uppercase;
	}

	.history-row {
		display: grid;
		grid-template-columns: auto 1fr auto auto;
		align-items: center;
		gap: 0.45rem;
		padding: 0.45rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.04);
		font-size: 0.8rem;
	}

	.history-row:last-child {
		border-bottom: 0;
	}

	.history-row strong {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.history-row small {
		color: var(--color-text-muted, #94a3b8);
		font-size: 0.68rem;
	}

	.history-row b {
		color: #ffd54a;
		white-space: nowrap;
	}

	.achievements {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(245px, 1fr));
		gap: 0.55rem;
		padding: 0 0.7rem 0.75rem;
	}

	.ach {
		display: flex;
		gap: 0.65rem;
		padding: 0.65rem;
		border-radius: 0.85rem;
		border: 1px solid rgba(255, 255, 255, 0.06);
		background: rgba(255, 255, 255, 0.025);
		opacity: 0.62;
	}

	.ach.done,
	.ach.ready {
		opacity: 1;
	}

	.ach.done {
		border-color: rgba(34, 197, 94, 0.32);
		background: rgba(34, 197, 94, 0.07);
	}

	.ach.ready {
		border-color: rgba(255, 174, 0, 0.32);
		background: rgba(255, 174, 0, 0.06);
	}

	.ach-icon {
		font-size: 1.45rem;
		line-height: 1;
		flex: none;
		width: 2rem;
		text-align: center;
	}

	.ach-body {
		min-width: 0;
		flex: 1;
	}

	.ach-title {
		display: flex;
		justify-content: space-between;
		gap: 0.4rem;
		align-items: baseline;
	}

	.ach-title strong {
		font-size: 0.84rem;
	}

	.bonus {
		font-size: 0.7rem;
		font-weight: 800;
		color: #ffd54a;
		white-space: nowrap;
	}

	.ach p {
		margin: 0.15rem 0 0.4rem;
		font-size: 0.72rem;
		line-height: 1.35;
		color: var(--color-text-muted, #94a3b8);
	}

	.ach-track {
		height: 0.35rem;
		border-radius: 999px;
		background: rgba(255, 255, 255, 0.08);
		overflow: hidden;
	}

	.ach-track i {
		display: block;
		height: 100%;
		border-radius: inherit;
		background: var(--color-primary, #ff6b00);
	}

	.ach.done .ach-track i {
		background: var(--color-success, #22c55e);
	}

	.ach small {
		display: block;
		margin-top: 0.3rem;
		font-size: 0.66rem;
		color: var(--color-text-muted, #94a3b8);
	}

	.guide-row {
		display: flex;
		align-items: flex-start;
		gap: 0.6rem;
		padding: 0.55rem 0.4rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.04);
	}

	.guide-row:last-child {
		border-bottom: 0;
	}

	.guide-icon {
		font-size: 1.15rem;
		width: 1.6rem;
		text-align: center;
		flex: none;
	}

	.guide-row > div {
		flex: 1;
		min-width: 0;
	}

	.guide-row strong {
		font-size: 0.83rem;
	}

	.guide-row p {
		margin: 0.1rem 0 0;
		font-size: 0.72rem;
		color: var(--color-text-muted, #94a3b8);
		line-height: 1.35;
	}

	.guide-pts {
		font-size: 0.78rem;
		font-weight: 800;
		color: var(--color-success, #22c55e);
		white-space: nowrap;
		padding-top: 0.1rem;
	}

	.guide-row.neg .guide-pts {
		color: var(--color-danger, #ef4444);
	}

	.panel.negative .panel-head h2 {
		color: #fca5a5;
	}

	.explain {
		padding: 0 0.95rem 0.9rem;
		color: var(--color-text-muted, #94a3b8);
		font-size: 0.8rem;
		line-height: 1.5;
	}

	.explain p {
		margin: 0 0 0.55rem;
	}

	.explain b {
		color: var(--color-text, #f8fafc);
	}

	.days {
		display: grid;
		grid-template-columns: repeat(7, 1fr);
		gap: 0.35rem;
		padding: 0.2rem 0.75rem 0.9rem;
		min-height: 8.5rem;
	}

	.day {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
		min-width: 0;
	}

	.day-name {
		font-size: 0.65rem;
		color: var(--color-text-muted, #94a3b8);
	}

	.day.today .day-name {
		color: var(--color-primary-light, #ffae00);
		font-weight: 800;
	}

	.day-bar {
		width: 100%;
		height: 5.6rem;
		border-radius: 0.45rem;
		background: rgba(255, 255, 255, 0.045);
		display: flex;
		align-items: flex-end;
		overflow: hidden;
	}

	.day-bar i {
		width: 100%;
		border-radius: 0.4rem 0.4rem 0 0;
		background: linear-gradient(180deg, #ffae00, #ff6b00);
	}

	.day-bar i.neg {
		background: linear-gradient(180deg, #f87171, #b91c1c);
	}

	.day.future {
		opacity: 0.4;
	}

	.day-pts {
		font-size: 0.68rem;
		font-weight: 700;
	}

	.day-pts.neg {
		color: #f87171;
	}

	.event {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		padding: 0.5rem 0.4rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.04);
	}

	.event:last-child {
		border-bottom: 0;
	}

	.event-icon {
		width: 1.5rem;
		text-align: center;
		flex: none;
	}

	.event > div {
		flex: 1;
		min-width: 0;
	}

	.event strong {
		display: block;
		font-size: 0.8rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.event small {
		font-size: 0.66rem;
		color: var(--color-text-muted, #94a3b8);
	}

	.event b {
		font-size: 0.82rem;
		color: var(--color-success, #22c55e);
		white-space: nowrap;
	}

	.event b.neg {
		color: var(--color-danger, #ef4444);
	}

	.empty-inline {
		padding: 0.4rem 0.95rem 1rem;
		color: var(--color-text-muted, #94a3b8);
		font-size: 0.8rem;
	}

	.empty {
		padding: 2rem 1rem;
		text-align: center;
		color: var(--color-text-muted, #94a3b8);
	}

	.btn {
		margin-top: 0.7rem;
		padding: 0.6rem 1rem;
		border-radius: 0.75rem;
		border: 0;
		background: var(--color-primary, #ff6b00);
		color: #0f172a;
		font-weight: 800;
		cursor: pointer;
	}

	.skeleton {
		display: grid;
		gap: 0.7rem;
	}

	.sk {
		border-radius: 1rem;
		background: linear-gradient(90deg, #1e293b, #273449, #1e293b);
		background-size: 200% 100%;
		animation: shimmer 1.3s linear infinite;
	}

	.sk-hero {
		height: 12rem;
	}

	.sk-row {
		height: 3.8rem;
	}

	@keyframes shimmer {
		from {
			background-position: 200% 0;
		}
		to {
			background-position: -200% 0;
		}
	}

	@media (min-width: 720px) {
		.hero {
			grid-template-columns: 1.1fr 1fr;
			align-items: center;
		}

		.identity {
			grid-column: 1;
		}

		.numbers {
			grid-column: 2;
		}

		.season,
		.levels {
			grid-column: 1 / -1;
		}
	}

	@media (max-width: 420px) {
		.legends {
			padding-left: 0.7rem;
			padding-right: 0.7rem;
		}

		.numbers b {
			font-size: 1.15rem;
		}

		.achievements {
			grid-template-columns: 1fr;
		}

		.history-row {
			grid-template-columns: auto 1fr auto;
		}

		.history-row small {
			display: none;
		}
	}
</style>
