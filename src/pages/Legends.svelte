<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { navigate as goto } from '$lib/router.js';
	import { api } from '$lib/api';
	import { auth } from '$lib/stores/auth';
	import { online } from '$lib/stores/online';
	import db from '$lib/db/admonDb.js';

	const user = $derived($auth.user);

	let score = $state<any>(null);
	let avatar = $state<any>(null);
	let ranking = $state<any[]>([]);
	let weeklyWinner = $state<any>(null);
	let winners = $state<any[]>([]);
	let loading = $state(true);
	let tab = $state<'ranking' | 'historial' | 'rivales' | 'mis_puntos'>('ranking');
	let canvas: HTMLCanvasElement | null = $state(null);
	let shareLoading = $state(false);
	let animFrame = 0;
	let counterAnim = $state(0);
	let prevScore = 0;

	let celebrations = $state<any>(null);
	let scoreLog = $state<any>(null);
	let rivalesIndex = $state(0);

	function scrollRivales(dir: number) {
		if (ranking.length === 0) return;
		rivalesIndex = (rivalesIndex + dir + ranking.length) % ranking.length;
	}

	// ── Offline cache ──
	// Métricas retiradas: no deben mostrarse aunque vengan de cache vieja (SW/IDB).
	const RETIRED_METRICS = new Set(['sync_completado']);

	function sanitizeScoreLog(sl: any): any | null {
		if (!sl || !Array.isArray(sl.eventos)) return sl;
		const eventos = sl.eventos.filter((e: any) => !RETIRED_METRICS.has(e?.metrica));
		if (eventos.length === sl.eventos.length) return sl;
		const total_semana = eventos.reduce((a: number, e: any) => a + (e?.puntos || 0), 0);
		return { ...sl, eventos, total_semana };
	}

	async function cacheLegendsData() {
		try {
			await db.legendsCache.put({ id: 'score', data: score, ts: Date.now() });
			await db.legendsCache.put({ id: 'ranking', data: ranking, ts: Date.now() });
			await db.legendsCache.put({ id: 'weeklyWinner', data: weeklyWinner, ts: Date.now() });
			await db.legendsCache.put({ id: 'winners', data: winners, ts: Date.now() });
			await db.legendsCache.put({ id: 'avatar', data: avatar, ts: Date.now() });
			await db.legendsCache.put({ id: 'celebrations', data: celebrations, ts: Date.now() });
			await db.legendsCache.put({ id: 'scoreLog', data: scoreLog, ts: Date.now() });
		} catch {}
	}

	async function loadCachedData() {
		try {
			const [s, r, w, wh, a, cel, sl] = await Promise.all([
				db.legendsCache.get('score'),
				db.legendsCache.get('ranking'),
				db.legendsCache.get('weeklyWinner'),
				db.legendsCache.get('winners'),
				db.legendsCache.get('avatar'),
				db.legendsCache.get('celebrations'),
				db.legendsCache.get('scoreLog'),
			]);
			if (s?.data) score = s.data;
			if (r?.data) ranking = r.data;
			if (w?.data) weeklyWinner = w.data;
			if (wh?.data) winners = wh.data;
			if (a?.data) avatar = a.data;
			if (cel?.data) celebrations = cel.data;
			if (sl?.data) scoreLog = sanitizeScoreLog(sl.data);
		} catch {}
	}

	// ── Particulas animadas ──
	interface Particle {
		x: number; y: number; vx: number; vy: number;
		size: number; alpha: number; color: string; life: number;
	}
	let particles: Particle[] = [];
	let particleCtx: CanvasRenderingContext2D | null = null;

	function initParticles() {
		if (!canvas) return;
		particleCtx = canvas.getContext('2d');
		resizeCanvas();
		spawnParticles();
		animateParticles();
	}

	function resizeCanvas() {
		if (!canvas) return;
		canvas.width = window.innerWidth;
		canvas.height = 300;
	}

	function spawnParticles() {
		const colors = ['#FF6B00', '#FFD700', '#00BCD4', '#4ade80', '#f87171', '#a78bfa'];
		for (let i = 0; i < 40; i++) {
			particles.push({
				x: Math.random() * (canvas?.width || 400),
				y: Math.random() * 300,
				vx: (Math.random() - 0.5) * 0.5,
				vy: -Math.random() * 0.8 - 0.2,
				size: Math.random() * 3 + 1,
				alpha: Math.random() * 0.6 + 0.2,
				color: colors[Math.floor(Math.random() * colors.length)],
				life: Math.random() * 200 + 100,
			});
		}
	}

	function animateParticles() {
		if (!particleCtx || !canvas) return;
		particleCtx.clearRect(0, 0, canvas.width, canvas.height);
		for (const p of particles) {
			p.x += p.vx;
			p.y += p.vy;
			p.life--;
			if (p.life <= 0 || p.y < -10) {
				p.x = Math.random() * canvas.width;
				p.y = canvas.height + 10;
				p.life = Math.random() * 200 + 100;
			}
			particleCtx.beginPath();
			particleCtx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
			particleCtx.fillStyle = p.color;
			particleCtx.globalAlpha = p.alpha * (p.life / 200);
			particleCtx.fill();
			particleCtx.globalAlpha = 1;
		}
		animFrame = requestAnimationFrame(animateParticles);
	}

	// ── Contador animado ──
	function animateCounter(target: number) {
		const duration = 1200;
		const start = performance.now();
		const from = prevScore;
		function tick(now: number) {
			const elapsed = now - start;
			const progress = Math.min(elapsed / duration, 1);
			const ease = 1 - Math.pow(1 - progress, 3);
			counterAnim = Math.round(from + (target - from) * ease);
			if (progress < 1) requestAnimationFrame(tick);
		}
		requestAnimationFrame(tick);
		prevScore = target;
	}


	// Compartir como imagen — dibujo directo en canvas (sin html2canvas)
	async function shareCard() {
		if (shareLoading) return;
		shareLoading = true;
		try {
			// WhatsApp Stories: 1080x1920 (9:16)
			const W = 1080, H = 1920;
			const cvs = document.createElement('canvas');
			cvs.width = W; cvs.height = H;
			const ctx = cvs.getContext('2d')!;

			// Fondo negro para compartir
			ctx.fillStyle = '#000000';
			ctx.fillRect(0, 0, W, H);

			// Dibujar avatar (si existe)
			if (avatar?.avatar) {
				const img = new Image();
				img.src = `data:image/png;base64,${avatar.avatar}`;
				await new Promise<void>((res) => { img.onload = () => res(); img.onerror = () => res(); });
				// object-fit: cover centrado
				const imgRatio = img.width / img.height;
				const cardRatio = W / H;
				let sx = 0, sy = 0, sw = img.width, sh = img.height;
				if (imgRatio > cardRatio) {
					sw = img.height * cardRatio;
					sx = (img.width - sw) / 2;
				} else {
					sh = img.width / cardRatio;
					sy = (img.height - sh) / 2;
				}
				ctx.drawImage(img, sx, sy, sw, sh, 0, 0, W, H);
			} else {
				// Placeholder
				ctx.fillStyle = '#0a0f1a';
				ctx.fillRect(0, 0, W, H);
				ctx.font = '240px sans-serif';
				ctx.textAlign = 'center';
				ctx.fillText('👤', W / 2, H / 2);
			}

			// Overlay gradiente
			const grad = ctx.createLinearGradient(0, H * 0.55, 0, H);
			grad.addColorStop(0, 'rgba(0,0,0,0)');
			grad.addColorStop(0.4, 'rgba(0,0,0,0.55)');
			grad.addColorStop(1, 'rgba(0,0,0,0.85)');
			ctx.fillStyle = grad;
			ctx.fillRect(0, H * 0.55, W, H * 0.45);

			const centerX = W / 2;
			let yPos = H * 0.65;

			// Nombre
			const nick = score?.nickname || avatar?.nickname || user?.nombre || 'Jugador';
			ctx.fillStyle = '#ffffff';
			ctx.font = '900 72px Outfit, sans-serif';
			ctx.textAlign = 'center';
			ctx.shadowColor = 'rgba(0,0,0,0.5)';
			ctx.shadowBlur = 16;
			ctx.fillText(nick, centerX, yPos);
			yPos += 60;

			// Nivel
			const nivel = score?.nivel || 'Bronce';
			const icono = score?.icono_nivel || '🥉';
			ctx.font = '700 44px Outfit, sans-serif';
			ctx.fillStyle = nivelColor(nivel);
			ctx.fillText(`${icono} ${nivel}`, centerX, yPos);
			yPos += 90;

			// Puntos
			ctx.fillStyle = '#FFD700';
			ctx.shadowColor = 'rgba(255,215,0,0.6)';
			ctx.shadowBlur = 40;
			ctx.font = '900 128px Outfit, sans-serif';
			ctx.fillText(`${counterAnim}`, centerX, yPos);
			ctx.shadowBlur = 0;
			yPos += 50;

			// Label puntos
			ctx.fillStyle = 'rgba(255,255,255,0.8)';
			ctx.font = '700 32px Outfit, sans-serif';
			ctx.fillText('ECCSA POINTS', centerX, yPos);
			yPos += 80;

			// Stats
			const racha = score?.racha_dias ?? 0;
			const pos = ranking.find((r: any) => r.es_yo)?.posicion || '?';
			ctx.font = '700 40px Outfit, sans-serif';
			ctx.fillStyle = '#ffffff';
			ctx.fillText(`🔥 ${racha} días racha    #${pos} posición`, centerX, yPos);

			// Compartir
			const blob = await new Promise<Blob>((resolve) => {
				cvs.toBlob((b: Blob) => resolve(b!), 'image/png');
			});
			const fileName = `${nick.replace(/\s+/g, '-').toLowerCase()}.png`;
			const file = new File([blob], fileName, { type: 'image/png' });
			if (navigator.share && navigator.canShare?.({ files: [file] })) {
				await navigator.share({
					title: 'ECCSA Legends',
					text: `Mira mis puntos en ECCSA Legends: ${counterAnim} pts semanales`,
					files: [file],
				});
			} else {
				const url = URL.createObjectURL(blob);
				const a = document.createElement('a');
				a.href = url; a.download = fileName; a.click();
				URL.revokeObjectURL(url);
			}
		} catch (e) { console.error('Share error:', e); }
		shareLoading = false;
	}

	onMount(async () => {
		// Cargar cache offline primero
		await loadCachedData();

		if ($online) {
			try {
				const [s, a, r, w, wh, cel, sl] = await Promise.all([
					api.get('/legends/score').catch(() => null),
					api.get('/legends/avatar').catch(() => null),
					api.get('/legends/ranking').catch(() => ({ ranking: [] })),
					api.get('/legends/weekly-winner').catch(() => null),
					api.get('/legends/winners').catch(() => ({ winners: [] })),
					api.get('/legends/celebrations').catch(() => null),
					api.get('/legends/score-log').catch(() => null),
				]);
				score = s;
				avatar = a;
				ranking = r.ranking || [];
				weeklyWinner = w;
				winners = wh.winners || [];
				celebrations = cel;
				scoreLog = sanitizeScoreLog(sl);
				await cacheLegendsData();
			} catch {}
		}

		if (score?.puntuacion_semanal !== undefined) {
			animateCounter(score.puntuacion_semanal);
		}

		loading = false;
		setTimeout(() => { initParticles(); }, 100);
	});

	onDestroy(() => {
		if (animFrame) cancelAnimationFrame(animFrame);
	});

	function medalEmoji(pos: number) {
		if (pos === 1) return '🥇';
		if (pos === 2) return '🥈';
		if (pos === 3) return '🥉';
		return `#${pos}`;
	}

	function nivelColor(nivel: string) {
		switch (nivel) {
			case 'Diamante': return '#00BCD4';
			case 'Oro': return '#FFD700';
			case 'Plata': return '#C0C0C0';
			default: return '#CD7F32';
		}
	}

	function nivelGlow(nivel: string) {
		switch (nivel) {
			case 'Diamante': return '0 0 30px rgba(0,188,212,0.5)';
			case 'Oro': return '0 0 30px rgba(255,215,0,0.5)';
			case 'Plata': return '0 0 20px rgba(192,192,192,0.3)';
			default: return '0 0 15px rgba(205,127,50,0.2)';
		}
	}

	function getMonthName(): string {
		if (celebrations?.mes) return celebrations.mes;
		const m = new Date().getMonth();
		const months = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
		return months[m];
	}

	function formatDate(d: string) {
		if (!d) return '';
		return new Date(d).toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: '2-digit' });
	}
</script>

<svelte:head>
	<style>
		@keyframes pulse-glow { 0%,100% { opacity: 0.4; } 50% { opacity: 0.8; } }
		@keyframes slide-up { from { opacity:0; transform:translateY(20px); } to { opacity:1; transform:translateY(0); } }
		@keyframes shimmer { 0% { background-position: -200% center; } 100% { background-position: 200% center; } }
		@keyframes bounce-in { 0% { transform: scale(0.3); opacity:0; } 50% { transform: scale(1.05); } 70% { transform: scale(0.9); } 100% { transform: scale(1); opacity:1; } }
		@keyframes neon-pulse { 0%,100% { text-shadow: 0 0 10px #FF6B00, 0 0 20px #FF6B00, 0 0 40px #FF6B00; } 50% { text-shadow: 0 0 20px #FF6B00, 0 0 40px #FF6B00, 0 0 80px #FF6B00; } }
	
	/* Hero 9:16 — White bg, avatar gigante, overlay */
	.hero-card-916 { aspect-ratio: 9/16; max-height: 72vh; width: 100%; max-width: 340px; margin: 0 auto 0.8rem; background: transparent; border-radius: 28px; position: relative; overflow: hidden; z-index: 1; box-shadow: 0 8px 32px rgba(0,0,0,0.3); display: flex; flex-direction: column; align-items: center; justify-content: flex-end; }
	.hero-bg-engrane { position: absolute; top: 5%; left: 50%; transform: translateX(-50%); width: 120%; max-width: 500px; opacity: 0.08; pointer-events: none; z-index: 0; filter: grayscale(0.3); }
	.hero-avatar-img-full { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; object-position: top center; z-index: 1; }
	.hero-avatar-placeholder-full { position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 8rem; background: linear-gradient(180deg, #0a0f1a 0%, #050810 100%); z-index: 1; }
	.hero-overlay { position: relative; z-index: 3; width: 100%; padding: 2rem 1rem 1rem; background: linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.6) 40%, rgba(0,0,0,0.85) 100%); text-align: center; }
	.hero-name { font-size: 1.3rem; font-weight: 900; color: #ffffff; letter-spacing: 0.03em; text-shadow: 0 2px 8px rgba(0,0,0,0.5); }
	.hero-nivel { font-size: 0.8rem; font-weight: 700; margin-top: 0.1rem; text-shadow: 0 1px 4px rgba(0,0,0,0.5); }
	.hero-score { text-align: center; margin-top: 0.3rem; }
	.hero-score-num { font-size: 2.8rem; font-weight: 900; line-height: 1; display: block; color: #FFD700; text-shadow: 0 0 20px rgba(255,215,0,0.6), 0 2px 8px rgba(0,0,0,0.5); }
	.hero-score-label { font-size: 0.6rem; color: rgba(255,255,255,0.8); text-transform: uppercase; letter-spacing: 0.2em; font-weight: 700; display: block; text-shadow: 0 1px 4px rgba(0,0,0,0.5); }
	.hero-stats { display: flex; gap: 2rem; justify-content: center; margin-top: 0.5rem; }
	.hero-stat { display: flex; flex-direction: column; align-items: center; }
	.hero-stat-val { font-size: 0.9rem; font-weight: 700; color: #ffffff; text-shadow: 0 1px 4px rgba(0,0,0,0.5); }
	.hero-stat-label { font-size: 0.5rem; color: rgba(255,255,255,0.7); text-transform: uppercase; text-shadow: 0 1px 4px rgba(0,0,0,0.5); }
	.share-btn { z-index: 2; width: 100%; padding: 0.7rem; border-radius: 14px; border: 1px solid rgba(255,107,0,0.3); background: linear-gradient(135deg, rgba(255,107,0,0.15), rgba(255,171,0,0.1)); color: #FFAE00; font-weight: 700; font-size: 0.8rem; cursor: pointer; transition: all 0.3s; }
	.share-btn:hover { background: linear-gradient(135deg, rgba(255,107,0,0.25), rgba(255,171,0,0.2)); border-color: #FF6B00; box-shadow: 0 0 20px rgba(255,107,0,0.2); }
	.share-btn:disabled { opacity: 0.5; cursor: not-allowed; }
	.share-spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid rgba(255,174,0,0.3); border-top-color: #FFAE00; border-radius: 50%; animation: spin 0.8s linear infinite; vertical-align: middle; margin-right: 0.3rem; }
</style>
</svelte:head>

<div class="legends-page">
	<!-- PARTICLES CANVAS -->
	<canvas bind:this={canvas} class="particles-canvas"></canvas>

	{#if loading}
		<div class="loading">
			<div class="loading-ring">
				<div class="ring-inner">🏆</div>
			</div>
			<span class="loading-text">Cargando leyendas...</span>
		</div>
	{:else}
		<!-- HEADER -->
		<div class="legends-header" style="animation: slide-up 0.5s ease-out">
			<button class="back-btn" onclick={() => goto('/')}>←</button>
			<h1 class="title-epic">ECCSA LEGENDS</h1>
			<div></div>
		</div>

		<!-- WEEKLY WINNER -->
		{#if weeklyWinner?.hay_ganador}
			<div class="weekly-banner" style="animation: slide-up 0.6s ease-out">
				<div class="weekly-crown">👑</div>
				<div class="weekly-text">
					<span class="weekly-label">⚡ LEYENDA DE LA SEMANA ⚡</span>
					<span class="weekly-name">{weeklyWinner.nombre}</span>
					<span class="weekly-pts">{weeklyWinner.puntuacion} ECCSA Points</span>
				</div>
				<div class="weekly-sparkles">✨</div>
			</div>
		{/if}

		<!-- HERO CARD 9:16 — White, avatar gigante, overlay -->
		<div class="hero-card-916" style="animation: slide-up 0.7s ease-out">
			<img src="/engrane.png" alt="" class="hero-bg-engrane" />

			{#if avatar?.avatar}
				<img src="data:image/png;base64,{avatar.avatar}" alt="Avatar" class="hero-avatar-img-full" />
			{:else}
				<div class="hero-avatar-placeholder-full">👤</div>
			{/if}

			{#if ranking.length > 0}
				<div class="position-badge">
					<span class="position-hash">#</span>
					<span class="position-num">{ranking.find((r: any) => r.es_yo)?.posicion || '?'}</span>
					<span class="position-total">/ {ranking.length}</span>
				</div>
			{/if}

			<div class="hero-overlay">
				<div class="hero-name">{score?.nickname || avatar?.nickname || user?.nombre || 'Jugador'}</div>
				<div class="hero-nivel" style="color: {(ranking.find((r: any) => r.es_yo)?.posicion || 99) <= 3 ? nivelColor(score?.nivel || 'Bronce') : '#64748b'}">
					{medalEmoji(ranking.find((r: any) => r.es_yo)?.posicion || 0)}
				</div>
				<div class="hero-score">
					<span class="hero-score-num">{counterAnim}</span>
					<span class="hero-score-label">ECCSA POINTS</span>
				</div>
				<div class="hero-stats">
					<div class="hero-stat">
						<span class="hero-stat-val">🔥 {score?.racha_dias ?? 0}</span>
						<span class="hero-stat-label">Días racha</span>
					</div>
					<div class="hero-stat">
						<span class="hero-stat-val">{ranking.find((r: any) => r.es_yo)?.posicion || '?'}</span>
						<span class="hero-stat-label">Posición</span>
					</div>
				</div>
			</div>
		</div>

		<button class="share-btn" onclick={shareCard} disabled={shareLoading}>
			{#if shareLoading}
				<span class="share-spinner"></span> Generando...
			{:else}
				📱 Compartir como imagen
			{/if}
		</button>

<!-- TABS -->
		<div class="tabs" style="animation: slide-up 1.1s ease-out">
			<button class="tab" class:active={tab === 'ranking'} onclick={() => tab = 'ranking'}>
				<span class="tab-icon">📊</span>
			</button>
			<button class="tab" class:active={tab === 'rivales'} onclick={() => tab = 'rivales'}>
				<span class="tab-icon">🏁</span>
			</button>
			<button class="tab" class:active={tab === 'mis_puntos'} onclick={() => tab = 'mis_puntos'}>
				<span class="tab-icon">📋</span>
			</button>
			<button class="tab" class:active={tab === 'historial'} onclick={() => tab = 'historial'}>
				<span class="tab-icon">🏆</span>
			</button>
		</div>

		{#if tab === 'ranking'}
			<div class="ranking-section" style="animation: slide-up 1.2s ease-out">
				{#if ranking.length === 0}
					<div class="empty-epic">
						<span class="empty-icon">🎮</span>
						<span>Sin actividad aún</span>
						<span class="empty-sub">¡Sé el primero en competir!</span>
					</div>
				{:else}
					<div class="ranking-list">
						{#each ranking as r, i (r.id_usuario)}
							<div class="rank-item" class:is-me={r.es_yo} class:is-top3={r.posicion <= 3}
								style="animation: slide-up {1.2 + i * 0.08}s ease-out">
								<div class="rank-pos" class:medal={r.posicion <= 3}>
									{medalEmoji(r.posicion)}
								</div>
								<div class="rank-avatar" style="box-shadow: {r.posicion <= 3 ? '0 0 12px ' + nivelColor(r.nivel) : 'none'}">
									{#if r.avatar}
										<img src="data:image/png;base64,{r.avatar}" alt="" class="rank-avatar-img" />
									{:else}
										<div class="rank-avatar-placeholder">👤</div>
									{/if}
								</div>
								<div class="rank-info">
									<span class="rank-name">{r.nombre}{r.es_yo ? ' ⭐' : ''}</span>
								</div>
								<div class="rank-pts">
									{r.puntuacion_semanal}
									<span class="pts-label"> pts</span>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		{:else if tab === 'rivales'}
			<div class="rivales-section" style="animation: slide-up 1.2s ease-out">
				{#if ranking.length === 0}
					<div class="empty-epic">
						<span class="empty-icon">👥</span>
						<span>Sin rivales aún</span>
						<span class="empty-sub">Los rivales aparecen cuando hay actividad</span>
					</div>
				{:else}
					<div class="rivales-counter">
						<span class="rivales-counter-val">{rivalesIndex + 1}</span>
						<span class="rivales-counter-sep"> / </span>
						<span class="rivales-counter-total">{ranking.length}</span>
					</div>
					<div class="rivales-container">
						<button class="rivales-btn prev" onclick={() => scrollRivales(-1)} aria-label="Anterior">
							<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<path d="M15 18l-6-6 6-6"/>
							</svg>
						</button>
						<div class="rivales-track" bind:this={rivalesTrack}>
							{#each ranking as r, i (r.id_usuario)}
								{#if i === rivalesIndex}
									<div class="rivales-card" class:is-me={r.es_yo} class:is-top3={r.posicion <= 3}>
										<div class="card-glow" style="background: linear-gradient(135deg, {nivelColor(r.nivel)}22, {nivelColor(r.nivel)}00); box-shadow: inset 0 0 40px {nivelColor(r.nivel)}22;"></div>
										<div class="card-medal" style="color: {r.posicion <= 3 ? nivelColor(r.nivel) : '#64748b'}">
											{medalEmoji(r.posicion)}
										</div>
										<div class="card-avatar-wrapper" style="box-shadow: 0 0 20px {nivelColor(r.nivel)};">
											{#if r.avatar}
												<img src="data:image/png;base64,{r.avatar}" alt="" class="card-avatar-img" />
											{:else}
												<div class="card-avatar-placeholder">👤</div>
											{/if}
											{#if r.posicion === 1}
												<div class="crown-badge">👑</div>
											{/if}
										</div>
										<div class="card-name">{r.nombre}{r.es_yo ? ' ⭐' : ''}</div>
										<div class="card-nivel" style="color: {r.posicion <= 3 ? nivelColor(r.nivel) : '#64748b'}">{medalEmoji(r.posicion)}</div>
										<div class="card-stats">
											<div class="stat">
												<span class="stat-val">{r.puntuacion_semanal}</span>
												<span class="stat-label">Pts Sem</span>
											</div>
											<div class="stat fire">
												<span class="stat-val">{r.racha_dias ?? 0}</span>
												<span class="stat-label">🔥 Días</span>
											</div>
										</div>
										{#if r.es_yo}
											<div class="me-badge">TÚ</div>
										{/if}
									</div>
								{/if}
							{/each}
						</div>
						<button class="rivales-btn next" onclick={() => scrollRivales(1)} aria-label="Siguiente">
							<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<path d="M9 18l6-6-6-6"/>
							</svg>
						</button>
					</div>
				{/if}
			</div>
		{:else if tab === 'historial'}
			<div class="winners-section" style="animation: slide-up 1.2s ease-out">
				{#if winners.length === 0}
					<div class="empty-epic">
						<span class="empty-icon">📅</span>
						<span>Aún no hay ganadores</span>
						<span class="empty-sub">Los domingos se calcula la leyenda semanal</span>
					</div>
				{:else}
					<div class="winners-list">
						{#each winners as w, i}
							<div class="winner-item" class:first={i === 0}
								style="animation: slide-up {1.2 + i * 0.08}s ease-out">
								<div class="winner-medal">{i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : '📅'}</div>
								<div class="winner-info">
									<span class="winner-name">{w.nombre}</span>
									<span class="winner-date">{formatDate(w.fecha_inicio)} — {formatDate(w.fecha_fin)}</span>
								</div>
								<div class="winner-pts">{w.puntuacion} <span class="pts-label">pts</span></div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		{:else if tab === 'mis_puntos'}
			<div class="score-log-section" style="animation: slide-up 1.2s ease-out">
				{#if !scoreLog}
					<div class="empty-epic">
						<span class="empty-icon">📋</span>
						<span>Sin datos esta semana</span>
						<span class="empty-sub">Tus puntos aparecerán aquí</span>
					</div>
				{:else if scoreLog.eventos?.length === 0}
					<div class="empty-epic">
						<span class="empty-icon">🎯</span>
						<span>Sin actividad esta semana</span>
						<span class="empty-sub">¡Registra reportes, kilómetros o tickets para ganar puntos!</span>
					</div>
				{:else}
					<div class="score-log-header">
						<div class="score-log-total">
							<span class="total-num">{scoreLog.total_semana}</span>
							<span class="total-label">ECCSA Points esta semana</span>
						</div>
						<div class="score-log-sync">
							🔄 Sincronización en tiempo real<br/>
							📅 Reset: domingo 3:00 AM
						</div>
					</div>
					<div class="score-log-list">
						{#each scoreLog.eventos as evt, i}
							<div class="score-log-item" class:positive={evt.puntos > 0} class:negative={evt.puntos < 0}
								style="animation: slide-up {1.2 + i * 0.05}s ease-out">
								<div class="log-icon">{evt.icono}</div>
								<div class="log-info">
									<span class="log-desc">{evt.descripcion}</span>
									<span class="log-time">{new Date(evt.fecha).toLocaleString('es-MX', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: 'short' })}</span>
								</div>
								<div class="log-pts" class:pos={evt.puntos > 0} class:neg={evt.puntos < 0}>
									{evt.puntos > 0 ? '+' : ''}{evt.puntos}
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		{/if}
	{/if}
</div>

<style>
	.legends-page {
		min-height: 100vh; background: #050810;
		padding: 1rem; padding-bottom: 5rem;
		font-family: 'Outfit', sans-serif; position: relative; overflow: hidden;
	}

	/* ── Particles ── */
	.particles-canvas {
		position: absolute; top: 0; left: 0; width: 100%; height: 300px;
		pointer-events: none; z-index: 0;
	}

	/* ── Loading ── */
	.loading { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 60vh; gap: 1.5rem; z-index: 1; position: relative; }
	.loading-ring {
		width: 80px; height: 80px; border-radius: 50%;
		border: 3px solid rgba(255,107,0,0.1);
		border-top-color: #FF6B00; border-right-color: #FFD700;
		animation: spin 1s linear infinite;
		display: flex; align-items: center; justify-content: center;
	}
	.ring-inner { font-size: 2rem; animation: spin 1s linear infinite reverse; }
	.loading-text { color: #FF6B00; font-size: 0.9rem; font-weight: 600; letter-spacing: 0.1em; }
	@keyframes spin { to { transform: rotate(360deg); } }

	/* ── Header ── */
	.legends-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; position: relative; z-index: 1; }
	.back-btn { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; color: #94a3b8; font-size: 1.2rem; cursor: pointer; padding: 0.4rem 0.6rem; transition: all 0.2s; }
	.back-btn:hover { background: rgba(255,107,0,0.15); border-color: #FF6B00; color: #FF6B00; }
	.title-epic {
		font-size: 1.1rem; font-weight: 900; letter-spacing: 0.15em;
		background: linear-gradient(90deg, #FF6B00, #FFD700, #FF6B00);
		background-size: 200% auto;
		-webkit-background-clip: text; -webkit-text-fill-color: transparent;
		background-clip: text;
		animation: shimmer 3s linear infinite;
	}

	/* ── Weekly Banner ── */
	.weekly-banner {
		background: linear-gradient(135deg, rgba(255,215,0,0.12), rgba(255,107,0,0.08));
		border: 1px solid rgba(255,215,0,0.3); border-radius: 16px;
		padding: 0.8rem 1rem; margin-bottom: 1rem;
		display: flex; align-items: center; gap: 0.8rem;
		position: relative; overflow: hidden; z-index: 1;
		box-shadow: 0 0 20px rgba(255,215,0,0.1);
	}
	.weekly-crown { font-size: 2.2rem; animation: float 3s ease-in-out infinite; }
	.weekly-text { display: flex; flex-direction: column; flex: 1; }
	.weekly-label { font-size: 0.6rem; color: #FFD700; text-transform: uppercase; letter-spacing: 0.15em; font-weight: 700; }
	.weekly-name { font-size: 1rem; font-weight: 800; color: #f1f5f9; }
	.weekly-pts { font-size: 0.75rem; color: #FFD700; font-weight: 600; }
	.weekly-sparkles { font-size: 1.5rem; animation: pulse-glow 1.5s ease-in-out infinite; }

	/* ── Hero Card ── */
	.hero-card {
		background: linear-gradient(180deg, rgba(20,30,50,0.95), rgba(8,12,25,0.98));
		border: 1px solid rgba(255,255,255,0.08); border-radius: 24px;
		padding: 2rem 1.2rem 1.5rem; text-align: center; margin-bottom: 1.2rem;
		position: relative; overflow: hidden; z-index: 1;
		box-shadow: 0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.05);
	}

	.hero-bg-effects { position: absolute; inset: 0; overflow: hidden; pointer-events: none; z-index: 0; }
	.hex {
		position: absolute; border-radius: 50%;
		filter: blur(60px); opacity: 0.08;
	}

	/* Avatar - Epic Animation */
	.avatar-wrapper {
		position: relative; width: 180px; height: 180px; margin: 0 auto 1rem; z-index: 2;
		animation: avatar-float 4s ease-in-out infinite;
	}
	@keyframes avatar-float { 0%,100% { transform: translateY(0px); } 50% { transform: translateY(-10px); } }

	/* Anillo exterior lento */
	.avatar-ring-outer {
		position: absolute; inset: -14px; border-radius: 50%;
		border: 2px solid var(--glow-color); opacity: 0.25;
		animation: ring-breathe 3s ease-in-out infinite;
	}
	@keyframes ring-breathe { 0%,100% { transform: scale(1); opacity: 0.25; } 50% { transform: scale(1.05); opacity: 0.4; } }

	/* Anillo giratorio con gradiente */
	.avatar-ring-spin {
		position: absolute; inset: -8px; border-radius: 50%;
		background: conic-gradient(from 0deg, transparent 0%, var(--glow-color) 25%, transparent 50%, var(--glow-color) 75%, transparent 100%);
		opacity: 0.5; animation: spin 4s linear infinite;
		mask: radial-gradient(farthest-side, transparent calc(100% - 2px), #fff calc(100% - 2px));
		-webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 2px), #fff calc(100% - 2px));
	}
	@keyframes spin { to { transform: rotate(360deg); } }

	/* Anillo interior sutil */
	.avatar-ring-inner {
		position: absolute; inset: -3px; border-radius: 50%;
		border: 1px solid rgba(255,255,255,0.1);
	}

	/* Imagen del avatar */
	.avatar-wrapper .avatar-img {
		width: 180px; height: 180px; border-radius: 50%; object-fit: cover;
		position: relative; z-index: 3;
		border: 3px solid rgba(255,255,255,0.15);
		box-shadow: 0 0 30px var(--glow-color), inset 0 0 20px rgba(0,0,0,0.3);
	}

	/* Glow principal pulsante */
	.avatar-glow-main {
		position: absolute; inset: -20px; border-radius: 50%; z-index: 0;
		background: var(--glow-color); opacity: 0.15; filter: blur(25px);
		animation: glow-pulse 2.5s ease-in-out infinite;
	}
	@keyframes glow-pulse { 0%,100% { opacity: 0.15; transform: scale(1); } 50% { opacity: 0.3; transform: scale(1.08); } }

	/* Glow ring sutil */
	.avatar-glow-ring {
		position: absolute; inset: -35px; border-radius: 50%; z-index: 0;
		border: 1px solid var(--glow-color); opacity: 0.08;
		animation: ring-expand 4s ease-in-out infinite;
	}
	@keyframes ring-expand { 0%,100% { transform: scale(0.9); opacity: 0.08; } 50% { transform: scale(1.05); opacity: 0.15; } }

	/* Partículas orbitales */
	.avatar-particles { position: absolute; inset: 0; z-index: 4; pointer-events: none; }
	.particle {
		position: absolute; width: 4px; height: 4px; border-radius: 50%;
		background: var(--glow-color); opacity: 0;
		left: 50%; top: 50%;
		animation: orbit var(--duration) linear var(--delay) infinite;
		box-shadow: 0 0 6px var(--glow-color), 0 0 12px var(--glow-color);
	}
	@keyframes orbit {
		0% { transform: rotate(calc(var(--i) * 45deg)) translateX(85px) rotate(calc(var(--i) * -45deg)); opacity: 0; }
		10% { opacity: 0.8; }
		50% { opacity: 0.4; }
		90% { opacity: 0.8; }
		100% { transform: rotate(calc(var(--i) * 45deg + 360deg)) translateX(85px) rotate(calc(var(--i) * -45deg - 360deg)); opacity: 0; }
	}

	/* Sparkles para Diamante */
	.diamond-sparkles { position: absolute; inset: -40px; z-index: 5; pointer-events: none; }
	.sparkle {
		position: absolute; font-size: 0.7rem; color: #FFAE00;
		left: 50%; top: 50%;
		animation: sparkle-float 2.5s ease-in-out calc(var(--i) * 0.4s) infinite;
		text-shadow: 0 0 8px #FFAE00, 0 0 16px #FF6B00;
	}
	.sparkle:nth-child(1) { transform: rotate(0deg) translateY(-70px); }
	.sparkle:nth-child(2) { transform: rotate(60deg) translateY(-70px); }
	.sparkle:nth-child(3) { transform: rotate(120deg) translateY(-70px); }
	.sparkle:nth-child(4) { transform: rotate(180deg) translateY(-70px); }
	.sparkle:nth-child(5) { transform: rotate(240deg) translateY(-70px); }
	.sparkle:nth-child(6) { transform: rotate(300deg) translateY(-70px); }
	@keyframes sparkle-float {
		0%,100% { opacity: 0; transform: rotate(calc(var(--i) * 60deg)) translateY(-65px) scale(0.5); }
		50% { opacity: 1; transform: rotate(calc(var(--i) * 60deg)) translateY(-75px) scale(1.2); }
	}

	.avatar-placeholder {
		font-size: 3.5rem; display: flex; align-items: center; justify-content: center;
		background: rgba(30,41,59,0.8); border-radius: 50%; width: 180px; height: 180px;
	}

	.player-name { font-size: 1.15rem; font-weight: 700; color: #f1f5f9; margin-bottom: 0.6rem; letter-spacing: 0.05em; position: relative; z-index: 2; }

	.passkey-banner {
		background: linear-gradient(135deg, rgba(255,107,0,0.15), rgba(255,171,0,0.1));
		border: 1px solid rgba(255,107,0,0.3); border-radius: 12px;
		padding: 0.8rem 1rem; margin-bottom: 1rem;
		display: flex; flex-direction: column; align-items: center; gap: 0.3rem;
		position: relative; z-index: 2;
	}
	.passkey-icon { font-size: 1.5rem; }
	.passkey-text { font-size: 0.7rem; color: #FFAE00; font-weight: 600; text-align: center; }
	.passkey-hint { font-size: 0.6rem; color: #94a3b8; }

	.score-visible { text-align: center; margin-bottom: 0.5rem; position: relative; z-index: 2; }
	.score-visible-num {
		font-size: 2.2rem; font-weight: 900; line-height: 1; display: block;
		background: linear-gradient(180deg, #FF6B00, #FFD700);
		-webkit-background-clip: text; -webkit-text-fill-color: transparent;
		background-clip: text;
		animation: neon-pulse 3s ease-in-out infinite;
	}
	.score-visible-label { font-size: 0.55rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.15em; }

	/* Score de fondo (detras del avatar) */
	.score-bg {
		position: absolute; top: 50%; left: 50%; transform: translate(-50%, -60%);
		text-align: center; z-index: 1; pointer-events: none;
	}
	.score-bg-number {
		font-size: 5rem; font-weight: 900; line-height: 1; display: block;
		background: linear-gradient(180deg, rgba(255,107,0,0.25), rgba(255,215,0,0.15));
		-webkit-background-clip: text; -webkit-text-fill-color: transparent;
		background-clip: text;
		filter: blur(1px);
	}
	.score-bg-label {
		font-size: 0.55rem; color: rgba(255,107,0,0.3); text-transform: uppercase;
		letter-spacing: 0.2em; font-weight: 700;
	}

	/* Stats */
	.stats-row { display: flex; justify-content: center; gap: 1rem; }
	.stat-badge {
		display: flex; align-items: center; gap: 0.4rem;
		background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
		border-radius: 20px; padding: 0.4rem 0.8rem;
	}
	.stat-badge.fire { border-color: rgba(249,115,22,0.3); background: rgba(249,115,22,0.08); }
	.stat-icon { font-size: 1rem; }
	.stat-val { font-size: 0.75rem; color: #94a3b8; font-weight: 600; }

	/* Tabs */
	.tabs { display: flex; gap: 0.5rem; margin-bottom: 1rem; position: relative; z-index: 1; }
	.tab {
		flex: 1; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);
		border-radius: 12px; padding: 0.7rem; color: #64748b; font-size: 0.8rem;
		font-weight: 600; cursor: pointer; text-align: center; transition: all 0.3s;
		display: flex; align-items: center; justify-content: center; gap: 0.4rem;
	}
	.tab.active {
		background: linear-gradient(135deg, rgba(255,107,0,0.15), rgba(255,215,0,0.08));
		border-color: rgba(255,107,0,0.4); color: #FF6B00;
		box-shadow: 0 0 15px rgba(255,107,0,0.15);
	}
	.tab-icon { font-size: 1rem; }

	/* Ranking */
	.ranking-section { margin-bottom: 1.5rem; position: relative; z-index: 1; }
	.empty-epic { display: flex; flex-direction: column; align-items: center; padding: 2.5rem 0; gap: 0.5rem; }
	.empty-icon { font-size: 3rem; opacity: 0.5; }
	.empty-epic span:nth-child(2) { color: #64748b; font-size: 0.9rem; }
	.empty-sub { color: #475569; font-size: 0.75rem; }

	.ranking-list { display: flex; flex-direction: column; gap: 0.5rem; }
	.rank-item {
		display: flex; align-items: center; gap: 0.6rem;
		background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);
		border-radius: 14px; padding: 0.7rem 0.8rem; transition: all 0.3s;
	}
	.rank-item.is-me {
		border-color: rgba(255,107,0,0.4);
		background: linear-gradient(135deg, rgba(255,107,0,0.1), rgba(255,107,0,0.03));
		box-shadow: 0 0 15px rgba(255,107,0,0.1);
	}
	.rank-item.is-top3 { background: rgba(255,215,0,0.04); border-color: rgba(255,215,0,0.15); }
	.rank-pos { font-size: 1rem; font-weight: 800; color: #475569; min-width: 2.2rem; text-align: center; }
	.rank-pos.medal { font-size: 1.4rem; }
	.rank-avatar { width: 36px; height: 36px; flex-shrink: 0; border-radius: 50%; overflow: hidden; }
	.rank-avatar-img { width: 36px; height: 36px; border-radius: 50%; object-fit: cover; }
	.rank-avatar-placeholder { width: 36px; height: 36px; border-radius: 50%; background: rgba(255,255,255,0.06); display: flex; align-items: center; justify-content: center; font-size: 1rem; }
	.rank-info { flex: 1; display: flex; flex-direction: column; }
	.rank-name { font-size: 0.85rem; font-weight: 600; color: #e2e8f0; }
	.rank-nivel { font-size: 0.65rem; font-weight: 600; }
	.rank-pts { font-size: 1rem; font-weight: 800; color: #FF6B00; }
	.pts-label { font-size: 0.6rem; color: #64748b; font-weight: 400; }

	/* Winners */
	.winners-section { margin-bottom: 1.5rem; position: relative; z-index: 1; }
	.winners-list { display: flex; flex-direction: column; gap: 0.5rem; }
	.winner-item { display: flex; align-items: center; gap: 0.6rem; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; padding: 0.6rem 0.8rem; }
	.winner-item.first { background: linear-gradient(135deg, rgba(255,215,0,0.1), rgba(255,215,0,0.03)); border-color: rgba(255,215,0,0.25); box-shadow: 0 0 15px rgba(255,215,0,0.08); }
	.winner-medal { font-size: 1.3rem; }
	.winner-info { flex: 1; display: flex; flex-direction: column; }
	.winner-name { font-size: 0.85rem; font-weight: 600; color: #e2e8f0; }
	.winner-date { font-size: 0.65rem; color: #64748b; }
	.winner-pts { font-size: 0.95rem; font-weight: 800; color: #FFD700; }

	/* Rivales */
	.rivales-section { margin-bottom: 1.5rem; position: relative; z-index: 1; }
	.rivales-counter {
		text-align: center; margin-bottom: 0.8rem;
		font-size: 0.85rem; color: #64748b; font-weight: 600;
	}
	.rivales-counter-val { color: #FF6B00; font-size: 1.1rem; font-weight: 800; }
	.rivales-counter-sep { color: #475569; }
	.rivales-counter-total { color: #94a3b8; }
	.rivales-container {
		display: flex; align-items: center; gap: 0.5rem; position: relative;
	}
	.rivales-btn {
		flex-shrink: 0; width: 40px; height: 40px; border-radius: 50%;
		background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
		color: #94a3b8; display: flex; align-items: center; justify-content: center;
		cursor: pointer; transition: all 0.2s; z-index: 2;
	}
	.rivales-btn:hover { background: rgba(255,107,0,0.15); border-color: #FF6B00; color: #FF6B00; }
	.rivales-track {
		flex: 1; display: flex; justify-content: center; min-height: 320px;
		position: relative; overflow: hidden;
	}
	.rivales-card {
		width: 100%; max-width: 300px; border-radius: 20px; padding: 1.5rem 1rem;
		background: linear-gradient(180deg, rgba(20,30,50,0.95), rgba(8,12,25,0.98));
		border: 1px solid rgba(255,255,255,0.08);
		position: relative; overflow: hidden; text-align: center;
		box-shadow: 0 8px 32px rgba(0,0,0,0.4);
		animation: slide-up 0.3s ease-out;
	}
	.rivales-card.is-me {
		border-color: rgba(255,107,0,0.4);
		box-shadow: 0 0 20px rgba(255,107,0,0.15), 0 8px 32px rgba(0,0,0,0.4);
	}
	.rivales-card.is-top3 { border-color: rgba(255,215,0,0.2); }
	.card-glow {
		position: absolute; inset: 0; pointer-events: none; z-index: 0;
	}
	.card-medal { font-size: 1.8rem; margin-bottom: 0.8rem; position: relative; z-index: 1; }
	.card-avatar-wrapper {
		width: 100px; height: 100px; border-radius: 50%; margin: 0 auto 0.8rem;
		overflow: visible; position: relative; z-index: 1;
	}
	.card-avatar-img { width: 100px; height: 100px; border-radius: 50%; object-fit: cover; border: 3px solid rgba(255,255,255,0.15); }
	.card-avatar-placeholder {
		width: 100px; height: 100px; border-radius: 50%;
		background: rgba(255,255,255,0.06); display: flex; align-items: center; justify-content: center;
		font-size: 2.5rem; border: 3px solid rgba(255,255,255,0.1);
	}
	.crown-badge {
		position: absolute; top: -8px; right: -4px; font-size: 1.5rem; z-index: 2;
		filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5));
	}
	.crown-badge.silver { font-size: 1.3rem; }
	.crown-badge.bronze { font-size: 1.3rem; }
	.card-name { font-size: 1.1rem; font-weight: 700; color: #f1f5f9; margin-bottom: 0.3rem; position: relative; z-index: 1; }
	.card-nivel { font-size: 0.75rem; font-weight: 600; margin-bottom: 0.8rem; position: relative; z-index: 1; }
	.card-stats {
		display: flex; justify-content: center; gap: 1rem; position: relative; z-index: 1;
	}
	.card-stats .stat { display: flex; flex-direction: column; align-items: center; }
	.card-stats .stat-val { font-size: 1.1rem; font-weight: 800; color: #FF6B00; }
	.card-stats .stat.fire .stat-val { color: #f97316; }
	.card-stats .stat-label { font-size: 0.6rem; color: #64748b; }
	.me-badge {
		position: absolute; top: 12px; right: 12px;
		background: linear-gradient(135deg, #FF6B00, #FFD700);
		color: #050810; font-size: 0.6rem; font-weight: 800;
		padding: 0.2rem 0.5rem; border-radius: 8px;
		box-shadow: 0 2px 8px rgba(255,107,0,0.4); z-index: 2;
	}

	/* Hero 9:16 — White bg, avatar gigante, overlay */
	.hero-card-916 { aspect-ratio: 9/16; max-height: 72vh; width: 100%; max-width: 340px; margin: 0 auto 0.8rem; background: transparent; border-radius: 28px; position: relative; overflow: hidden; z-index: 1; box-shadow: 0 8px 32px rgba(0,0,0,0.3); display: flex; flex-direction: column; align-items: center; justify-content: flex-end; }
	.hero-bg-engrane { position: absolute; top: 5%; left: 50%; transform: translateX(-50%); width: 120%; max-width: 500px; opacity: 0.08; pointer-events: none; z-index: 0; filter: grayscale(0.3); }
	.hero-avatar-img-full { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; object-position: top center; z-index: 1; }
	.hero-avatar-placeholder-full { position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 8rem; background: linear-gradient(180deg, #0a0f1a 0%, #050810 100%); z-index: 1; }
	.hero-overlay { position: relative; z-index: 3; width: 100%; padding: 2rem 1rem 1rem; background: linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.6) 40%, rgba(0,0,0,0.85) 100%); text-align: center; }
	.hero-name { font-size: 1.3rem; font-weight: 900; color: #ffffff; letter-spacing: 0.03em; text-shadow: 0 2px 8px rgba(0,0,0,0.5); }
	.hero-nivel { font-size: 0.8rem; font-weight: 700; margin-top: 0.1rem; text-shadow: 0 1px 4px rgba(0,0,0,0.5); }
	.hero-score { text-align: center; margin-top: 0.3rem; }
	.hero-score-num { font-size: 2.8rem; font-weight: 900; line-height: 1; display: block; color: #FFD700; text-shadow: 0 0 20px rgba(255,215,0,0.6), 0 2px 8px rgba(0,0,0,0.5); }
	.hero-score-label { font-size: 0.6rem; color: rgba(255,255,255,0.8); text-transform: uppercase; letter-spacing: 0.2em; font-weight: 700; display: block; text-shadow: 0 1px 4px rgba(0,0,0,0.5); }
	.hero-stats { display: flex; gap: 2rem; justify-content: center; margin-top: 0.5rem; }
	.hero-stat { display: flex; flex-direction: column; align-items: center; }
	.hero-stat-val { font-size: 0.9rem; font-weight: 700; color: #ffffff; text-shadow: 0 1px 4px rgba(0,0,0,0.5); }
	.hero-stat-label { font-size: 0.5rem; color: rgba(255,255,255,0.7); text-transform: uppercase; text-shadow: 0 1px 4px rgba(0,0,0,0.5); }
	.share-btn { z-index: 2; width: 100%; padding: 0.7rem; border-radius: 14px; border: 1px solid rgba(255,107,0,0.3); background: linear-gradient(135deg, rgba(255,107,0,0.15), rgba(255,171,0,0.1)); color: #FFAE00; font-weight: 700; font-size: 0.8rem; cursor: pointer; transition: all 0.3s; }
	.share-btn:hover { background: linear-gradient(135deg, rgba(255,107,0,0.25), rgba(255,171,0,0.2)); border-color: #FF6B00; box-shadow: 0 0 20px rgba(255,107,0,0.2); }
	.share-btn:disabled { opacity: 0.5; cursor: not-allowed; }
	.share-spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid rgba(255,174,0,0.3); border-top-color: #FFAE00; border-radius: 50%; animation: spin 0.8s linear infinite; vertical-align: middle; margin-right: 0.3rem; }

	/* ── Celebraciones Full-Screen ── */
	.celebrations-fullscreen {
		min-height: 100vh; width: calc(100% + 2rem); margin-left: -1rem;
		background: linear-gradient(180deg, #050810 0%, #0a0f1e 20%, #0f1628 50%, #0a0f1e 80%, #050810 100%);
		position: relative; overflow: hidden;
		display: flex; flex-direction: column; align-items: center; justify-content: center;
		padding: 2rem 1.5rem; margin-top: 2rem;
	}
	.cel-bg { position: absolute; inset: 0; pointer-events: none; z-index: 0; overflow: hidden; }
	.cel-glow { position: absolute; border-radius: 50%; filter: blur(80px); }
	.cel-glow.g1 { width: 300px; height: 300px; background: rgba(236,72,153,0.12); top: -80px; left: -60px; animation: cel-float-glow 8s ease-in-out infinite; }
	.cel-glow.g2 { width: 250px; height: 250px; background: rgba(34,197,94,0.1); bottom: -60px; right: -40px; animation: cel-float-glow 10s ease-in-out infinite 2s; }
	.cel-glow.g3 { width: 200px; height: 200px; background: rgba(255,215,0,0.08); top: 50%; left: 50%; transform: translate(-50%,-50%); animation: cel-float-glow 12s ease-in-out infinite 4s; }
	@keyframes cel-float-glow { 0%,100% { transform: translate(0,0) scale(1); opacity: 0.6; } 50% { transform: translate(15px,-20px) scale(1.15); opacity: 1; } }
	.cel-confetti {
		position: absolute; top: -10px; width: 100%; height: 20px;
		background: repeating-linear-gradient(90deg, transparent, transparent 20px, #FF6B00 20px, #FF6B00 22px, transparent 22px, transparent 40px, #FFD700 40px, #FFD700 42px, transparent 42px, transparent 60px, #00BCD4 60px, #00BCD4 62px);
		opacity: 0.15; animation: cel-confetti-fall 15s linear infinite;
	}
	.cel-confetti.c2 { animation-delay: 5s; opacity: 0.1; height: 15px; background: repeating-linear-gradient(90deg, transparent, transparent 30px, #a78bfa 30px, #a78bfa 32px, transparent 32px, transparent 50px, #f87171 50px, #f87171 52px); }
	.cel-confetti.c3 { animation-delay: 10s; opacity: 0.08; height: 10px; background: repeating-linear-gradient(90deg, transparent, transparent 15px, #4ade80 15px, #4ade80 17px, transparent 17px, transparent 35px, #ec4899 35px, #ec4899 37px); }
	@keyframes cel-confetti-fall { 0% { top: -20px; opacity: 0; } 10% { opacity: 0.15; } 100% { top: 110%; opacity: 0; } }
	.cel-header { text-align: center; position: relative; z-index: 2; margin-bottom: 2rem; }
	.cel-emoji-main {
		font-size: 4.5rem; display: block; margin-bottom: 0.5rem;
		animation: cel-bounce-in 1s ease-out, cel-float-emoji 3s ease-in-out infinite 1s;
		filter: drop-shadow(0 0 20px rgba(236,72,153,0.4));
	}
	@keyframes cel-bounce-in { 0% { transform: scale(0); opacity: 0; } 50% { transform: scale(1.2); } 70% { transform: scale(0.9); } 100% { transform: scale(1); opacity: 1; } }
	@keyframes cel-float-emoji { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-12px); } }
	.cel-title {
		font-size: 1.8rem; font-weight: 900; margin: 0;
		background: linear-gradient(135deg, #FF6B00, #FFD700, #ec4899, #a78bfa);
		background-size: 300% 300%;
		-webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
		animation: cel-gradient-shift 4s ease-in-out infinite;
	}
	@keyframes cel-gradient-shift { 0%,100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
	.cel-subtitle { font-size: 0.8rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.2em; margin-top: 0.3rem; }
	.cel-content { position: relative; z-index: 2; width: 100%; max-width: 400px; display: flex; flex-direction: column; gap: 1.5rem; }
	.cel-section-header {
		display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.8rem;
		padding-bottom: 0.5rem; border-bottom: 1px solid rgba(255,255,255,0.06);
	}
	.cel-section-icon { font-size: 1.5rem; }
	.cel-section-label { font-size: 1rem; font-weight: 700; color: #f1f5f9; flex: 1; }
	.cel-section-count {
		background: rgba(255,107,0,0.15); color: #FF6B00; font-size: 0.7rem; font-weight: 700;
		padding: 0.15rem 0.5rem; border-radius: 10px;
	}
	.cel-person {
		display: flex; align-items: center; gap: 0.8rem;
		background: linear-gradient(135deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01));
		border: 1px solid rgba(255,255,255,0.06); border-radius: 16px;
		padding: 0.9rem 1rem; margin-bottom: 0.5rem;
		transition: all 0.3s;
	}
	.cel-person:hover { border-color: rgba(255,107,0,0.3); background: linear-gradient(135deg, rgba(255,107,0,0.06), rgba(255,107,0,0.02)); transform: translateX(4px); }
	@keyframes cel-slide { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
	.cel-person-avatar {
		font-size: 2rem; width: 52px; height: 52px; display: flex; align-items: center; justify-content: center;
		border-radius: 50%; flex-shrink: 0;
	}
	.cel-person-avatar.cake { background: linear-gradient(135deg, rgba(236,72,153,0.15), rgba(236,72,153,0.05)); box-shadow: 0 0 20px rgba(236,72,153,0.15); }
	.cel-person-avatar.star { background: linear-gradient(135deg, rgba(34,197,94,0.15), rgba(34,197,94,0.05)); box-shadow: 0 0 20px rgba(34,197,94,0.15); }
	.cel-person-info { flex: 1; }
	.cel-person-name { font-size: 1.1rem; font-weight: 700; color: #f1f5f9; }
	.cel-person-detail { font-size: 0.75rem; color: #94a3b8; margin-top: 0.1rem; }
	.cel-person-sparkle { font-size: 1.2rem; animation: cel-sparkle-pulse 2s ease-in-out infinite; }
	@keyframes cel-sparkle-pulse { 0%,100% { opacity: 0.5; transform: scale(0.8); } 50% { opacity: 1; transform: scale(1.1); } }
	.cel-footer { position: relative; z-index: 2; text-align: center; margin-top: 2rem; }
	.cel-footer-text {
		font-size: 0.85rem; color: #94a3b8; font-weight: 600;
		animation: cel-pulse-text 3s ease-in-out infinite;
	}
	@keyframes cel-pulse-text { 0%,100% { opacity: 0.6; } 50% { opacity: 1; text-shadow: 0 0 15px rgba(255,107,0,0.3); } }

	/* ── Score Log (Mis Puntos) ── */
	.score-log-section { position: relative; z-index: 2; margin-top: 0.5rem; }
	.score-log-header {
		display: flex; justify-content: space-between; align-items: center;
		background: linear-gradient(135deg, rgba(255,107,0,0.12), rgba(255,107,0,0.04));
		border: 1px solid rgba(255,107,0,0.2); border-radius: 16px;
		padding: 1rem 1.2rem; margin-bottom: 0.8rem;
	}
	.score-log-total { display: flex; flex-direction: column; }
	.total-num { font-size: 2rem; font-weight: 900; color: #FF6B00; line-height: 1; }
	.total-label { font-size: 0.75rem; color: #94a3b8; font-weight: 600; margin-top: 0.2rem; }
	.score-log-sync { font-size: 0.7rem; color: #64748b; text-align: right; line-height: 1.4; }
	.score-log-list { display: flex; flex-direction: column; gap: 0.4rem; }
	.score-log-item {
		display: flex; align-items: center; gap: 0.7rem;
		background: linear-gradient(135deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01));
		border: 1px solid rgba(255,255,255,0.06); border-radius: 12px;
		padding: 0.7rem 0.9rem;
		transition: all 0.2s;
	}
	.score-log-item:hover { border-color: rgba(255,107,0,0.2); }
	.score-log-item.positive { border-left: 3px solid #22c55e; }
	.score-log-item.negative { border-left: 3px solid #ef4444; }
	.log-icon { font-size: 1.3rem; flex-shrink: 0; width: 32px; text-align: center; }
	.log-info { flex: 1; display: flex; flex-direction: column; gap: 0.1rem; }
	.log-desc { font-size: 0.85rem; font-weight: 600; color: #e2e8f0; }
	.log-time { font-size: 0.7rem; color: #64748b; }
	.log-pts {
		font-size: 1rem; font-weight: 900; flex-shrink: 0; min-width: 40px; text-align: right;
	}
	.log-pts.pos { color: #22c55e; }
	.log-pts.neg { color: #ef4444; }
</style>
