/** @boki/ui — © 2026 Camilo Calderón. All rights reserved. */

import { inject } from '@angular/core';
import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { BokiLogger } from '../logging/logger.service';
import { AppError } from './app-error';

/**
 * Functional HTTP interceptor that maps HttpErrorResponse to AppError.
 *
 * - Catches HttpErrorResponse, converts it via AppError.fromHttp().
 * - Logs the AppError at ERROR level with context 'http'.
 * - Re-throws the AppError so the calling service/store can handle it.
 * - Does NOT retry by default.
 *
 * Register in withInterceptors([bokiHttpErrorInterceptor]):
 *
 *   provideHttpClient(withInterceptors([bokiHttpErrorInterceptor]))
 *
 * Do NOT pass to provideBokiErrors() — the consumer wires it into
 * provideHttpClient() so they control interceptor order.
 */
export const bokiHttpErrorInterceptor: HttpInterceptorFn = (req, next) => {
  const log = inject(BokiLogger).withContext('http');

  return next(req).pipe(
    catchError((raw: unknown) => {
      if (raw instanceof HttpErrorResponse) {
        const appError = AppError.fromHttp(raw.status, req.urlWithParams, raw);
        log.error(appError.userMessage, { code: appError.code, technical: appError.technical });
        return throwError(() => appError);
      }
      // Non-HTTP errors pass through unchanged.
      return throwError(() => raw);
    }),
  );
};
