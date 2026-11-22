<!-- MiniMapa — fragmento de mapa con enlace (Mi Asistencia, D4 A).
     Usa el mapa estático de OpenStreetMap (sin API key) y cae al enlace si la
     imagen no carga o no hay red. -->
<script>
	let { lat = null, lon = null, ancho = 280, alto = 140, zoom = 16 } = $props();

	let roto = $state(false);
	const hay = $derived(lat != null && lon != null);
	const url = $derived(hay ? `https://www.google.com/maps?q=${lat},${lon}` : null);
	const img = $derived(
		hay
			? `https://staticmap.openstreetmap.de/staticmap.php?center=${lat},${lon}` +
				`&zoom=${zoom}&size=${ancho}x${alto}&markers=${lat},${lon},red-pushpin`
			: null
	);
</script>

{#if hay}
	<div class="mini-mapa">
		{#if !roto}
			<a href={url} target="_blank" rel="noopener" title="Ver en Google Maps">
				<img
					src={img}
					alt="Ubicación de la comprobación"
					width={ancho}
					height={alto}
					loading="lazy"
					onerror={() => (roto = true)}
				/>
			</a>
		{/if}
		<a class="ver-mapa" href={url} target="_blank" rel="noopener">Ver en el mapa</a>
	</div>
{/if}

<style>
	.mini-mapa {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		margin-top: 0.6rem;
	}
	.mini-mapa img {
		display: block;
		width: 100%;
		max-width: 280px;
		height: auto;
		border-radius: var(--radius-xs);
		border: 1px solid var(--color-line);
		/* Las teselas de OpenStreetMap son claras: en una app oscura el mapa se
		   veía como un recuadro blanco. Se invierte para que case con el tema. */
		filter: invert(1) hue-rotate(180deg) brightness(0.9) contrast(0.9);
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
