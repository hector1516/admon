<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { api } from '$lib/api.js';
	import Paginacion from '$lib/components/Paginacion.svelte';

	// Notas del equipo → tabla HUB_DashboardNotas, la MISMA que lee la pantalla
	// 📌 del Dashboard de la oficina (kiosco, dashboard.ecc-sa.com.mx:8101).
	// El kiosco es solo lectura: lo que se captura acá aparece solo en la TV.
	// Color = acento de la nota en el kiosco · Fija = sale arriba del todo.
	// Sin permiso propio (igual que ECCSA IA): todos los logueados.
	//
	// Se renderiza como PESTAÑA de la página "Dashboard" (el botón del menú,
	// src/pages/Panel.svelte; prop `embebido`): en ese modo no pone su propio
	// header ni el botón ⬅️ de volver, porque el Panel ya trae su encabezado y
	// la barra de pestañas (la ruta /notas abre el Panel con esta pestaña).

	let { embebido = false } = $props();

	let notas = $state([]);
	let pagina = $state(1);
	let loading = $state(true);
	let error = $state('');
	let aviso = $state('');

	// Editor en panel (sin popup): abierto = 'nueva' | id de la nota | null
	let editorAbierto = $state(false);
	let editandoId = $state(null);
	let formTitulo = $state('');
	let formContenido = $state('');
	let formColor = $state('#F59E0B');
	let formFija = $state(false);
	let guardando = $state(false);

	// Paleta de acentos: los mismos tonos que el kiosco usa por defecto.
	const COLORES = [
		{ hex: '#F59E0B', nombre: 'Ámbar' },
		{ hex: '#EF4444', nombre: 'Rojo' },
		{ hex: '#22C55E', nombre: 'Verde' },
		{ hex: '#3B82F6', nombre: 'Azul' },
		{ hex: '#A855F7', nombre: 'Morado' },
		{ hex: '#94A3B8', nombre: 'Gris' }
	];

	// La BD guarda hora de México sin offset: se renderiza tal cual (componentes
	// del string) para que se vea igual en cualquier dispositivo.
	function fmtFecha(iso) {
		if (!iso) return '—';
		const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
		if (m) return `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}`;
		return '—';
	}

	const POR_PAGINA = 100;
	const pagActual = $derived(notas.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA));

	async function cargar() {
		try {
			notas = (await api.get('/notas')) || [];
			error = '';
		} catch (e) {
			error = e.message === 'Sesión expirada' ? e.message : 'No se pudieron cargar las notas.';
		} finally {
			loading = false;
		}
	}

	function abrirNueva() {
		editandoId = null;
		formTitulo = '';
		formContenido = '';
		formColor = '#F59E0B';
		formFija = false;
		editorAbierto = true;
		aviso = '';
	}

	function abrirEditar(n) {
		editandoId = n.id;
		formTitulo = n.titulo;
		formContenido = n.contenido;
		formColor = n.color || '#F59E0B';
		formFija = !!n.fija;
		editorAbierto = true;
		aviso = '';
	}

	function cancelarEditor() {
		editorAbierto = false;
		editandoId = null;
	}

	async function guardar() {
		if (!formTitulo.trim() || !formContenido.trim()) {
			error = 'El título y el contenido no pueden estar vacíos.';
			return;
		}
		guardando = true;
		error = '';
		try {
			const cuerpo = {
				titulo: formTitulo,
				contenido: formContenido,
				color: formColor,
				fija: formFija
			};
			if (editandoId === null) {
				const creada = await api.post('/notas', cuerpo);
				notas = [creada, ...notas];
				aviso = '✅ Nota creada. Ya aparece en el Dashboard de la oficina.';
			} else {
				const editada = await api.put(`/notas/${editandoId}`, cuerpo);
				notas = notas.map((n) => (n.id === editandoId ? editada : n));
				aviso = '✅ Nota actualizada.';
			}
			cancelarEditor();
		} catch (e) {
			error = e.message || 'No se pudo guardar la nota.';
		} finally {
			guardando = false;
		}
	}

	async function borrar(n) {
		if (!confirm(`¿Borrar la nota "${n.titulo}"?`)) return;
		error = '';
		try {
			await api.delete(`/notas/${n.id}`);
			notas = notas.filter((x) => x.id !== n.id);
			if (editandoId === n.id) cancelarEditor();
			aviso = '🗑️ Nota borrada.';
		} catch (e) {
			error = e.message || 'No se pudo borrar la nota.';
		}
	}

	onMount(async () => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
		await cargar();
	});
</script>

<div class:page={!embebido}>
	{#if !embebido}
		<div class="header">
			<button class="btn btn-sm btn-secondary" onclick={() => navigate('/dashboard')} title="Volver">⬅️</button>
			<h1>📝 Notas</h1>
			<div style="flex:1"></div>
			<button class="btn btn-sm btn-primary" onclick={abrirNueva}>➕ Nueva nota</button>
		</div>
	{:else}
		<!-- Modo pestaña: el botón queda arriba a la derecha, bajo la barra de pestañas -->
		<div class="embed-bar">
			<button class="btn btn-sm btn-primary" onclick={abrirNueva}>➕ Nueva nota</button>
		</div>
	{/if}

	{#if aviso}
		<div class="nota-aviso">{aviso}</div>
	{/if}
	{#if error}
		<div class="state err">⚠️ {error}</div>
	{/if}

	<!-- Editor en panel (sin popup): se abre arriba de la lista -->
	{#if editorAbierto}
		<div class="editor">
			<div class="editor-title">{editandoId === null ? '➕ Nueva nota' : '✏️ Editar nota'}</div>
			<div class="field">
				<input class="input" placeholder="Título de la nota" bind:value={formTitulo} maxlength="200" />
			</div>
			<div class="field">
				<textarea class="input editor-contenido" rows="6" placeholder="Escribe el contenido…" bind:value={formContenido}></textarea>
			</div>
			<div class="editor-opciones">
				<div class="colores">
					<span class="opciones-lbl">Color en el Dashboard:</span>
					{#each COLORES as c}
						<button
							type="button"
							class="color-chip"
							class:sel={formColor === c.hex}
							style="--c:{c.hex}"
							title={c.nombre}
							aria-label={c.nombre}
							onclick={() => (formColor = c.hex)}
						></button>
					{/each}
				</div>
				<label class="fija-check">
					<input type="checkbox" bind:checked={formFija} />
					📌 Fijar arriba
				</label>
			</div>
			<div class="editor-acciones">
				<button class="btn btn-sm btn-primary" onclick={guardar} disabled={guardando || !formTitulo.trim() || !formContenido.trim()}>
					{guardando ? '⏳ Guardando…' : '💾 Guardar'}
				</button>
				<button class="btn btn-sm btn-secondary" onclick={cancelarEditor} disabled={guardando}>Cancelar</button>
			</div>
		</div>
	{/if}

	<p class="hint">Notas del equipo · cada nota muestra su autor · salen también en la pantalla 📌 del Dashboard de la oficina (solo se muestran las 3 primeras, las fijas van arriba)</p>

	{#if loading}
		<div class="state">⏳ Cargando notas…</div>
	{:else if notas.length === 0}
		<div class="state">📝 No hay notas todavía. ¡Crea la primera con “➕ Nueva nota”!</div>
	{:else}
		<div class="notas-lista">
			{#each pagActual as n (n.id)}
				<article class="nota-card" style="--c:{n.color}">
					<div class="nota-head">
						<h2 class="nota-titulo">{#if n.fija}<span class="nota-fija">📌 fija</span>{/if}{n.titulo}</h2>
						<div class="nota-acciones">
							<button class="btn-icon" onclick={() => abrirEditar(n)} title="Editar">✏️</button>
							<button class="btn-icon" onclick={() => borrar(n)} title="Borrar">🗑️</button>
						</div>
					</div>
					<div class="nota-contenido">{n.contenido}</div>
					<div class="nota-meta">
						<span class="nota-autor">👤 {n.autor}</span>
						<span>🕒 {fmtFecha(n.fecha_creacion)}{n.fecha_modificado ? ` · editada ${fmtFecha(n.fecha_modificado)}` : ''}</span>
					</div>
				</article>
			{/each}
		</div>
		<Paginacion total={notas.length} bind:pagina porPagina={POR_PAGINA} etiqueta="notas" />
	{/if}
</div>

<style>
	/* Modo pestaña del Dashboard: sin padding propio (lo da la .page del
	   Dashboard) y el botón de nueva nota alineado a la derecha. */
	.embed-bar { display: flex; justify-content: flex-end; margin-bottom: 0.75rem; }

	.nota-aviso {
		padding: 0.5rem 0.75rem;
		background: rgba(34, 197, 94, 0.12);
		color: #22C55E;
		font-size: 0.8rem;
		border-radius: 8px;
		margin-bottom: 0.75rem;
	}

	/* Editor en panel */
	.editor {
		background: var(--color-surface);
		border: 1px solid var(--color-primary);
		border-radius: 14px;
		padding: 1rem;
		margin-bottom: 1rem;
	}
	.editor-title { font-weight: 700; font-size: 0.95rem; margin-bottom: 0.75rem; }
	.editor .field { margin-bottom: 0.6rem; }
	.editor-contenido { resize: vertical; min-height: 120px; line-height: 1.5; }
	.editor-acciones { display: flex; gap: 0.5rem; }
	.editor-opciones {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.6rem;
		margin-bottom: 0.75rem;
	}
	.colores { display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap; }
	.opciones-lbl { font-size: 0.72rem; color: var(--color-text-muted); margin-right: 0.15rem; }
	.color-chip {
		width: 22px;
		height: 22px;
		border-radius: 50%;
		background: var(--c);
		border: 2px solid transparent;
		cursor: pointer;
		padding: 0;
	}
	.color-chip.sel { border-color: var(--color-text); box-shadow: 0 0 0 2px var(--c); }
	.fija-check { display: flex; align-items: center; gap: 0.35rem; font-size: 0.78rem; cursor: pointer; }

	/* Lista de notas */
	.notas-lista { display: flex; flex-direction: column; gap: 0.8rem; }
	.nota-card {
		background: var(--color-surface);
		border: 1px solid rgba(255, 255, 255, 0.06);
		border-left: 5px solid var(--c, #F59E0B);
		border-radius: 14px;
		padding: 0.9rem 1rem;
	}
	.nota-fija {
		font-size: 0.62rem;
		font-weight: 700;
		color: var(--color-text-muted);
		background: rgba(255, 255, 255, 0.08);
		padding: 0.15rem 0.45rem;
		border-radius: 999px;
		margin-right: 0.4rem;
		vertical-align: middle;
	}
	.nota-head { display: flex; align-items: flex-start; gap: 0.5rem; }
	.nota-titulo { font-size: 1rem; margin: 0; flex: 1; line-height: 1.3; }
	.nota-acciones { display: flex; gap: 0.15rem; flex-shrink: 0; }
	.btn-icon {
		background: transparent;
		border: none;
		font-size: 0.95rem;
		cursor: pointer;
		padding: 0.25rem 0.4rem;
		border-radius: 8px;
		transition: background 0.1s;
	}
	.btn-icon:hover { background: rgba(255, 255, 255, 0.07); }
	.nota-contenido {
		white-space: pre-wrap;
		word-wrap: break-word;
		font-size: 0.88rem;
		line-height: 1.55;
		color: var(--color-text);
		margin-top: 0.45rem;
	}
	.nota-meta {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		gap: 0.4rem;
		margin-top: 0.7rem;
		padding-top: 0.55rem;
		border-top: 1px solid rgba(255, 255, 255, 0.06);
		font-size: 0.72rem;
		color: var(--color-text-muted);
	}
	.nota-autor { font-weight: 600; color: var(--color-text); }
</style>
