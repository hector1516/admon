<!-- SyncHeader — skin: ingram (rediseñado, incluye bottom nav) -->
<script>
  import { onMount } from 'svelte';

  let { usuario = '', appVersion = '', shellVersion = '', fetcher = null, onsync = null, navItems = null, destacado = '/mi-asistencia' } = $props();

  // --- Nombre del módulo actual ---
  function getModuleName() {
    if (typeof window === 'undefined') return 'App';
    const p = window.location.pathname;
    const NOMBRES = {
      '/': 'App', '/dashboard': 'Dashboard', '/cotizaciones': 'Cotizaciones',
      '/cotizaciones/nueva': 'Nueva Cotización', '/clientes': 'Clientes',
      '/admin': 'Administración', '/legends': 'ECCSA Legends',
      '/estatus_servicios': 'Estatus de Servicios', '/kilometros': 'Kilómetros',
      '/tickets_oxxogas': 'Tickets OxxoGas', '/ia': 'ECCSA IA',
      '/panel': 'Dashboard', '/config': 'Configuración', '/perfil': 'Perfil',
      '/busqueda': 'Búsqueda', '/notas': 'Notas', '/firmas': 'Firmas',
      '/reglas': 'Reglas', '/redactar': 'Redactar', '/notificaciones': 'Notificaciones',
      '/tickets': 'Tickets', '/vales': 'Vales', '/reportes': 'Reportes',
      '/': 'Home', '/tickets': 'Tickets', '/kilometros': 'Kilometros', '/configuracion': 'Configuracion', '/conocimiento': 'Conocimiento', '/vm': 'VM', '/repositorio': 'Repositorio', '/remisiones': 'Remisiones',
    };
    if (NOMBRES[p]) return NOMBRES[p];
    if (p.startsWith('/cotizaciones/')) return 'Detalle Cotización';
    if (p.startsWith('/clientes/')) return 'Detalle Cliente';
    if (p.startsWith('/tickets_oxxogas/')) return 'Detalle Ticket';
    if (p.startsWith('/kilometros/')) return 'Detalle Kilómetros';
    if (p.startsWith('/cuenta/')) return 'Cuenta';
    return 'App';
  }

  let nombreModulo = $state(getModuleName());
  let urlCopiada = $state(false);
  let navVisible = $state(true);
  let lastScrollY = 0;
  let ticking = false;

  function handleScroll() {
    if (!ticking) {
      requestAnimationFrame(() => {
        const currentScrollY = window.scrollY;
        if (currentScrollY > lastScrollY + 50) {
          navVisible = false;
        } else if (currentScrollY < lastScrollY) {
          navVisible = true;
        }
        lastScrollY = currentScrollY;
        ticking = false;
      });
      ticking = true;
    }
  }

  onMount(() => {
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  });

  async function copiarUrl() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      urlCopiada = true;
      setTimeout(() => urlCopiada = false, 2000);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = window.location.href;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      urlCopiada = true;
      setTimeout(() => urlCopiada = false, 2000);
    }
  }

  function navigate(path) {
    if (typeof window !== 'undefined') {
      window.location.href = path;
    }
  }

  // Tres destinos: inicio y los dos laterales. El del centro es siempre Mi
  // Asistencia (`destacado`), así que aquí no se pide.
  const _navRoutes = (Array.isArray(navItems) && navItems.length >= 3)
    ? navItems
    : ['/dashboard', '/legends', '/perfil'];
  const _navItems = [
    { action: () => { if (window.history.length > 1) window.history.back(); else navigate(_navRoutes[0] || '/'); } },
    { action: () => navigate(_navRoutes[0] || '/') },
    { action: () => navigate(destacado) },
    { action: () => navigate(_navRoutes[1] || '/') },
    { action: () => navigate(_navRoutes[2] || '/') },
  ];

  function isActiveNav(index) {
    const p = typeof window !== 'undefined' ? window.location.pathname : '';
    if (index === 0) return false;
    if (index === 1) return p === (_navRoutes[0] || '/') || p === '/' || p === '';
    if (index === 2) return p === destacado;
    if (index === 3) return p === (_navRoutes[1] || '/');
    if (index === 4) return p === (_navRoutes[2] || '/');
    return false;
  }
</script>

<!-- Banner superior -->
<header class="sync-header" class:hidden={!navVisible}>
  <div class="sh-row sh-top">
    <span class="sh-modulo">{nombreModulo}</span>
    {#if usuario}
      <span class="sh-usuario">{usuario}</span>
    {/if}
  </div>
  <div class="sh-row sh-url" onclick={copiarUrl} role="button" tabindex="0">
    <span class="sh-url-text">{typeof window !== 'undefined' ? window.location.href : ''}</span>
    {#if urlCopiada}
      <span class="sh-copiado">Copiado!</span>
    {/if}
  </div>
</header>

<!-- Barra inferior -->
<nav class="bottom-nav" class:hidden={!navVisible}>
  {#each _navItems as item, i}
    <button
      class="nav-item"
      class:active={isActiveNav(i)}
      class:destacado={i === 2}
      onclick={item.action}
      aria-label={i === 2 ? 'Mi Asistencia' : 'nav'}
    >
      {#if i === 0}
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 19-7-7 7-7"/><path d="M19 12H5"/></svg>
      {:else if i === 1}
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
      {:else if i === 2}
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
      {:else if i === 3}
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/></svg>
      {:else}
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
      {/if}
    </button>
  {/each}
</nav>

<style>
  .sync-header {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: var(--z-nav, 100);
    padding: 0.5rem 1rem;
    background: rgba(15, 23, 42, 0.85);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
    will-change: transform;
  }
  .sync-header.hidden {
    transform: translateY(-100%);
  }
  .sh-row { display: flex; align-items: center; gap: 0.5rem; }
  .sh-top { justify-content: space-between; }
  .sh-modulo { font-size: var(--font-size-lg); font-weight: 700; color: var(--color-text, var(--color-text-strong)); }
  .sh-usuario { font-size: var(--font-size-xs); color: var(--color-text-muted, var(--color-text-muted)); }
  .sh-url { cursor: pointer; margin-top: 0.15rem; }
  .sh-url-text {
    font-size: var(--font-size-2xs); font-family: monospace;
    color: var(--color-text-muted, var(--color-text-muted));
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    max-width: 85%;
  }
  .sh-copiado { font-size: var(--font-size-2xs); color: var(--color-primary, var(--color-primary)); font-weight: 600; }

  .bottom-nav {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    z-index: var(--z-nav, 100);
    background: rgba(15, 23, 42, 0.85);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    display: flex;
    justify-content: space-around;
    padding: 0.4rem 0;
    padding-bottom: max(0.4rem, env(safe-area-inset-bottom));
    transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
    will-change: transform;
  }
  .bottom-nav.hidden {
    transform: translateY(100%);
  }
  .nav-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.15rem;
    padding: 0.4rem 0.75rem;
    border-radius: var(--radius-xs, 4px);
    cursor: pointer;
    transition: all 0.15s;
    color: var(--color-text-muted, var(--color-text-muted));
    background: none;
    border: none;
    font-family: inherit;
    min-width: 50px;
    min-height: 44px;
  }
  .nav-item.active {
    color: var(--color-primary, var(--color-primary));
    background: rgba(255, 107, 0, 0.1);
  }

  /* Botón central destacado (Mi Asistencia): más grande, elevado y en acento.
     Es la acción que la gente hace dos veces al día, así que gana el pulgar. */
  .nav-item.destacado {
    width: 3.4rem;
    height: 3.4rem;
    min-width: 3.4rem;
    border-radius: 999px;
    background: var(--color-info);
    color: var(--color-surface);
    transform: translateY(-14px);
    box-shadow: 0 8px 20px color-mix(in srgb, var(--color-info) 45%, transparent);
  }
  .nav-item.destacado:active {
    transform: translateY(-12px) scale(0.96);
  }
</style>