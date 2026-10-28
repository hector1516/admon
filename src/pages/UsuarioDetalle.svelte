<script>
	import { onMount, onDestroy } from 'svelte';
	import { navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { api } from '$lib/api.js';
	import PasswordInput from '$lib/components/PasswordInput.svelte';

	// id viene de la ruta /usuarios/:id (micro-router, modo runes -> $props)
	let { id } = $props();

	// Grupos de permisos idénticos a PERM_GROUPS del HUB (views/administrador_usuarios.py)
	const PERM_GROUPS = {
		'📊 Administración': [
			['AccesoConfiguracion', 'Configuración (Cambio PW)'],
			['AccesoUsuarios', 'Administrador de Usuarios'],
			['AccesoAppConfig', 'AppConfig ⚙️'],
			['AccesoEdicionBD', 'Edición BD 🗄️'],
			['Notificaciones', 'Notificaciones Push 🔔'],
			['AccesoConfigurarCorreo', 'Configurar Correo 📧'],
			['AccesoConfigAI', 'Configuración IA 🤖']
		],
		'📋 Operativo': [
			['AccesoReportes', 'Reportes de Servicio'],
			['AccesoRegistroReportes', 'Registro de Reportes'],
			['AccesoCotizacionesReportes', 'Cotizaciones Serv/Proy'],
			['AccesoClientes', 'Clientes'],
			['AccesoRegistroKilometros', 'Registro Kilómetros'],
			['AccesoAutomoviles', 'Automóviles']
		],
		'💰 Financiero': [
			['AccesoCotizaciones', 'Cotizaciones Materiales'],
			['AccesoCalculo', 'Cálculos 🧮'],
			['AccesoProveedores', 'Proveedores 🏭'],
			['AccesoOC', 'Órdenes de Compra 🛒'],
			['AccesoNominas', 'Nóminas 💵'],
			['AccesoInventario', 'Inventario 📦']
		],
		'⏰ Tiempo': [
			['AccesoVacaciones', 'Vacaciones ✈️'],
			['AccesoMisVacaciones', 'Mis Vacaciones 🏖️'],
			['AccesoHorasExtras', 'Horas Extras ⏰'],
			['AccesoMisHorasExtras', 'Mis Horas Extras 🕒']
		],
		'⛽ OxxoGas': [
			['AccesoOxxoGas', 'Gmail OxxoGas ⛽'],
			['AccesoValesOxxoGas', 'Vales OxxoGas 🚗'],
			['AccesoRegistroTicketOxxoGas', 'Ticket OxxoGas 🎫'],
			['AccesoSolicitarVales', 'Solicitar Vales QR 📲'],
			['AccesoAdminVales', 'Admin Vales QR ✅'],
			['AccesoConfigOxxogas', 'Config OxxoGas ⚙️']
		],
		'🔧 Otros': [
			['AccesoVM', 'Programas VM'],
			['AccesoDeteccionRed', 'Detección de Red 📡'],
			['AccesoPdfConfig', 'Guardado PDFs 📁']
		]
	};

	let loading = $state(true);
	let error = $state('');
	let msg = $state('');
	let busy = $state(false);

	let nombre = $state('');
	let email = $state('');
	let curpRfc = $state('');
	let nss = $state('');
	let puesto = $state('');
	let password = $state('');
	let fechaIngreso = $state('');
	let activo = $state(true);
	let accesos = $state({});
	let isSelf = $state(false);

	// 📷 Fotografía (HUB_UsuariosFotos, tabla aparte). `fotoUrl` es un blob URL
	// local: la foto pesa, y meterla en el <img src> como base64 atascaría la
	// ficha; por eso se pide al backend por HTTP y serevoca al salir.
	let fotoUrl = $state('');
	let tieneFoto = $state(false);
	let busyFoto = $state(false);
	let msgFoto = $state('');
	let errFoto = $state('');

	// Teléfono / MAC: se guarda en HUB_NetworkDevices (la tabla del escáner de
	// red 📡 que mide entradas y salidas de la oficina), vinculada por IdUsuario.
	// 🎴 Enlace de la tarjeta NFC (app colaboradores.ecc-sa.com.mx). El token se
	// deriva en el backend (api/ficha_nfc.py) porque el secreto no debe estar en
	// el navegador: con el secreto en el cliente, cualquiera que abriera las
	// herramientas de desarrollo podría derivar el enlace de cualquier persona.
	let fichaUrl = $state('');
	let copiado = $state(false);

	async function cargarFicha() {
		try {
			const d = await api.get(`/users/${id}/ficha`);
			fichaUrl = d?.url || '';
		} catch (e2) {
			console.error('Error cargando la ficha NFC:', e2);
			fichaUrl = '';
		}
	}

	async function copiarFicha() {
		try {
			await navigator.clipboard.writeText(fichaUrl);
			copiado = true;
			setTimeout(() => (copiado = false), 1800);
		} catch {
			// Sin permiso de portapapeles (o sin HTTPS): se selecciona el texto.
			const el = document.querySelector('.ficha-url');
			if (el) {
				const rango = document.createRange();
				rango.selectNodeContents(el);
				const sel = window.getSelection();
				sel.removeAllRanges();
				sel.addRange(rango);
			}
		}
	}

	let macTel = $state('');
	let macNombre = $state('');
	let tel = $state(null); // estado del dispositivo + presencia (AQUI/FUERA)
	let busyMac = $state(false);
	let msgMac = $state('');
	let errMac = $state('');

	// Initials para el avatar cuando no hay foto: "Héctor Peña" → "HP".
	function iniciales(nombre) {
		const partes = String(nombre || '').trim().split(/\s+/).filter(Boolean);
		if (!partes.length) return '?';
		return ((partes[0][0] || '') + (partes.length > 1 ? partes[partes.length - 1][0] : '')).toUpperCase();
	}

	async function cargarFoto() {
		try {
			const r = await fetch(`/api/users/${id}/foto`, { headers: auth.authHeader() });
			if (!r.ok) { tieneFoto = false; return; }
			const blob = await r.blob();
			if (fotoUrl) URL.revokeObjectURL(fotoUrl);
			fotoUrl = URL.createObjectURL(blob);
			tieneFoto = true;
		} catch {
			tieneFoto = false; // sin conexión o sin foto: se muestra el avatar
		}
	}

	async function onElegirFoto(ev) {
		const file = ev.target.files?.[0];
		ev.target.value = ''; // permite volver a elegir el mismo archivo
		if (!file) return;
		if (!/^image\/(jpeg|png|webp|gif)$/.test(file.type)) {
			errFoto = 'Usa una imagen JPEG, PNG, WEBP o GIF.';
			return;
		}
		if (file.size > 5 * 1024 * 1024) {
			errFoto = 'La foto pesa más de 5 MB. Bájala de tamaño y súbela de nuevo.';
			return;
		}
		busyFoto = true;
		errFoto = '';
		msgFoto = '';
		try {
			const base64 = await new Promise((res, rej) => {
				const fr = new FileReader();
				fr.onload = () => res(String(fr.result));
				fr.onerror = () => rej(new Error('No se pudo leer el archivo.'));
				fr.readAsDataURL(file);
			});
			const r = await fetch(`/api/users/${id}/foto`, {
				method: 'PUT',
				headers: apiHeaders(),
				body: JSON.stringify({ contenido_base64: base64, content_type: file.type })
			});
			const data = await r.json().catch(() => ({}));
			if (!r.ok) throw new Error(data.detail || 'No se pudo guardar la foto.');
			await cargarFoto();
			msgFoto = '✅ Foto actualizada.';
		} catch (e) {
			errFoto = e.message || 'No se pudo guardar la foto.';
		} finally {
			busyFoto = false;
		}
	}

	async function onQuitarFoto() {
		if (!confirm('¿Quitar la foto de este usuario?')) return;
		busyFoto = true;
		errFoto = '';
		msgFoto = '';
		try {
			const r = await fetch(`/api/users/${id}/foto`, { method: 'DELETE', headers: auth.authHeader() });
			const data = await r.json().catch(() => ({}));
			if (!r.ok) throw new Error(data.detail || 'No se pudo borrar la foto.');
			if (fotoUrl) URL.revokeObjectURL(fotoUrl);
			fotoUrl = '';
			tieneFoto = false;
			msgFoto = '🗑️ Foto quitada.';
		} catch (e) {
			errFoto = e.message || 'No se pudo borrar la foto.';
		} finally {
			busyFoto = false;
		}
	}

	function fmtFecha(iso) {
		if (!iso) return '—';
		const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
		if (m) return `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}`;
		return '—';
	}

	function apiHeaders() {
		return { 'Content-Type': 'application/json', ...auth.authHeader() };
	}

	function tieneAcceso() {
		try {
			const raw = localStorage.getItem('admon_user');
			const u = raw ? JSON.parse(raw) : null;
			return !!(u && u.acceso_usuarios);
		} catch {
			return false;
		}
	}

	function myEmail() {
		try {
			const raw = localStorage.getItem('admon_user');
			const u = raw ? JSON.parse(raw) : null;
			return (u && u.email ? String(u.email) : '').trim().toLowerCase();
		} catch {
			return '';
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
		try {
			// GET con caché offline: red primero, si no hay red sirve el
			// detalle cacheado por el prefetch (últimos 10 usuarios).
			const d = await api.get(`/users/${id}`);
			nombre = d.nombre || '';
			email = d.email || '';
			curpRfc = d.curp_rfc || '';
			nss = d.nss || '';
			puesto = d.puesto || '';
			password = d.password || '';
			fechaIngreso = d.fecha_ingreso || '';
			activo = !!d.activo;
			const a = {};
			for (const g of Object.values(PERM_GROUPS)) for (const [k] of g) a[k] = !!d[k];
			accesos = a;
			isSelf = (email || '').trim().toLowerCase() === myEmail();
			// MAC del teléfono (HUB_NetworkDevices); si falla no bloquea la ficha
			try {
				tel = await api.get(`/users/${id}/telefono`);
				macTel = tel?.mac || '';
				macNombre = tel?.nombre_dispositivo || '';
			} catch (e2) {
				console.error('Error cargando MAC:', e2);
			}
			// 📷 Foto del usuario (HUB_UsuariosFotos). También tolerant: si no
			// hay foto o falla, se queda el avatar de iniciales.
			await cargarFoto();
			// 🎴 Enlace NFC. Tolerant: si falta el secreto en HUB_Config, la ficha
			// simplemente no se muestra y el resto de la pantalla sigue igual.
			await cargarFicha();
		} catch (e) {
			console.error('Error cargando usuario:', e);
			error = e.message === 'Sesión expirada' ? e.message : `No se pudo cargar: ${e.message || 'sin detalle'}`;
		} finally {
			loading = false;
		}
	});

	// Libera el blob URL de la foto al salir de la página (si no, el navegador
	// lo mantiene hasta que se recarga entera).
	onDestroy(() => {
		if (fotoUrl) URL.revokeObjectURL(fotoUrl);
	});

	async function guardar() {
		msg = '';
		error = '';
		if (!nombre.trim() || !email.trim() || !password.trim()) {
			error = 'Nombre, correo y contraseña son obligatorios.';
			return;
		}
		busy = true;
		try {
			const res = await fetch(`/api/users/${id}`, {
				method: 'PUT',
				headers: apiHeaders(),
				body: JSON.stringify({
					nombre: nombre.trim(),
					email: email.trim(),
					password,
					activo,
					fecha_ingreso: fechaIngreso || null,
					curp_rfc: curpRfc.trim(),
					nss: nss.trim(),
					puesto: puesto.trim(),
					accesos
				})
			});
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al actualizar.');
			msg = '✅ Usuario actualizado.';
		} catch (e) {
			error = e.message || 'Error al actualizar.';
		} finally {
			busy = false;
		}
	}

	async function guardarMac() {
		msgMac = '';
		errMac = '';
		busyMac = true;
		try {
			const res = await fetch(`/api/users/${id}/telefono`, {
				method: 'PUT',
				headers: apiHeaders(),
				body: JSON.stringify({ mac: macTel.trim(), nombre_dispositivo: macNombre.trim() })
			});
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al guardar la MAC.');
			tel = data;
			macTel = data.mac || '';
			macNombre = data.nombre_dispositivo || '';
			msgMac = data.mac
				? '✅ MAC vinculada. El escáner 📡 ya puede medir sus entradas y salidas.'
				: '✅ Teléfono desvinculado (el historial se conserva).';
		} catch (e) {
			errMac = e.message || 'Error al guardar la MAC.';
		} finally {
			busyMac = false;
		}
	}

	async function eliminar() {
		if (isSelf) return;
		if (!confirm(`¿Eliminar al usuario "${nombre}"?`)) return;
		msg = '';
		error = '';
		busy = true;
		try {
			const res = await fetch(`/api/users/${id}`, { method: 'DELETE', headers: auth.authHeader() });
			const data = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(data.detail || 'Error al eliminar.');
			navigate('/usuarios', { replace: true });
		} catch (e) {
			error = e.message || 'Error al eliminar.';
			busy = false;
		}
	}
</script>

<div class="page">
	<div class="header">
		<button class="btn btn-sm btn-secondary" on:click={() => navigate('/usuarios')} title="Volver">⬅️</button>
		<h1>✏️ {nombre || 'Usuario'}</h1>
	</div>

	{#if loading}
		<div class="empty">Cargando…</div>
	{:else if error && !nombre}
		<div class="card"><p style="color: var(--color-danger); margin: 0;">{error}</p></div>
	{:else}
		<div class="card" style="margin-bottom: 0.75rem;">
			<div class="card-title">👤 Foto</div>
			<div class="foto-row">
				<div class="avatar">
					{#if fotoUrl}
						<img src={fotoUrl} alt="Foto de {nombre}" />
					{:else}
						<span>{iniciales(nombre) || '👤'}</span>
					{/if}
				</div>
				<div class="foto-campo">
					<p class="hint" style="margin: 0 0 0.6rem;">
						Una sola foto por usuario. Se usa en su ficha y queda disponible por API
						(<code>GET /api/users/&lt;id&gt;/foto</code>) para las otras apps.
					</p>
					<input
						id="ud-foto"
						type="file"
						accept="image/jpeg,image/png,image/webp,image/gif"
						on:change={onElegirFoto}
						disabled={busyFoto}
					/>
					{#if errFoto}<div class="msg err" style="margin-top: 0.5rem;">{errFoto}</div>{/if}
					{#if msgFoto}<div class="msg ok" style="margin-top: 0.5rem;">{msgFoto}</div>{/if}
					{#if tieneFoto}
					<button
						class="btn btn-secondary btn-block"
						on:click={onQuitarFoto}
						disabled={busyFoto}
						style="margin-top: 0.5rem;"
					>
							{busyFoto ? 'Quitando…' : '🗑️ Quitar foto'}
						</button>
					{/if}
				</div>
			</div>
		</div>

		<!-- 🎴 Tarjeta NFC. El enlace es FIJO y no cambia nunca: sale del Id del
		     usuario, así que la tarjeta puede grabarse una vez y seguir valiendo
		     aunque la persona cambie de nombre, de foto o de puesto. -->
		<div class="card" style="margin-bottom: 0.75rem;">
			<div class="card-title">🎴 Tarjeta NFC</div>
			{#if fichaUrl}
				<p class="hint" style="margin: 0 0 0.6rem;">
					Graba este enlace en la tarjeta. Al tocarla con el móvil se abre la
					ficha con el contacto, el WhatsApp y la dirección de la empresa.
				</p>
				<div class="ficha-row">
					<code class="ficha-url">{fichaUrl}</code>
					<button class="btn btn-sm" on:click={copiarFicha}>
						{copiado ? '✅ Copiado' : '📋 Copiar'}
					</button>
				</div>
				<div class="ficha-extra">
					<a class="btn btn-sm btn-secondary" href={fichaUrl} target="_blank" rel="noopener">
						👁️ Ver ficha
					</a>
					<a
						class="btn btn-sm btn-secondary"
						href={`${fichaUrl}/contacto.vcf`}
						target="_blank"
						rel="noopener"
					>
						👤 vCard
					</a>
				</div>
			{:else}
				<p class="hint" style="margin: 0;">
					Sin enlace: falta el secreto <code>colab_ficha_secreto</code> en
					<code>HUB_Config</code> (lo define la migración <code>0060</code>).
				</p>
			{/if}
		</div>

		<div class="card" style="margin-bottom: 0.75rem;">
			<div class="card-title">📝 Datos</div>
			<div class="grid2">
				<div class="field">
					<label for="ud-nombre">Nombre completo:</label>
					<input id="ud-nombre" class="input" bind:value={nombre} />
				</div>
				<div class="field">
					<label for="ud-email">Correo electrónico:</label>
					<input id="ud-email" type="email" class="input" bind:value={email} />
				</div>
				<div class="field">
					<label for="ud-curp">CURP / RFC:</label>
					<input id="ud-curp" class="input" placeholder="Ej: PEGC850101ABC" bind:value={curpRfc} />
				</div>
				<div class="field">
					<label for="ud-nss">NSS (número de seguro social):</label>
					<input
						id="ud-nss"
						class="input"
						inputmode="numeric"
						placeholder="Ej: 12345678901 (11 dígitos)"
						bind:value={nss}
						on:blur={() => (nss = nss.replace(/\D/g, ''))}
					/>
				</div>
				<div class="field">
					<label for="ud-puesto">Puesto:</label>
					<input
						id="ud-puesto"
						class="input"
						placeholder="Ej: Supervisor de mantenimiento, Analista, Chofer…"
						maxlength="120"
						bind:value={puesto}
					/>
				</div>
				<div class="field">
					<label for="ud-fecha">Fecha de ingreso:</label>
					<input id="ud-fecha" type="date" class="input" bind:value={fechaIngreso} />
				</div>
			</div>
			<div class="field">
				<label for="ud-pw">Contraseña:</label>
				<PasswordInput id="ud-pw" autocomplete="new-password" bind:value={password} />
			</div>
			<label class="check"><input type="checkbox" bind:checked={activo} /> Usuario activo</label>
		</div>

		<div class="card" style="margin-bottom: 0.75rem;">
			<div class="card-title">📱 MAC del teléfono</div>
			<p class="hint" style="margin: 0 0 0.6rem;">
				📡 Detección de Red: con esta MAC el escáner mide las <b>entradas y salidas</b> de la
				oficina. Los iPhone con “dirección Wi-Fi privada” rotan su MAC: si deja de detectarse,
				vuelve a anotarla aquí.
			</p>
			<div class="field">
				<label for="ud-mac">MAC del celular:</label>
				<input
					id="ud-mac"
					class="input"
					placeholder="EE:E2:FD:A3:43:EC"
					bind:value={macTel}
					on:blur={() => (macTel = macTel.trim().toUpperCase())}
				/>
			</div>
			<div class="field">
				<label for="ud-mac-nombre">Nombre del dispositivo (opcional):</label>
				<input id="ud-mac-nombre" class="input" placeholder="Ej: iPhone Héctor" bind:value={macNombre} />
			</div>

			{#if tel && tel.id_dispositivo}
				<div class="tel-estado">
					{#if tel.estado === 'AQUI'}
						<span class="tel-chip tel-aqui">🟢 En la oficina</span>
					{:else}
						<span class="tel-chip">⚪ Fuera</span>
					{/if}
					{#if tel.ultimo_evento}
						<span class="tel-chip">
							{tel.ultimo_evento.tipo === 'ENTRADA' ? '⬅️ Última entrada' : '➡️ Última salida'}:
							{fmtFecha(tel.ultimo_evento.fecha)}
						</span>
					{/if}
					{#if tel.ultima_vez_en_red}
						<span class="tel-chip">📶 Visto: {fmtFecha(tel.ultima_vez_en_red)}</span>
					{/if}
				</div>
			{:else}
				<p class="hint" style="margin: 0 0 0.6rem;">➕ Sin MAC registrada — anóntala para empezar a medir su asistencia.</p>
			{/if}

			{#if errMac}<div class="msg err">{errMac}</div>{/if}
			{#if msgMac}<div class="msg ok">{msgMac}</div>{/if}

			<button class="btn btn-secondary btn-block" on:click={guardarMac} disabled={busyMac}>
				{busyMac ? 'Guardando…' : macTel.trim() ? '💾 Guardar MAC' : '💾 Desvincular teléfono'}
			</button>
		</div>

		<div class="card" style="margin-bottom: 0.75rem;">
			<div class="card-title">🔑 Permisos</div>
			<div class="perm-grid">
				{#each Object.entries(PERM_GROUPS) as [grupo, perms]}
					<div class="perm-grupo">
						<p class="perm-titulo">{grupo}</p>
						{#each perms as [key, label]}
							<label class="check"><input type="checkbox" bind:checked={accesos[key]} /> {label}</label>
						{/each}
					</div>
				{/each}
			</div>
		</div>

		{#if error}
			<div class="msg err">{error}</div>
		{/if}
		{#if msg}
			<div class="msg ok">{msg}</div>
		{/if}

		<button class="btn btn-primary btn-block" on:click={guardar} disabled={busy}>
			{busy ? 'Guardando…' : '💾 Guardar cambios'}
		</button>
		{#if isSelf}
			<p class="hint" style="margin-top: 0.75rem;">ℹ️ No puedes eliminar tu propia cuenta desde aquí.</p>
		{:else}
			<button class="btn btn-danger btn-block" style="margin-top: 0.5rem;" on:click={eliminar} disabled={busy}>
				🚨 Eliminar usuario
			</button>
		{/if}
	{/if}
</div>

<style>
	.card-title { font-weight: 700; font-size: 1.05rem; margin-bottom: 0.75rem; }
	.msg { padding: 0.6rem 0.75rem; border-radius: 8px; font-size: 0.85rem; margin-bottom: 0.75rem; }
	.msg.err { background: rgba(239,68,68,0.1); color: #EF4444; }
	.msg.ok { background: rgba(34,197,94,0.1); color: #22C55E; }
	.check { display: flex; align-items: center; gap: 0.5rem; font-size: 0.9rem; margin-bottom: 0.5rem; cursor: pointer; }
	.check input { width: 1.1rem; height: 1.1rem; flex-shrink: 0; }
	.hint { font-size: 0.85rem; color: var(--color-text-muted); }
	.tel-estado { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.6rem; }
	.tel-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		font-size: 0.75rem;
		padding: 0.25rem 0.55rem;
		border-radius: 999px;
		background: rgba(255, 255, 255, 0.06);
		color: var(--color-text-muted);
	}
	.tel-aqui { background: rgba(34, 197, 94, 0.14); color: #22C55E; }

	/* Recuadros más grandes que los .card del shell (mismo estilo, más aire
	   adentro). Es una regla con scope de este componente, así que no toca
	   styles/app.css ni el check del shell. */
	.card { margin-bottom: 0.75rem; padding: 1.5rem; }

	/* Dos columnas en pantallas anchas: los campos cortos caben uno junto al
	   otro y la tarjeta no se alarga de más. */
	.grid2 { display: grid; grid-template-columns: 1fr; gap: 0 1.25rem; }
	@media (min-width: 760px) {
		.grid2 { grid-template-columns: 1fr 1fr; }
	}

	/* Foto: avatar grande a la izquierda, controles a la derecha; en pantallas
	   estrechas se apilan. */
	.foto-row { display: flex; gap: 1.25rem; align-items: flex-start; flex-wrap: wrap; }
	.foto-campo { flex: 1; min-width: 14rem; }
	.avatar {
		width: 7rem;
		height: 7rem;
		border-radius: 999px;
		flex-shrink: 0;
		overflow: hidden;
		background: rgba(255, 255, 255, 0.08);
		display: flex;
		align-items: center;
		justify-content: center;
		border: 3px solid var(--color-primary);
	}
	.avatar img { width: 100%; height: 100%; object-fit: cover; }
	.avatar span { font-size: 2.25rem; font-weight: 700; color: var(--color-text-muted); }
	@media (min-width: 760px) {
		.avatar { width: 9rem; height: 9rem; }
		.avatar span { font-size: 3rem; }
	}

	/* Permisos: un recuadro por grupo, en dos columnas cuando hay sitio. */
	.perm-grid { display: grid; grid-template-columns: 1fr; gap: 0.5rem 1.5rem; }
	@media (min-width: 760px) {
		.perm-grid { grid-template-columns: 1fr 1fr; }
	}
	.perm-grupo {
		background: rgba(255, 255, 255, 0.03);
		border: 1px solid rgba(255, 255, 255, 0.06);
		border-radius: var(--radius);
		padding: 0.85rem 1rem;
	}
	.perm-titulo { font-weight: 700; font-size: 0.9rem; margin: 0 0 0.5rem; }

	code { font-size: 0.75rem; background: rgba(255, 255, 255, 0.08); padding: 0.1rem 0.3rem; border-radius: 4px; }
</style>
