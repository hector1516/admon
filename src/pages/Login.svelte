<script>
	import { onMount } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import {
		passkeySupported,
		hasPasskeyFlag,
		loginWithPasskey,
		registerPasskey,
		randomDeviceName
	} from '$lib/passkey.js';
import AuroraBackground from '$lib/components/effects/AuroraBackground.svelte';
import TextGenerate from '$lib/components/effects/TextGenerate.svelte';

	let email = $state('');
	let password = $state('');
	let error = $state('');
	let loading = $state(false);
	let privateMode = $state(false);
	// passkey-first (estilo Field): 'auto' intenta biometría al abrir;
	// 'password' muestra el form; 'suggest' ofrece crear la passkey 1a vez.
	let mode = $state('password');
	let pkSupported = $state(false);
	let suggestLoading = $state(false);
	let suggestName = $state('');

	// Detectar navegación privada: localStorage no persiste ahí
	try {
		localStorage.setItem('__t', '1');
		if (localStorage.getItem('__t') !== '1') privateMode = true;
		localStorage.removeItem('__t');
	} catch {
		privateMode = true;
	}

	onMount(async () => {
		pkSupported = passkeySupported();
		if (pkSupported && hasPasskeyFlag() && !privateMode) {
			mode = 'auto';
			try {
				await loginWithPasskey();
				navigate('/dashboard', { replace: true });
				return;
			} catch {
				// Cancelado o fallo: caer al login normal
				mode = 'password';
			}
		}
	});

	function afterPasswordLogin() {
		// Sin passkey en este equipo: sugerir crearla (label = Nickname si existe)
		if (pkSupported && !hasPasskeyFlag() && !privateMode) {
			let nick = '';
			try {
				const u = JSON.parse(localStorage.getItem('admon_user') || 'null');
				nick = (u?.nickname || '').trim();
			} catch {
				nick = '';
			}
			suggestName = nick || randomDeviceName();
			mode = 'suggest';
		} else {
			navigate('/dashboard', { replace: true });
		}
	}

	async function createPasskey() {
		suggestLoading = true;
		error = '';
		try {
			await registerPasskey(suggestName || randomDeviceName());
			navigate('/dashboard', { replace: true });
		} catch (e) {
			error = e.message || 'No se pudo crear la passkey.';
		} finally {
			suggestLoading = false;
		}
	}

	async function usePasskey() {
		loading = true;
		error = '';
		try {
			await loginWithPasskey();
			navigate('/dashboard', { replace: true });
		} catch (e) {
			error = e.message || 'Passkey cancelada o no válida. Usa tu contraseña.';
		} finally {
			loading = false;
		}
	}

	async function login() {
		if (!email || !password) {
			error = 'Por favor, complete todos los campos.';
			return;
		}
		loading = true;
		error = '';
		try {
			await auth.login(email, password);
			afterPasswordLogin();
		} catch (e) {
			error = e.message || 'Usuario o contraseña incorrectos.';
		} finally {
			loading = false;
		}
	}

	function limpiar() {
		email = '';
		password = '';
		error = '';
	}
</script>

<AuroraBackground class="login-page">
	<div class="login-page-inner">
	<div class="login-card">
		<img class="logo-img" src="/admon_logo.png" alt="Admon ECCSA" />
		<h1><TextGenerate text="ADMON" /></h1>
		<p class="subtitle">ECCSA AUTOMATION</p>

		{#if privateMode}
			<div class="error">⚠️ Estás en navegación privada: la sesión NO se guardará al cerrar el navegador. Abre en una pestaña normal para mantener la sesión.</div>
		{/if}

		{#if mode === 'auto'}
			<p class="auto-wait">🔐 Esperando tu huella / Face ID...</p>
			<button type="button" class="btn btn-secondary btn-block" on:click={() => { mode = 'password'; }}>
				Usar contraseña
			</button>
		{:else if mode === 'suggest'}
			<div class="suggest">
				<div style="font-size:2rem">🔐</div>
				<p><strong>Entra más rápido la próxima vez.</strong><br />Crea tu passkey y usa tu huella o Face ID en este equipo.<br />Se llamará: <strong>“{suggestName}”</strong></p>
				{#if error}
					<div class="error">{error}</div>
				{/if}
				<button type="button" class="btn btn-primary btn-block" on:click={createPasskey} disabled={suggestLoading}>
					{suggestLoading ? 'Creando...' : '🔐 Crear mi passkey'}
				</button>
				<button type="button" class="btn btn-secondary btn-block" style="margin-top:0.5rem" on:click={() => navigate('/dashboard', { replace: true })}>
					Ahora no
				</button>
			</div>
		{:else}
			{#if pkSupported && !privateMode}
				<button type="button" class="btn btn-primary btn-block" style="margin-bottom:1rem" on:click={usePasskey} disabled={loading}>
					🔐 Entrar con passkey
				</button>
				<p class="divider">o con contraseña</p>
			{/if}

			<form on:submit={(e) => { e.preventDefault(); login(); }}>
				<div class="field">
					<label for="email">Usuario o Correo:</label>
					<input
						id="email"
						type="email"
						class="input"
						placeholder="usuario@ecc-ssa.com.mx o usuario@ecc-sa.com.mx"
						autocomplete="username"
						bind:value={email}
					/>
				</div>

				<div class="field">
					<label for="password">Contraseña:</label>
					<input
						id="password"
						type="password"
						class="input"
						placeholder="Ingrese su contraseña"
						autocomplete="current-password"
						bind:value={password}
					/>
				</div>

				{#if error}
					<div class="error" style="margin-top:1rem;">
						{error}
					</div>
				{/if}

				<div class="field" style="margin-top:1rem;">
					<button type="submit" class="btn btn-primary btn-block" disabled={loading}>
						{loading ? 'Verificando…' : '🔑 Ingresar'}
					</button>
				</div>
				<button type="button" class="btn btn-secondary btn-block" style="margin-top:0.5rem" on:click={limpiar}>
					⬅️ Limpiar
				</button>
			</form>
		{/if}
	</div>
</div>
</AuroraBackground>

<style>
	.login-page {
		min-height: 100dvh;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1.5rem;
		background: transparent;
	}
	.login-card {
		width: 100%;
		max-width: 360px;
		text-align: center;
	}
	.logo-img {
		width: 120px;
		height: 120px;
		object-fit: cover;
		border-radius: 24px;
		margin-bottom: 0.5rem;
	}
	h1 {
		font-size: 1.5rem;
		font-weight: 700;
		margin: 0 0 0.15rem;
		letter-spacing: 1px;
	}
	.subtitle {
		color: var(--color-text-muted);
		margin: 0 0 2rem;
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 2px;
	}
	.field {
		text-align: left;
		margin-bottom: 1rem;
	}
	.auto-wait {
		color: var(--color-text-muted);
		padding: 1.5rem 0;
	}
	.suggest {
		background: rgba(59, 130, 246, 0.08);
		border: 1px solid rgba(59, 130, 246, 0.3);
		border-radius: 12px;
		padding: 1.25rem 1rem;
	}
	.suggest p { font-size: 0.9rem; margin: 0.5rem 0 1rem; }
	.divider {
		color: var(--color-text-muted);
		font-size: 0.8rem;
		margin: 0 0 1rem;
	}
	.error {
		background: rgba(239, 68, 68, 0.1);
		color: #EF4444;
		padding: 0.75rem;
		border-radius: 8px;
		font-size: 0.85rem;
		margin-bottom: 1rem;
		text-align: left;
	}
</style>
