import { Injectable, inject } from '@angular/core';
import { Observable, catchError, map, throwError } from 'rxjs';
import type { ThemeFile } from '@shared/ui';
import type { ThemeStudioStore, ThemeVersion, ThemeVersionPage } from '@solercia/ui/theme-studio';
import { OrgThemeApi, type OrgThemeVersion } from '@entities/organization/org-theme.api';
import { readApiError } from '@shared/lib/api-error';
import { TenantThemeService } from './tenant-theme.service';

const toVersion = (v: OrgThemeVersion): ThemeVersion => ({
  id: v.id,
  userName: v.user_name,
  userId: v.user_id,
  appliedAt: v.applied_at,
  initialCapture: v.initial_capture,
  sourceVersionId: v.source_version_id,
});

/** Identificador o cursor del Studio (`number | string`) → entero de la API, o `null`. */
function toApiId(id: ThemeVersion['id'] | null | undefined): number | null {
  if (id === null || id === undefined || id === '') return null;
  const value = Number(id);
  return Number.isFinite(value) ? value : null;
}

/**
 * El Studio solo muestra el mensaje del servidor cuando el error lo trae como `userMessage` (o en
 * un sobre `error.message`). El sobre de esta API es `{detail, code, status}`, así que se traduce
 * aquí. Sin `detail` (fallo de red, página de error de un proxy) el error pasa tal cual y el Studio
 * usa su texto propio.
 */
function toStoreError(error: unknown): unknown {
  const { detail } = readApiError(error);
  return detail ? { userMessage: detail } : error;
}

function withStoreError<T>(source: Observable<T>): Observable<T> {
  return source.pipe(catchError((error: unknown) => throwError(() => toStoreError(error))));
}

/**
 * Adaptador de `THEME_STUDIO_STORE` (`@solercia/ui/theme-studio`) sobre el tema por organización
 * (`/organizations/me/theme` y su historial). Solo traduce: nombres de campo en snake_case, el
 * cursor `before`, la versión de origen `source_version_id` y el sobre de error.
 *
 * `apply` pasa por `TenantThemeService.save`, que persiste y además empuja el tema guardado a toda
 * la aplicación; emite el tema TAL COMO QUEDÓ PERSISTIDO, que es lo que el Studio necesita para
 * no llamar a `ThemeService.refresh()` (aquí no hay `SOL_TENANT_RESOLVER`: no haría nada).
 *
 * Sin `uploadLogo`: no existe un endpoint de carga de archivos, así que el Studio oculta los
 * botones de carga y el logo entra por URL.
 *
 * A diferencia del adaptador de PANDORA, no se retira `modes.*.component.table.variant` del
 * payload. Allá se quita para que el payload coincida con el de su pantalla anterior; aquí no hay
 * un contrato previo que conservar y dejarlo permite que `sol-data-table` siga la variante del
 * tema de forma nativa, con el mismo resultado que las reglas de `meta.tableStyle`.
 */
@Injectable({ providedIn: 'root' })
export class OrgThemeStudioStore implements ThemeStudioStore {
  private readonly api = inject(OrgThemeApi);
  private readonly tenantTheme = inject(TenantThemeService);

  load(): Observable<ThemeFile | null> {
    return withStoreError(this.api.getTheme().pipe(map((res) => res.data ?? null)));
  }

  apply(
    theme: ThemeFile,
    sourceVersionId: ThemeVersion['id'] | null = null,
  ): Observable<ThemeFile> {
    return withStoreError(this.tenantTheme.save(theme, toApiId(sourceVersionId)));
  }

  listVersions(before: ThemeVersionPage['next'] = null): Observable<ThemeVersionPage> {
    return withStoreError(
      this.api.getVersions(toApiId(before)).pipe(
        map((res) => ({ versions: res.data.versions.map(toVersion), next: res.data.next })),
      ),
    );
  }

  getVersion(id: ThemeVersion['id']): Observable<ThemeFile> {
    return withStoreError(this.api.getVersion(Number(id)).pipe(map((res) => res.data.theme)));
  }
}
