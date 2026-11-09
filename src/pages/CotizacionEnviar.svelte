<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
import { Send } from 'lucide-svelte';
	import { auth } from '$lib/stores/auth.js';
	import { header, partidas } from '$lib/cotizacionesApi.js';
	import { folioFmt } from '$lib/cotizaciones.js';

	// Enviar cotización por correo como el HUB (PDF adjunto + copia al remitente).

	let { clave } = $props();

	let folio = $state(null);
	let toEmail = $state('');
	let subject = $state('');
	let body = $state('');
	let senderEmail = $state('');
	let loading = $state(true);
	let error = $state('');
	let msg = $state('');
	let busy = $state(false);

	function tieneAcceso() {
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && u.acceso_cotizaciones);
		} catch {
			return false;
		}
	}

	function myInfo() {
		try {
			return JSON.parse(localStorage.getItem('admon_user') || '{}');
		} catch {
			return {};
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
		if (String(clave).startsWith('local-')) {
			error = 'Primero sincroniza la cotización para enviarla por correo.';
			loading = false;
			return;
		}
		folio = parseInt(clave, 10);
		try {
			const h = await header(folio);
			const items = await partidas(folio);
			const me = myInfo();
			senderEmail = me.email || '';
			subject = `Envio cotizacion con Folio: ${folioFmt(folio)}`;
			let líneas = items.length
				? 'Material solicitado:\n' + items.map((p) => `- Cantidad: ${p.cantidad} | Descripción: ${p.descripcion}`).join('\n')
				: 'No hay partidas de materiales en esta cotización.';
			body =
				`Buen día,\n\nAdjunto a este correo enviamos la cotización solicitada sobre el siguiente material:\n\n` +
				`${líneas}\n\nSaludos cordiales,\n${me.nombre || ''}\n${senderEmail}`;
		} catch (e) {
			error = e.message === 'Sesión expirada' ? e.message : `No se pudo cargar (${e.message || 'sin conexión'}).`;
		} finally {
			loading = false;
		}
	});

	async function onEnviar() {
		error = '';
		msg = '';
		if (!toEmail.trim() || !toEmail.includes('@')) {
			error = 'Escribe el correo del destinatario.';
			return;
		}
		busy = true;
		try {
			const res = await fetch(`/api/cotizaciones/${folio}/enviar`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json', ...auth.authHeader() },
				body: JSON.stringify({ to_email: toEmail.trim(), subject, body })
			});
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'No se pudo enviar.');
			msg = '🎉 ¡Correo enviado exitosamente!';
		} catch (e) {
			error = e.message || 'No se pudo enviar.';
		} finally {
			busy = false;
		}
	}
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" on:click={() => navigate(`/cotizaciones/${clave}`)} title="Volver">⬅️</button>
		<h1>📧 Enviar {folio ? folioFmt(folio) : ''}</h1>
	</div>

	{#if loading}
		<div class="empty">Cargando…</div>
	{:else if error && !subject}
		<div class="card"><p style="color: var(--color-danger); margin: 0;">{error}</p></div>
	{:else}
		<div class="card">
			<div class="field">
				<label for="ev-to">Enviar a (correo del destinatario):</label>
				<input id="ev-to" type="email" class="input" placeholder="ejemplo@cliente.com" bind:value={toEmail} />
			</div>
			<div class="field">
				<label for="ev-subject">Asunto:</label>
				<input id="ev-subject" class="input" bind:value={subject} />
			</div>
			<div class="field">
				<label for="ev-body">Cuerpo del correo:</label>
				<textarea id="ev-body" class="input" rows="10" bind:value={body}></textarea>
			</div>
			<p class="hint">ℹ️ Se enviará copia automática (CC) a tu correo: {senderEmail || '—'}</p>

			{#if error}
				<div class="msg err">{error}</div>
			{/if}
			{#if msg}
				<div class="msg ok">{msg}</div>
			{/if}

			<button class="btn btn-primary btn-block" on:click={onEnviar} disabled={busy || !toEmail.trim()}>
				{busy ? 'Enviando…' : '<Send size={16} /> Enviar correo'}
			</button>
		</div>
	{/if}
</div>

<style>
	.msg { padding: 0.6rem 0.75rem; border-radius: 8px; font-size: 0.85rem; margin-bottom: 0.75rem; }
	.msg.err { background: rgba(239,68,68,0.1); color: #EF4444; }
	.msg.ok { background: rgba(34,197,94,0.1); color: #22C55E; }
	.hint { font-size: 0.8rem; color: var(--color-text-muted); }
	.card { margin-bottom: 0.75rem; }
</style>
