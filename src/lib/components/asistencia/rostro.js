/*
 * rostro.js — descriptor facial en el navegador (Mi Asistencia, D1 A).
 *
 * El descriptor (128 números) se calcula aquí y viaja al backend, que lo compara
 * contra `HUB_UsuariosFaciales.Embedding`. La foto nunca sale del teléfono.
 *
 * Requiere `@vladmandic/face-api` instalado y los modelos en `/models`:
 *   tiny_face_detector, face_landmark_68, face_recognition (~6,7 MB).
 *
 * Dos guardas que costaron un bug:
 *   - `videoListo()`: no se analiza un <video> sin imagen (la inferencia se
 *     queda colgada para siempre en un fotograma de 0×0).
 *   - `conTiempo()`: si el modelo tarda o el backend de tfjs no arranca, el
 *     flujo sigue (cuenta el intento) en vez de congelar la pantalla.
 */

export const UMBRAL = 0.55;
export const TIEMPO_MAX_DETECCION_MS = 8000;
export const ESPERA_VIDEO_MS = 2000;

let faceapi = null;
let cargado = false;

/** Carga la librería y los modelos una sola vez. */
export async function cargarModelo(base = '/models') {
	if (cargado) return;
	if (!faceapi) faceapi = await import('@vladmandic/face-api');
	await Promise.all([
		faceapi.nets.tinyFaceDetector.loadFromUri(base),
		faceapi.nets.faceLandmark68Net.loadFromUri(base),
		faceapi.nets.faceRecognitionNet.loadFromUri(base)
	]);
	cargado = true;
}

/** True si el <video> ya tiene imagen decodificada (readyState >= 2). */
export function videoListo(video) {
	if (!video) return false;
	if (!video.videoWidth || !video.videoHeight) return false;
	return Number(video.readyState) >= 2;
}

/**
 * Espera hasta `ms` a que el <video> tenga imagen. Devuelve si la tiene.
 *
 * Sirve para separar dos fallos que se veían iguales: «la cámara no entrega
 * imagen» (permiso, otra app usándola, iOS que no arranca el stream) y «no hay
 * cara en el encuadre». Antes los dos decían «No veo tu cara».
 */
export async function esperarVideo(video, ms = ESPERA_VIDEO_MS) {
	const limite = Date.now() + ms;
	while (Date.now() < limite) {
		if (videoListo(video)) return true;
		await new Promise((r) => setTimeout(r, 100));
	}
	return videoListo(video);
}

/** Resuelve con el valor de la promesa, o null si tarda más de `ms`. */
export async function conTiempo(promesa, ms) {
	let temporizador;
	const tope = new Promise((resolve) => {
		temporizador = setTimeout(() => resolve(null), ms);
	});
	try {
		return await Promise.race([promesa, tope]);
	} finally {
		clearTimeout(temporizador);
	}
}

/** Devuelve el descriptor de la cara en el <video>, o null si no hay cara. */
export async function describir(videoEl, { esperaMaxima = ESPERA_VIDEO_MS } = {}) {
	if (!videoEl) return null;
	if (!(await esperarVideo(videoEl, esperaMaxima))) return null;

	if (!cargado) await cargarModelo();
	const deteccion = await conTiempo(
		faceapi
			.detectSingleFace(videoEl, new faceapi.TinyFaceDetectorOptions({ inputSize: 224 }))
			.withFaceLandmarks()
			.withFaceDescriptor(),
		TIEMPO_MAX_DETECCION_MS
	);
	if (!deteccion) return null;
	return Array.from(deteccion.descriptor);
}

/** Compara dos descriptores (útil para probar el umbral en el cliente). */
export function comparar(a, b, umbral = UMBRAL) {
	if (!a || !b || a.length !== b.length) return { coincide: false, score: null };
	let suma = 0;
	for (let i = 0; i < a.length; i++) {
		const d = a[i] - b[i];
		suma += d * d;
	}
	const score = Math.sqrt(suma);
	return { coincide: score <= umbral, score: Math.round(score * 1000) / 1000 };
}
