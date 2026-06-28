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

/**
 * Functional interceptor: attaches the bearer token to every protected request
 * and, on a 401, transparently refreshes the access token once and retries the
 * original request. If the refresh fails, the session is cleared and the user
 * is sent to /login. Loops are prevented by skipping the auth endpoints.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  const token = auth.token();
  const authReq =
    token && !isAuthEndpoint(req.url) ? withToken(req, token) : req;

  return next(authReq).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401 && !isAuthEndpoint(req.url)) {
        return handle401(req, next, auth, router);
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
): Observable<HttpEvent<unknown>> {
  if (isRefreshing) {
    // A refresh is already in flight: wait for the new token, then retry once.
    return refreshedToken$.pipe(
      filter((value): value is string => value !== null),
      take(1),
      switchMap((freshToken) => next(withToken(req, freshToken))),
    );
  }

  isRefreshing = true;
  refreshedToken$.next(null);

  return auth.refresh().pipe(
    switchMap((res) => {
      isRefreshing = false;
      refreshedToken$.next(res.access_token);
      return next(withToken(req, res.access_token));
    }),
    catchError((err) => {
      isRefreshing = false;
      auth.clearSession();
      void router.navigate(['/login']);
      return throwError(() => err);
    }),
  );
}
