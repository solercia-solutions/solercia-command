/** @boki/ui — © 2026 Camilo Calderón. All rights reserved. */

/**
 * Typed application error with a stable code, a user-facing message in
 * Spanish, optional technical detail, and optional original cause.
 *
 * Use AppError.fromHttp() to convert an HttpErrorResponse into an AppError.
 */
export class AppError extends Error {
  override readonly name = 'AppError';

  constructor(
    /** Machine-readable error code (e.g. 'NOT_FOUND', 'UNAUTHENTICATED'). */
    public readonly code: string,
    /** User-facing message in Spanish — safe to display in the UI. */
    public readonly userMessage: string,
    /** Optional technical detail for logs (not shown to users). */
    public readonly technical?: string,
    /** Original cause (e.g. the raw HttpErrorResponse). */
    public override readonly cause?: unknown,
  ) {
    super(userMessage);
    // Restore prototype chain in transpiled ES5 targets.
    Object.setPrototypeOf(this, new.target.prototype);
  }

  /**
   * Maps an HTTP status code + context into an AppError with a Spanish
   * user-facing message. Intended for use inside bokiHttpErrorInterceptor.
   *
   * @param status  HTTP status code (0 for network errors).
   * @param url     Request URL (used in technical detail).
   * @param cause   Original error value (e.g. HttpErrorResponse).
   */
  static fromHttp(status: number, url: string, cause?: unknown): AppError {
    if (status === 0) {
      return new AppError(
        'NETWORK',
        'No fue posible conectar con el servidor. Verifica tu conexión e intenta de nuevo.',
        `Network error — ${url}`,
        cause,
      );
    }
    if (status === 401) {
      return new AppError(
        'UNAUTHENTICATED',
        'Tu sesión ha expirado. Por favor, inicia sesión nuevamente.',
        `401 Unauthorized — ${url}`,
        cause,
      );
    }
    if (status === 403) {
      return new AppError(
        'FORBIDDEN',
        'No tienes permisos para realizar esta acción.',
        `403 Forbidden — ${url}`,
        cause,
      );
    }
    if (status === 404) {
      return new AppError(
        'NOT_FOUND',
        'El recurso solicitado no fue encontrado.',
        `404 Not Found — ${url}`,
        cause,
      );
    }
    if (status === 422) {
      return new AppError(
        'VALIDATION',
        'Los datos enviados no son válidos. Revisa el formulario e intenta de nuevo.',
        `422 Unprocessable Entity — ${url}`,
        cause,
      );
    }
    if (status >= 400 && status < 500) {
      return new AppError(
        'CLIENT',
        'La solicitud no pudo completarse. Verifica los datos e intenta de nuevo.',
        `${status} Client Error — ${url}`,
        cause,
      );
    }
    if (status >= 500) {
      return new AppError(
        'SERVER',
        'Ocurrió un error en el servidor. Por favor, intenta más tarde.',
        `${status} Server Error — ${url}`,
        cause,
      );
    }
    return new AppError(
      'UNKNOWN',
      'Ocurrió un error inesperado. Por favor, intenta de nuevo.',
      `HTTP ${status} — ${url}`,
      cause,
    );
  }
}
