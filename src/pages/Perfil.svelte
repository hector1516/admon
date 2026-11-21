<script>
	import { onMount } from 'svelte';
	import { api, isNetworkError } from '$lib/api.js';
	import { auth } from '$lib/stores/auth.js';
	import { navigate } from '$lib/router.js';
	import { APP_VERSION, SHELL_VERSION } from '$lib/shell.js';
	import ActionsBar from '$lib/components/ActionsBar.svelte';

	let { onSalir = null } = $props();

	let perfil = $state(null);
	let cargando = $state(true);
	let error = $state('');
	let editando = $state(false);
	let nombre = $state('');
	let email = $state('');
	let passwordActual = $state('');
	let passwordNueva = $state('');
	let guardando = $state(false);
	let mensaje = $state('');
	let mensajeTipo = $state('success');
	let fotoPreview = $state(null);
	let subiendoFoto = $state(false);

	// Skin selector
	let skins = $state([]);
	let skinActivo = $state('default');
	let cambiandoSkin = $state(false);

	onMount(async () => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
		await cargarPerfil();
		await cargarSkin();
	});

	async function cargarSkin() {
		try {
			const r = await api.get('/skin');
			skins = r.skins || [];
			skinActivo = r.activo || 'default';
			// Aplicar skin al root
			document.documentElement.setAttribute('data-skin', skinActivo);
		} catch (e) {
			// Silencioso
		}
	}

	async function cambiarSkin(skinId) {
		if (skinId === skinActivo) return;
		cambiandoSkin = true;
		try {
			await api.put('/skin', { skin: skinId });
			skinActivo = skinId;
			document.documentElement.setAttribute('data-skin', skinId);
		} catch (e) {
			alert(e.message || 'Error al cambiar skin.');
		} finally {
			cambiandoSkin = false;
		}
	}

	async function cargarPerfil() {
		cargando = true;
		error = '';
		try {
			perfil = await api.get('/perfil');
			nombre = perfil.nombre || '';
			email = perfil.email || '';
			fotoPreview = perfil.foto || null;
		} catch (e) {
			error = e.message || 'Error al cargar perfil.';
		} finally {
			cargando = false;
		}
	}

	async function guardarDatos() {
		if (!nombre.trim() || !email.trim()) {
			mensaje = 'Nombre y email son obligatorios.';
			mensajeTipo = 'danger';
			return;
		}
		guardando = true;
		mensaje = '';
		try {
			await api.put('/perfil', { nombre, email });
			mensaje = 'Datos actualizados correctamente.';
			mensajeTipo = 'success';
			// Actualizar localStorage
			const user = auth.getUser();
			if (user) {
				user.nombre = nombre;
				user.email = email;
				localStorage.setItem('admon_user', JSON.stringify(user));
			}
		} catch (e) {
			mensaje = e.message || 'Error al guardar.';
			mensajeTipo = 'danger';
		} finally {
			guardando = false;
		}
	}

	async function cambiarPassword() {
		if (!passwordActual || !passwordNueva) {
			mensaje = 'Completa ambos campos de contraseña.';
			mensajeTipo = 'danger';
			return;
		}
		if (passwordNueva.length < 6) {
			mensaje = 'La contraseña nueva debe tener al menos 6 caracteres.';
			mensajeTipo = 'danger';
			return;
		}
		guardando = true;
		mensaje = '';
		try {
			await api.put('/perfil/password', { password_actual: passwordActual, password_nueva: passwordNueva });
			mensaje = 'Contraseña cambiada correctamente.';
			mensajeTipo = 'success';
			passwordActual = '';
			passwordNueva = '';
		} catch (e) {
			mensaje = e.message || 'Error al cambiar contraseña.';
			mensajeTipo = 'danger';
		} finally {
			guardando = false;
		}
	}

	async function subirFoto(event) {
		const file = event.target.files?.[0];
		if (!file) return;
		subiendoFoto = true;
		mensaje = '';
		try {
			const formData = new FormData();
			formData.append('foto', file);
			const token = localStorage.getItem('admon_token');
			const res = await fetch('/api/perfil/foto', {
				method: 'PUT',
				headers: token ? { Authorization: `Bearer ${token}` } : {},
				body: formData,
			});
			if (!res.ok) {
				const err = await res.json().catch(() => ({}));
				throw new Error(err.detail || 'Error al subir foto');
			}
			const data = await res.json();
			if (data.foto) {
				fotoPreview = data.foto;
				mensaje = 'Foto actualizada.';
				mensajeTipo = 'success';
			}
		} catch (e) {
			mensaje = e.message || 'Error al subir foto.';
			mensajeTipo = 'danger';
		} finally {
			subiendoFoto = false;
		}
	}

	function cerrarSesion() {
		auth.logout();
		navigate('/login', { replace: true });
	}
</script>

<div class="page">
	<div class="header">
		<div class="brand-col" style="display: flex; align-items: center; gap: 0.5rem;">
			<button class="btn btn-sm btn-secondary" onclick={() => navigate('/dashboard')} title="Volver">
				Volver
			</button>
			<h1 class="brand">Perfil</h1>
		</div>
		<ActionsBar onlogout={cerrarSesion} />
	</div>

	{#if cargando}
		<div class="empty">
			<div class="mb-spinner"></div>
			<p>Cargando perfil...</p>
		</div>
	{:else if error}
		<div class="alert alert-danger">
			<span>{error}</span>
			<button class="btn btn-sm" onclick={cargarPerfil}>Reintentar</button>
		</div>
	{:else if perfil}
		<!-- Foto de perfil -->
		<div class="card perfil-foto-card">
			<div class="foto-container">
				{#if fotoPreview}
					<img src={fotoPreview} alt="Foto de perfil" class="foto-preview" loading="lazy" />
				{:else}
					<div class="foto-placeholder">
						{perfil.nombre?.charAt(0)?.toUpperCase() || '?'}
					</div>
				{/if}
				<label class="btn btn-sm btn-secondary foto-btn" class:disabled={subiendoFoto}>
					{subiendoFoto ? 'Subiendo...' : 'Cambiar foto'}
					<input type="file" accept="image/*" onchange={subirFoto} style="display: none;" disabled={subiendoFoto} />
				</label>
			</div>
			<div class="perfil-info">
				<h2>{perfil.nombre}</h2>
				<p class="perfil-email">{perfil.email}</p>
				{#if perfil.puesto}
					<p class="perfil-puesto">{perfil.puesto}</p>
				{/if}
			</div>
		</div>

		{#if mensaje}
			<div class="alert {mensajeTipo === 'success' ? 'alert-success' : 'alert-danger'}">
				<span>{mensaje}</span>
			</div>
		{/if}

		<!-- Datos personales -->
		<div class="card">
			<h3 class="section-title">Datos personales</h3>
			<div class="field">
				<label for="nombre">Nombre</label>
				<input id="nombre" type="text" class="input" bind:value={nombre} />
			</div>
			<div class="field">
				<label for="email">Email</label>
				<input id="email" type="email" class="input" bind:value={email} />
			</div>
			<button class="btn btn-primary" onclick={guardarDatos} disabled={guardando}>
				{guardando ? 'Guardando...' : 'Guardar datos'}
			</button>
		</div>

		<!-- Cambiar contraseña -->
		<div class="card">
			<h3 class="section-title">Cambiar contraseña</h3>
			<div class="field">
				<label for="pass-actual">Contraseña actual</label>
				<input id="pass-actual" type="password" class="input" bind:value={passwordActual} />
			</div>
			<div class="field">
				<label for="pass-nueva">Contraseña nueva</label>
				<input id="pass-nueva" type="password" class="input" bind:value={passwordNueva} />
			</div>
			<button class="btn btn-primary" onclick={cambiarPassword} disabled={guardando}>
				{guardando ? 'Cambiando...' : 'Cambiar contraseña'}
			</button>
		</div>

		<!-- Permisos (solo lectura) -->
		<div class="card">
			<h3 class="section-title">Permisos</h3>
			<div class="permisos-grid">
				{#each Object.entries(perfil.permisos) as [key, val]}
					<div class="permiso-item {val ? 'permiso-activo' : 'permiso-inactivo'}">
						<span class="permiso-check">{val ? '✓' : '✗'}</span>
						<span class="permiso-nombre">{key.replace(/_/g, ' ')}</span>
					</div>
				{/each}
			</div>
		</div>

		<!-- Apariencia / Skin selector -->
		<div class="card">
			<h3 class="section-title">Apariencia</h3>
			<p style="font-size: var(--font-size-xs); color: var(--color-text-muted); margin: 0 0 0.75rem;">
				Selecciona el diseño de la app. El cambio aplica a todos los usuarios.
			</p>
			<div class="skins-grid">
				{#each skins as skin (skin.id)}
					<button
						class="skin-card {skinActivo === skin.id ? 'skin-activo' : ''}"
						onclick={() => cambiarSkin(skin.id)}
						disabled={cambiandoSkin}
					>
						<div class="skin-nombre">{skin.nombre}</div>
						<div class="skin-desc">{skin.descripcion}</div>
						{#if skinActivo === skin.id}
							<span class="skin-check">✓</span>
						{/if}
					</button>
				{/each}
			</div>
		</div>

		<!-- Cerrar sesión -->
		<div class="card">
			<button class="btn btn-danger btn-block" onclick={cerrarSesion}>
				Cerrar sesión
			</button>
		</div>

		<div class="version-info">
			Admon v{APP_VERSION || '?'} | Shell v{SHELL_VERSION || '?'}
		</div>
	{/if}
</div>

<style>
	.brand-col { display: flex; flex-direction: column; gap: 0; }
	.brand { display: flex; align-items: center; gap: 0.5rem; margin: 0; font-size: var(--font-size-xl); }

	.mb-spinner {
		width: 28px; height: 28px; margin: 0 auto 0.75rem;
		border: 3px solid var(--color-surface-2);
		border-top-color: var(--color-primary);
		border-radius: 50%;
		animation: mb-spin 0.8s linear infinite;
	}
	@keyframes mb-spin { to { transform: rotate(360deg); } }

	.alert { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.85rem 1rem; border-radius: var(--radius-sm); font-size: var(--font-size-sm); margin-bottom: 1rem; }
	.alert-danger { background: rgba(239, 68, 68, 0.15); color: var(--color-danger); }
	.alert-success { background: rgba(34, 197, 94, 0.15); color: var(--color-success, var(--color-success)); }

	.card { background: var(--color-surface-1, var(--color-surface)); border-radius: var(--radius-sm, 8px); padding: 1rem; margin-bottom: 0.75rem; }
	.section-title { font-size: var(--font-size-sm); font-weight: 600; margin: 0 0 0.75rem; }

	.field { margin-bottom: 0.75rem; }
	.field label { display: block; font-size: var(--font-size-sm); color: var(--color-text-muted); margin-bottom: 0.35rem; }
	.input { width: 100%; padding: 0.5rem 0.75rem; border-radius: 6px; border: 1px solid var(--color-border, var(--color-surface-2)); background: var(--color-surface-2, var(--color-surface-2)); color: var(--color-text); font-size: var(--font-size-sm); box-sizing: border-box; }

	.perfil-foto-card { display: flex; align-items: center; gap: 1rem; }
	.foto-container { display: flex; flex-direction: column; align-items: center; gap: 0.5rem; }
	.foto-preview { width: 80px; height: 80px; border-radius: 50%; object-fit: cover; }
	.foto-placeholder { width: 80px; height: 80px; border-radius: 50%; background: var(--color-primary, var(--color-info)); display: flex; align-items: center; justify-content: center; font-size: var(--font-size-3xl); font-weight: 700; color: white; }
	.foto-btn { cursor: pointer; }
	.perfil-info h2 { margin: 0 0 0.25rem; font-size: var(--font-size-lg); }
	.perfil-email { color: var(--color-text-muted); font-size: var(--font-size-sm); margin: 0; }
	.perfil-puesto { color: var(--color-text-muted); font-size: var(--font-size-xs); margin: 0.25rem 0 0; }

	.permisos-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 0.4rem; }
	.permiso-item { display: flex; align-items: center; gap: 0.4rem; padding: 0.35rem 0.5rem; border-radius: 4px; font-size: var(--font-size-xs); }
	.permiso-activo { background: rgba(34, 197, 94, 0.1); }
	.permiso-inactivo { background: rgba(107, 114, 128, 0.1); opacity: 0.6; }
	.permiso-check { font-weight: 700; }
	.permiso-nombre { text-transform: capitalize; }

	.version-info { text-align: center; font-size: var(--font-size-2xs); color: var(--color-text-muted); margin-top: 1rem; }

	.skins-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 0.5rem; }
	.skin-card {
		background: var(--color-surface-2, var(--color-surface-2)); border-radius: 8px; padding: 0.75rem;
		text-align: left; cursor: pointer; border: 2px solid transparent;
		transition: border-color 0.15s, transform 0.15s; position: relative;
	}
	.skin-card:hover { transform: translateY(-1px); }
	.skin-card.skin-activo { border-color: var(--color-primary, var(--color-info)); }
	.skin-nombre { font-weight: 600; font-size: var(--font-size-sm); margin-bottom: 0.2rem; }
	.skin-desc { font-size: var(--font-size-xs); color: var(--color-text-muted); }
	.skin-check {
		position: absolute; top: 0.5rem; right: 0.5rem;
		color: var(--color-primary, var(--color-info)); font-weight: 700; font-size: var(--font-size-base);
	}

	.empty { text-align: center; padding: 2rem; color: var(--color-text-muted); }
</style>