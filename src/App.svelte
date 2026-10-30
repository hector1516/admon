<script>
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { path, navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { online, onlinePing } from '$lib/stores/online.js';
	import SyncHeader from '$lib/components/SyncHeader.svelte';
	import Changelog from '$lib/components/Changelog.svelte';
import BusquedaGlobal from '$lib/components/BusquedaGlobal.svelte';
	import { syncPull, syncPush, pendingCount, syncing, refreshPending } from '$lib/sync.js';
	import { prefetchOffline } from '$lib/offlinePrefetch.js';
	import { APP_VERSION, SHELL_VERSION } from '$lib/shell.js';
	import './responsive.css';
	import Login from './pages/Login.svelte';
	import Dashboard from './pages/Dashboard.svelte';
import Panel from './pages/Panel.svelte';
	import Cotizaciones from './pages/Cotizaciones.svelte';
	import CotizacionDetalle from './pages/CotizacionDetalle.svelte';
	import CotizacionNueva from './pages/CotizacionNueva.svelte';
import CotizacionComparar from './pages/CotizacionComparar.svelte';
	import CotizacionEditar from './pages/CotizacionEditar.svelte';
	import CotizacionNota from './pages/CotizacionNota.svelte';
	import PartidasAdmin from './pages/PartidasAdmin.svelte';
	import CotizacionPdf from './pages/CotizacionPdf.svelte';
	import CotizacionEnviar from './pages/CotizacionEnviar.svelte';
	import CotizacionEstatus from './pages/CotizacionEstatus.svelte';
	import UsuarioDetalle from './pages/UsuarioDetalle.svelte';
	import Admin from './pages/Admin.svelte';
	import Clientes from './pages/Clientes.svelte';
	import ClienteDetalle from './pages/ClienteDetalle.svelte';
	import RegistroReportes from './pages/RegistroReportes.svelte';
	import RegistroReporteDetalle from './pages/RegistroReporteDetalle.svelte';
	import RegistroReportePreview from './pages/RegistroReportePreview.svelte';
	import EccsaIa from './pages/EccsaIa.svelte';
	import Config from './pages/Config.svelte';
	import Legends from './pages/Legends.svelte';
	import TicketsOxxoGas from './pages/TicketsOxxoGas.svelte';
	import Kilometros from './pages/Kilometros.svelte';
	import KilometroVehiculo from './pages/KilometroVehiculo.svelte';
	import TicketOxxoGasDetalle from './pages/TicketOxxoGasDetalle.svelte';

	let ready = $state(false);
	let splashDone = $state(false);
	let splashMsg = $state('');
	let splashProgress = $state(0);

	const splashMessages = [
		'💻 Inicializando matriz de datos cuánticos...',
		'🚀 Calibrando condensadores de flujo...',
		'☕ Convirtiendo café en líneas de código...',
		'🤖 Entrenando a los duendes del servidor...',
		'📡 Alineando satélites geosíncronos de ECCSA...',
		'🔑 Desencriptando algoritmos de acceso...',
		'⚙️ Alineando los engranes del servidor de bases de datos...'
	];

	onMount(async () => {
		// Splash corto con logo Admon
		const msgs = [...splashMessages].sort(() => Math.random() - 0.5).slice(0, 2);
		for (let i = 0; i < msgs.length; i++) {
			splashMsg = msgs[i];
			splashProgress = ((i + 1) / msgs.length) * 100;
			await new Promise((r) => setTimeout(r, 800));
		}
		splashDone = true;

		auth.init();
		if (!auth.isLoggedIn() && window.location.pathname !== '/login') {
			navigate('/login', { replace: true });
		}
		ready = true;
		onlinePing().catch(() => {});
		if (auth.isLoggedIn()) {
			syncPull().then(() => syncPush()).catch(() => {});
		}
	});

	// Prefetch offline: en cuanto hay sesión (login por contraseña/passkey o
	// restauración al cargar) se precargan los últimos 10 registros + detalles
	// de cada módulo a IndexedDB. Throttle interno de 5 min + disparo propio
	// al recuperar la conexión (ver offlinePrefetch.js).
	$effect(() => {
		if ($auth.user) prefetchOffline();
	});

	// ── Notificaciones push ─────────────────────────────────────────────────
	// El service worker, al tocar una notificación, NO abre una ventana nueva:
	// en iOS eso deja la PWA en blanco. Enfoca la pestaña que ya está abierta y
	// le pasa la ruta por postMessage (ver public/sw.js). Si nadie escucha este
	// mensaje, el toque "hace nada": la app se enfoca pero no navega, y parece
	// que el aviso está roto.
	function onMensajeSW(event) {
		const d = event.data || {};
		if (d.type === 'FORCE_RELOAD') {
			window.location.reload();
			return;
		}
		if (d.type === 'ABRIR_RUTA' && d.url) {
			navigate(d.url);
			// Se limpia el badge: si el usuario abrió un aviso, ya lo está viendo.
			navigator.serviceWorker?.controller?.postMessage({ type: 'LIMPIAR_BADGE' });
		}
	}

	onMount(() => {
		navigator.serviceWorker?.addEventListener('message', onMensajeSW);
		return () => navigator.serviceWorker?.removeEventListener('message', onMensajeSW);
	});

	// ── Banner común ECCSA-Shell ─────────────────────────────────────────────
	// El componente es del shell y no sabe nada de Admon: el estado, el usuario
	// y el clic le llegan por props, y `fetcher` le aporta la cabecera Bearer
	// que Admon usa (antes el fetch peludo daba 401 y el 🏢/🏠 nunca se
	// resolvía). Mismo cableado que en Field. Ver ECCSA-Shell/docs/CONTRATO.md.
	function shellEstado() {
		if (!get(online)) return 'offline';
		if (get(syncing)) return 'syncing';
		// 'pending' vs 'idle' lo decide el componente a partir de `pendientes`.
		return 'idle';
	}

	async function shellSync() {
		if (!get(online) || get(syncing)) return;
		await onlinePing();
		await syncPush();
		refreshPending();
	}

	function shellFetch(url) {
		const token = auth.getToken();
		return fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
	}

</script>

{#if !splashDone}
	<div class="splash">
		<img class="splash-logo-img" src="/admon_logo.png" alt="Admon ECCSA" />
		<div class="splash-title">Admon</div>
		<div class="splash-msg">{splashMsg}</div>
		<div class="splash-bar">
			<div class="splash-bar-fill" style="width:{splashProgress}%"></div>
		</div>
	</div>
{:else if ready}
	{#if $auth.user}
		<SyncHeader
			estado={shellEstado()}
			pendientes={$pendingCount}
			usuario={$auth.user.nombre}
			appVersion={APP_VERSION}
			shellVersion={SHELL_VERSION}
			fetcher={shellFetch}
			onsync={shellSync}
		/>

		<!-- Popup de novedades (del shell). Va UNA vez acá, en el App, para
		     que salte aunque se entre por cualquier ruta. El texto de los
		     cambios está en public/changelog.json, así se edita sin recompilar. -->
		<Changelog appId="admon" appName="Admon" version={APP_VERSION}
		           url="/changelog.json" />
	{/if}

	<!-- shell-below-banner: el padding para no quedar bajo el banner fijo lo
	     pone el shell (era un 3.8rem mágico repetido en cada app). -->
	<div class={$auth.user ? 'shell-below-banner' : ''}>
		{#if $path === '/login'}
			<Login />
		{:else if $path === '/dashboard' || $path === '/'}
			<Dashboard />
			{:else if $path === '/cotizaciones_materiales'}
				<Cotizaciones />
			{:else if $path === '/cotizaciones/nueva'}
				<CotizacionNueva />
			{:else if $path.startsWith('/cotizaciones/') && $path.endsWith('/partidas')}
				<PartidasAdmin clave={$path.split('/')[2]} />
			{:else if $path.startsWith('/cotizaciones/') && $path.endsWith('/editar')}
				<CotizacionEditar clave={$path.split('/')[2]} />
			{:else if $path.startsWith('/cotizaciones/') && $path.endsWith('/nota')}
				<CotizacionNota clave={$path.split('/')[2]} />
			{:else if $path.startsWith('/cotizaciones/') && $path.endsWith('/pdf')}
				<CotizacionPdf clave={$path.split('/')[2]} />
			{:else if $path.startsWith('/cotizaciones/') && $path.endsWith('/enviar')}
				<CotizacionEnviar clave={$path.split('/')[2]} />
			{:else if $path.startsWith('/cotizaciones/') && $path.endsWith('/estatus')}
				<CotizacionEstatus clave={$path.split('/')[2]} />
			{:else if $path === '/cotizaciones/comparar'}
				<CotizacionComparar />
			{:else if $path.startsWith('/cotizaciones/')}
				<CotizacionDetalle clave={$path.split('/')[2]} />
{:else if $path === '/admin'}
			<!-- Módulo Administración: pestañas 🕘 Asistencia + 👥 Administración.
			     /admin abre en Asistencia (la de uso diario). -->
			<Admin />
			{:else if $path === '/admin/usuarios'}
				<Admin initialTab="usuarios" />
			{:else if $path === '/usuarios'}
				<!-- Ruta vieja del módulo de usuarios (la que usan el botón
				     "Volver" de cada ficha y los enlaces ya publicados): ahora abre
				     la pestaña 👥 Administración del módulo. -->
				<Admin initialTab="usuarios" />
			{:else if $path.startsWith('/usuarios/')}
				<UsuarioDetalle id={$path.split('/')[2]} />
			{:else if $path === '/ia'}
				<EccsaIa />
{:else if $path === '/clientes'}
				<Clientes />
			{:else if $path.startsWith('/clientes/')}
				<ClienteDetalle id={$path.split('/')[2]} />
			{:else if $path === '/registro_reportes'}
				<RegistroReportes />
			{:else if $path.startsWith('/registro_reportes/') && $path.endsWith('/preview')}
				<RegistroReportePreview id={$path.split('/')[2]} />
			{:else if $path.startsWith('/registro_reportes/')}
				<RegistroReporteDetalle id={$path.split('/')[2]} />
			{:else if $path === '/config'}
				<Config />
			{:else if $path === '/legends'}
				<Legends />
			{:else if $path === '/kilometros'}
				<Kilometros />
			{:else if $path.startsWith('/kilometros/vehiculo/')}
				<!-- 4 segmentos: ["", "kilometros", "vehiculo", id] → el id va en [3] -->
				<KilometroVehiculo id={$path.split('/')[3]} />
			{:else if $path === '/tickets_oxxogas'}
				<TicketsOxxoGas />
			{:else if $path.startsWith('/tickets_oxxogas/')}
				<TicketOxxoGasDetalle id={$path.split('/')[2]} />
			{:else if $path === '/panel'}
				<!-- Botón "Dashboard" del menú: página de pestañas -->
				<Panel />
			{:else if $path === '/pantalla_tv'}
				<!-- Pestaña "Pantalla de la TV" del Dashboard -->
				<Panel initialTab="pantalla" />
			{:else if $path === '/notas'}
				<!-- Alias: abre el Dashboard con la pestaña Notas activa
				     (bookmarks, prefetch y deep-links) -->
				<Panel initialTab="notas" />
		{:else}
			<Dashboard />
		{/if}
		<div class="version-badge">Admon v{APP_VERSION}</div>
		<BusquedaGlobal />
	</div>
{:else}
	<div class="splash">
		<img class="splash-logo-img" src="/admon_logo.png" alt="Admon ECCSA" />
		<div class="splash-title">Admon</div>
	</div>
{/if}
