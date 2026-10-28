<script>
	import { online } from '$lib/stores/online.js';
	import { servingFromCache } from '$lib/offline.js';

	// Aviso de trabajo sin conexión para los módulos que ya degradan a la copia
	// local (IndexedDB). El store `servingFromCache` lo pone api.get cuando la
	// respuesta vino de la caché en vez de la red, así que se distingue entre
	// "estás viendo lo último guardado" y "este módulo aún no se descargó".
	let { compacto = false } = $props();
</script>

{#if !$online}
	<div class="aviso-offline" class:compacto role="status">
		{#if $servingFromCache}
			<span>📴 Sin conexión — mostrando los datos guardados en este dispositivo.</span>
		{:else}
			<span>🔴 Sin conexión — todavía no hay una copia guardada de este módulo.</span>
		{/if}
	</div>
{/if}

<style>
	.aviso-offline {
		margin: 0 0 0.75rem;
		padding: 0.55rem 0.7rem;
		border-radius: 8px;
		font-size: 0.8rem;
		background: rgba(239, 68, 68, 0.1);
		border: 1px solid rgba(239, 68, 68, 0.35);
		color: #fca5a5;
	}
	.aviso-offline.compacto {
		padding: 0.35rem 0.5rem;
		font-size: 0.75rem;
	}
</style>
