import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { readApiError } from '@shared/lib/api-error';

/** Cabecera que transporta el código de seguimiento de una respuesta, cuando el backend lo envía. */
const TRACE_ID_HEADER = 'X-Request-Id';

/** Último error HTTP que el interceptor llevó a una página de error, ya normalizado. */
export interface ErrorDiagnostic {
  status: number;
  /** `detail` del sobre de error del backend; `null` si la respuesta no lo trae. */
  detail: string | null;
  traceId: string | null;
}

/**
 * Guarda el último error que `error.interceptor.ts` llevó a una página de error, para que esa
 * página muestre el mensaje real del backend y el código de seguimiento aunque ningún componente
 * haya reaccionado directamente al error.
 */
@Injectable({ providedIn: 'root' })
export class ErrorDiagnosticsService {
  private readonly lastSignal = signal<ErrorDiagnostic | null>(null);

  readonly last = this.lastSignal.asReadonly();

  record(error: HttpErrorResponse): void {
    this.lastSignal.set({
      status: error.status,
      detail: readApiError(error).detail,
      traceId: error.headers.get(TRACE_ID_HEADER),
    });
  }
}
