<script>
	// Campo de contraseña con botón para mostrar/ocultar (modo runes).
	let { value = $bindable(''), id = '', placeholder = '', autocomplete = 'new-password' } = $props();
	let show = $state(false);
</script>

<div class="pw-wrap">
	<input
		{id}
		type={show ? 'text' : 'password'}
		class="input pw-input"
		{placeholder}
		{autocomplete}
		bind:value
	/>
	<button type="button" class="pw-toggle" on:click={() => (show = !show)} title={show ? 'Ocultar contraseña' : 'Mostrar contraseña'}>
		{show ? '🙈' : '👁️'}
	</button>
</div>

<style>
	.pw-wrap { position: relative; }
	.pw-input { padding-right: 2.75rem; }
	.pw-toggle {
		position: absolute;
		right: 0.4rem;
		top: 50%;
		transform: translateY(-50%);
		background: none;
		border: none;
		font-size: 1.1rem;
		cursor: pointer;
		padding: 0.25rem;
		line-height: 1;
	}
</style>
