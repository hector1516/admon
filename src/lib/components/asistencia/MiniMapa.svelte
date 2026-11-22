<!-- MiniMapa — fragmento de mapa con enlace (Mi Asistencia, D4 A).
     Usa una tesela de OpenStreetMap (256 px, sin API key) y un pin al centro.
     Antes se pedía el mapa estático de staticmap.openstreetmap.de, que se cae a
     menudo: cuando falla no queda imagen y parece que no hay mapa.
     Si la tesela no carga, queda el enlace, que siempre funciona. -->
<script>
	let { lat = null, lon = null, zoom = 16, alto = 160 } = $props();

	let roto = $state(false);
	const hay = $derived(lat != null && lon != null);

	/** Tesela (x, y) de OSM que contiene el punto (slippy map estándar). */
	function tesela(latitud, longitud, z) {
		const n = 2 ** z;
		const x = Math.floor(((longitud + 180) / 360) * n);
		const rad = (latitud * Math.PI) / 180;
		const y = Math.floor(
			((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * n
		);
		return { x, y };
	}

	const t = $derived(hay ? tesela(Number(lat), Number(lon), zoom) : null);
	const img = $derived(
		t ? `https://tile.openstreetmap.org/${zoom}/${t.x}/${t.y}.png` : null
	);
	const url = $derived(hay ? `https://www.google.com/maps?q=${lat},${lon}` : null);
	const coords = $derived(
		hay ? `${Number(lat).toFixed(5)}, ${Number(lon).toFixed(5)}` : ''
	);
</script>

{#if hay}
	<div class="mini-mapa">
		{#if !roto}
			<a class="marco" href={url} target="_blank" rel="noopener" title="Abrir en Google Maps">
				<img
					src={img}
					alt="Mapa de la ubicación"
					loading="lazy"
					style="height: {alto}px"
					onerror={() => (roto = true)}
				/>
				<span class="pin" aria-hidden="true"></span>
			</a>
		{/if}
		<div class="pie">
			<span class="coords">{coords}</span>
			<a class="ver-mapa" href={url} target="_blank" rel="noopener">Ver en el mapa →</a>
		</div>
	</div>
{/if}

<style>
	.mini-mapa {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		margin-top: 0.6rem;
	}
	.marco {
		position: relative;
		display: block;
		border-radius: var(--radius-xs);
		overflow: hidden;
		border: 1px solid var(--color-line);
		background: var(--color-surface-2);
	}
	/* La tesela de OSM es clara: se invierte para que case con el tema. */
	.marco img {
		display: block;
		width: 100%;
		object-fit: cover;
		filter: invert(1) hue-rotate(180deg) brightness(0.92) contrast(0.9);
	}
	.pin {
		position: absolute;
		top: 50%;
		left: 50%;
		width: 0.7rem;
		height: 0.7rem;
		margin: -0.35rem 0 0 -0.35rem;
		border-radius: 999px;
		background: var(--color-info);
		box-shadow: 0 0 0 2px var(--color-surface);
	}
	.pie {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
	.coords {
		font-size: var(--font-size-2xs);
		color: var(--color-text-dim);
		font-variant-numeric: tabular-nums;
	}
	.ver-mapa {
		font-size: var(--font-size-xs);
		color: var(--color-text-strong);
		text-decoration: underline;
		text-underline-offset: 2px;
	}
	.ver-mapa:hover {
		color: var(--color-info);
	}
</style>
