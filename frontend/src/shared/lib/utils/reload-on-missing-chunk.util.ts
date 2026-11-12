import type { NavigationError } from '@angular/router';

/**
 * Un rebuild cambia el hash de TODOS los chunks (`outputHashing: "all"` en angular.json) y el
 * servidor responde 404 a los que ya no existen. Una pestaña abierta antes del despliegue sigue
 * ejecutando el `main` anterior: al abrir por primera vez una ruta perezosa pide un chunk que ya
 * no está, `loadComponent` rechaza y el router aborta la navegación sin pintar nada ni avisar.
 * Aquí se reconoce ese fallo y se recarga la página completa sobre la URL destino, que trae el
 * `index.html` nuevo. Cualquier otro error de navegación se deja pasar intacto.
 */
export const MISSING_CHUNK_PATTERN =
  /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|ChunkLoadError/i;

/** Última URL por la que se recargó; evita el bucle si el despliegue quedó incompleto. */
export const MISSING_CHUNK_RELOAD_KEY = 'sol-reload-missing-chunk';

/** Dependencias sustituibles en pruebas: el storage de sesión y la recarga de página. */
export interface MissingChunkReloadDeps {
  storage: Pick<Storage, 'getItem' | 'setItem'> | null;
  assign: (url: string) => void;
}

function defaultDeps(): MissingChunkReloadDeps {
  let storage: MissingChunkReloadDeps['storage'] = null;
  try {
    storage = globalThis.sessionStorage ?? null;
  } catch {
    // Sin storage (modo privado restringido) se recarga igual, una sola vez por instancia.
  }
  return { storage, assign: (url) => globalThis.location.assign(url) };
}

/**
 * Devuelve `true` si el error corresponde a un chunk que ya no existe en el servidor
 * (Chrome/Edge, Safari, Firefox y webpack usan mensajes distintos).
 */
export function isMissingChunkError(error: unknown): boolean {
  const cause = error as { message?: unknown } | undefined;
  const message = String(cause?.message ?? error ?? '');
  return MISSING_CHUNK_PATTERN.test(message);
}

/**
 * Desenlace del manejador:
 * - `ignored`: el error no es de chunk faltante y sigue su curso normal.
 * - `reloaded`: se recargó la página sobre la URL destino.
 * - `blocked`: la misma URL ya había fallado tras una recarga (despliegue incompleto);
 *   no se recarga de nuevo y el llamador debe avisarle a la persona usuaria, porque el
 *   router deja la navegación abortada sin pintar nada.
 */
export type MissingChunkOutcome = 'ignored' | 'reloaded' | 'blocked';

/**
 * Manejador para `withNavigationErrorHandler`: recarga la página sobre `error.url` la
 * primera vez que falla un chunk; si la misma URL vuelve a fallar tras recargar, corta
 * el bucle y devuelve `blocked`.
 */
export function reloadOnMissingChunk(
  error: NavigationError,
  deps: MissingChunkReloadDeps = defaultDeps(),
): MissingChunkOutcome {
  if (!isMissingChunkError(error.error)) return 'ignored';

  let alreadyReloaded = false;
  try {
    alreadyReloaded = deps.storage?.getItem(MISSING_CHUNK_RELOAD_KEY) === error.url;
    deps.storage?.setItem(MISSING_CHUNK_RELOAD_KEY, error.url);
  } catch {
    // Storage lleno o bloqueado: se recarga igual, una sola vez por instancia.
  }
  if (alreadyReloaded) return 'blocked';

  deps.assign(error.url);
  return 'reloaded';
}
