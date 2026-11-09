<script>
	import { Trash2 } from 'lucide-svelte';

	let { onConfirm, label = 'Borrar', disabled = false, size = 'sm' } = $props();
	let progress = $state(0);
	let interval = null;

	function startHold() {
		if (disabled) return;
		if (!confirm(`¿Eliminar ${label.toLowerCase()}?`)) return;
		progress = 0;
		interval = setInterval(() => {
			progress += 2;
			if (progress >= 100) {
				clearInterval(interval);
				interval = null;
				progress = 0;
				onConfirm();
			}
		}, 40);
	}

	function cancelHold() {
		if (interval) {
			clearInterval(interval);
			interval = null;
		}
		progress = 0;
	}
</script>

<button
	class="btn btn-danger btn-{size} btn-hold"
	onpointerdown={startHold}
	onpointerup={cancelHold}
	onpointerleave={cancelHold}
	disabled={disabled}
>
	<Trash2 size={size === 'sm' ? 16 : 18} />
	<span>{label}</span>
	<div class="hold-fill" style="width: {progress}%"></div>
</button>

<style>
	.btn-hold {
		position: relative;
		overflow: hidden;
	}
	.hold-fill {
		position: absolute;
		top: 0;
		left: 0;
		bottom: 0;
		background: rgba(239, 68, 68, 0.4);
		transition: width 0.04s linear;
		pointer-events: none;
		z-index: 0;
	}
	.btn-hold > * {
		position: relative;
		z-index: 1;
	}
</style>