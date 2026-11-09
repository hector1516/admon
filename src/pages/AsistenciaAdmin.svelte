<!--
	🕘 Asistencia del día — quién entró y quién salió HOY.

	Misma información que la pantalla "🕘 Asistencia de hoy" del kiosco
	Dashboard (la app de la TV), pero leída directo del backend de Admon
	(`/api/asistencia`) en vez del snapshot en disco del kiosco: así los datos
	son del momento, sin esperar a que otro proceso refresque el snapshot.

	El cálculo NO es de esta vista: el backend toma la PRIMERA entrada y la
	ÚLTIMA salida del día de cada persona (la MAC aparece en la red cuando el
	escáner la ve, y eso pasa minutos después de que alguien cruzó la puerta),
	con el mismo ajuste que el kiosco. Acá sólo se pinta.

	Adaptación a esta interfaz: en vez de una rejilla calculada para un TV de
	1920×1080, es una rejilla que se acomoda al ancho de la pantalla, con
	métricas arriba, botón de refresco y la aclaración de que la hora sale de
	la red y no de un checador.
-->
<script>
	import { RefreshCw } from 'lucide-svelte';

	import { onMount, onDestroy } from 'svelte';
	import { auth } from '$lib/stores/auth.js';

	// Cada cuánto se refresca solo. La pantalla del kiosco lo hace su worker
	// cada 2 min; acá basta un minuto y no depende de ningún otro proceso.
	const AUTO_MS = 60_000;

	let datos = $state({ personas: [], total: 0, dentro: 0, salieron: 0, actualizado: '',
		estado: 'sin_datos', ciclo_scan: '', minutos_sin_scan: 0,
		ultimo_evento: '', minutos_sin_movimiento: 0, marcha: null });
	let loading = $state(true);
	let error = $state('');
	// 📷 Avatar por usuario: {id → blob URL}. Igual que en la lista de
	// usuarios: la foto pesa, así que se pide sólo la de quienes tienen y se
	// cachea en la sesión para no volver a bajarla en cada refresco.
	let avatares = $state({});

	let timer = null;
	let enVuelo = false;

	/*
		`en_sitio` sale del ÚLTIMO evento de cada quien, así que sólo es confiable
		si el escáner sigue escaneando y si lo que escribió es real. Si lo uno o
		lo otro falla, la pantalla estaría diciendo "sigue en la oficina" con
		información que no la sostiene (lo que pasó el 30 de septiembre: el
		escáner se cayó a las 15:56, nadie registró su salida y todos aparecían
		en verde toda la noche). Con datos congelados o con una marcha simultánea
		NO se pinta el estado: se avisa que no se sabe.

		OJO: lo que decide es el CICLO del escáner, no la última entrada o salida.
		Los movimientos son por evento — si a media mañana nadie entra ni sale en
		media hora no se registra nada y eso es normal, no es que el escáner esté
		caído.
	*/
	const congelado = $derived(datos.estado === 'congelado');
	const inestable = $derived(datos.estado === 'inestable');
	const futuro = $derived(datos.estado === 'futuro');
	const sinEstado = $derived(congelado || inestable || futuro);

	/** "7 h 12 min" a partir de los minutos, para el aviso de datos viejos. */
	function antiguedad(min) {
		const m = Math.max(0, Math.floor(min || 0));
		const h = Math.floor(m / 60);
		return h ? `${h} h ${m % 60} min` : `${m} min`;
	}

	function hhmm(iso) {
		if (!iso) return '';
		const t = Date.parse(iso.replace(' ', 'T'));
		if (Number.isNaN(t)) return '';
		const d = new Date(t);
		return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
	}

	/** Iniciales para el círculo cuando la persona no tiene foto. */
	function iniciales(nombre) {
		const partes = String(nombre || '').trim().split(/\s+/).filter(Boolean);
		if (!partes.length) return '?';
		if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
		return (partes[0][0] + partes[1][0]).toUpperCase();
	}

	function dosDigitos(n) {
		return String(n ?? 0).padStart(2, '0');
	}

	// Sólo quienes tienen entrada se pintan: una persona con la MAC vista en la
	// red pero sin ENTRADA del día no tiene hora de llegada que mostrar.
	const conRegistro = $derived((datos.personas || []).filter((p) => p.entrada));

	async function cargarAvatares() {
		await Promise.all(
			conRegistro
				.filter((p) => p.tiene_foto && !avatares[p.id_usuario])
				.map(async (p) => {
					try {
						const r = await fetch(`/api/users/${p.id_usuario}/foto`, { headers: auth.authHeader() });
						if (!r.ok) return;
						const blob = await r.blob();
						avatares = { ...avatares, [p.id_usuario]: URL.createObjectURL(blob) };
					} catch {
						// sin conexión o sin foto: se queda el avatar de iniciales
					}
				})
		);
	}

	async function cargar(silencioso = false) {
		if (enVuelo) return; // no encimar refrescos si la petición tarda más que el intervalo
		enVuelo = true;
		if (!silencioso) loading = true;
		try {
			const r = await fetch('/api/asistencia', { headers: auth.authHeader() });
			if (r.status === 401) {
				error = 'Sesión expirada. Vuelve a entrar.';
				return;
			}
			const data = await r.json();
			if (!r.ok) throw new Error(data.detail || 'No se pudo cargar la asistencia.');
			datos = data;
			error = '';
		} catch (e) {
			// En un refresco automático no se tapa lo que ya está en pantalla:
			// un fallo de red momentáneo no debería dejar la pantalla en blanco.
			if (!silencioso) error = e.message || 'No se pudo cargar. Revisa tu conexión.';
		} finally {
			loading = false;
			enVuelo = false;
		}
		// Las fotos se piden después de pintar: la lista sale ya con iniciales.
		await cargarAvatares();
	}

	onMount(() => {
		cargar();
		timer = setInterval(() => {
			// Sólo con la pestaña a la vista: refrescar en segundo plano no
			// aporta nada y sí gasta batería y datos en el celular.
			if (!document.hidden) cargar(true);
		}, AUTO_MS);
	});

	onDestroy(() => {
		if (timer) clearInterval(timer);
		// Libera los blob URL de las fotos (el navegador no los suelta solo).
		Object.values(avatares).forEach((u) => URL.revokeObjectURL(u));
	});
</script>

<!-- Barra: refresco a la mano + de cuándo son los datos que se ven. -->
<div class="embed-bar">
	<span class="actualizado">
		{#if sinEstado}
			Último ciclo del escáner: <b>{datos.ciclo_scan?.slice(11) || 'nunca'}</b>
			{#if datos.ultimo_evento}· último movimiento {datos.ultimo_evento.slice(11)}{/if}
		{:else if datos.actualizado}
			Actualizado <b>{datos.actualizado.slice(11)}</b> · se refresca solo cada minuto
			{#if datos.ultimo_evento}<span class="dim">· último movimiento {datos.ultimo_evento.slice(11)}</span>{/if}
		{/if}
	</span>
	<button class="btn btn-sm btn-secondary" onclick={() => cargar()} disabled={loading}>
		{loading ? 'Cargando…' : '<RefreshCw size={16} /> Actualizar'}
	</button>
</div>

<!--
	Datos que no sostienen el estado. En los dos casos lo que se ve abajo es real
	(las horas de llegada y salida no envejecen ni se inventan), pero el "sigue
	en la oficina / ya se fue" no se puede afirmar, así que no se pinta de verde
	ni de rojo. El aviso va arriba de todo porque lo que falta es información.
-->
{#if congelado}
	<div class="alerta">
		<span class="alerta-ic">⚠️</span>
		<span>
			<b>El escáner de red no corre desde hace {antiguedad(datos.minutos_sin_scan)}</b>
			{#if datos.ciclo_scan}(último ciclo a las {datos.ciclo_scan.slice(11)}){:else}(nunca ha registrado un ciclo){/if}.
			No se sabe quién sigue en la oficina: abajo se ve cuándo entró y salió cada
			quien la última vez que se registró, pero el estado de "en sitio / fuera" no
			es confiable. Hay que revisar el escáner.
		</span>
	</div>
{:else if inestable}
	<div class="alerta">
		<span class="alerta-ic">⚠️</span>
		<span>
			<b>El detector cambió el estado de {datos.marcha?.personas} personas de un jalón</b>
			({datos.marcha?.tipo === 'SALIDA' ? 'salidas' : 'entradas'} entre las
			{datos.marcha?.desde} y las {datos.marcha?.hasta}). Eso no son movimientos reales:
			pasa cuando el escáner se reinicia o se cae la red un momento. Se espera a que
			se estabilice para volver a pintar quién está aquí.
		</span>
	</div>
{:else if futuro}
	<div class="alerta">
		<span class="alerta-ic">⚠️</span>
		<span>
			<b>Hay registros con fecha que todavía no llega</b> (el escáner escribió un
			ciclo con hora {datos.ciclo_scan?.slice(11)}). Los relojes no coinciden, así que
			las horas de arriba no son de fiar hasta que se revise el detector.
		</span>
	</div>
{/if}

{#if loading}
	<div class="empty">Cargando asistencia…</div>
{:else if error}
	<div class="card"><p class="err">{error}</p></div>
{:else if datos.estado === 'sin_datos'}
	<div class="empty">
		Todavía no hay ningún registro de hoy.
		<span class="vacio-sub">
			Aquí aparece cada persona en cuanto su equipo o celular conocido se
			conecta a la red de la oficina.
		</span>
	</div>
{:else}
	<!-- Métricas: cuántas se registraron hoy y cómo están ahora. -->
	<div class="metricas" class:neutral={sinEstado}>
		<div class="metrica">
			<span class="rot">Registradas</span>
			<span class="num">{dosDigitos(datos.total)}</span>
		</div>
		<div class="metrica sitio">
			<span class="rot">🟢 En sitio{sinEstado ? ' (¿?)' : ''}</span>
			<span class="num">{dosDigitos(datos.dentro)}</span>
		</div>
		<div class="metrica fuera">
			<span class="rot">🔴 Fuera{sinEstado ? ' (¿?)' : ''}</span>
			<span class="num">{dosDigitos(datos.salieron)}</span>
		</div>
	</div>

	{#if conRegistro.length === 0}
		<div class="empty">
			Todavía nadie ha registrado movimientos hoy.
			<span class="vacio-sub">
				Aquí aparece cada persona en cuanto su equipo o celular conocido se
				conecta a la red de la oficina.
			</span>
		</div>
	{:else}
		<div class="rejilla" class:neutral={sinEstado}>
			{#each conRegistro as p (p.id_usuario)}
				<article class="tarjeta" class:sitio={p.en_sitio} class:fuera={!p.en_sitio}>
					<div class="cabeza">
						<div class="avatar">
							{#if avatares[p.id_usuario]}
								<img src={avatares[p.id_usuario]} alt="Foto de {p.nombre}" />
							{:else}
								<span>{iniciales(p.nombre)}</span>
							{/if}
						</div>
						<div class="datos">
							<div class="nombre">{p.nombre}</div>
							{#if p.en_sitio && p.reingreso}
								<!-- Salió y volvió: la salida no se muestra (ya no aplica), pero
								     sí cuándo entró en la visita en la que sigue. -->
								<div class="reingreso">↩️ volvió {hhmm(p.reingreso)}</div>
							{/if}
						</div>
					</div>

					<div class="horas">
						<div class="hora">
							<span class="rot">Llegó</span>
							<span class="hhmm llegada">{hhmm(p.entrada)}</span>
						</div>
						{#if !p.en_sitio && p.salida}
							<div class="hora">
								<span class="rot">Se fue</span>
								<span class="hhmm ida">{hhmm(p.salida)}</span>
							</div>
						{/if}
					</div>
				</article>
			{/each}
		</div>
	{/if}
{/if}

<!--
	La aclaración va fuera del bloque de arriba a propósito: también tiene que
	leerse cuando la pantalla sale vacía, que es justo cuando alguien necesita
	saber por qué.
-->
<p class="nota">
	ℹ️ Los horarios se calculan solos a partir de la red de la oficina (cuando un
	equipo o celular conocido se conecta), por lo que pueden variar algunos
	minutos y no siempre detectan todas las entradas ni todas las salidas.
	<b>Es información orientativa, no un registro oficial de asistencia.</b>
</p>

<style>
	/* Todo el estilo va local al componente: `src/styles/app.css` es del shell
	   canónico y el CI valida que no se toque a mano. */

	.embed-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		flex-wrap: wrap;
		margin-bottom: 0.75rem;
	}
	.actualizado {
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}
	.actualizado b { color: var(--color-text); }
	.actualizado .dim { color: var(--color-text-muted); }
	.err { color: var(--color-danger); margin: 0; }

	/* Métricas: los tres números de arriba, con el mismo código de color que
	   los estados de las tarjetas (verde = aquí, rojo = ya se fue). */
	.metricas {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.75rem;
		margin-bottom: 0.9rem;
	}
	.metrica {
		background: var(--color-surface, rgba(255, 255, 255, 0.04));
		border: 1px solid rgba(255, 255, 255, 0.1);
		border-radius: 12px;
		padding: 0.6rem 0.85rem;
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}
	.metrica .rot {
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--color-text-muted);
	}
	.metrica .num {
		font-size: 1.5rem;
		font-weight: 800;
		line-height: 1.1;
		font-variant-numeric: tabular-nums;
	}
	.metrica.sitio { border-color: rgba(74, 222, 128, 0.4); }
	.metrica.sitio .num { color: #4ade80; }
	.metrica.fuera { border-color: rgba(248, 113, 113, 0.35); }
	.metrica.fuera .num { color: #f87171; }

	/* Rejilla que se acomoda al ancho en vez de calcularse para un TV de
	   1920×1080: en celular cae a una columna y en escritorio a varias. */
	.rejilla {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
		gap: 0.75rem;
	}

	/* Una tarjeta = una persona: avatar y nombre arriba, las horas abajo.
	   Verde = sigue en la oficina, rojo = ya salió. */
	.tarjeta {
		display: flex;
		flex-direction: column;
		gap: 0.7rem;
		padding: 0.85rem 1rem;
		border-radius: 14px;
		background: rgba(255, 255, 255, 0.03);
	}
	.tarjeta.sitio {
		background: linear-gradient(100deg, rgba(34, 197, 94, 0.22) 0%, rgba(22, 163, 74, 0.07) 100%);
		border: 1px solid rgba(74, 222, 128, 0.5);
	}
	.tarjeta.fuera {
		background: linear-gradient(100deg, rgba(239, 68, 68, 0.22) 0%, rgba(185, 28, 28, 0.07) 100%);
		border: 1px solid rgba(248, 113, 113, 0.45);
	}

	/*
		Datos que no sostienen el estado (escáner congelado, marcha simultánea o
	reloj desfasado): se
	cae el color de estado. Poner
		"verde = en la oficina" cuando no se sabe es justamente el error que hizo
		esta pantalla. Las horas se conservan porque ésas no envejecen: "llegó
		08:22" sigue siendo cierto aunque el dato sea de hace horas.
	*/
	.rejilla.neutral .tarjeta {
		background: rgba(255, 255, 255, 0.03);
		border: 1px dashed rgba(148, 163, 184, 0.35);
	}
	.metricas.neutral .metrica.sitio,
	.metricas.neutral .metrica.fuera { border-color: rgba(148, 163, 184, 0.3); }
	.metricas.neutral .metrica.sitio .num,
	.metricas.neutral .metrica.fuera .num { color: var(--color-text-muted); }

	/* Aviso de datos congelados: va arriba de todo, en rojo/ámbar, porque lo
	   que falta es información y no un detalle. */
	.alerta {
		display: flex;
		align-items: flex-start;
		gap: 0.6rem;
		margin-bottom: 0.85rem;
		padding: 0.7rem 0.9rem;
		border-radius: 12px;
		background: rgba(245, 158, 11, 0.12);
		border: 1px solid rgba(245, 158, 11, 0.45);
		font-size: 0.83rem;
		line-height: 1.45;
		color: #fcd34d;
	}
	.alerta b { color: #fde68a; }
	.alerta-ic { flex-shrink: 0; }

	.cabeza { display: flex; align-items: center; gap: 0.75rem; min-width: 0; }
	.datos { flex: 1; min-width: 0; }
	.nombre {
		font-weight: 700;
		font-size: 1rem;
		line-height: 1.25;
		overflow-wrap: anywhere;
	}
	.reingreso {
		font-size: 0.78rem;
		color: #86efac;
		margin-top: 0.15rem;
	}

	.avatar {
		width: 2.9rem;
		height: 2.9rem;
		border-radius: 999px;
		flex-shrink: 0;
		overflow: hidden;
		background: rgba(0, 0, 0, 0.3);
		border: 2px solid rgba(255, 255, 255, 0.15);
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.avatar img { width: 100%; height: 100%; object-fit: cover; }
	.avatar span { font-size: 0.95rem; font-weight: 700; color: var(--color-text-muted); }

	.horas { display: flex; flex-wrap: wrap; gap: 0.5rem; }
	.hora {
		display: flex;
		align-items: baseline;
		gap: 0.45rem;
		padding: 0.3rem 0.6rem;
		border-radius: 10px;
		background: rgba(2, 6, 23, 0.36);
		border: 1px solid rgba(255, 255, 255, 0.1);
	}
	.rot {
		font-size: 0.66rem;
		font-weight: 800;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: rgba(255, 255, 255, 0.6);
	}
	.hhmm {
		font-size: 1.05rem;
		font-weight: 800;
		line-height: 1;
		font-variant-numeric: tabular-nums;
	}
	.llegada { color: #86efac; }
	.ida { color: #fca5a5; }

	.vacio-sub {
		display: block;
		margin-top: 0.3rem;
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	.nota {
		margin: 0.9rem 0 0;
		padding: 0.6rem 0.85rem;
		border-radius: 12px;
		background: rgba(148, 163, 184, 0.06);
		border: 1px solid rgba(148, 163, 184, 0.12);
		font-size: 0.78rem;
		line-height: 1.45;
		color: var(--color-text-muted);
	}
	.nota b { color: var(--color-text); }

	@media (max-width: 520px) {
		/* En celular las tres métricas en 3 columnas se aprietan demasiado. */
		.metricas { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.5rem; }
		.metrica { padding: 0.5rem 0.6rem; }
		.metrica .num { font-size: 1.2rem; }
		.metrica .rot { font-size: 0.62rem; letter-spacing: 0.04em; }
	}
</style>