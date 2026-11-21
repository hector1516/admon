/**
 * Fechas en hora local, sin el salto a UTC.
 *
 * `new Date().toISOString()` devuelve la hora UTC. En México (UTC-6) eso
 * significa que **a partir de las 18:00 el día ya cambió**: un reporte
 * capturado de noche quedaba fechado al día siguiente, y los filtros de "hoy"
 * buscaban el día equivocado. Es el bug de horario que reaparecía.
 */

/** Fecha local en formato YYYY-MM-DD. */
export function fechaLocal(d = new Date()) {
	const y = d.getFullYear();
	const m = String(d.getMonth() + 1).padStart(2, '0');
	const dd = String(d.getDate()).padStart(2, '0');
	return `${y}-${m}-${dd}`;
}

/** Fecha y hora local con offset: 2026-11-21T09:30:00-06:00. */
export function isoLocal(d = new Date()) {
	const pad = (n) => String(n).padStart(2, '0');
	const off = -d.getTimezoneOffset();
	const signo = off >= 0 ? '+' : '-';
	const hh = pad(Math.floor(Math.abs(off) / 60));
	const mm = pad(Math.abs(off) % 60);
	return (
		`${fechaLocal(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}:` +
		`${pad(d.getSeconds())}${signo}${hh}:${mm}`
	);
}
