// Helper para obtener la imagen de un automóvil.
// Prioridad: imagen subida (custom) > imagen por defecto en /autos/ > null

const BASE = '/autos/';

function slugify(name) {
	if (!name) return '';
	return String(name)
		.toLowerCase()
		.trim()
		.replace(/\s+/g, '-')
		.replace(/[^a-z0-9-]/g, '');
}

export function getAutoImage(marcaModelo, imagenCustom = null) {
	if (imagenCustom) return imagenCustom;
	if (!marcaModelo) return null;
	const slug = slugify(marcaModelo);
	if (!slug) return null;
	return `${BASE}${slug}.png`;
}

export function autoImageExists(marcaModelo) {
	// Lista de slugs disponibles (deben coincidir con los archivos en public/autos/)
	const available = [
		'honda-city-blanco',
		'honda-city-gris',
		'honda-civic',
		'honda-fit',
		'kia-rio-21',
		'lincoln-navigator-2003',
		'mg5',
		'nissan-np-300',
		'nissan-versa-acero',
		'nissan-versa-blanco',
		'nissan-versa-gris',
		'suzuki-swift',
	];
	const slug = slugify(marcaModelo);
	return available.includes(slug);
}