<!-- ErrorState — componente estándar del shell -->
<script>
  import { AlertTriangle } from 'lucide-svelte';

  let { message = 'Error al cargar', onRetry = null } = $props();
</script>

<div class="error-state">
  <div class="error-icon"><AlertTriangle size={40} strokeWidth={1.5} /></div>
  <p class="error-msg">{message}</p>
  {#if onRetry}
    <button class="btn btn-sm btn-secondary" onclick={onRetry}>Reintentar</button>
  {/if}
</div>

<style>
  .error-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem 1.5rem;
    text-align: center;
    color: var(--color-danger, var(--color-danger));
  }
  .error-icon { font-size: var(--font-size-3xl); margin-bottom: 0.75rem; }
  .error-msg { font-size: var(--font-size-sm); margin: 0 0 1rem; color: var(--color-text-muted, var(--color-text-muted)); }
  .btn { padding: 0.4rem 0.75rem; border-radius: 6px; border: none; cursor: pointer; font-size: var(--font-size-sm); }
  .btn-secondary { background: var(--color-surface-2, var(--color-surface-2)); color: white; }
  .btn-sm { padding: 0.25rem 0.5rem; font-size: var(--font-size-xs); }
</style>