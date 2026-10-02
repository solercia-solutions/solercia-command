import { DestroyRef, inject, signal, type Signal } from '@angular/core';

/**
 * Breakpoint móvil canónico del proyecto (estructura base, NO tematizable).
 *
 * Bajo este ancho la aplicación cambia a su comportamiento móvil BASE:
 * bottom-nav en lugar de sidebar, header sin botón de menú y objetivos
 * táctiles de 44 px. Un tema JSON no puede alterarlo — los tokens solo
 * estilizan la estructura resultante.
 *
 * El valor coincide con el que usan las hojas de estilo de los widgets del
 * shell (max-width: 767px).
 */
export const MOBILE_BREAKPOINT_PX = 768;

/** Media query canónica de viewport móvil (equivalente CSS: `@media (max-width: 767px)`). */
export const MOBILE_MEDIA_QUERY = `(max-width: ${MOBILE_BREAKPOINT_PX - 1}px)`;

/**
 * Convierte una media query en una señal booleana reactiva al viewport.
 *
 * Debe invocarse en contexto de inyección (constructor o inicializador de
 * campo): usa `DestroyRef` para retirar el listener al destruirse el
 * consumidor. Guarda para jsdom/SSR: sin `window.matchMedia` la señal queda
 * en `false` estático (comportamiento desktop, igual que hoy).
 */
export function observeMediaQuery(query: string): Signal<boolean> {
  const destroyRef = inject(DestroyRef);
  const matches = signal(false);

  // matchMedia no existe en jsdom — sin señal del sistema, se asume desktop.
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return matches.asReadonly();
  }

  const mediaQueryList = window.matchMedia(query);
  matches.set(mediaQueryList.matches);

  // addEventListener puede faltar en mocks minimalistas — guarda defensiva.
  if (typeof mediaQueryList.addEventListener === 'function') {
    const onChange = (event: MediaQueryListEvent): void => matches.set(event.matches);
    mediaQueryList.addEventListener('change', onChange);
    destroyRef.onDestroy(() => mediaQueryList.removeEventListener('change', onChange));
  }

  return matches.asReadonly();
}

/**
 * Señal reactiva de "viewport móvil" según el breakpoint canónico.
 * Azúcar sobre `observeMediaQuery(MOBILE_MEDIA_QUERY)`.
 */
export function observeMobileViewport(): Signal<boolean> {
  return observeMediaQuery(MOBILE_MEDIA_QUERY);
}
