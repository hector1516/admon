<script>
	import { ArrowLeft } from 'lucide-svelte';

	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import Notas from './Notas.svelte';
	import PantallaTv from './PantallaTv.svelte';

	// 📊 Dashboard (el botón del menú): página contenedora de PESTAÑAS con
	// las funciones nuevas de la app. Hoy vive aquí la pantalla de la TV
	// (notas que se capturan acá y salen solas en el Dashboard de la
	// oficina) y las que se vayan agregando entrarán como más pestañas.
	// La segunda pestaña, "📺 Pantalla de la TV", trae el control remoto del
	// kiosco y la subida de la imagen de portada.
	//
	// Para AGREGAR una pestaña nueva:
	//   1) agrega su entrada en TABS (id · icono · etiqueta · ruta),
	//   2) registra la ruta en App.svelte → <Panel initialTab="su_id" />,
	//   3) agrega su bloque {#if tab === 'su_id'} en el markup de abajo.
	// Cada pestaña es una ruta real (/panel, /notas): el enlace se puede
	// compartir, el botón ⬅️ del navegador retrocede y el deep-link abre
	// directo en esa pestaña.
	const TABS = [
		{ id: 'notas', icon: '📝', label: 'Notas', path: '/notas' },
		{ id: 'pantalla', icon: '📺', label: 'Pantalla de la TV', path: '/pantalla_tv' }
	];

	// initialTab lo pasa App.svelte según la ruta (/panel → primera pestaña,
	// /notas → notas).
	let { initialTab = TABS[0].id } = $props();
	let tab = $state(initialTab);

	onMount(() => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
	});
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" onclick={() => navigate('/dashboard')} title="Volver"><ArrowLeft size={16} /></button>
		<h1>📊 Dashboard</h1>
	</div>

	<nav class="tabs" aria-label="Secciones del Dashboard">
		{#each TABS as t (t.id)}
			<button class="tab" class:active={tab === t.id} onclick={() => navigate(t.path)}>
				<span class="tab-ico">{t.icon}</span>{t.label}
			</button>
		{/each}
	</nav>

	{#if tab === 'notas'}
		<!-- Pestaña Notas: el módulo completo (HUB_DashboardNotas, la misma
		     tabla que lee la pantalla 📌 del Dashboard de la oficina) -->
		<Notas embebido />
	{:else if tab === 'pantalla'}
		<!-- Pestaña Pantalla de la TV: control remoto del kiosco + imagen de
		     portada (HUB_PantallaImagenes) -->
		<PantallaTv />
	{/if}
</div>

<style>
	/* Barra de pestañas del Dashboard */
	.tabs {
		display: flex;
		gap: 0.25rem;
		margin: 0.15rem 0 1rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.08);
		overflow-x: auto;
		-webkit-overflow-scrolling: touch;
	}
	.tab {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.55rem 0.9rem;
		font-size: 0.88rem;
		font-weight: 600;
		font-family: inherit;
		color: var(--color-text-muted);
		background: transparent;
		border: none;
		border-bottom: 3px solid transparent;
		border-radius: 8px 8px 0 0;
		cursor: pointer;
		white-space: nowrap;
		transition: color 0.12s, background 0.12s;
	}
	.tab:hover { color: var(--color-text); background: rgba(255, 255, 255, 0.04); }
	.tab.active {
		color: var(--color-primary-light);
		border-bottom-color: var(--color-primary);
		background: rgba(255, 107, 0, 0.08);
	}
	.tab-ico { font-size: 1rem; line-height: 1; }
</style>
