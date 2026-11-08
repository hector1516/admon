<script>
	import { onMount, tick } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { api } from '$lib/api.js';
	import { marked } from 'marked';

	// ECCSA IA — chat de UNA SOLA conversación por usuario (estilo ChatGPT).
	// Wobnimo: mascota 3D (Volt, robot LED) que reacciona al estado del chat.
	// Backend clon del HUB views/edwin_jarvis.py: 3 tools
	// (execute_query, send_quote_pdf, send_service_reports) + sugerencias SAT.
	// Sin sidebar: al abrir se usa la conversación más reciente del usuario
	// (o se crea una si no existe) y el botón 🗑️ la borra para empezar de cero.

	let conversacion = $state(null);
	let mensajes = $state([]);
	let nuevoMensaje = $state('');
	let enviando = $state(false);
	let loading = $state(true);
	let error = $state('');
	let messagesContainer = $state(null);
	let mascotState = $state('idle'); // idle | thinking | speaking | celebrating | error
	let mascotContainer = $state(null);

	// Sugerencias iniciales (solo cuando la conversación está vacía)
	const sugerencias = [
		'📦 ¿Cuántas cotizaciones tenemos este mes?',
		'💡 Sugiere claves SAT para un motor eléctrico',
		'📋 Resumen de reportes de servicio de la semana',
		'📧 Envíame una cotización por correo'
	];

	// marked sin sanitizer propio: escapamos el HTML de entrada primero para que
	// la respuesta del modelo no pueda inyectar scripts; el Markdown (tablas,
	// listas, negritas) sigue procesándose con normalidad.
	marked.setOptions({ breaks: true, gfm: true });
	function renderMd(texto) {
		const escapado = String(texto ?? '')
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;');
		return marked.parse(escapado);
	}

	function apiHeaders() {
		return { 'Content-Type': 'application/json', ...auth.authHeader() };
	}

	// Una sola conversación: la más reciente; si no existe, se crea.
	async function abrirConversacion() {
		try {
			const lista = (await api.get('/ia/conversaciones')) || [];
			if (lista.length > 0) {
				await cargarMensajes(lista[0]);
			} else {
				await crearConversacion();
			}
		} catch (e) {
			error = e.message === 'Sesión expirada' ? e.message : 'No se pudo abrir la conversación.';
		} finally {
			loading = false;
		}
	}

	async function crearConversacion() {
		const res = await fetch('/api/ia/conversaciones', {
			method: 'POST',
			headers: apiHeaders(),
			body: JSON.stringify({ titulo: 'Nueva conversación' })
		});
		const data = await res.json().catch(() => ({}));
		if (!res.ok) throw new Error(data.detail || 'Error al crear la conversación.');
		conversacion = { Id: data.Id, Titulo: data.Titulo, FechaCreacion: data.FechaCreacion };
		mensajes = [];
	}

	async function cargarMensajes(conv) {
		conversacion = conv;
		mensajes = (await api.get(`/ia/conversaciones/${conv.Id}/mensajes`)) || [];
		autoScroll();
	}

	async function borrarConversacion() {
		if (!conversacion) return;
		if (!confirm('¿Borrar la conversación y empezar de cero?')) return;
		error = '';
		try {
			const res = await fetch(`/api/ia/conversaciones/${conversacion.Id}`, {
				method: 'DELETE',
				headers: auth.authHeader()
			});
			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				throw new Error(data.detail || 'Error al borrar.');
			}
			await crearConversacion();
		} catch (e) {
			error = e.message || 'Error al borrar la conversación.';
		}
	}

	async function enviarMensaje(textoLibre) {
		const texto = (textoLibre ?? nuevoMensaje).trim();
		if (!texto || !conversacion || enviando) return;
		nuevoMensaje = '';
		enviando = true;
		error = '';
		mascotState = 'thinking';

		// UI optimista: el mensaje del usuario aparece de inmediato
		const msgUsuario = {
			Id: Date.now(),
			Role: 'user',
			Contenido: texto,
			FechaRegistro: new Date().toISOString()
		};
		mensajes = [...mensajes, msgUsuario];
		autoScroll();

		try {
			const res = await fetch(`/api/ia/conversaciones/${conversacion.Id}/mensajes`, {
				method: 'POST',
				headers: apiHeaders(),
				body: JSON.stringify({ contenido: texto })
			});
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al enviar.');

			// Reemplaza con el historial real (incluye la respuesta de la IA)
			mensajes = data.mensajes || [];
			mascotState = 'celebrating';

			// El backend titula la conversación con la primera pregunta
			if (conversacion.Titulo === 'Nueva conversación' && data.titulo) {
				conversacion.Titulo = data.titulo;
			}
			// Volver a idle después de celebrar
			setTimeout(() => { mascotState = 'idle'; }, 2000);
		} catch (e) {
			error = e.message || 'Error al enviar mensaje.';
			mascotState = 'error';
			mensajes = mensajes.filter((m) => m.Id !== msgUsuario.Id);
			setTimeout(() => { mascotState = 'idle'; }, 3000);
		} finally {
			enviando = false;
			autoScroll();
		}
	}

	function compartirWhatsApp(texto) {
		const clean = (texto || '').replace(/<[^>]*>/g, '').replace(/\*\*/g, '').trim();
		const url = 'https://wa.me/?text=' + encodeURIComponent(clean.slice(0, 500));
		window.open(url, '_blank');
	}

function formatearFecha(fecha) {
		if (!fecha) return '';
		const d = new Date(fecha);
		const hoy = new Date();
		const ayer = new Date(hoy);
		ayer.setDate(ayer.getDate() - 1);
		if (d.toDateString() === hoy.toDateString()) {
			return 'Hoy ' + d.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
		}
		if (d.toDateString() === ayer.toDateString()) {
			return 'Ayer ' + d.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
		}
		return d.toLocaleDateString('es-MX', { day: '2-digit', month: 'short' }) +
			' ' + d.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
	}

	// Configurar mascota Wobnimo
	function setupMascot() {
		if (!mascotContainer) return;
		const el = mascotContainer.querySelector('wobnimo-mascot');
		if (!el) return;
		customElements.whenDefined('wobnimo-mascot').then(() => {
			el.setAttribute('character', 'volt');
			el.setAttribute('state', mascotState);
		});
	}

	$effect(() => {
		void mascotState;
		setupMascot();
	});

	async function autoScroll() {
		await tick();
		if (messagesContainer) messagesContainer.scrollTop = messagesContainer.scrollHeight;
	}

	// Mantener el scroll abajo cuando llegan mensajes o cambia el "escribiendo"
	$effect(() => {
		void mensajes.length;
		void enviando;
		autoScroll();
	});

	onMount(async () => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
		// Cargar Wobnimo (mascota 3D Volt)
		if (!document.querySelector('script[src*="wobnimo"]')) {
			const script = document.createElement('script');
			script.type = 'module';
			script.src = 'https://cdn.jsdelivr.net/npm/wobnimo@0.2/dist/wobnimo.js';
			document.head.appendChild(script);
		}
		await abrirConversacion();
	});
</script>

<div class="chat-page">
	<!-- Header del chat (estilo app de mensajería) -->
	<header class="chat-header">
		<button class="btn-icon" on:click={() => navigate('/')} title="Volver">⬅️</button>
		<div class="chat-title">
			<div class="chat-avatar wobnimo-avatar" bind:this={mascotContainer}>
			{@html '<wobnimo-mascot character="volt" state="' + mascotState + '"></wobnimo-mascot>'}
		</div>
			<div class="chat-names">
				<strong>ECCSA IA</strong>
				<span class="chat-status">🟢 En línea · asistente de ECCSA Automation</span>
			</div>
		</div>
		<button class="btn-icon" on:click={borrarConversacion} title="Borrar la conversación">🗑️</button>
	</header>

	{#if error}
		<div class="chat-error">{error}</div>
	{/if}

	<!-- Mensajes -->
	<div class="chat-messages" bind:this={messagesContainer}>
		{#if loading}
			<div class="chat-loading">⏳ Abriendo conversación…</div>
		{:else if mensajes.length === 0}
			<div class="message assistant">
				<div class="message-bubble">
					<div class="msg-avatar">🤖</div>
					<div class="msg-body">
						<div class="chat-sender-label">ECCSA IA</div>
						<div class="msg-content">
							¡Hola! Soy <b>ECCSA IA</b>, tu asistente virtual de <b>ECCSA Automation</b>.<br /><br />
							Tengo acceso a la base de datos para ayudarte con:<br />
							• 📦 Cotizaciones y partidas de materiales<br />
							• 📋 Reportes de servicio técnico<br />
							• 👥 Clientes, tickets y kilómetros<br /><br />
							También puedo <b>sugerir claves SAT</b> y <b>enviar PDFs por correo</b>.
							¿En qué puedo ayudarte hoy?
						</div>
					</div>
				</div>
				<div class="sugerencias">
					{#each sugerencias as s}
						<button class="chip-sug" on:click={() => enviarMensaje(s.replace(/^\S+\s/, ''))}>{s}</button>
					{/each}
				</div>
			</div>
		{:else}
			{#each mensajes as m (m.Id)}
				{@const esIA = m.Role === 'model' || m.Role === 'assistant'}
				<div class="message" class:user={!esIA} class:assistant={esIA}>
					{#if esIA}
						<div class="msg-avatar">🤖</div>
					{/if}
					<div class="message-bubble">
						{#if esIA}
							<div class="chat-sender-label">ECCSA IA</div>
							<div class="msg-content md">{@html renderMd(m.Contenido)}</div>
						{:else}
							<div class="msg-content">{m.Contenido}</div>
						{/if}
						{#if esIA}
							<button class="btn-wa-share" on:click={() => compartirWhatsApp(m.Contenido)} title="Compartir por WhatsApp">
								📱 WhatsApp
							</button>
						{/if}
						<div class="msg-time">{formatearFecha(m.FechaRegistro)}</div>
					</div>
				</div>
			{/each}
			{#if enviando}
				<div class="message assistant typing">
					<div class="msg-avatar">🤖</div>
					<div class="message-bubble">
						<div class="msg-typing"><span></span><span></span><span></span></div>
					</div>
				</div>
			{/if}
		{/if}
	</div>

	<!-- Caja de entrada -->
	<footer class="chat-input">
		<form on:submit={(e) => { e.preventDefault(); enviarMensaje(); }}>
			<div class="input-wrapper">
				<textarea
					bind:value={nuevoMensaje}
					placeholder="Escribe tu pregunta a ECCSA IA… (Enter envía, Shift+Enter salto de línea)"
					rows={1}
					on:keydown={(e) => {
						if (e.key === 'Enter' && !e.shiftKey) {
							e.preventDefault();
							enviarMensaje();
						}
					}}
					disabled={enviando || !conversacion}
				></textarea>
				<button type="submit" class="btn-send" disabled={!nuevoMensaje.trim() || enviando || !conversacion} title="Enviar">➤</button>
			</div>
		</form>
		<div class="input-hint">ECCSA IA puede cometer errores; verifica los datos importantes.</div>
	</footer>
</div>

<style>
	.chat-page {
		display: flex;
		flex-direction: column;
		/* Autoajuste a la pantalla COMPLETA: la página vive dentro de
		   .shell-below-banner, que ya empuja el contenido var(--banner-h) hacia
		   abajo por el banner fijo. Con height:100vh el total quedaba
		   100vh + banner = más alto que la pantalla (se desbordaba en móvil).
		   Se resta el banner y se usa dvh (viewport dinámico) para que la
		   barra del navegador móvil no inflen la altura. */
		height: calc(100vh - var(--banner-h));
		height: calc(100dvh - var(--banner-h));
		background: var(--color-background);
	}

	/* Header */
	.chat-header {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.7rem 0.9rem;
		background: var(--color-surface);
		border-bottom: 1px solid var(--color-border);
		flex-shrink: 0;
	}
	.btn-icon {
		background: transparent;
		border: none;
		color: var(--color-text);
		font-size: 1.05rem;
		cursor: pointer;
		padding: 0.35rem 0.5rem;
		border-radius: 8px;
		transition: background 0.1s;
	}
	.btn-icon:hover { background: rgba(255, 255, 255, 0.06); }
	.chat-title { display: flex; align-items: center; gap: 0.55rem; flex: 1; min-width: 0; }
	.chat-avatar {
		width: 36px; height: 36px; border-radius: 50%;
		background: rgba(255, 107, 0, 0.15);
		display: flex; align-items: center; justify-content: center;
		font-size: 1.1rem; flex-shrink: 0;
	}
	.wobnimo-avatar {
		width: 120px; height: 120px;
		background: rgba(255, 107, 0, 0.1);
		border: 2px solid rgba(255, 107, 0, 0.3);
		border-radius: 12px;
		overflow: visible;
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		position: relative;
	}
	.wobnimo-avatar wobnimo-mascot {
		width: 100%;
		height: 100%;
		display: block;
	}
	.chat-names { display: flex; flex-direction: column; min-width: 0; }
	.chat-names strong { font-size: 0.95rem; line-height: 1.2; }
	.chat-status { font-size: 0.68rem; color: var(--color-text-muted); }

	.chat-error {
		padding: 0.5rem 1rem;
		background: rgba(239, 68, 68, 0.12);
		color: #EF4444;
		font-size: 0.8rem;
		text-align: center;
		flex-shrink: 0;
	}

	/* Mensajes */
	.chat-messages {
		flex: 1;
		overflow-y: auto;
		padding: 1.1rem 1rem 0.5rem;
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
	}
	.chat-loading { text-align: center; color: var(--color-text-muted); padding: 3rem 1rem; }

	.message { display: flex; width: 100%; animation: fadeIn 0.18s ease; gap: 0.5rem; }
	.message.user { justify-content: flex-end; }
	.message.assistant { justify-content: flex-start; }
	@keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

	.msg-avatar {
		width: 30px; height: 30px; border-radius: 50%;
		background: rgba(255, 107, 0, 0.15);
		display: flex; align-items: center; justify-content: center;
		font-size: 0.95rem; flex-shrink: 0; margin-top: 0.2rem;
	}

	.message-bubble {
		max-width: min(78%, 720px);
		padding: 0.7rem 0.95rem;
		border-radius: 16px;
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}
	.message.user .message-bubble {
		background: var(--color-primary);
		color: #fff;
		border-bottom-right-radius: 4px;
	}
	.message.assistant .message-bubble {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		color: var(--color-text);
		border-bottom-left-radius: 4px;
	}
	.message.typing .message-bubble { padding: 0.8rem 1rem; }

	.chat-sender-label { font-size: 0.7rem; color: #94A3B8; font-weight: 700; letter-spacing: 0.02em; }
	.msg-content { line-height: 1.55; white-space: pre-wrap; word-wrap: break-word; }
	/* Respuestas de la IA en Markdown (tablas, listas, negritas) */
	.msg-content.md { white-space: normal; }
	.msg-content.md :global(table) {
		border-collapse: collapse;
		margin: 0.5rem 0;
		font-size: 0.82rem;
		width: 100%;
		display: block;
		overflow-x: auto;
	}
	.msg-content.md :global(th),
	.msg-content.md :global(td) {
		border: 1px solid var(--color-border);
		padding: 0.3rem 0.55rem;
		text-align: left;
	}
	.msg-content.md :global(th) { background: rgba(255, 255, 255, 0.05); }
	.msg-content.md :global(ul),
	.msg-content.md :global(ol) { margin: 0.4rem 0; padding-left: 1.2rem; }
	.msg-content.md :global(p) { margin: 0.35rem 0; }
	.msg-content.md :global(code) {
		background: rgba(255, 255, 255, 0.08);
		padding: 0.1rem 0.3rem;
		border-radius: 4px;
		font-size: 0.85em;
	}
	.msg-content.md :global(pre) {
		background: rgba(0, 0, 0, 0.35);
		padding: 0.6rem 0.75rem;
		border-radius: 8px;
		overflow-x: auto;
	}
	.msg-content.md :global(pre code) { background: transparent; padding: 0; }

	.msg-time { font-size: 0.62rem; opacity: 0.55; text-align: right; margin-top: 0.25rem; }
	.btn-wa-share { margin-top: 0.4rem; padding: 0.3rem 0.7rem; font-size: 0.7rem; border-radius: 8px; border: 1px solid rgba(37,211,102,0.3); background: rgba(37,211,102,0.1); color: #25D366; cursor: pointer; font-family: inherit; font-weight: 600; transition: all 0.15s; display: inline-block; }
	.btn-wa-share:hover { background: rgba(37,211,102,0.2); }
	.message.user .msg-time { color: rgba(255, 255, 255, 0.8); }

	.msg-typing { display: flex; gap: 4px; padding: 0.2rem 0.1rem; }
	.msg-typing span {
		width: 7px; height: 7px; background: var(--color-text-muted); border-radius: 50%;
		animation: typing 1.4s infinite ease-in-out;
	}
	.msg-typing span:nth-child(2) { animation-delay: 0.2s; }
	.msg-typing span:nth-child(3) { animation-delay: 0.4s; }
	@keyframes typing { 0%, 60%, 100% { transform: translateY(0); } 30% { transform: translateY(-5px); } }

	/* Sugerencias iniciales */
	.sugerencias { display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 0.6rem; max-width: min(78%, 720px); }
	.chip-sug {
		background: transparent;
		border: 1px solid var(--color-border);
		color: var(--color-text);
		border-radius: 999px;
		padding: 0.4rem 0.8rem;
		font-size: 0.78rem;
		cursor: pointer;
		font-family: inherit;
		transition: all 0.12s;
	}
	.chip-sug:hover { border-color: var(--color-primary); background: rgba(255, 107, 0, 0.1); }

	/* Entrada */
	.chat-input {
		padding: 0.7rem 1rem 0.55rem;
		background: var(--color-surface);
		border-top: 1px solid var(--color-border);
		flex-shrink: 0;
	}
	.input-wrapper { display: flex; gap: 0.5rem; align-items: flex-end; }
	.input-wrapper textarea {
		flex: 1;
		min-height: 46px;
		max-height: 160px;
		padding: 0.75rem 1rem;
		border: 1px solid var(--color-border);
		border-radius: 23px;
		background: var(--color-background);
		color: var(--color-text);
		font-family: inherit;
		font-size: 0.95rem;
		line-height: 1.45;
		resize: none;
		transition: border-color 0.15s;
	}
	.input-wrapper textarea:focus { outline: none; border-color: var(--color-primary); }
	.input-wrapper textarea::placeholder { color: var(--color-text-muted); }
	.btn-send {
		width: 46px; height: 46px;
		border-radius: 50%;
		background: var(--color-primary);
		color: #fff;
		border: none;
		cursor: pointer;
		display: flex; align-items: center; justify-content: center;
		font-size: 1.15rem;
		transition: transform 0.1s, background 0.15s;
		flex-shrink: 0;
	}
	.btn-send:hover:not(:disabled) { background: var(--color-primary-light); transform: scale(1.05); }
	.btn-send:disabled { opacity: 0.4; cursor: not-allowed; }
	.input-hint { text-align: center; font-size: 0.63rem; color: var(--color-text-muted); margin-top: 0.4rem; }

	/* Móvil */
	@media (max-width: 640px) {
		.message-bubble { max-width: 86%; }
		.sugerencias { max-width: 100%; }
	}
</style>
