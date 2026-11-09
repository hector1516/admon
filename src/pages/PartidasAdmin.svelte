<script>
	import { Save } from 'lucide-svelte';

	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { header, partidas, partidaAdd, partidaUpdate, partidaDelete, satSugerir } from '$lib/cotizacionesApi.js';
	import { fmtMXN, ventaUnit, totales, folioFmt } from '$lib/cotizaciones.js';

	let { clave } = $props();

	let h = $state(null);
	let items = $state([]);
	let loading = $state(true);
	let error = $state('');
	let msg = $state('');
	let busy = $state(false);

	// Formulario (nueva o edición)
	let editando = $state(null); // número de partida o null
	let cantidad = $state(1);
	let precioCompra = $state(0);
	let usarFactor = $state(true);
	let factor = $state(0.25);
	let flete = $state(0);
	let proveedor = $state('');
	let tiempoEntrega = $state(1);
	let descripcion = $state('');
	// Códigos SAT CFDI 4.0 (vacío = el servidor los resuelve solo al guardar)
	let satProd = $state('');
	let satUnidad = $state('');
	let satInfo = $state('');
	let satBusy = $state(false);
	// Artículo genérico de compras (NO es el código SAT): "controlador lógico",
	// "disyuntor", "cable de comunicación". Va al PDF antes del SAT y la unidad.
	let articuloGenerico = $state('');

	function tieneAcceso() {
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && u.acceso_cotizaciones);
		} catch {
			return false;
		}
	}

	let bloqueado = $derived((h?.color ?? 0) === 1 || (h?.color ?? 0) === 2);
	let tots = $derived(totales(items));
	let ventaPreview = $derived(ventaUnit(precioCompra, usarFactor ? factor : 0));
	let importePreview = $derived(ventaPreview * (parseInt(cantidad, 10) || 0) + (parseFloat(flete) || 0));
	let formListo = $derived(descripcion.trim() && (parseInt(cantidad, 10) || 0) >= 1 && !busy);

	async function cargar() {
		loading = true;
		error = '';
		try {
			h = await header(clave);
			items = await partidas(h.folio ?? h.idLocal);
		} catch (e) {
			error = e.message === 'Sesión expirada' ? e.message : `No se pudo cargar (${e.message || 'sin conexión'}).`;
		} finally {
			loading = false;
		}
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
		await cargar();
	});

	function limpiarForm() {
		editando = null;
		cantidad = 1;
		precioCompra = 0;
		usarFactor = true;
		factor = 0.25;
		flete = 0;
		proveedor = '';
		tiempoEntrega = 1;
		descripcion = '';
		satProd = '';
		satUnidad = '';
		satInfo = '';
		articuloGenerico = '';
	}

	function seleccionar(p) {
		editando = p.partida;
		cantidad = p.cantidad;
		precioCompra = p.precio_compra;
		usarFactor = (p.factor || 0) > 0;
		factor = p.factor || 0;
		flete = p.flete || 0;
		proveedor = p.proveedor || '';
		tiempoEntrega = p.tiempo_entrega ?? 0;
		descripcion = p.descripcion || '';
		satProd = p.sat_prod_serv || '';
		satUnidad = p.sat_unidad || '';
		satInfo = p.sat_fuente ? `Guardado (fuente: ${p.sat_fuente})` : '';
		articuloGenerico = p.articulo_generico || '';
		msg = '';
		error = '';
	}

	function payload() {
		return {
			cantidad: parseInt(cantidad, 10) || 0,
			descripcion: descripcion.trim(),
			precio_compra: parseFloat(precioCompra) || 0,
			factor: usarFactor ? parseFloat(factor) || 0 : 0,
			proveedor,
			tiempo_entrega: parseInt(tiempoEntrega, 10) || 0,
			dolar: 0,
			flete: parseFloat(flete) || 0,
			sat_prod_serv: satProd.trim(),
			sat_unidad: satUnidad.trim(),
			articulo_generico: articuloGenerico.trim()
		};
	}

	// Botón 🤖: resuelve códigos SAT de la descripción en vivo (índice →
	// reglas locales → 1 llamada IA) sin guardar la partida.
	async function onSugerirSat() {
		error = '';
		msg = '';
		if (!descripcion.trim()) {
			error = 'Escribe primero la descripción de la partida.';
			return;
		}
		satBusy = true;
		try {
			const s = await satSugerir(descripcion);
			if (s) {
				satProd = s.clave_prod_serv || '';
				satUnidad = s.clave_unidad || '';
				// El artículo genérico solo se rellena si está vacío: lo que ya
				// escribió el usuario se respeta.
				let articuloRelleno = false;
				if (s.articulo_generico && !articuloGenerico.trim()) {
					articuloGenerico = s.articulo_generico;
					articuloRelleno = true;
				}
				const origen = { indice: 'índice local', reglas: 'reglas locales', ia: 'IA Gemini' }[s.origen] || s.fuente;
				satInfo = `Sugerido por ${origen}${articuloRelleno ? ' (también el artículo)' : ''}${s.razon ? ` · ${s.razon}` : ''}`;
				// Si no hubo artículo, se dice: mejor un aviso que un campo
				// que "pareció" haberse llenado y sigue vacío.
				if (!articuloRelleno && !articuloGenerico.trim()) {
					msg = '⚠️ Se sugieren los códigos SAT, pero no el artículo genérico: escríbelo a mano (p. ej. "bloque de contactos").';
				}
			} else {
				satInfo = '';
				msg = '⚠️ Sin sugerencia (sin API key de IA o descripción muy corta). Captura los códigos manualmente.';
			}
		} catch (e) {
			error = e.message || 'No se pudo consultar la sugerencia SAT.';
		} finally {
			satBusy = false;
		}
	}

	async function onGuardar() {
		error = '';
		msg = '';
		busy = true;
		try {
			const key = h.folio ?? h.idLocal;
			let r;
			if (editando == null) {
				r = await partidaAdd(key, payload());
				msg = r.pendiente ? '⏳ Partida guardada offline. Se sincronizará.' : '✅ Partida agregada.';
			} else {
				r = await partidaUpdate(key, editando, payload());
				msg = r.pendiente ? '⏳ Cambios guardados offline. Se sincronizarán.' : '✅ Partida actualizada.';
			}
			limpiarForm();
			await cargar();
		} catch (e) {
			error = e.message || 'No se pudo guardar.';
		} finally {
			busy = false;
		}
	}

	async function onEliminar() {
		if (editando == null) return;
		if (!confirm(`¿Eliminar la partida #${editando}?`)) return;
		error = '';
		msg = '';
		busy = true;
		try {
			const key = h.folio ?? h.idLocal;
			const r = await partidaDelete(key, editando);
			msg = r.pendiente ? '⏳ Eliminación guardada offline. Se sincronizará.' : '✅ Partida eliminada.';
			limpiarForm();
			await cargar();
		} catch (e) {
			error = e.message || 'No se pudo eliminar.';
		} finally {
			busy = false;
		}
	}
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" on:click={() => navigate(`/cotizaciones/${clave}`)} title="Volver">⬅️</button>
		<h1>📋 Partidas {h ? folioFmt(h.folio ?? h.idLocal) : ''}</h1>
	</div>

	{#if loading}
		<div class="empty">Cargando…</div>
	{:else if error && !h}
		<div class="card"><p style="color: var(--color-danger); margin: 0;">{error}</p></div>
	{:else if h}
		{#if bloqueado}
			<div class="card" style="border-color: rgba(239,68,68,0.4);">
				<p style="margin: 0; font-size: 0.85rem;">🔒 Cotización bloqueada (lista para facturar / facturada).</p>
			</div>
		{/if}

		<div class="card" style="margin-bottom: 0.75rem;">
			<div class="card-title">Partidas registradas ({items.length})</div>
			{#if items.length === 0}
				<p style="margin: 0; font-size: 0.85rem; color: var(--color-text-muted);">
					ℹ️ Sin partidas aún. Usa el formulario de abajo para agregar la primera.
				</p>
			{:else}
				<div class="list">
					{#each items as p (p.partida)}
						<button class="list-card" class:selected={editando === p.partida} on:click={() => seleccionar(p)} disabled={bloqueado}>
							<div style="flex: 1; min-width: 0; text-align: left;">
								<div style="font-size: 0.75rem; color: var(--color-text-muted);">
									#{p.partida} · cant. {p.cantidad}
									{#if !p.synced}<span class="badge badge-warning" style="font-size: 0.6rem;">⏳</span>{/if}
								</div>
								<div style="font-size: 0.9rem; font-weight: 600;">{p.descripcion}</div>
								<div style="font-size: 0.75rem; color: var(--color-text-muted);">
									${Number(p.precio_compra).toFixed(2)} × (1+{p.factor}){p.flete ? ` + flete $${Number(p.flete).toFixed(2)}` : ''}
								</div>
								{#if p.articulo_generico}
									<div style="font-size: 0.7rem; color: var(--color-text-muted);">📦 {p.articulo_generico}</div>
								{/if}
								{#if p.sat_prod_serv}
									<div style="font-size: 0.7rem; color: var(--color-text-muted);">
										🧾 SAT: {p.sat_prod_serv}{p.sat_unidad ? ` · ${p.sat_unidad}` : ''}
										{#if p.sat_fuente}· {p.sat_fuente}{/if}
									</div>
								{/if}
							</div>
							<div style="font-weight: 700; color: var(--color-primary-light); flex-shrink: 0;">{fmtMXN(p.total_venta)}</div>
						</button>
					{/each}
				</div>
			{/if}
			<div style="margin-top: 0.75rem; font-size: 0.9rem;">
				<div style="display: flex; justify-content: space-between;"><span style="color: var(--color-text-muted);">Subtotal</span><strong>{fmtMXN(tots.subtotal)}</strong></div>
				<div style="display: flex; justify-content: space-between;"><span style="color: var(--color-text-muted);">IVA 16%</span><strong>{fmtMXN(tots.iva)}</strong></div>
				<div style="display: flex; justify-content: space-between; font-size: 1.05rem;"><span>Total</span><strong style="color: var(--color-primary-light);">{fmtMXN(tots.total)}</strong></div>
			</div>
		</div>

		{#if !bloqueado}
			<div class="card">
				<div class="card-title">{editando == null ? '➕ Nueva partida' : `✏️ Modificar partida #${editando}`}</div>
				<p class="hint">🇲🇽 Todos los montos de compra y flete en pesos mexicanos (MXN).</p>

				<div class="grid-2">
					<div class="field">
						<label for="pa-cant">Cantidad:</label>
						<input id="pa-cant" type="number" class="input" min="1" step="1" bind:value={cantidad} />
					</div>
					<div class="field">
						<label for="pa-precio">Precio compra unit. ($):</label>
						<input id="pa-precio" type="number" class="input" min="0" step="10" bind:value={precioCompra} />
					</div>
				</div>

				<div class="grid-2">
					<div class="field">
						<label class="check"><input type="checkbox" bind:checked={usarFactor} /> Usar factor</label>
						<input type="number" class="input" min="0" step="0.01" bind:value={factor} disabled={!usarFactor} aria-label="Factor" />
					</div>
					<div class="field">
						<label for="pa-flete">Flete ($):</label>
						<input id="pa-flete" type="number" class="input" min="0" step="10" bind:value={flete} />
					</div>
				</div>

				<div class="grid-2">
					<div class="field">
						<label for="pa-prov">Proveedor:</label>
						<input id="pa-prov" class="input" placeholder="Opcional" bind:value={proveedor} />
					</div>
					<div class="field">
						<label for="pa-entrega">Entrega (días hábiles):</label>
						<input id="pa-entrega" type="number" class="input" min="0" step="1" bind:value={tiempoEntrega} />
					</div>
				</div>

				<div class="field">
					<label for="pa-desc">Descripción de la partida:</label>
					<textarea id="pa-desc" class="input" rows="2" placeholder="Descripción detallada del material…" bind:value={descripcion}></textarea>
				</div>

				<div class="field">
					<label for="pa-articulo">Artículo genérico:</label>
					<input id="pa-articulo" class="input" maxlength="200"
						placeholder="Ej. controlador lógico, disyuntor, cable de comunicación"
						bind:value={articuloGenerico} />
					<p class="hint">Cómo se llama el artículo en compras (sin marca ni modelo). Va al PDF antes del código SAT y de la unidad.</p>
				</div>

				<div class="grid-2">
					<div class="field">
						<label for="pa-satprod">Clave producto SAT (8 dígitos):</label>
						<input id="pa-satprod" class="input" placeholder="Ej. 84039000" maxlength="8" bind:value={satProd} />
					</div>
					<div class="field">
						<label for="pa-satuni">Clave unidad SAT:</label>
						<input id="pa-satuni" class="input" placeholder="Ej. H87" maxlength="3" bind:value={satUnidad} />
					</div>
				</div>
				<button class="btn btn-secondary btn-block" on:click={onSugerirSat} disabled={satBusy || busy || !descripcion.trim()}>
					{satBusy ? 'Consultando…' : '🤖 Sugerir artículo y SAT por descripción'}
				</button>
				{#if satInfo}
					<p class="hint" style="margin-top: 0.35rem;">🧾 {satInfo}</p>
				{/if}
				<p class="hint">Déjalos vacíos y al guardar el servidor los resuelve solo (índice → reglas → IA).</p>

				<p style="font-weight: 600;">
					💰 Venta unitario: <span style="color: var(--color-primary-light);">{fmtMXN(ventaPreview)}</span>
					| Importe: <span style="color: var(--color-primary-light);">{fmtMXN(importePreview)}</span>
				</p>

				{#if error}
					<div class="msg err">{error}</div>
				{/if}
				{#if msg}
					<div class="msg ok">{msg}</div>
				{/if}

				{#if editando == null}
					<button class="btn btn-primary btn-block" on:click={onGuardar} disabled={!formListo}>
						{busy ? 'Guardando…' : '<Save size={16} /> Guardar partida'}
					</button>
				{:else}
					<div class="grid-2" style="margin-bottom: 0.5rem;">
						<button class="btn btn-secondary btn-block" on:click={limpiarForm}>❌ Cancelar</button>
						<button class="btn btn-primary btn-block" on:click={onGuardar} disabled={!formListo}>
							{busy ? 'Guardando…' : '<Save size={16} /> Guardar cambios'}
						</button>
					</div>
					<HoldButton label="Eliminar partida" onConfirm={onEliminar} disabled={busy} size="md" block={true} />
				{/if}
			</div>
		{/if}
	{/if}
</div>

<style>
	.card-title { font-weight: 700; font-size: 1rem; margin-bottom: 0.25rem; }
	.hint { font-size: 0.8rem; color: var(--color-text-muted); }
	.msg { padding: 0.6rem 0.75rem; border-radius: 8px; font-size: 0.85rem; margin-bottom: 0.75rem; }
	.msg.err { background: rgba(239,68,68,0.1); color: #EF4444; }
	.msg.ok { background: rgba(34,197,94,0.1); color: #22C55E; }
	.card { margin-bottom: 0.75rem; }
	.list-card.selected { border-color: var(--color-primary); }
</style>
