import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import type { UserRole } from '@entities/user/user.model';
import { ACTIVE_ORG_KEY } from '@features/organizations/active-org.store';

const TOKEN_KEY = 'sp-token';

/** The authenticated user as returned by /auth/login and /auth/me. */
export interface CurrentUser {
  id: string;
  email: string;
  full_name?: string | null;
  primer_nombre?: string | null;
  segundo_nombre?: string | null;
  primer_apellido?: string | null;
  segundo_apellido?: string | null;
  dependency_id?: string | null;
  is_active?: boolean;
  organization_id?: string;
  roles?: UserRole[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user?: CurrentUser;
}

export interface RefreshResponse {
  access_token: string;
  token_type: string;
}

/**
 * Holds the JWT bearer token and exposes authentication state as signals.
 *
 * The access token is persisted in localStorage so a page reload keeps the
 * session; the refresh token lives in an httpOnly cookie set by the backend
 * (so it never reaches JavaScript). On a 401 the interceptor calls refresh()
 * to silently mint a new access token.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly _token = signal<string | null>(
    localStorage.getItem(TOKEN_KEY),
  );
  private readonly _user = signal<CurrentUser | null>(null);

  /** True when an access token is stored. Drives the guard and the shell. */
  readonly isAuthenticated = computed<boolean>(() => this._token() !== null);

  /** The current user (after login or /auth/me), or null. */
  readonly user = this._user.asReadonly();

  /** True when the user has the ADMIN role. Gates the admin navigation. */
  readonly isAdmin = computed<boolean>(() =>
    (this._user()?.roles ?? []).some((role) => role.code === 'ADMIN'),
  );

  /**
   * POST /auth/login — stores the returned access token and (when present)
   * the user. `withCredentials` lets the browser keep the refresh cookie.
   */
  login(email: string, password: string): Observable<LoginResponse> {
    return this.http
      .post<LoginResponse>(
        `${apiBase}/auth/login`,
        { email, password },
        { withCredentials: true },
      )
      .pipe(
        tap((res) => {
          this.setToken(res.access_token);
          if (res.user) {
            this._user.set(res.user);
          }
        }),
      );
  }

  /**
   * POST /auth/refresh — exchanges the refresh cookie for a fresh access
   * token (the backend also rotates the cookie). Called by the interceptor.
   */
  refresh(): Observable<RefreshResponse> {
    return this.http
      .post<RefreshResponse>(
        `${apiBase}/auth/refresh`,
        {},
        { withCredentials: true },
      )
      .pipe(tap((res) => this.setToken(res.access_token)));
  }

  /** GET /auth/me — the currently authenticated user, including roles. */
  me(): Observable<CurrentUser> {
    return this.http
      .get<CurrentUser>(`${apiBase}/auth/me`)
      .pipe(tap((user) => this._user.set(user)));
  }

  /**
   * Log out: best-effort POST /auth/logout to clear the refresh cookie, then
   * drop the local session regardless of the server outcome.
   */
  logout(): void {
    this.http
      .post(`${apiBase}/auth/logout`, {}, { withCredentials: true })
      .subscribe({ next: () => {}, error: () => {} });
    this.clearSession();
  }

  /** Drop the local session without calling the server (used on refresh fail).
   *
   * Also clears `sp-active-org` (gotcha crítico del design: si no se limpia,
   * tras el login de OTRO usuario en el mismo navegador el interceptor
   * seguiría enviando `X-Organization-Id` de una empresa ajena -> 403 en
   * toda la sesión nueva).
   */
  clearSession(): void {
    this._token.set(null);
    this._user.set(null);
    localStorage.removeItem(TOKEN_KEY);
    try {
      localStorage.removeItem(ACTIVE_ORG_KEY);
    } catch {
      // Storage no disponible: nada que limpiar.
    }
  }

  /** Current raw access token, or null. Read by the auth interceptor. */
  token(): string | null {
    return this._token();
  }

  private setToken(token: string): void {
    this._token.set(token);
    localStorage.setItem(TOKEN_KEY, token);
  }
}
