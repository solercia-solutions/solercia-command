import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { I18nService } from '@shared/i18n';
import { AlertService } from '@shared/lib/alerts';
import { ErrorDiagnosticsService } from './error-diagnostics.service';
import { SKIP_GLOBAL_ERROR_HANDLING } from './error-handling.context';

/**
 * Manejador global de errores HTTP: decide qué hacer cuando ninguna pantalla maneja el error.
 *
 * - 403 → página `/prohibido`; `>= 500` → página `/error-servidor`. El error queda en
 *   `ErrorDiagnosticsService` para que la página muestre el mensaje real del backend.
 * - Sin respuesta del servidor (status 0) → alerta de red.
 * - 401 no se toca: lo resuelve `authInterceptor` (refresco del token, reintento y `/login`).
 * - El resto de 4xx sigue su curso hacia quien hizo la petición.
 *
 * Quedan fuera de toda decisión automática `/auth/*` (el formulario de login y la hidratación de
 * la sesión ya interpretan sus propios errores) y las peticiones marcadas con
 * `SKIP_GLOBAL_ERROR_HANDLING`. En todos los casos el error se relanza intacto.
 *
 * Se registra DESPUÉS de `authInterceptor`: ve primero la respuesta cruda y también el reintento
 * que sigue a un refresco del token.
 */
export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  if (req.context.get(SKIP_GLOBAL_ERROR_HANDLING) || req.url.includes('/auth/')) {
    return next(req);
  }

  const router = inject(Router);
  const alert = inject(AlertService);
  const i18n = inject(I18nService);
  const diagnostics = inject(ErrorDiagnosticsService);

  return next(req).pipe(
    catchError((error: unknown) => {
      if (!(error instanceof HttpErrorResponse)) {
        return throwError(() => error);
      }

      if (error.status === 0) {
        alert.showError(i18n.translate('shared.errorState.network'));
      } else if (error.status === 403 || error.status >= 500) {
        diagnostics.record(error);
        void router.navigate([error.status === 403 ? '/prohibido' : '/error-servidor']);
      }

      return throwError(() => error);
    }),
  );
};
