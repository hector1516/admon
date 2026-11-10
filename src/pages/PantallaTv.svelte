<script>
	import { Upload , Clock, Play, Recycle, SkipForward } from 'lucide-svelte';

	import { onMount, onDestroy } from 'svelte';
	import { auth } from '$lib/stores/auth.js';
	import { api } from '$lib/api.js';
import HoldButton from '$lib/components/HoldButton.svelte';

	// Pestaña "Pantalla de la TV" del módulo Notas.
	//
	// Dos cosas, sin llamadas entre apps:
	//  1) Imagen de portada → se sube por la API a HUB_PantallaImagenes; el
	//     snapshotter del kiosco la lee de ahí y la muestra. No va por HTTP al
	//     Dashboard, así que no hay que pegarle a la TV ni esperar respuesta.
	//  2) Control remoto del kiosco: GET /api/pantalla/estado (sin token) y
	//     POST /api/pantalla/comando (con token, que vive en el servidor).
	//     La TV consulta cada 3 s: el cambio se ve en pantalla en ~3 s, por eso
	//     mostramos "enviado" y luego el "confirmado" cuando la pantalla lo
	//     obedece.

	let estado = $state(null);
	let cargando = $state(true);
	let error = $state('');
	let aviso = $state('');
	let mandando = $state(false);
	let timer = null;

	// Imagen de portada
	let portada = $state(null); // { id, titulo, ancho, alto, base64, fech|subida }
	let historial = $state([]);
	let archivo = $state(null);
	let tituloPortada = $state('');
	let leyendoArchivo = $state(false);
	let subiendo = $state(false);

	async function cargarEstado() {
		try {
			const e = await api.get('/pantalla/estado');
			if (e && e.error) {
				error = e.error;
				estado = null;
			} else {
				estado = e;
				error = '';
			}
		} catch (ex) {
			error = ex.message || 'No se pudo leer el estado de la pantalla.';
			estado = null;
		} finally {
			cargando = false;
		}
	}

	async function cargarPortada() {
		try {
			const d = await api.get('/pantalla/portada');
			portada = d.activa || null;
			historial = d.historial || [];
		} catch (ex) {
			error = ex.message || 'No se pudo leer la portada.';
		}
	}

	// La TV publica las pantallas al arrancar y confirma los comandos: se
	// refresca solo cada 5 s para que "confirmado" y "tv conectada" no queden
	// congelados.
	function empezarPolling() {
		timer = setInterval(() => {
			if (!mandando && document.visibilityState === 'visible') cargarEstado();
		}, 5000);
	}

	onMount(async () => {
		if (!auth.isLoggedIn()) return;
		await Promise.all([cargarEstado(), cargarPortada()]);
		empezarPolling();
	});

	onDestroy(() => {
		if (timer) clearInterval(timer);
	});

	function leerArchivo(e) {
		const f = e.target.files && e.target.files[0];
		if (!f) return;
		if (f.size > 12 * 1024 * 1024) {
			error = 'Esa imagen pesa más de 12 MB.';
			return;
		}
		archivo = f;
		error = '';
		aviso = '';
	}

	async function subirPortada() {
		if (!archivo) return;
		subiendo = true;
		error = '';
		aviso = '';
		leyendoArchivo = true;
		try {
			const base64 = await new Promise((resolve, reject) => {
				const r = new FileReader();
				r.onload = () => resolve(String(r.result));
				r.onerror = () => reject(new Error('No se pudo leer el archivo.'));
				r.readAsDataURL(archivo);
			});
			await api.post('/pantalla/portada', {
				contenido_base64: base64,
				content_type: archivo.type || 'image/jpeg',
				titulo: tituloPortada.trim()
			});
			aviso = '✅ Subida. La TV la toma en su próxima vuelta.';
			archivo = null;
			tituloPortada = '';
			// limpia el input de archivo para poder volver a elegir el mismo
			const inp = document.getElementById('pantalla-archivo');
			if (inp) inp.value = '';
			await cargarPortada();
		} catch (ex) {
			error = ex.message || 'No se pudo subir la imagen.';
		} finally {
			subiendo = false;
			leyendoArchivo = false;
		}
	}

	async function restaurar(id) {
		error = '';
		aviso = '';
		try {
			await api.post(`/pantalla/portada/${id}/restaurar`);
			aviso = '✅ Portada restaurada. La TV la toma en su próxima vuelta.';
			await cargarPortada();
		} catch (ex) {
			error = ex.message || 'No se pudo restaurar.';
		}
	}

	async function borrarImagen(id) {
		if (!confirm('¿Borrar esta imagen del historial?')) return;
		error = '';
		try {
			await api.delete(`/pantalla/portada/${id}`);
			await cargarPortada();
		} catch (ex) {
			error = ex.message || 'No se pudo borrar.';
		}
	}

	async function mandar(accion, pantalla = null) {
		mandando = true;
		error = '';
		aviso = '';
		try {
			const r = await api.post('/pantalla/comando', { accion, pantalla });
			if (r && r.ok === false) {
				// El panel devuelve {"ok": false, "error": "..."}: se muestra, no se traga
				error = r.error || 'La pantalla rechazó el comando.';
			} else {
				aviso = `📡 Comando enviado: ${accion}${pantalla ? ` → ${pantalla}` : ''}. La TV lo toma en ~3 s.`;
				await cargarEstado();
			}
		} catch (ex) {
			error = ex.message || 'No se pudo mandar el comando.';
		} finally {
			mandando = false;
		}
	}

	function fmtFecha(iso) {
		if (!iso) return '—';
		const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
		return m ? `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}` : '—';
	}
</script>

<div class="pantalla-tv">
	{#if aviso}<div class="msg ok">{aviso}</div>{/if}
	{#if error}<div class="msg err">⚠️ {error}</div>{/if}

	<!-- ─────────── Control remoto ─────────── -->
	<div class="card">
		<div class="card-title">📡 Control de la pantalla</div>

		{#if cargando}
			<div class="state">⏳ Leyendo la pantalla…</div>
		{:else if !estado}
			<div class="state err">No hay comunicación con el kiosco de la oficina.</div>
		{:else}
			<div class="tv-estado">
				{#if estado.tv_conectada}
					<span class="chip chip-ok">🟢 TV conectada</span>
				{:else}
					<span class="chip chip-off">⚪ TV desconectada</span>
				{/if}
				{#if estado.comando}
					<span class="chip">Último: {estado.comando.accion}{estado.comando.pantalla ? ` → ${estado.comando.pantalla}` : ''}</span>
				{/if}
				{#if estado.confirmado}
					<span class="chip chip-ok">✅ Confirmado {estado.confirmado.hecho ? fmtFecha(estado.confirmado.hecho) : ''}</span>
				{/if}
			</div>

			{#if !estado.tv_conectada}
				<p class="hint">La TV está desconectada: los comandos quedan pendientes hasta que vuelva.</p>
			{/if}

			<!-- Pausa y seguir van juntos a propósito: dejar "pausa" sola
			     congelaría la pantalla y en una TV eso parece una falla. -->
			<div class="acciones">
				<button class="btn btn-sm btn-primary" disabled={mandando} onclick={() => mandar('avanzar')}>
					<SkipForward size={16} /> Avanzar
				</button>
				<button class="btn btn-sm btn-secondary" disabled={mandando} onclick={() => mandar('seguir')}>
					<Play size={16} /> Seguir rotando
				</button>
			</div>

			<p class="hint" style="margin-top: 0.5rem;">Cambiar a una pantalla concreta reinicia el contador a 45 s:</p>
			<div class="pantallas">
				{#each estado.pantallas || [] as p (p.id)}
					<button
						class="pantalla-btn"
						class:actual={estado.comando?.pantalla === p.id}
						disabled={mandando}
						onclick={() => mandar('ver', p.id)}
						title={`Ver ${p.label} en la TV`}
					>
						<span class="p-ico">{p.icono}</span>{p.label}
					</button>
				{/each}
			</div>
		{/if}
	</div>

	<!-- ─────────── Imagen de portada ─────────── -->
	<div class="card">
		<div class="card-title">🖼️ Imagen de portada</div>
		<p class="hint">
			Imagen a pantalla completa que la TV muestra con un título encima
			(dimensiones ideales 1920×1080). No se manda a la TV: se guarda y la
			pantalla la toma sola en su próxima vuelta.
		</p>

		{#if portada}
			<div class="preview">
				{#if portada.base64}
					<img src="data:{portada.contenttype};base64,{portada.base64}" alt="Portada actual" />
				{/if}
				<div class="preview-meta">
					<strong>{portada.titulo || 'Sin título'}</strong>
					<span>🟢 En pantalla</span>
					{#if portada.ancho && portada.alto}
						<span>📐 {portada.ancho}×{portada.alto}{portada.ancho === 1920 && portada.alto === 1080 ? ' ✅' : ' ⚠️'}</span>
					{/if}
					<span>🕒 {fmtFecha(portada.fechasubida)}</span>
				</div>
			</div>
		{:else}
			<div class="state">Sin portada: la pantalla "portada" sale vacía.</div>
		{/if}

		<div class="field">
			<label for="pantalla-archivo">Subir imagen (JPG, PNG o WEBP):</label>
			<input
				id="pantalla-archivo"
				type="file"
				accept="image/png,image/jpeg,image/webp"
				onchange={leerArchivo}
				disabled={subiendo}
			/>
		</div>
		<div class="field">
			<label for="pantalla-titulo">Título sobrepuesto (vacío = "ECCSA en &lt;mes actual&gt;"):</label>
			<input
				id="pantalla-titulo"
				class="input"
				placeholder="ECCSA en Octubre"
				bind:value={tituloPortada}
				maxlength="120"
			/>
		</div>
		<button
			class="btn btn-sm btn-primary btn-block"
			disabled={!archivo || subiendo}
			onclick={subirPortada}
		>
			{subiendo ? (leyendoArchivo ? '<Clock size={16} /> Subiendo…' : '<Clock size={16} /> Preparando…') : '<Upload size={16} /> Subir a la pantalla'}
		</button>

		{#if historial.length > 1}
			<p class="hint" style="margin-top: 0.9rem;">Historial:</p>
			<div class="historial">
				{#each historial as h (h.id)}
					<div class="hist-item" class:inactivo={!h.activo}>
						<span class="h-titulo">{h.titulo || 'Sin título'}</span>
						<span class="h-meta">{fmtFecha(h.fechasubida)}{h.ancho ? ` · ${h.ancho}×${h.alto}` : ''}</span>
						{#if h.activo}
							<span class="chip chip-ok">en pantalla</span>
						{:else}
							<button class="btn-icon" onclick={() => restaurar(h.id)} title="Volver a ponerla"><Recycle size={16} /></button>
							<HoldButton label="Borrar" onConfirm={() => borrarImagen(h.id)} size="sm" />
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>

<style>
	.card-title { font-weight: 700; font-size: 1rem; margin-bottom: 0.25rem; }
	.msg { padding: 0.6rem 0.75rem; border-radius: 8px; font-size: 0.85rem; margin-bottom: 0.75rem; }
	.msg.ok { background: rgba(34, 197, 94, 0.1); color: #22C55E; }
	.msg.err { background: rgba(239, 68, 68, 0.1); color: #EF4444; }
	.hint { font-size: 0.78rem; color: var(--color-text-muted); margin: 0.35rem 0; }
	.state { font-size: 0.85rem; color: var(--color-text-muted); padding: 0.5rem 0; }
	.state.err { color: #EF4444; }

	.tv-estado { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.75rem; }
	.chip {
		font-size: 0.72rem;
		padding: 0.22rem 0.55rem;
		border-radius: 999px;
		background: rgba(255, 255, 255, 0.06);
		color: var(--color-text-muted);
	}
	.chip-ok { background: rgba(34, 197, 94, 0.14); color: #22C55E; }
	.chip-off { background: rgba(148, 163, 184, 0.16); color: #94A3B8; }

	.acciones { display: flex; flex-wrap: wrap; gap: 0.5rem; }

	.pantallas { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-top: 0.25rem; }
	.pantalla-btn {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		padding: 0.55rem 0.65rem;
		font-size: 0.8rem;
		font-weight: 600;
		font-family: inherit;
		color: var(--color-text);
		background: var(--color-surface-2);
		border: 1px solid rgba(255, 255, 255, 0.06);
		border-radius: 10px;
		cursor: pointer;
		text-align: left;
	}
	.pantalla-btn:disabled { opacity: 0.5; cursor: default; }
	.pantalla-btn.actual { border-color: var(--color-primary); color: var(--color-primary-light); }
	.p-ico { font-size: 1rem; line-height: 1; }

	.preview { margin: 0.75rem 0; }
	.preview img {
		width: 100%;
		border-radius: 10px;
		border: 1px solid rgba(255, 255, 255, 0.08);
		display: block;
	}
	.preview-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin-top: 0.45rem; font-size: 0.78rem; color: var(--color-text-muted); }

	.historial { display: flex; flex-direction: column; gap: 0.4rem; }
	.hist-item {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.45rem 0.55rem;
		background: var(--color-surface-2);
		border-radius: 10px;
		font-size: 0.8rem;
	}
	.hist-item.inactivo { opacity: 0.85; }
	.h-titulo { font-weight: 600; color: var(--color-text); flex: 1; }
	.h-meta { font-size: 0.72rem; color: var(--color-text-muted); }
	.btn-icon {
		background: transparent;
		border: none;
		font-size: 0.9rem;
		cursor: pointer;
		padding: 0.2rem 0.35rem;
		border-radius: 8px;
	}
	.btn-icon:hover { background: rgba(255, 255, 255, 0.08); }
</style>
