import { HttpContext, HttpContextToken } from '@angular/common/http';

/**
 * Exclusión del manejador global de errores (`error.interceptor.ts`). Una petición que la lleva
 * en `true` no dispara ni las páginas de error (403, ≥ 500) ni la alerta de red: la marcan las
 * peticiones de fondo y las de pantallas que ya muestran su propio error en el sitio.
 */
export const SKIP_GLOBAL_ERROR_HANDLING = new HttpContextToken<boolean>(() => false);

/** Contexto listo para `HttpClient`: `{ context: skipGlobalErrorHandling() }`. */
export function skipGlobalErrorHandling(): HttpContext {
  return new HttpContext().set(SKIP_GLOBAL_ERROR_HANDLING, true);
}
