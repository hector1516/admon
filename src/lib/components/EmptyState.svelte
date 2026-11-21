<!-- EmptyState — componente estándar del shell -->
<script>
  import { Inbox, Search, BookOpen, Monitor, Package } from 'lucide-svelte';

  let { icon = '📭', icono = null, title = 'Sin datos', description = '', actionLabel = '', action = null } = $props();

  // Los emojis que hoy pasan las apps se dibujan como icono de lucide, para
  // que el estado vacío hable el mismo idioma visual que el resto de la UI.
  // `icono` permite pasar un componente propio cuando haga falta.
  const MAPA = {
    '📭': Inbox, '📥': Inbox, '🔍': Search, '🔎': Search,
    '📖': BookOpen, '📚': BookOpen, '🖥️': Monitor, '🖥': Monitor,
    '📦': Package
  };

  let Icono = $derived(icono || MAPA[icon] || null);
</script>

<div class="empty-state">
  <div class="empty-icon">
    {#if Icono}
      <svelte:component this={Icono} size={48} strokeWidth={1.5} />
    {:else}
      {icon}
    {/if}
  </div>
  <h3 class="empty-title">{title}</h3>
  {#if description}
    <p class="empty-desc">{description}</p>
  {/if}
  {#if actionLabel && action}
    <button class="btn btn-primary btn-sm" onclick={action}>{actionLabel}</button>
  {/if}
</div>

<style>
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem 1.5rem;
    text-align: center;
    color: var(--color-text-muted, var(--color-text-muted));
  }
  .empty-icon { font-size: 3rem; line-height: 1; margin-bottom: 1rem; opacity: 0.6; }
  .empty-title { font-size: var(--font-size-base); font-weight: 600; margin: 0 0 0.5rem; color: var(--color-text, var(--color-text-strong)); }
  .empty-desc { font-size: var(--font-size-sm); line-height: 1.5; margin: 0 0 1rem; max-width: 300px; }
  .btn { padding: 0.4rem 0.75rem; border-radius: 6px; border: none; cursor: pointer; font-size: var(--font-size-sm); }
  .btn-primary { background: var(--color-primary, var(--color-info)); color: white; }
  .btn-sm { padding: 0.25rem 0.5rem; font-size: var(--font-size-xs); }
</style>
