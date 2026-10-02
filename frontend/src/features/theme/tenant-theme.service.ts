import { Injectable, inject, signal } from '@angular/core';
import { Observable, map, tap } from 'rxjs';
import { ThemeService, isRenderableTheme, THEME_SOURCE } from '@shared/ui';
import type { ThemeFile } from '@shared/ui';
import { OrgThemeApi } from '@entities/organization/org-theme.api';

/**
 * Session-level owner of the ORGANIZATION theme (multi-tenant branding).
 *
 * Bridges the backend (`/organizations/me/theme`, via the THEME_SOURCE port
 * adapter) with @solercia/ui's ThemeService using the PUSH approach
 * (`setTenantTheme`): the pull pipeline (`SOL_TENANT_RESOLVER`) only types
 * numeric tenant ids, which does not fit this backend's UUID organizations.
 *
 * State:
 * - `saved` — the ThemeFile persisted for the org (`null` = bundled default).
 * - `loaded` — a load attempt finished (the shell's hydration effect guards
 *   on it, same contract as `MenuService.loaded`).
 *
 * The Theme Studio persists through `save()` (see `OrgThemeStudioStore`), so
 * an applied theme reaches the whole app without a reload.
 */
@Injectable({ providedIn: 'root' })
export class TenantThemeService {
  private readonly source = inject(THEME_SOURCE);
  private readonly theme = inject(ThemeService);
  private readonly api = inject(OrgThemeApi);

  private readonly _saved = signal<ThemeFile | null>(null);
  private readonly _loaded = signal(false);
  private loading = false;

  /** Persisted org theme (`null` = default bundled theme). */
  readonly saved = this._saved.asReadonly();

  /** True once a load attempt has finished (success or error). */
  readonly loaded = this._loaded.asReadonly();

  /**
   * Fetch the org theme once per session and apply it. A `null` API response
   * keeps the bundled default. Errors also fall back to the default (theming
   * never blocks the app), but still mark the load as done.
   */
  load(): void {
    if (this.loading) {
      return;
    }
    this.loading = true;
    void this.source
      .loadTheme('me')
      .then((file) => {
        this._saved.set(isRenderableTheme(file) ? file : null);
        this.theme.setTenantTheme(this._saved());
      })
      .catch(() => {
        this._saved.set(null);
        this.theme.setTenantTheme(null);
      })
      .finally(() => {
        this.loading = false;
        this._loaded.set(true);
      });
  }

  /** Drop the tenant theme (logout): back to the bundled default. */
  clear(): void {
    this.loading = false;
    this._saved.set(null);
    this._loaded.set(false);
    this.theme.setTenantTheme(null);
  }

  /**
   * Persist the theme for the whole organization and apply it. Emits the
   * theme AS PERSISTED; `sourceVersionId` is the restored history version the
   * change is based on. A persisted theme that does not render is emitted but
   * never adopted, so the app keeps the theme it had.
   */
  save(
    file: ThemeFile,
    sourceVersionId: number | null = null,
  ): Observable<ThemeFile> {
    return this.api.putTheme(file, sourceVersionId).pipe(
      map((res) => res.data),
      tap((persisted) => {
        if (!isRenderableTheme(persisted)) {
          return;
        }
        this._saved.set(persisted);
        this.theme.setTenantTheme(persisted);
      }),
    );
  }

  /** Reset the organization to the bundled default theme. */
  reset(): Observable<unknown> {
    return this.api.deleteTheme().pipe(
      tap(() => {
        this._saved.set(null);
        this.theme.setTenantTheme(null);
      }),
    );
  }
}
