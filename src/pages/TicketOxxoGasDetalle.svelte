<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { api } from '$lib/api.js';

	// Detalle de un ticket de OxxoGas como PÁGINA COMPLETA
	// (ruta /tickets_oxxogas/:id, deep-link soportado por el fallback SPA).
	// Los datos vienen del índice (GET /api/tickets-oxxogas) y se filtran por id.

	let { id } = $props();

	let t = $state(null);
	let loading = $state(true);
	let error = $state('');
	let imgError = $state(false); // offline o imagen no disponible

	function tieneAcceso() {
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && u.acceso_vales_oxxogas);
		} catch {
			return false;
		}
	}

	function token() {
		return localStorage.getItem('admon_token') || '';
	}

	// w=0 => imagen original (el backend solo hace thumbnail si w>0)
	function imgUrl(ticket, w) {
		return `/api/tickets-oxxogas/${ticket.id}/imagen?w=${w}&token=${encodeURIComponent(token())}`;
	}

	function fmtFecha(iso) {
		if (!iso) return '—';
		const d = new Date(iso);
		const p = (n) => String(n).padStart(2, '0');
		return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
	}

	function fmtMonto(m) {
		return m != null ? `$${Number(m).toFixed(2)}` : null;
	}

	// ── Qué fecha mostrar ────────────────────────────────────────────────────
	// El vale se PIDE antes de cargar y el ticket se CAPTURA después, a veces
	// días después (el #60: vale del 29/09, ticket del 06/10). La fecha que
	// interesa es la del vale; la del ticket solo se usa como respaldo cuando
	// el ticket no tiene vale enlazado (16 de 26 al momento de escribir esto).
	function fechaBase() {
		return t?.fecha_vale || t?.fecha || null;
	}
	function esFechaVale() {
		return !!(t && t.fecha_vale);
	}

	// ── Zoom de la foto del ticket ──────────────────────────────────────────
	// El recuadro de la imagen es pequeño en móvil y el folio del vale no se
	// lee. Un lightbox a pantalla completa con zoom + arrastre lo resuelve
	// sin sacar al usuario de la página. La imagen ya está en caché (se pide
	// con w=0, la misma URL que usa el recuadro), así que abre al instante.
	let zoomOpen = $state(false);
	let zoom = $state(1); // escala 1..6
	let panX = $state(0);
	let panY = $state(0);
	let dragging = $state(false);
	let stageEl = $state(null);

	// Niveles discretos para los botones: evita acumular decimales con +
	// y − repetidos (1.4 * 1/1.4 no vuelve exactamente a 1).
	const NIVELES = [1, 1.4, 2, 2.8, 4, 6];

	// Origen del arrastre (solo se usa mientras dragging = true).
	let dragSX = 0;
	let dragSY = 0;
	let dragOX = 0;
	let dragOY = 0;

	function abrirZoom() {
		if (!t?.tiene_foto || imgError) return;
		resetZoom();
		zoomOpen = true;
	}

	function cerrarZoom() {
		zoomOpen = false;
		resetZoom();
	}

	function resetZoom() {
		zoom = 1;
		panX = 0;
		panY = 0;
		dragging = false;
	}

	// zoom siempre sale de NIVELES, así que indexOf localiza la posición real.
	function zoomStep(dir) {
		let i = NIVELES.indexOf(zoom);
		if (i === -1) i = 0;
		i = Math.max(0, Math.min(NIVELES.length - 1, i + (dir > 0 ? 1 : -1)));
		zoom = NIVELES[i];
		// Al volver a 1x el desplazamiento no tiene sentido: se limpia para
		// que la próxima apertura no arranque en una esquina.
		if (zoom === 1) {
			panX = 0;
			panY = 0;
		}
	}

	function limitarPan() {
		// No dejar que la foto se "pierda" fuera del encuadre: el desplazamiento
		// máximo es la mitad del sobrante al escalar, con un pequeño margen.
		const r = stageEl?.getBoundingClientRect?.();
		if (!r) return;
		const mx = (r.width * (zoom - 1)) / 2 + 48;
		const my = (r.height * (zoom - 1)) / 2 + 48;
		panX = Math.max(-mx, Math.min(mx, panX));
		panY = Math.max(-my, Math.min(my, panY));
	}

	function onDown(e) {
		if (zoom <= 1) return; // sin zoom no hay nada que mover
		dragging = true;
		dragSX = e.clientX;
		dragSY = e.clientY;
		dragOX = panX;
		dragOY = panY;
		try {
			e.currentTarget.setPointerCapture(e.pointerId);
		} catch {
			/* navegador viejo: el move sigue funcionando por bubbling */
		}
	}

	function onMove(e) {
		if (!dragging) return;
		panX = dragOX + (e.clientX - dragSX);
		panY = dragOY + (e.clientY - dragSY);
		limitarPan();
	}

	function onUp() {
		// Cierre por gesto: un toque SIN arrastre a 1x cierra el lightbox (la
		// señal natural de "ya la vi"). Con zoom el mismo toque sirve para
		// acomodar la foto, así que ahí no se cierra.
		// Va aquí y no como onclick del encuadre: evita el aviso a11y de
		// "click sobre un <div> sin rol/teclado".
		const huboArrastre = dragging;
		dragging = false;
		if (!huboArrastre && zoom === 1) cerrarZoom();
	}

	function onKey(e) {
		if (!zoomOpen) return;
		if (e.key === 'Escape') cerrarZoom();
		else if (e.key === '+' || e.key === 'ArrowUp') zoomStep(1);
		else if (e.key === '-' || e.key === 'ArrowDown') zoomStep(-1);
		else if (e.key === '0') resetZoom();
		else return;
		e.preventDefault();
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
			const lista = await api.get('/tickets-oxxogas');
			t = (lista || []).find((x) => String(x.id) === String(id)) || null;
			if (!t) error = 'No se encontró el ticket.';
		} catch (e) {
			error = e.message === 'Sesión expirada' ? e.message : e.message || 'No se pudo cargar el ticket.';
		} finally {
			loading = false;
		}
	});
</script>

<!-- Teclado: Esc cierra, +/− ajustan, 0 restablece. Inofensivo en móvil. -->
<svelte:window onkeydown={onKey} />

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" onclick={() => navigate('/tickets_oxxogas')} title="Volver al listado">⬅️</button>
		<h1>🎫 Ticket {t ? `#${t.folio}` : ''}</h1>
		<div style="flex:1"></div>
		{#if t}<span class="fecha-head">🕐 {fmtFecha(fechaBase())}{#if esFechaVale()}<i>del vale</i>{/if}</span>{/if}
	</div>

	{#if loading}
		<div class="state">⏳ Cargando ticket…</div>
	{:else if error}
		<div class="state err">⚠️ {error}</div>
	{:else if t}
		<div class="grid">
			<div class="img-box" class:has-zoom={t.tiene_foto && !imgError}>
				{#if t.tiene_foto && !imgError}
					<!--
					  La foto va DENTRO de un <button>: da área táctil completa,
					  resuelve el teclado (Enter/Espacio) y evita el aviso a11y de
					  "click sobre <img>". El 🔍 pasa a span para no anidar botones.
					-->
					<button class="img-zoom-trigger" type="button" onclick={abrirZoom} aria-label="Ampliar la foto del ticket {t.folio}">
						<img
							src={imgUrl(t, 0)}
							alt="Ticket {t.folio}"
							onerror={() => (imgError = true)}
						/>
						<span class="zoom-fab" aria-hidden="true">🔍</span>
						<span class="zoom-hint">Toca para ampliar</span>
					</button>
				{:else if t.tiene_foto}
					<div class="no-photo">📴<span>Foto no disponible sin conexión</span></div>
				{:else}
					<div class="no-photo">🎫<span>Sin foto registrada</span></div>
				{/if}
			</div>

			<div class="col">
				<!--
				  Orden fijo pedido: Fecha y hora → Nombre → Cantidad → Folio →
				  Auto → Empresa → Proyecto/Servicio. Los siete van SIEMPRE
				  visibles (con "—" o "Pendiente") para que el orden no se
				  corra cuando falta algún dato.
				  · fecha  = HUB_OxxoGasTickets.FechaRegistro (cuando se capturó
				    el vale en Field)
				  · nombre = usuario que lo capturó
				  · cantidad = Monto del vale enlazado en MXN; si aún no hay
				    factura enlazada, queda "Pendiente"
				-->
				<div class="info-box">
					<div class="info-label">🎫 Datos del ticket</div>
					<div class="info-line">
						<span>🕐 Fecha y hora</span>
						{#if esFechaVale()}
							<strong>{fmtFecha(fechaBase())}<i class="tag-vale">del vale</i></strong>
						{:else}
							<strong>{fmtFecha(fechaBase())}<i class="tag-ticket">del ticket</i></strong>
						{/if}
					</div>
					<div class="info-line"><span>👤 Nombre</span><strong>{t.capturo || '—'}</strong></div>
					<div class="info-line">
						<span>💰 Cantidad</span>
						{#if t.monto != null}
							<strong>{fmtMonto(t.monto)}</strong>
						{:else}
							<span class="pend-inline">⏳ Pendiente</span>
						{/if}
					</div>
					<div class="info-line"><span>🎫 Folio</span><strong class="folio-inline">#{t.folio}</strong></div>
					{#if t.vale}
						<div class="info-line"><span>🎫 Vale</span><strong class="folio-inline">{t.vale}</strong></div>
					{/if}
					<div class="info-line"><span>🚗 Auto</span><strong>{[t.marca_modelo, t.placas].filter(Boolean).join(' · ') || '—'}</strong></div>
					<div class="info-line"><span>🏢 Empresa</span><strong>{t.cliente || '—'}</strong></div>
					<div class="info-line"><span>📝 Proyecto / Servicio</span><strong>{t.descripcion || '—'}</strong></div>
				</div>

				<div class="info-box">
					<div class="info-label">Relación factura ↔ estación</div>
					{#if t.factura}
						<div class="info-line"><span>🧾 Factura</span><strong>{t.factura}</strong></div>
						{#if t.litros != null}<div class="info-line"><span>⛽ Litros</span><strong>{Number(t.litros).toFixed(2)} L</strong></div>{/if}
						{#if t.concepto}<div class="info-line"><span>🛒 Concepto</span><strong>{t.concepto}</strong></div>{/if}
					{:else}
						<div class="pend-row">⏳ Factura: <strong>Pendiente</strong></div>
					{/if}
					{#if t.estacion}
						<div class="info-line"><span>⛽ Estación</span><strong>{t.estacion}</strong></div>
					{:else}
						<div class="pend-row">⏳ Estación: <strong>Pendiente</strong></div>
					{/if}
				</div>

				<button class="btn btn-secondary btn-back" onclick={() => navigate('/tickets_oxxogas')}>⬅️ Volver al listado de tickets</button>
			</div>
		</div>
	{/if}
</div>

{#if zoomOpen && t}
	<!-- Lightbox de la foto: escala 1x–6x, arrastre con el dedo/ratón,
	     cierra con Esc, con ✕ o tocando el encuadre a 1x. -->
	<div class="lightbox" role="dialog" aria-modal="true" aria-label="Foto ampliada del ticket">
		<div class="lb-bar">
			<button class="btn btn-sm btn-secondary" onclick={cerrarZoom}>✕</button>
			<span class="lb-folio">🎫 #{t.folio}</span>
			<div class="lb-spacer"></div>
			<button class="lb-btn" onclick={() => zoomStep(-1)} disabled={zoom <= 1} aria-label="Alejar">−</button>
			<span class="lb-pct">{Math.round(zoom * 100)}%</span>
			<button class="lb-btn" onclick={() => zoomStep(1)} disabled={zoom >= 6} aria-label="Acercar">＋</button>
			<button class="lb-btn lb-reset" onclick={resetZoom} disabled={zoom === 1 && panX === 0 && panY === 0} aria-label="Restablecer">↺</button>
		</div>

		<div
			class="lb-stage"
			class:is-zoomed={zoom > 1}
			class:is-drag={dragging}
			role="img"
			aria-label="Foto ampliada del ticket {t.folio}; usa − y ＋ para cambiar el tamaño"
			bind:this={stageEl}
			onpointerdown={onDown}
			onpointermove={onMove}
			onpointerup={onUp}
			onpointercancel={onUp}
		>
			<img
				class:is-drag={dragging}
				src={imgUrl(t, 0)}
				alt=""
				style="transform: translate({panX}px, {panY}px) scale({zoom})"
				draggable="false"
			/>
		</div>

		<div class="lb-foot">Arrastra para mover · − / ＋ para el tamaño · toca la foto o pulsa ✕ para cerrar</div>
	</div>
{/if}

<style>
	.page { max-width: 1200px; margin: 0 auto; padding: 1rem; }
	.header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
	.header h1 { font-size: 1.25rem; margin: 0; color: #f1f5f9; }
	.fecha-head { font-size: 0.78rem; color: #94a3b8; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 999px; padding: 0.25rem 0.7rem; }
	.state { text-align: center; color: #94a3b8; padding: 3rem 1rem; font-size: 0.9rem; }
	.state.err { color: #f87171; }

	.grid { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); gap: 1.1rem; align-items: start; }
	@media (max-width: 860px) { .grid { grid-template-columns: 1fr; } }

	.img-box { position: relative; background: #0f172a; border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 14px; overflow: hidden; display: flex; align-items: center; justify-content: center; }
	.img-box img { width: 100%; max-height: 82vh; object-fit: contain; display: block; }
	.img-box.has-zoom img { cursor: zoom-in; }

	/* Toda la foto es el área de toque. Reset del <button> para que no
	   traiga estilos de agente de usuario ni encoge la imagen. */
	.img-zoom-trigger { display: block; width: 100%; padding: 0; margin: 0; border: 0; background: none; position: relative; cursor: zoom-in; font: inherit; color: inherit; -webkit-appearance: none; appearance: none; }
	.img-zoom-trigger:focus-visible { outline: 2px solid #ff6b00; outline-offset: -2px; }

	/* Disparador visual del zoom: 44px de área táctil (mínimo de diseño). */
	.zoom-fab { position: absolute; top: 0.55rem; right: 0.55rem; width: 44px; height: 44px; padding: 0; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.14); background: rgba(2, 6, 23, 0.72); -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px); font-size: 1.05rem; display: flex; align-items: center; justify-content: center; cursor: pointer; z-index: 2; transition: background 0.15s, border-color 0.15s; }
	.zoom-fab:hover, .zoom-fab:focus-visible { background: rgba(255, 107, 0, 0.3); border-color: rgba(255, 107, 0, 0.65); outline: none; }
	.zoom-hint { position: absolute; left: 0.55rem; bottom: 0.55rem; font-size: 0.68rem; color: #94a3b8; background: rgba(2, 6, 23, 0.72); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 999px; padding: 0.2rem 0.6rem; pointer-events: none; }

	/* ── Lightbox ───────────────────────────────────────────────────────── */
	.lightbox { position: fixed; inset: 0; z-index: 1000; background: rgba(2, 6, 23, 0.96); display: flex; flex-direction: column; }
	.lb-bar { display: flex; align-items: center; gap: 0.35rem; padding: 0.55rem 0.65rem; background: rgba(15, 23, 42, 0.9); border-bottom: 1px solid rgba(255, 255, 255, 0.08); flex-wrap: wrap; }
	.lb-folio { font-family: ui-monospace, 'Cascadia Mono', monospace; color: #ffae00; font-size: 0.85rem; font-weight: 700; letter-spacing: 0.5px; }
	.lb-spacer { flex: 1; }
	.lb-btn { min-width: 44px; min-height: 44px; padding: 0; border-radius: 10px; border: 1px solid rgba(255, 255, 255, 0.12); background: rgba(255, 255, 255, 0.06); color: #f8fafc; font-size: 1.15rem; line-height: 1; cursor: pointer; transition: background 0.15s, border-color 0.15s; }
	.lb-btn:not(:disabled):hover, .lb-btn:not(:disabled):focus-visible { background: rgba(255, 107, 0, 0.22); border-color: rgba(255, 107, 0, 0.6); outline: none; }
	.lb-btn:disabled { opacity: 0.3; cursor: default; }
	.lb-reset { background: rgba(255, 174, 0, 0.12); border-color: rgba(255, 174, 0, 0.4); }
	.lb-pct { min-width: 3.1rem; text-align: center; font-size: 0.78rem; color: #94a3b8; font-variant-numeric: tabular-nums; }

	.lb-stage { position: relative; flex: 1; overflow: hidden; display: flex; align-items: center; justify-content: center; touch-action: none; user-select: none; -webkit-user-select: none; cursor: pointer; }
	.lb-stage.is-zoomed { cursor: grab; }
	.lb-stage.is-zoomed.is-drag { cursor: grabbing; }
	.lb-stage img { max-width: 100%; max-height: 100%; object-fit: contain; transform-origin: center center; transition: transform 0.12s ease-out; will-change: transform; pointer-events: none; }
	.lb-stage img.is-drag { transition: none; }

	.lb-foot { padding: 0.5rem 0.8rem calc(0.5rem + env(safe-area-inset-bottom, 0px)); font-size: 0.7rem; color: #64748b; text-align: center; background: rgba(15, 23, 42, 0.85); border-top: 1px solid rgba(255, 255, 255, 0.06); }

	.no-photo { display: flex; flex-direction: column; align-items: center; gap: 0.4rem; color: #475569; font-size: 3.5rem; padding: 4rem 0; }
	.no-photo span { font-size: 0.8rem; }

	.col { display: flex; flex-direction: column; gap: 0.8rem; }

	.info-box { background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 12px; padding: 0.8rem 0.95rem; }
	.info-label { font-size: 0.7rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.6px; color: #FFAE00; margin-bottom: 0.5rem; }
	.info-line { display: flex; justify-content: space-between; gap: 1rem; font-size: 0.85rem; padding: 0.3rem 0; border-bottom: 1px dashed rgba(255, 255, 255, 0.05); }
	.info-line:last-child { border-bottom: none; }
	.info-line span { color: #94a3b8; flex-shrink: 0; }
	.info-line strong { color: #f1f5f9; text-align: right; font-weight: 600; overflow-wrap: anywhere; }

	/* Folio en la lista ordenada: mono y acento, sin ser el héroe de la página.
	   Specificity >= `.info-line strong` para ganar sin !important. */
	.info-line .folio-inline { font-family: ui-monospace, 'Cascadia Mono', monospace; color: #FFAE00; letter-spacing: 0.5px; }

	/* Cantidad sin vale enlazado todavía. Idem: gana a `.info-line span`. */
	.info-line .pend-inline { color: #fbbf24; font-size: 0.85rem; flex-shrink: 0; }

	/* Etiqueta que aclara de qué fecha se trata: la del vale (la del
	   combustible) o, si no hay vale enlazado, la del ticket. Se pone como
	   <i> para no heredar el estilo del <strong> ni del <span> del label. */
	i.tag-vale,
	i.tag-ticket {
		font-style: normal;
		font-size: 0.68rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.4px;
		margin-left: 0.45rem;
		padding: 0.1rem 0.4rem;
		border-radius: 999px;
		white-space: nowrap;
		vertical-align: middle;
	}
	i.tag-vale { color: #ffae00; background: rgba(255, 174, 0, 0.14); border: 1px solid rgba(255, 174, 0, 0.35); }
	i.tag-ticket { color: #94a3b8; background: rgba(148, 163, 184, 0.12); border: 1px solid rgba(148, 163, 184, 0.28); }

	/* Mismo distintivo, versión compacta, en la burbuja del header. */
	.fecha-head i {
		font-style: normal;
		font-size: 0.62rem;
		font-weight: 800;
		text-transform: uppercase;
		letter-spacing: 0.4px;
		color: #ffae00;
		margin-left: 0.35rem;
	}

	.pend-row { font-size: 0.85rem; color: #fbbf24; background: rgba(251, 191, 36, 0.08); border: 1px dashed rgba(251, 191, 36, 0.35); border-radius: 8px; padding: 0.5rem 0.65rem; margin: 0.3rem 0; }
	.btn-back { width: 100%; }
</style>
