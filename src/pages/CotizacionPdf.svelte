<script>
	import { Download, Upload , ArrowLeft } from 'lucide-svelte';

	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { folioFmt } from '$lib/cotizaciones.js';

	// Vista previa del PDF como Field (iframe full-screen + Compartir/Descargar).
	// El PDF se pide con ?token= en la URL (el iframe no puede mandar headers).

	let { clave } = $props();

	let folio = $state(null);
	let pdfUrl = $state('');
	let pdfBlob = $state(null);
	let pdfOk = $state(false);
	let loading = $state(true);
	let error = $state('');
	let msg = $state('');
	let sharing = $state(false);

	function tieneAcceso() {
		try {
			const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
			return !!(u && u.acceso_cotizaciones);
		} catch {
			return false;
		}
	}

	function fileName() {
		return `Cotizacion_${folioFmt(folio)}.pdf`;
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
			error = 'El PDF solo está disponible después de sincronizar la cotización.';
			loading = false;
			return;
		}
		folio = parseInt(clave, 10);
		const token = localStorage.getItem('admon_token') || '';
		pdfUrl = `/api/cotizaciones/${folio}/pdf?token=${encodeURIComponent(token)}&t=${Date.now()}`;
		// Pre-fetch del blob para que share() no necesite await fetch()
		// (Safari invalida el gesture token si hay await antes de share)
		try {
			const res = await fetch(pdfUrl, { headers: auth.authHeader() });
			if (res.ok) {
				pdfBlob = await res.blob();
				pdfOk = true;
			} else {
				const d = await res.json().catch(() => ({}));
				error = d.detail || 'No se pudo generar el PDF (¿sin partidas?).';
			}
		} catch {
			error = 'No se pudo obtener el PDF. Revisa tu conexión.';
		}
		loading = false;
	});

	async function ensureBlob() {
		if (pdfBlob) return true;
		try {
			const res = await fetch(pdfUrl, { headers: auth.authHeader() });
			if (!res.ok) return false;
			pdfBlob = await res.blob();
			pdfOk = true;
			return true;
		} catch {
			return false;
		}
	}

	function downloadPdfNative() {
		if (!pdfBlob) {
			msg = '⚠️ PDF no disponible todavía. Espera un momento…';
			return;
		}
		const url = URL.createObjectURL(pdfBlob);
		const a = document.createElement('a');
		a.href = url;
		a.download = fileName();
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		setTimeout(() => URL.revokeObjectURL(url), 10000);
		msg = '📥 Descargando. En iPhone ábrelo y usa Compartir → WhatsApp.';
	}

	async function sharePdf() {
		msg = '';
		if (!(await ensureBlob())) {
			msg = '⚠️ No se pudo obtener el PDF. Intenta de nuevo.';
			return;
		}
		sharing = true;
		const finish = () => {
			sharing = false;
		};
		const file = new File([pdfBlob], fileName(), { type: 'application/pdf', lastModified: Date.now() });
		window._sharedPdfFile = file; // persistencia anti-GC
		const nav = navigator;
		if (!nav.share || !nav.canShare || !nav.canShare({ files: [file] })) {
			downloadPdfNative();
			finish();
			return;
		}
		try {
			await nav.share({ files: [file] });
			msg = '✅ PDF compartido correctamente.';
		} catch (err) {
			if (err && err.name !== 'AbortError') downloadPdfNative();
		}
		finish();
	}
</script>

<div class="page" style="padding: 0; display: flex; flex-direction: column; height: 100dvh;">
	<div class="header" style="flex-shrink: 0; padding: 0.5rem 1rem 0;">
		<button class="btn btn-sm btn-secondary" on:click={() => navigate(`/cotizaciones/${clave}`)} title="Volver"><ArrowLeft size={16} /></button>
		<h1>📄 {folio ? folioFmt(folio) : 'PDF'}</h1>
	</div>

	{#if loading}
		<p style="color: var(--color-text-muted); text-align: center; padding: 2rem;">Generando PDF…</p>
	{:else if error && !pdfOk}
		<div class="empty" style="margin: 1rem;">{error}</div>
		<div style="text-align: center; padding: 1rem;">
			<button class="btn btn-secondary" on:click={() => navigate(`/cotizaciones/${clave}`)}><ArrowLeft size={16} /> Volver</button>
		</div>
	{:else}
		<div style="display: flex; gap: 0.5rem; padding: 0.5rem 1rem; flex-shrink: 0;">
			<button class="btn btn-secondary btn-block" on:click={sharePdf} disabled={sharing}>
				{sharing ? '…' : '<Upload size={16} /> Compartir'}
			</button>
			<button class="btn btn-primary btn-block" on:click={downloadPdfNative}><Download size={16} /> Descargar</button>
		</div>
		{#if msg}
			<p style="font-size: 0.8rem; color: var(--color-text-muted); text-align: center; margin: 0 1rem 0.4rem;">{msg}</p>
		{/if}
		<iframe src={pdfUrl} title="PDF" style="flex: 1; border: none; width: 100%;"></iframe>
	{/if}
</div>
