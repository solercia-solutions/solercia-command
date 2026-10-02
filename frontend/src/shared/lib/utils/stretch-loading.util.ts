import { DestroyRef, Signal, computed, effect, inject, signal } from '@angular/core';

/**
 * "Estira" una señal de carga a un tiempo mínimo visible.
 *
 * Problema: con un backend rápido `loading` pasa de `true` a `false` en pocos
 * ms, así que el skeleton parpadea de forma imperceptible (el usuario "no lo
 * ve"). Este helper mantiene la carga en `true` al menos `minMs` desde que se
 * activó — patrón anti-flash estándar: el estado de carga se PERCIBE sin
 * agregar latencia real a los datos (estos ya llegaron; solo se difiere el
 * apagado visual del skeleton).
 *
 * Debe llamarse dentro de un contexto de inyección (constructor/field
 * initializer): usa `effect` y limpia su timer con el `DestroyRef` del host.
 *
 * @param source señal de carga real (true mientras la petición está en vuelo)
 * @param minMs  tiempo mínimo que el skeleton permanece visible (default 450ms)
 */
export function stretchLoading(source: Signal<boolean>, minMs = 450): Signal<boolean> {
  const visible = signal(source());
  const destroyRef = inject(DestroyRef);
  let onSince = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const clear = (): void => {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  };

  effect(() => {
    const loading = source();
    clear();
    if (loading) {
      onSince = Date.now();
      visible.set(true);
      return;
    }
    // Apagado: respeta el mínimo desde que se encendió.
    const elapsed = Date.now() - onSince;
    if (elapsed >= minMs) {
      visible.set(false);
    } else {
      timer = setTimeout(() => {
        visible.set(false);
        timer = null;
      }, minMs - elapsed);
    }
  });

  destroyRef.onDestroy(clear);

  return computed(() => visible());
}
