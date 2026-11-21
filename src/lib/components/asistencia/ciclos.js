/*
 * ciclos.js — agrupa los marcados de Mi Asistencia en ciclos entrada→salida.
 *
 * El backend devuelve los marcados sueltos (`HUB_AsistenciaMarcado`). Aquí se
 * empareja cada Entrada con la Salida que le sigue para pintar **una tarjeta
 * por ciclo**, con horas trabajadas y horas extra calculadas con la LFT:
 *   - jornada diaria configurable (`HUB_AsistenciaConfigLFT.HorasJornada`)
 *   - las primeras 9 h extra de la semana se pagan dobles
 *   - el resto de la semana, triples
 *   - máximo 3 h extra al día (LFT art. 66)
 *
 * Sin dependencias: se puede probar con `node --test` (ver tests/).
 */

export const HORAS_JORNADA = 8;
export const EXTRAS_DOBLES_SEMANA = 9;
export const EXTRAS_MAX_DIA = 3;

/** Convierte Fecha + Hora de un marcado en un Date local (nunca UTC). */
export function instante(marcado) {
	if (!marcado || !marcado.Fecha || !marcado.Hora) return null;
	const fecha =
		marcado.Fecha instanceof Date
			? `${marcado.Fecha.getFullYear()}-${String(marcado.Fecha.getMonth() + 1).padStart(2, '0')}-${String(
					marcado.Fecha.getDate()
				).padStart(2, '0')}`
			: String(marcado.Fecha).slice(0, 10);
	const hora = String(marcado.Hora).slice(0, 8);
	const d = new Date(`${fecha}T${hora}`);
	return Number.isNaN(d.getTime()) ? null : d;
}

/** Lunes de la semana de esa fecha, como clave `YYYY-M-D`. */
export function claveSemana(fecha) {
	const d = new Date(fecha.getFullYear(), fecha.getMonth(), fecha.getDate());
	const desdeLunes = (d.getDay() + 6) % 7; // domingo=6, lunes=0
	d.setDate(d.getDate() - desdeLunes);
	return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

function redondear(n) {
	return Math.round(n * 100) / 100;
}

/** Horas decimales → texto corto: `8 h`, `8 h 30 min`, `15 min`. */
export function formatoHoras(horas) {
	if (horas == null || Number.isNaN(Number(horas))) return '—';
	const totalMin = Math.round(Number(horas) * 60);
	if (totalMin === 0) return '0 h';
	const h = Math.floor(totalMin / 60);
	const m = totalMin % 60;
	if (!h) return `${m} min`;
	return m ? `${h} h ${m} min` : `${h} h`;
}

function mismoDia(a, b) {
	return (
		a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
	);
}

/**
 * Agrupa los marcados en ciclos.
 *
 * @param {Array} marcados filas de /mi-asistencia/historial (en cualquier orden)
 * @param {Object} opciones
 * @param {Date}   opciones.ahora        instante de referencia para ciclos abiertos
 * @param {number} opciones.horasJornada horas de la jornada diaria (LFT)
 * @returns {Array} ciclos del más nuevo al más viejo
 */
export function agruparCiclos(marcados = [], opciones = {}) {
	const {
		ahora = new Date(),
		horasJornada = HORAS_JORNADA,
		extrasDoblesSemana = EXTRAS_DOBLES_SEMANA,
		extrasMaxDia = EXTRAS_MAX_DIA
	} = opciones;

	const orden = marcados
		.filter(Boolean)
		.map((m) => ({ marcado: m, t: instante(m) }))
		.filter((x) => x.t && (x.marcado.Tipo === 'Entrada' || x.marcado.Tipo === 'Salida'))
		.sort((a, b) => a.t - b.t);

	const ciclos = [];
	let abierto = null;

	for (const { marcado, t } of orden) {
		if (marcado.Tipo === 'Entrada') {
			if (abierto) ciclos.push(cerrarCiclo(abierto, null, ahora, { horasJornada, extrasMaxDia }));
			abierto = { marcado, t };
			continue;
		}
		// Salida
		if (abierto) {
			ciclos.push(
				cerrarCiclo(abierto, { marcado, t }, ahora, { horasJornada, extrasMaxDia })
			);
			abierto = null;
		} else {
			ciclos.push({
				entrada: null,
				salida: marcado,
				inicio: null,
				fin: t,
				horas: null,
				extras: 0,
				dobles: 0,
				triples: 0,
				excede_limite_dia: false,
				abierto: false,
				olvidado: false,
				sinEntrada: true,
				ubicacion: ubicacionDe([marcado])
			});
		}
	}

	if (abierto) ciclos.push(cerrarCiclo(abierto, null, ahora, { horasJornada, extrasMaxDia }));

	// Reparto semanal de extras: dobles hasta 9 h, luego triples.
	const usado = new Map();
	for (const c of ciclos) {
		if (!c.extras || !c.inicio) continue;
		const semana = claveSemana(c.inicio);
		const previo = usado.get(semana) || 0;
		c.dobles = redondear(Math.max(0, Math.min(c.extras, extrasDoblesSemana - previo)));
		c.triples = redondear(Math.max(0, c.extras - c.dobles));
		usado.set(semana, previo + c.extras);
	}

	return ciclos.reverse();
}

function ubicacionDe(marcados) {
	const conGps = marcados.find((m) => m && m.Latitud != null && m.Longitud != null);
	if (!conGps) return null;
	return {
		lat: Number(conGps.Latitud),
		lon: Number(conGps.Longitud),
		precision: conGps.Precision != null ? Number(conGps.Precision) : null
	};
}

function cerrarCiclo(inicio, fin, ahora, { horasJornada, extrasMaxDia }) {
	const esHoy = mismoDia(inicio.t, ahora);
	const finReal = fin ? fin.t : esHoy ? ahora : null;
	const horas = finReal ? redondear((finReal - inicio.t) / 3600000) : null;
	const extras = horas == null ? 0 : redondear(Math.max(0, horas - horasJornada));

	return {
		entrada: inicio.marcado,
		salida: fin ? fin.marcado : null,
		inicio: inicio.t,
		fin: finReal,
		horas,
		extras,
		dobles: 0,
		triples: 0,
		excede_limite_dia: extras > extrasMaxDia,
		abierto: !fin,
		olvidado: !fin && !esHoy,
		sinEntrada: false,
		ubicacion: ubicacionDe([inicio.marcado, fin && fin.marcado])
	};
}
