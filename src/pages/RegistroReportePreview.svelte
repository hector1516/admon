<script>
	import { Download, RefreshCw, Upload } from 'lucide-svelte';

	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { api } from '$lib/api.js';

	// Página completa de previsualización PDF (pantalla completa, sin header extra)
	let { id } = $props();
	const idReporte = Number(id);

	let loading = $state(true);
	let error = $state('');
	let pdfBlob = $state(null);
	let reporte = $state({});

	function tieneAcceso() {
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && u.acceso_registro_reportes);
		} catch {
			return false;
		}
	}

	function apiHeaders() {
		return { 'Content-Type': 'application/json', ...auth.authHeader() };
	}

	async function cargar() {
		loading = true;
		error = '';
		// Detalle con caché offline (red primero, fallback a caché local)
		try {
			reporte = await api.get(`/reportes/${idReporte}`);
		} catch (e) {
			error = e.message === 'Sesión expirada' ? e.message : `Error: ${e.message}`;
			loading = false;
			return;
		}
		// PDF: binario que requiere red (no se cachea en IndexedDB)
		try {
			const pdfRes = await fetch(`/api/reportes/${idReporte}/pdf?token=${encodeURIComponent(auth.getToken())}`, { headers: auth.authHeader() });
			if (pdfRes.ok) {
				pdfBlob = await pdfRes.blob();
			} else {
				const d = await pdfRes.json().catch(() => ({}));
				error = d.detail || 'No se pudo generar el PDF.';
			}
		} catch {
			error = '📴 Sin conexión: el PDF necesita red (los datos del reporte sí están disponibles offline).';
		}
		loading = false;
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

	async function descargar() {
		if (!pdfBlob) return;
		const url = URL.createObjectURL(pdfBlob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `Reporte_${reporte.Folio}.pdf`;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	}

	async function compartir() {
		if (!pdfBlob) return;
		const file = new File([pdfBlob], `Reporte_${reporte.Folio}.pdf`, { type: 'application/pdf' });
		if (navigator.canShare && navigator.canShare({ files: [file] })) {
			try {
				await navigator.share({ files: [file], title: `Reporte ${reporte.Folio}` });
			} catch {}
		} else {
			await descargar();
		}
	}

	function volver() {
		navigate(`/registro_reportes/${idReporte}`, { replace: true });
	}
</script>

<div class="preview-page">
	<header class="preview-header">
		<button class="btn btn-ghost" on:click={volver} title="Volver">⬅️</button>
		<h1>👁️ Previsualizar: {reporte.Folio}</h1>
		<div style="display: flex; gap: 0.5rem;">
			<button class="btn btn-secondary" on:click={descargar} disabled={!pdfBlob}><Download size={16} /> Descargar</button>
			<button class="btn btn-primary" on:click={compartir} disabled={!pdfBlob}><Upload size={16} /> Compartir</button>
		</div>
	</header>

	{#if loading}
		<div class="preview-loading">Cargando PDF…</div>
	{:else if error}
		<div class="preview-error">
			<p>{error}</p>
			<button class="btn btn-primary" on:click={cargar}><RefreshCw size={16} /> Reintentar</button>
			<button class="btn btn-secondary" on:click={volver}>⬅️ Volver</button>
		</div>
	{:else if pdfBlob}
		<iframe 
			class="preview-iframe"
			src={URL.createObjectURL(pdfBlob)} 
			title="PDF Preview"
		></iframe>
	{/if}
</div>

<style>
	.preview-page {
		display: flex;
		flex-direction: column;
		height: 100vh;
		background: var(--color-background);
	}

	.preview-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.75rem 1rem;
		background: var(--color-surface);
		border-bottom: 1px solid var(--color-border);
		flex-shrink: 0;
	}

	.preview-header h1 {
		margin: 0;
		font-size: 1.1rem;
		flex: 1;
		text-align: center;
	}

	.btn-ghost {
		background: transparent;
		border: none;
		color: var(--color-text-muted);
		cursor: pointer;
		padding: 0.5rem;
		border-radius: 8px;
	}
	.btn-ghost:hover { background: rgba(255,255,255,0.05); }

	.preview-loading,
	.preview-error {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 1rem;
		padding: 2rem;
		text-align: center;
		color: var(--color-text-muted);
	}

	.preview-iframe {
		flex: 1;
		width: 100%;
		border: none;
		background: white;
	}
</style>