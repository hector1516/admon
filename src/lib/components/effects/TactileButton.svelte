<!-- TactileButton.svelte — Botón físico con cara moldeada, borde firme y profundidad compresible -->
<script lang="ts">
  interface Props {
    label?: string;
    variant?: 'primary' | 'secondary' | 'danger' | 'success';
    size?: 'sm' | 'md' | 'lg';
    disabled?: boolean;
    onclick?: (e: MouseEvent) => void;
    children?: any;
  }

  let {
    label = '',
    variant = 'primary',
    size = 'md',
    disabled = false,
    onclick,
    children
  }: Props = $props();

  let pressed = $state(false);

  function handlePointerDown() {
    if (!disabled) pressed = true;
  }

  function handlePointerUp() {
    pressed = false;
  }

  function handlePointerLeave() {
    pressed = false;
  }
</script>

<button
  class="tactile-btn tactile-{variant} tactile-{size}"
  class:pressed
  class:disabled
  {disabled}
  onpointerdown={handlePointerDown}
  onpointerup={handlePointerUp}
  onpointerleave={handlePointerLeave}
  onclick={onclick}
>
  <span class="tactile-face">
    {#if children}
      {@render children()}
    {:else}
      {label}
    {/if}
  </span>
</button>

<style>
  .tactile-btn {
    position: relative;
    border: none;
    background: transparent;
    cursor: pointer;
    padding: 0;
    font-family: inherit;
    user-select: none;
    -webkit-user-select: none;
    touch-action: manipulation;
  }

  .tactile-btn.disabled {
    opacity: 0.5;
    cursor: not-allowed;
    pointer-events: none;
  }

  .tactile-face {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    border-radius: 12px;
    font-weight: 600;
    transition: transform 0.1s ease, box-shadow 0.1s ease;
    position: relative;
    z-index: 1;
  }

  /* Sizes */
  .tactile-sm .tactile-face { padding: 0.375rem 0.75rem; font-size: var(--font-size-xs); }
  .tactile-md .tactile-face { padding: 0.625rem 1.25rem; font-size: var(--font-size-base); }
  .tactile-lg .tactile-face { padding: 0.875rem 1.75rem; font-size: var(--font-size-lg); }

  /* Variants */
  .tactile-primary .tactile-face {
    background: linear-gradient(180deg, #FF8C33 0%, var(--color-primary) 100%);
    color: var(--color-white);
    box-shadow:
      0 4px 0 #CC5500,
      0 6px 12px rgba(255, 107, 0, 0.3),
      inset 0 1px 0 rgba(255, 255, 255, 0.2);
  }
  .tactile-primary.pressed .tactile-face {
    transform: translateY(3px);
    box-shadow:
      0 1px 0 #CC5500,
      0 2px 4px rgba(255, 107, 0, 0.2),
      inset 0 1px 0 rgba(255, 255, 255, 0.1);
  }

  .tactile-secondary .tactile-face {
    background: linear-gradient(180deg, var(--color-surface-2) 0%, var(--color-surface) 100%);
    color: var(--color-text-soft);
    box-shadow:
      0 4px 0 var(--color-bg),
      0 6px 12px rgba(0, 0, 0, 0.3),
      inset 0 1px 0 rgba(255, 255, 255, 0.1);
  }
  .tactile-secondary.pressed .tactile-face {
    transform: translateY(3px);
    box-shadow:
      0 1px 0 var(--color-bg),
      0 2px 4px rgba(0, 0, 0, 0.2),
      inset 0 1px 0 rgba(255, 255, 255, 0.05);
  }

  .tactile-danger .tactile-face {
    background: linear-gradient(180deg, var(--color-danger) 0%, #DC2626 100%);
    color: var(--color-white);
    box-shadow:
      0 4px 0 var(--color-danger-dark),
      0 6px 12px rgba(220, 38, 38, 0.3),
      inset 0 1px 0 rgba(255, 255, 255, 0.2);
  }
  .tactile-danger.pressed .tactile-face {
    transform: translateY(3px);
    box-shadow:
      0 1px 0 var(--color-danger-dark),
      0 2px 4px rgba(220, 38, 38, 0.2),
      inset 0 1px 0 rgba(255, 255, 255, 0.1);
  }

  .tactile-success .tactile-face {
    background: linear-gradient(180deg, var(--color-success) 0%, #16A34A 100%);
    color: var(--color-white);
    box-shadow:
      0 4px 0 #15803D,
      0 6px 12px rgba(22, 163, 74, 0.3),
      inset 0 1px 0 rgba(255, 255, 255, 0.2);
  }
  .tactile-success.pressed .tactile-face {
    transform: translateY(3px);
    box-shadow:
      0 1px 0 #15803D,
      0 2px 4px rgba(22, 163, 74, 0.2),
      inset 0 1px 0 rgba(255, 255, 255, 0.1);
  }
</style>