/*
 * rostro.js — descriptor facial en el navegador (Mi Asistencia, D1 A).
 *
 * El descriptor (128 números) se calcula aquí y viaja al backend, que lo compara
 * contra `HUB_UsuariosFaciales.Embedding`. La foto nunca sale del teléfono.
 *
 * Requiere `@vladmandic/face-api` instalado y los modelos en `/models`:
 *   tiny_face_detector, face_landmark_68, face_recognition (~6 MB).
 */

export const UMBRAL = 0.55;

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

/** Devuelve el descriptor de la cara en el <video>, o null si no ve una cara. */
export async function describir(videoEl) {
	if (!videoEl) return null;
	if (!cargado) await cargarModelo();
	const deteccion = await faceapi
		.detectSingleFace(videoEl, new faceapi.TinyFaceDetectorOptions({ inputSize: 224 }))
		.withFaceLandmarks()
		.withFaceDescriptor();
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
