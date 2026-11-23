/*
 * ciclos.js — agrupa los marcados de Mi Asistencia en ciclos entrada→salida.
 *
 * Horas extra (decidido el 2026-11-21): **solo el tiempo fuera del horario
 * asignado**. Si el horario del día es 09:00–18:30, entrar 08:20 suma 40 min y
 * salir 19:10 suma otros 40, aunque la persona no haya cumplido el horario
 * completo. Se aplica tal cual, sin condiciones.
 *
 * - Día de descanso trabajado → todo el turno es extra.
 * - Sin horario asignado → se mantiene la regla vieja (lo que pase de la
 *   jornada), para no romper a quien todavía no tiene horario.
 * - La comida fija del día se descuenta de las horas trabajadas solo si estuvo
 *   al menos la jornada + la comida; si se fue antes, no se descuenta.
 * - La LFT reparte la extra semanal: primeras 9 h dobles, el resto triples, y
 *   avisa si un día pasa de 3 h.
 *
 * Sin dependencias: se prueba con `node --test` (ver tests/).
 */

export const HORAS_JORNADA = 8;
export const EXTRAS_DOBLES_SEMANA = 9;
export const EXTRAS_MAX_DIA = 3;

/** 'HH:MM' o 'HH:MM:SS' → minutos desde medianoche. `null` si no se entiende. */
export function minutos(hora) {
	if (hora == null) return null;
	const partes = String(hora).split(':');
	if (partes.length < 2) return null;
	const h = Number(partes[0]);
	const m = Number(partes[1]);
	if (Number.isNaN(h) || Number.isNaN(m)) return null;
	return h * 60 + m;
}

/** Convierte Fecha + Hora de un marcado en un Date local (nunca UTC). */
export function instante(marcado) {
	if (!marcado || !marcado.Fecha || !marcado.Hora) return null;
	const fecha =
		marcado.Fecha instanceof Date
			? `${marcado.Fecha.getFullYear()}-${String(marcado.Fecha.getMonth() + 1).padStart(2, '0')}-${String(
					marcado.Fecha.getDate()
				).padStart(2, '0')}`
			: String(marcado.Fecha).slice(0, 10);
	const d = new Date(`${fecha}T${String(marcado.Hora).slice(0, 8)}`);
	return Number.isNaN(d.getTime()) ? null : d;
}

/** Lunes de la semana de esa fecha, como clave `YYYY-M-D`. */
export function claveSemana(fecha) {
	const d = new Date(fecha.getFullYear(), fecha.getMonth(), fecha.getDate());
	const desdeLunes = (d.getDay() + 6) % 7; // domingo=6, lunes=0
	d.setDate(d.getDate() - desdeLunes);
	return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

/** Día ISO de la fecha: 1 = lunes … 7 = domingo. */
export function diaIso(fecha) {
	return ((fecha.getDay() + 6) % 7) + 1;
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
	return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/**
 * Minutos fuera de la ventana del horario.
 * Devuelve `{ antes, despues }` en minutos, o `null` si el día es descanso.
 */
function minutosFuera(inicio, fin, sched) {
	const eS = minutos(sched.entrada);
	const sS = minutos(sched.salida);
	if (eS == null || sS == null) return null;

	let eA = inicio.getHours() * 60 + inicio.getMinutes();
	let sA = fin.getHours() * 60 + fin.getMinutes();
	let salidaProg = sS;
	if (salidaProg < eS) salidaProg += 1440; // horario nocturno
	if (sA < eA) sA += 1440; // el turno cruzó medianoche

	return {
		antes: Math.max(0, eS - eA),
		despues: Math.max(0, sA - salidaProg)
	};
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

/**
 * Agrupa los marcados en ciclos.
 *
 * @param {Array} marcados filas de /mi-asistencia/historial
 * @param {Object} opciones
 * @param {Date}   opciones.ahora               instante de referencia para ciclos abiertos
 * @param {number} opciones.horasJornada        jornada de la LFT (respaldo sin horario)
 * @param {Object} opciones.horario             mapa día ISO → { entrada, salida, comida } o null
 */
export function agruparCiclos(marcados = [], opciones = {}) {
	const {
		ahora = new Date(),
		horasJornada = HORAS_JORNADA,
		extrasDoblesSemana = EXTRAS_DOBLES_SEMANA,
		extrasMaxDia = EXTRAS_MAX_DIA,
		horario = null
	} = opciones;

	const orden = marcados
		.filter(Boolean)
		.map((m) => ({ marcado: m, t: instante(m) }))
		.filter((x) => x.t && (x.marcado.Tipo === 'Entrada' || x.marcado.Tipo === 'Salida'))
		.sort((a, b) => a.t - b.t);

	const config = { horasJornada, extrasMaxDia, horario };
	const ciclos = [];
	let abierto = null;

	for (const { marcado, t } of orden) {
		if (marcado.Tipo === 'Entrada') {
			if (abierto) ciclos.push(cerrarCiclo(abierto, null, ahora, config));
			abierto = { marcado, t };
			continue;
		}
		if (abierto) {
			ciclos.push(cerrarCiclo(abierto, { marcado, t }, ahora, config));
			abierto = null;
		} else {
			ciclos.push({
				entrada: null,
				salida: marcado,
				inicio: null,
				fin: t,
				horas: null,
				extras: 0,
				extra_antes: 0,
				extra_despues: 0,
				dobles: 0,
				triples: 0,
				excede_limite_dia: false,
				abierto: false,
				olvidado: false,
				sinEntrada: true,
				comida: 0,
				horario: null,
				ubicacion: ubicacionDe([marcado])
			});
		}
	}

	if (abierto) ciclos.push(cerrarCiclo(abierto, null, ahora, config));

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

function cerrarCiclo(inicio, fin, ahora, { horasJornada, extrasMaxDia, horario }) {
	const esHoy = mismoDia(inicio.t, ahora);
	const finReal = fin ? fin.t : esHoy ? ahora : null;
	const sched = horario ? horario[diaIso(inicio.t)] ?? null : undefined;

	// ── horas trabajadas ────────────────────────────────────────────────────
	const bruto = finReal ? (finReal - inicio.t) / 3600000 : null;
	let comida = 0;
	if (finReal && sched && !sched.descanso) {
		// La comida se descuenta si estuvo presente al menos todo el tramo del
		// horario (de la entrada a la salida programadas).
		const tramo = Math.max(0, (minutos(sched.salida) - minutos(sched.entrada)) / 60);
		const comidaDia = Number(sched.comida) || 0;
		if (bruto >= tramo) comida = comidaDia;
	}
	const horas = bruto == null ? null : redondear(Math.max(0, bruto - comida / 60));

	// ── extras ──────────────────────────────────────────────────────────────
	let minAntes = 0;
	let minDespues = 0;
	if (horas != null) {
		if (horario == null) {
			// Sin horario asignado: regla de la jornada (la de antes).
			minDespues = Math.max(0, horas - horasJornada) * 60;
		} else if (!sched || sched.descanso) {
			// Día de descanso trabajado: todo el turno es extra.
			minDespues = horas * 60;
		} else {
			const fuera = minutosFuera(inicio.t, finReal, sched);
			if (fuera) {
				minAntes = fuera.antes;
				minDespues = fuera.despues;
			}
		}
	}
	const extras = redondear((minAntes + minDespues) / 60);
	const extra_antes = redondear(minAntes / 60);
	const extra_despues = redondear(minDespues / 60);

	return {
		entrada: inicio.marcado,
		salida: fin ? fin.marcado : null,
		inicio: inicio.t,
		fin: finReal,
		horas,
		comida,
		extras,
		extra_antes,
		extra_despues,
		dobles: 0,
		triples: 0,
		excede_limite_dia: extras > extrasMaxDia,
		abierto: !fin,
		olvidado: !fin && !esHoy,
		sinEntrada: false,
		horario: sched || null,
		ubicacion: ubicacionDe([inicio.marcado, fin && fin.marcado])
	};
}


// ── Distancia a la oficina y viáticos ─────────────────────────────────
// El establecimiento está en Fray Luis de León 1713, Jardín Español,
// Monterrey. La LISR (art. 28, fracc. V) solo permite deducir gastos de
// viaje fuera de una faja de 50 km alrededor del establecimiento, así que la
// distancia se mide EN LÍNEA RECTA desde aquí, no como recorrido del día.
export const OFICINA_DEFECTO = { lat: 25.662117, lon: -100.280684 };
export const VIATICOS_KM_DEFECTO = 50;

const RADIO_TIERRA_KM = 6371.0088;

/**
 * Distancia en km entre dos coordenadas (haversine). `null` si falta alguna
 * o si están en (0,0): los dispositivos sin GPS reportan 0,0 y tomarlo como
 * ubicación real daría ~1,100 km de distancia.
 */
export function distanciaKm(lat1, lon1, lat2, lon2) {
	const [a, b, c, d] = [lat1, lon1, lat2, lon2].map(Number);
	if (![a, b, c, d].every(Number.isFinite)) return null;
	if ((a === 0 && b === 0) || (c === 0 && d === 0)) return null;
	const rad = (g) => (g * Math.PI) / 180;
	const dLat = rad(c - a);
	const dLon = rad(d - b);
	const h = Math.sin(dLat / 2) ** 2 +
		Math.cos(rad(a)) * Math.cos(rad(c)) * Math.sin(dLon / 2) ** 2;
	return 2 * RADIO_TIERRA_KM * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function distanciaDelCiclo(ciclo, oficina = OFICINA_DEFECTO) {
	let mejor = null;
	for (const m of [ciclo?.entrada, ciclo?.salida]) {
		if (!m) continue;
		const km = distanciaKm(m.Latitud, m.Longitud, oficina?.lat, oficina?.lon);
		if (km == null) continue;
		const p = Number(m.Precision);
		const orden = Number.isFinite(p) ? p : Infinity;
		if (!mejor || orden < mejor.orden) {
			mejor = { km, orden, precision: Number.isFinite(p) ? p : null };
		}
	}
	if (!mejor) return { km: null, enOficina: false, precision: null };
	return { km: mejor.km, enOficina: mejor.km < 0.3, precision: mejor.precision };
}

/**
 * Resumen del día: la MAYOR distancia a la oficina entre los marcados con GPS.
 * `aplica` es la regla de viáticos (>= umbral, por defecto 50 km).
 */
export function resumenViatico(ciclos = [], opciones = {}) {
	const { oficina = OFICINA_DEFECTO, umbralKm = VIATICOS_KM_DEFECTO } = opciones;
	let maxKm = null;
	for (const ciclo of ciclos) {
		const { km } = distanciaDelCiclo(ciclo, oficina);
		if (km == null) continue;
		if (maxKm == null || km > maxKm) maxKm = km;
	}
	if (maxKm == null) return { maxKm: null, aplica: false, sinGps: true };
	return { maxKm, aplica: maxKm >= Number(umbralKm), sinGps: false };
}
