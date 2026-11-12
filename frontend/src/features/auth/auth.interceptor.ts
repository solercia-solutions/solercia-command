import {
  HttpErrorResponse,
  HttpEvent,
  HttpHandlerFn,
  HttpInterceptorFn,
  HttpRequest,
} from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import {
  BehaviorSubject,
  Observable,
  catchError,
  filter,
  switchMap,
  take,
  throwError,
} from 'rxjs';
import { AuthService } from './auth.service';
import { ActiveOrgStore } from '@features/organizations/active-org.store';

/**
 * Module-level refresh coordination so concurrent 401s trigger a single
 * /auth/refresh: the first request refreshes, the rest wait for the new token.
 */
let isRefreshing = false;
const refreshedToken$ = new BehaviorSubject<string | null>(null);

/** Endpoints that must never carry a bearer token nor trigger a refresh retry. */
function isAuthEndpoint(url: string): boolean {
  return (
    url.includes('/auth/login') ||
    url.includes('/auth/refresh') ||
    url.includes('/auth/logout')
  );
}

function withToken(
  req: HttpRequest<unknown>,
  token: string,
): HttpRequest<unknown> {
  return req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
}

/** Adds `X-Organization-Id` with the active organization, when one is known. */
function withActiveOrg(
  req: HttpRequest<unknown>,
  organizationId: string,
): HttpRequest<unknown> {
  return req.clone({
    setHeaders: { 'X-Organization-Id': organizationId },
  });
}

/**
 * Functional interceptor: attaches the bearer token to every protected request
 * and, on a 401, transparently refreshes the access token once and retries the
 * original request. If the refresh fails, the session is cleared and the user
 * is sent to /login. Loops are prevented by skipping the auth endpoints.
 *
 * Also injects `X-Organization-Id` (frontend-org-switcher R3) with the
 * caller's active organization — omitted, same as the bearer token, on the
 * auth endpoints, and simply absent before the first `GET /organizations/mine`
 * resolves (the backend falls back to the first membership, so login never
 * breaks for lack of a header).
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const activeOrg = inject(ActiveOrgStore);

  const token = auth.token();
  let authReq =
    token && !isAuthEndpoint(req.url) ? withToken(req, token) : req;

  const organizationId = activeOrg.activeOrgId();
  if (organizationId && !isAuthEndpoint(req.url)) {
    authReq = withActiveOrg(authReq, organizationId);
  }

  return next(authReq).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401 && !isAuthEndpoint(req.url)) {
        return handle401(req, next, auth, router, organizationId);
      }
      if (error.status === 401 && req.url.includes('/auth/refresh')) {
        // The refresh itself was rejected: the session is no longer valid.
        auth.clearSession();
        void router.navigate(['/login']);
      }
      return throwError(() => error);
    }),
  );
};

function handle401(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
  auth: AuthService,
  router: Router,
  organizationId: string | null,
): Observable<HttpEvent<unknown>> {
  const withRetryHeaders = (token: string): HttpRequest<unknown> => {
    const withAuth = withToken(req, token);
    return organizationId ? withActiveOrg(withAuth, organizationId) : withAuth;
  };

  if (isRefreshing) {
    // A refresh is already in flight: wait for the new token, then retry once.
    return refreshedToken$.pipe(
      filter((value): value is string => value !== null),
      take(1),
      switchMap((freshToken) => next(withRetryHeaders(freshToken))),
    );
  }

  isRefreshing = true;
  refreshedToken$.next(null);

  return auth.refresh().pipe(
    switchMap((res) => {
      isRefreshing = false;
      refreshedToken$.next(res.access_token);
      return next(withRetryHeaders(res.access_token));
    }),
    catchError((err) => {
      isRefreshing = false;
      auth.clearSession();
      void router.navigate(['/login']);
      return throwError(() => err);
    }),
  );
}
