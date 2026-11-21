<!-- PageLayout — componente estándar del shell -->
<script>
  import { onMount } from 'svelte';

  let { title = '', subtitle = '', showBack = true, actions = null, children } = $props();

  function goBack() {
    if (window.history.length > 1) {
      window.history.back();
    } else {
      window.location.href = '/dashboard';
    }
  }
</script>

<div class="page-layout">
  <div class="page-header">
    <div class="header-left">
      {#if showBack}
        <button class="btn-back" onclick={goBack} aria-label="Volver">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 19-7-7 7-7"/><path d="M19 12H5"/></svg>
        </button>
      {/if}
      <div class="header-titles">
        <h1 class="page-title">{title}</h1>
        {#if subtitle}
          <p class="page-subtitle">{subtitle}</p>
        {/if}
      </div>
    </div>
    {#if actions}
      <div class="header-actions">
        {@render actions()}
      </div>
    {/if}
  </div>
  <div class="page-content">
    {@render children()}
  </div>
</div>

<style>
  .page-layout { display: flex; flex-direction: column; gap: 0; }
  .page-header {
    display: flex; align-items: center; justify-content: space-between;
    gap: 0.75rem; margin-bottom: 1rem;
  }
  .header-left { display: flex; align-items: center; gap: 0.5rem; }
  .btn-back {
    background: none; border: none; cursor: pointer;
    color: var(--color-text-muted, var(--color-text-muted));
    padding: 0.4rem; border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
    transition: background 0.15s;
  }
  .btn-back:hover { background: var(--color-surface-2, var(--color-surface-2)); }
  .header-titles { display: flex; flex-direction: column; gap: 0; }
  .page-title { font-size: var(--font-size-xl); font-weight: 700; margin: 0; color: var(--color-text, var(--color-text-strong)); }
  .page-subtitle { font-size: var(--font-size-xs); color: var(--color-text-muted, var(--color-text-muted)); margin: 0; }
  .header-actions { display: flex; gap: 0.5rem; align-items: center; }
  .page-content { display: flex; flex-direction: column; gap: 0.75rem; }
</style>