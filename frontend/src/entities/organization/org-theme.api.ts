import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import type { ThemeFile } from '@shared/ui';
import { apiBase } from '@shared/api/api.config';

/** Envelope `{data}` used by the backend for the theme resource. */
export interface OrgThemeResponse {
  data: ThemeFile | null;
  message?: string;
}

/**
 * Thin HTTP client for the per-organization theme resource.
 *
 * The tenant is always resolved server-side from the JWT (`/me/theme`), so
 * this client never sends an organization id. This is the ONLY place that
 * knows the backend theme contract (endpoint + `{data}` envelope).
 */
@Injectable({ providedIn: 'root' })
export class OrgThemeApi {
  private readonly http = inject(HttpClient);
  private readonly base = `${apiBase}/organizations/me/theme`;

  /** ThemeFile of the caller's organization, or `null` (default theme). */
  getTheme(): Observable<OrgThemeResponse> {
    return this.http.get<OrgThemeResponse>(this.base);
  }

  /** Persist the ThemeFile (RBAC ADMIN only). */
  putTheme(theme: ThemeFile): Observable<OrgThemeResponse> {
    return this.http.put<OrgThemeResponse>(this.base, theme);
  }

  /** Reset to the bundled default theme (RBAC ADMIN only). */
  deleteTheme(): Observable<OrgThemeResponse> {
    return this.http.delete<OrgThemeResponse>(this.base);
  }
}
