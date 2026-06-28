/** @boki/ui — © 2026 Camilo Calderón. All rights reserved. */

import { ErrorHandler, Injectable, inject } from '@angular/core';
import { BokiLogger } from '../logging/logger.service';
import { AppError } from './app-error';

/**
 * Global Angular ErrorHandler that routes uncaught errors through BokiLogger.
 *
 * - Logs at ERROR level with context 'uncaught' (never silently swallowed).
 * - Does NOT re-throw: ErrorHandler is the terminal handler, so re-throwing
 *   here can re-enter the zone error path and recurse.
 * - Exposes an optional `onError` hook for consumer-side reporting
 *   (e.g. Sentry, toast notification) without coupling the library to any
 *   specific notification mechanism.
 *
 * Register via provideBokiErrors() — do not add directly to providers unless
 * you need to subclass and override onError.
 */
@Injectable()
export class BokiErrorHandler implements ErrorHandler {
  private readonly log = inject(BokiLogger).withContext('uncaught');

  /**
   * Optional hook — override in a subclass or set after construction to
   * react to uncaught errors (show toast, report to Sentry, etc.).
   * Called AFTER logging, regardless of error type.
   */
  onError?: (error: unknown) => void;

  handleError(error: unknown): void {
    const appError = error instanceof AppError ? error : this.wrap(error);

    this.log.error(appError.userMessage ?? appError.message, {
      code:      appError instanceof AppError ? appError.code : undefined,
      technical: appError instanceof AppError ? appError.technical : undefined,
      original:  error,
    });

    // Forward to the consumer hook (toast, Sentry, etc.) after logging.
    this.onError?.(error);
  }

  private wrap(error: unknown): AppError {
    if (error instanceof Error) {
      return new AppError('UNCAUGHT', error.message, error.stack, error);
    }
    return new AppError('UNCAUGHT', 'An unexpected error occurred.', String(error), error);
  }
}
