/** @boki/ui — © 2026 Camilo Calderón. All rights reserved. */

import { ErrorHandler, Provider } from '@angular/core';
import { BokiErrorHandler } from './error-handler';

/**
 * Registers BokiErrorHandler as Angular's global ErrorHandler.
 *
 * Usage in app.config.ts:
 *
 *   import { provideHttpClient, withInterceptors } from '@angular/common/http';
 *   import { provideBokiErrors, bokiHttpErrorInterceptor } from '@boki/ui';
 *
 *   providers: [
 *     provideHttpClient(withInterceptors([bokiHttpErrorInterceptor])),
 *     provideBokiErrors(),
 *   ]
 *
 * NOTE: `bokiHttpErrorInterceptor` is NOT wired here intentionally.
 * The consumer adds it via withInterceptors() so they control interceptor
 * ordering (e.g. placing auth interceptors before or after).
 */
export function provideBokiErrors(): Provider[] {
  return [
    {
      provide: ErrorHandler,
      useClass: BokiErrorHandler,
    },
  ];
}
