<!--
	⚙️ Administración — página contenedora de PESTAÑAS.

	Antes esta pantalla era sólo la lista de usuarios ("👥 Administrador de
	usuarios"). Con la pestaña 🕘 Asistencia el módulo grew: la asistencia del
	día es lo que se mira todos los días, y lo de usuarios es lo que se toca de
	vez en cuando.

	Asistencia va PRIMERA porque es la que se revisa a diario; Administración
	(usuarios) es la segunda, que es la info que ya existía.

	Cada pestaña es una ruta real (/admin, /admin/usuarios) para que el enlace se
	pueda compartir, el botón ⬅️ del navegador retroceda y los deep-links abran
	directo en la pestaña pedida. La ruta vieja /usuarios sigue existiendo y
	abre esta misma página con la pestaña de Administración activa, porque el
	botón "Volver" de la ficha de cada usuario y los enlaces ya publicados
	apuntan ahí.
-->
<script>
	import { ArrowLeft } from 'lucide-svelte';

	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import Asistencia from './AsistenciaAdmin.svelte';
	import Usuarios from './Usuarios.svelte';

	const TABS = [
		{ id: 'asistencia', icon: '🕘', label: 'Asistencia', path: '/admin' },
		{ id: 'usuarios', icon: '👥', label: 'Administración', path: '/admin/usuarios' }
	];

	// initialTab lo pasa App.svelte según la ruta (/admin → asistencia,
	// /admin/usuarios y /usuarios → administración).
	let { initialTab = TABS[0].id } = $props();
	let tab = $state(initialTab);

	/** Mismo permiso que exige el módulo: la lista de usuarios es lo que se
	    protegía hasta ahora, y la asistencia va dentro del mismo módulo. */
	function tieneAcceso() {
		try {
			const raw = localStorage.getItem('admon_user');
			const u = raw ? JSON.parse(raw) : null;
			return !!(u && u.acceso_usuarios);
		} catch {
			return false;
		}
	}

	onMount(() => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
		if (!tieneAcceso()) {
			navigate('/dashboard', { replace: true });
		}
	});
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" onclick={() => navigate('/dashboard')} title="Volver"><ArrowLeft size={16} /></button>
		<h1>⚙️ Administración</h1>
	</div>

	<nav class="tabs" aria-label="Secciones de Administración">
		{#each TABS as t (t.id)}
			<button class="tab" class:active={tab === t.id} onclick={() => navigate(t.path)}>
				<span class="tab-ico">{t.icon}</span>{t.label}
			</button>
		{/each}
	</nav>

	{#if tab === 'asistencia'}
		<Asistencia />
	{:else if tab === 'usuarios'}
		<!-- La lista de usuarios, sin su propio encabezado: el de la pestaña
		     ya dice "⚙️ Administración" y la barra de pestañas dice cuál es. -->
		<Usuarios embebido />
	{/if}
</div>

<style>
	/* Barra de pestañas (misma pinta que la del Dashboard, en Panel.svelte). Va
	   local al componente a propósito: styles/app.css es del shell canónico. */
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