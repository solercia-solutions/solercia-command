import { HttpErrorResponse } from '@angular/common/http';

/** Normalised view of the API error envelope `{ detail, code, status, meta }`. */
export interface ApiError {
  /** HTTP status; `0` when the request never reached the server. */
  status: number;
  code: string | null;
  detail: string | null;
  meta: Record<string, unknown> | null;
}

/**
 * Reads the backend error envelope out of an `HttpErrorResponse` without
 * trusting its shape: every field is optional and type-checked so a proxy
 * error page or a network failure degrades to `null`s instead of throwing.
 */
export function readApiError(err: unknown): ApiError {
  if (!(err instanceof HttpErrorResponse)) {
    return { status: 0, code: null, detail: null, meta: null };
  }
  const body: unknown = err.error;
  const record =
    body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const detail = record['detail'];
  const code = record['code'];
  const meta = record['meta'];
  return {
    status: err.status,
    code: typeof code === 'string' && code.length > 0 ? code : null,
    detail: typeof detail === 'string' && detail.length > 0 ? detail : null,
    meta: meta && typeof meta === 'object' ? (meta as Record<string, unknown>) : null,
  };
}
