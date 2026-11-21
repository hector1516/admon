// Passkeys (WebAuthn) para Admon — port de Field src/lib/passkey.ts
// OJO: desde admon.ecc-sa.com.mx el navegador SOLO acepta passkeys con
// rpId = ecc-sa.com.mx (rp raíz). Las legacy (field./hub.) no son usables
// aquí (SecurityError del navegador), por eso no hay fallback dual RP.
import { startAuthentication, startRegistration } from '@simplewebauthn/browser';
import { auth } from './stores/auth.js';

export const PK_FLAG = 'admon_passkey';
// Hint del rp con el que la passkey funcionó por última vez (por si en el
// futuro hay más de un rp; hoy solo existe el raíz).
export const PK_RP_HINT = 'admon_passkey_rp';
export const RP_NUEVO = 'ecc-sa.com.mx';

export function passkeySupported() {
	try {
		return typeof window !== 'undefined' && !!window.PublicKeyCredential;
	} catch {
		return false;
	}
}

export function hasPasskeyFlag() {
	try {
		return localStorage.getItem(PK_FLAG) === '1';
	} catch {
		return false;
	}
}

export function setPasskeyFlag() {
	try {
		localStorage.setItem(PK_FLAG, '1');
	} catch {}
}

function setRpHint(rp) {
	try {
		localStorage.setItem(PK_RP_HINT, rp);
	} catch {}
}

function asOptions(raw) {
	return typeof raw === 'string' ? JSON.parse(raw) : raw;
}

function authHeaders() {
	return { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('admon_token') || ''}` };
}

// Nombres hilarantes estilo Ubuntu: animal raro + adjetivo (con genero).
// Mismo generador que Field/HUB para consistencia entre apps.
const ANIMALES = [
	['Ajolote', 'm'], ['Capibara', 'f'], ['Ornitorrinco', 'm'], ['Pangolín', 'm'],
	['Tardígrado', 'm'], ['Quokka', 'f'], ['Narval', 'm'], ['Jerbo', 'm'],
	['Okapi', 'm'], ['Aye-aye', 'm'], ['Pez borrón', 'm'], ['Kakapo', 'm'],
	['Wombat', 'm'], ['Equidna', 'f'], ['Lémur', 'm'], ['Suricata', 'f'],
	['Fosa', 'f'], ['Binturong', 'm'], ['Coatí', 'm'], ['Tapir', 'm'],
	['Vizcacha', 'f'], ['Almiquí', 'm'], ['Fénec', 'm'], ['Caracal', 'm'],
	['Ocelote', 'm'], ['Damán', 'm'], ['Civeta', 'f'], ['Kinkajú', 'm'],
	['Marmota', 'f'], ['Topo nariz estrellada', 'm'], ['Colugo', 'm'], ['Dugongo', 'm']
];
const ADJETIVOS = [
	['Veloz', 'Veloz'], ['Ansioso', 'Ansiosa'], ['Cósmico', 'Cósmica'], ['Eléctrico', 'Eléctrica'],
	['Místico', 'Mística'], ['Peludo', 'Peluda'], ['Dormilón', 'Dormilona'], ['Gruñón', 'Gruñona'],
	['Saltarín', 'Saltarina'], ['Cuántico', 'Cuántica'], ['Magnético', 'Magnética'], ['Fosforescente', 'Fosforescente'],
	['Épico', 'Épica'], ['Legendario', 'Legendaria'], ['Sigiloso', 'Sigilosa'], ['Esponjoso', 'Esponjosa'],
	['Gelatinoso', 'Gelatinosa'], ['Crocante', 'Crocante'], ['Despeinado', 'Despeinada'], ['Sonámbulo', 'Sonámbula'],
	['Hiperactivo', 'Hiperactiva'], ['Filosófico', 'Filosófica'], ['Dramático', 'Dramática'], ['Invisible', 'Invisible'],
	['Radioactivo', 'Radioactiva'], ['Pegajoso', 'Pegajosa'], ['Intergaláctico', 'Intergaláctica'], ['Atómico', 'Atómica'],
	['Sarcástico', 'Sarcástica'], ['Noctámbulo', 'Noctámbula'], ['Burbujeante', 'Burbujeante'], ['Mojado', 'Mojada']
];

export function randomDeviceName() {
	const [animal, genero] = ANIMALES[Math.floor(Math.random() * ANIMALES.length)];
	const [masc, fem] = ADJETIVOS[Math.floor(Math.random() * ADJETIVOS.length)];
	return `${animal} ${genero === 'm' ? masc : fem}`;
}

/**
 * Login con passkey discoverable (sin correo) en el rp raíz ecc-sa.com.mx.
 * Si el navegador no tiene passkeys de este rp, NotAllowedError se propaga
 * (aquí no hay fallback: el rp es el único soportado desde admon).
 */
export async function loginWithPasskey() {
	let o;
	try {
		o = await fetch('/api/passkeys/login/options', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ rp: RP_NUEVO })
		}).then(async (r) => {
			if (!r.ok) throw new Error('No se pudo iniciar la passkey');
			return r.json();
		});
	} catch (e) {
		if (e instanceof TypeError) throw new Error('Sin conexión a internet.');
		throw e;
	}
	const cred = await startAuthentication({ optionsJSON: asOptions(o.options) });
	const v = await fetch('/api/passkeys/login/verify', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ credential: cred, state: o.state })
	});
	if (!v.ok) {
		const e = await v.json().catch(() => ({ detail: 'Passkey no válida' }));
		throw new Error(e.detail || 'Passkey no válida');
	}
	const data = await v.json();
	auth.saveSession(data);
	setPasskeyFlag();
	setRpHint(RP_NUEVO);
}

/**
 * Paso de passkey para marcar asistencia (D3 B): devuelve el token de 2 min
 * que `/mi-asistencia/marcar` exige.
 */
export async function pasoAsistencia() {
	const o = await fetch('/api/mi-asistencia/passkey/options', {
		method: 'POST',
		headers: authHeaders(),
		body: JSON.stringify({ rp: RP_NUEVO })
	}).then(async (r) => {
		if (!r.ok) throw new Error('No se pudo iniciar la passkey');
		return r.json();
	});
	const cred = await startAuthentication({ optionsJSON: asOptions(o.options) });
	const v = await fetch('/api/mi-asistencia/passkey/verify', {
		method: 'POST',
		headers: authHeaders(),
		body: JSON.stringify({ credential: cred, state: o.state })
	});
	if (!v.ok) {
		const e = await v.json().catch(() => ({ detail: 'Passkey no válida' }));
		throw new Error(e.detail || 'Passkey no válida');
	}
	const data = await v.json();
	return data.stepup_token;
}

/**
 * Registro de passkey en este equipo (requiere sesión iniciada).
 * Siempre en el rp raíz; el label inicial puede sembrar el Nickname del
 * usuario si aún no tiene.
 */
export async function registerPasskey(label) {
	const o = await fetch('/api/passkeys/register/options', {
		method: 'POST',
		headers: authHeaders(),
		body: JSON.stringify({ label })
	}).then(async (r) => {
		if (!r.ok) {
			const e = await r.json().catch(() => ({ detail: 'No se pudo iniciar el registro' }));
			throw new Error(e.detail || 'No se pudo iniciar el registro');
		}
		return r.json();
	});
	const cred = await startRegistration({ optionsJSON: asOptions(o.options) });
	const v = await fetch('/api/passkeys/register/verify', {
		method: 'POST',
		headers: authHeaders(),
		body: JSON.stringify({ credential: cred, state: o.state, label })
	});
	if (!v.ok) {
		const e = await v.json().catch(() => ({ detail: 'No se pudo registrar la passkey' }));
		throw new Error(e.detail || 'No se pudo registrar la passkey');
	}
	setPasskeyFlag();
	setRpHint(RP_NUEVO);
}
