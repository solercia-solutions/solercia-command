import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import type { ThemeFile } from '@shared/ui';
import { apiBase } from '@shared/api/api.config';
import { skipGlobalErrorHandling } from '@shared/api/error-handling.context';

/** Envelope `{data}` used by the backend for the theme resource. */
export interface OrgThemeResponse {
  data: ThemeFile | null;
  message?: string;
}

/** One entry of the organization's theme history (backend shape). */
export interface OrgThemeVersion {
  id: number;
  /** Who applied it; `null` when the backend does not know (initial capture). */
  user_name: string | null;
  user_id: string | null;
  /** ISO 8601, UTC. */
  applied_at: string;
  /** `true` for the capture of the theme that existed before the history. */
  initial_capture: boolean;
  /** Version a restore was based on, or `null`. */
  source_version_id: number | null;
}

/** A history entry together with the ThemeFile that was applied. */
export interface OrgThemeVersionDetail extends OrgThemeVersion {
  theme: ThemeFile;
}

/** One page of the history, newest first; `next` is the cursor of the next page. */
export interface OrgThemeVersionPage {
  versions: OrgThemeVersion[];
  next: number | null;
}

/** Envelope of `PUT /me/theme`: the stored ThemeFile and the version it created. */
export interface OrgThemeAppliedResponse {
  data: ThemeFile;
  message?: string;
  meta?: { version: OrgThemeVersion };
}

/**
 * Thin HTTP client for the per-organization theme resource.
 *
 * The tenant is always resolved server-side (JWT + active organization), so
 * this client never sends an organization id. This is the ONLY place that
 * knows the backend theme contract (endpoints + `{data}` envelope).
 *
 * Every call opts out of the global error handler: the theme loads in the
 * background at sign-in (falling back to the default theme) and the Theme
 * Studio already shows its own error states and notices.
 */
@Injectable({ providedIn: 'root' })
export class OrgThemeApi {
  private readonly http = inject(HttpClient);
  private readonly base = `${apiBase}/organizations/me/theme`;

  /** ThemeFile of the caller's organization, or `null` (default theme). */
  getTheme(): Observable<OrgThemeResponse> {
    return this.http.get<OrgThemeResponse>(this.base, {
      context: skipGlobalErrorHandling(),
    });
  }

  /**
   * Persist the ThemeFile (RBAC ADMIN only). Every apply creates a history
   * entry; `sourceVersionId` is the restored version the change is based on.
   */
  putTheme(
    theme: ThemeFile,
    sourceVersionId: number | null = null,
  ): Observable<OrgThemeAppliedResponse> {
    const params: Record<string, number> = {};
    if (sourceVersionId !== null) params['source_version_id'] = sourceVersionId;
    return this.http.put<OrgThemeAppliedResponse>(this.base, theme, {
      params,
      context: skipGlobalErrorHandling(),
    });
  }

  /** Reset to the bundled default theme (RBAC ADMIN only). */
  deleteTheme(): Observable<OrgThemeResponse> {
    return this.http.delete<OrgThemeResponse>(this.base, {
      context: skipGlobalErrorHandling(),
    });
  }

  /** Theme history, 20 per page (RBAC ADMIN only); `before` is the cursor. */
  getVersions(
    before: number | null = null,
  ): Observable<{ data: OrgThemeVersionPage }> {
    const params: Record<string, number> = {};
    if (before !== null) params['before'] = before;
    return this.http.get<{ data: OrgThemeVersionPage }>(`${this.base}/versions`, {
      params,
      context: skipGlobalErrorHandling(),
    });
  }

  /** One history entry with its ThemeFile (RBAC ADMIN only). */
  getVersion(id: number): Observable<{ data: OrgThemeVersionDetail }> {
    return this.http.get<{ data: OrgThemeVersionDetail }>(
      `${this.base}/versions/${id}`,
      { context: skipGlobalErrorHandling() },
    );
  }
}
