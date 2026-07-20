import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import type { ThemeFile, ThemeSource } from '@shared/ui';
import { OrgThemeApi } from '@entities/organization/org-theme.api';

/**
 * Host adapter for @solercia/ui's THEME_SOURCE port (mirrors boki-front's
 * `BokiApiThemeSource`).
 *
 * Loads the tenant ThemeFile from `GET /organizations/me/theme` — the tenant
 * is resolved server-side from the JWT, so `tenantId` is ignored (accepted
 * only to honor the port's signature). Errors propagate to the caller
 * (`TenantThemeService` / ThemeService), which degrades silently to the
 * bundled default theme.
 *
 * NOTE: the pull pipeline of @solercia/ui 0.3.0 (`SOL_TENANT_RESOLVER`)
 * types tenant ids as `number | null`, which does not fit this backend's
 * UUID organizations — so the host drives this adapter directly (push via
 * `ThemeService.setTenantTheme`) instead of wiring a numeric resolver.
 */
@Injectable({ providedIn: 'root' })
export class OrgThemeSource implements ThemeSource {
  private readonly api = inject(OrgThemeApi);

  async loadTheme(_tenantId: number | string): Promise<ThemeFile | null> {
    const res = await firstValueFrom(this.api.getTheme());
    return res?.data ?? null;
  }
}
