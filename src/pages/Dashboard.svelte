<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import ActionsBar from '$lib/components/ActionsBar.svelte';

	// Menú de módulos estilo home de Field: icon/title/desc/path/perm.
	// Solo módulos funcionales; cada tarjeta requiere su permiso activo.
	// ECCSA IA va PRIMERO y sin permiso: en el HUB Jarvis está disponible para
	// todos los usuarios logueados (el backend no exige ningún Acceso).
	const modules = [
		{ icon: '🤖', title: 'ECCSA IA', desc: 'Asistente inteligente', path: '/ia' },
		// Botón "Dashboard": abre la página de pestañas (Notas y las que se
		// vayan agregando) — ver src/pages/Panel.svelte.
		{ icon: '📊', title: 'Dashboard', desc: 'Pantalla de la TV y más', path: '/panel' },
		{ icon: '📦', title: 'Cotizaciones Materiales', desc: 'Crear y gestionar', path: '/cotizaciones_materiales', perm: 'acceso_cotizaciones' },
		{ icon: '📋', title: 'Registro de Reportes', desc: 'Visualización global admin', path: '/registro_reportes', perm: 'acceso_registro_reportes' },
		{ icon: '🛠️', title: 'Administración', desc: 'Asistencia y usuarios', path: '/admin', perm: 'acceso_usuarios' },
		{ icon: '📇', title: 'Clientes', desc: 'Catálogo general', path: '/clientes', perm: 'acceso_cotizaciones' },
		{ icon: '⛽', title: 'Tickets de OxxoGas', desc: 'Tickets y facturas', path: '/tickets_oxxogas', perm: 'acceso_vales_oxxogas' },
		{ icon: '🛣️', title: 'Kilómetros', desc: 'Consumo semanal y captura', path: '/kilometros', perm: 'acceso_registro_kilometros' },
		// Legends: visible para todos los usuarios logueados (en Field la gatea el
		// permiso de kilómetros; aquí los datos son de la empresa y el ranking lo
		// calcula el worker de workersadmon para las dos apps).
		{ icon: '🏆', title: 'ECCSA Legends', desc: 'Ranking y puntos', path: '/legends' }
	];

	let user = $state(null);

	function visible(mod) {
		return !mod.perm || (user && user[mod.perm]);
	}

	function go(mod) {
		navigate(mod.path);
	}

	function handleLogout() {
		auth.logout();
		navigate('/login', { replace: true });
	}

	onMount(async () => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
		try {
			const raw = localStorage.getItem('admon_user');
			user = raw ? JSON.parse(raw) : null;
		} catch {
			user = null;
		}
	});
</script>

<div class="page">
	<div class="header">
		<div class="brand-col">
			<h1 class="brand"><img class="brand-logo" src="/admon_logo.png" alt="Admon" /> Admon</h1>
		</div>
		<!-- Barra de acciones del shell (⚙️ config · 🚪 salir). Admon no pasa
		     onnotif/ononline: no tiene cola de avisos ni usuarios en línea.
		     El componente los oculta si el manejador no está. -->
		<ActionsBar
			onconfig={() => navigate('/config')}
			onlogout={handleLogout}
		/>
	</div>

	<div class="module-grid">
		{#each modules as mod}
			{#if visible(mod)}
				<button class="module-card" on:click={() => go(mod)}>
					<span class="module-icon">{mod.icon}</span>
					<span class="module-title">{mod.title}</span>
					<span class="module-desc">{mod.desc}</span>
				</button>
			{/if}
		{/each}
	</div>
</div>

<style>
	.brand-col { display: flex; flex-direction: column; gap: 0; }
	.brand { display: flex; align-items: center; gap: 0.5rem; margin: 0; font-size: 1.2rem; }
	.brand-logo { width: 34px; height: 34px; object-fit: cover; border-radius: 8px; }
	/* Menú de módulos: la grilla y las tarjetas las pinta el shell
	   (.module-grid con las columnas por resolución y .module-card
	   rectangular de alto por contenido). El fix de estirar las tarjetas ya
	   no vive acá como un bloque propio: con el shell queda en un solo lado,
	   y esta página no lo sobrescribe. */


</style>
