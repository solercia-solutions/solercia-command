import { Injectable, signal } from '@angular/core';

/** localStorage key for the persisted active-organization id.
 *
 * Exported so `AuthService#clearSession()` can remove it on logout (gotcha
 * crítico del design: sin esto, tras el login de OTRO usuario en el mismo
 * navegador el header seguiría apuntando a una empresa ajena -> 403 en toda
 * la sesión).
 */
export const ACTIVE_ORG_KEY = 'sp-active-org';

/**
 * Holds the caller's active-organization id (empresa activa) as a signal,
 * hydrated from `localStorage` so it survives a reload.
 *
 * Design decision 5: switching organizations triggers a FULL page reload
 * (`window.location.reload()`) instead of a selective store reset — the
 * entire bootstrap (theme, menus, `/auth/me`, page data, WS) re-runs with
 * the new header, so there is zero risk of stale/residual state from the
 * previous organization leaking into a view.
 */
@Injectable({ providedIn: 'root' })
export class ActiveOrgStore {
  private readonly _activeOrgId = signal<string | null>(
    readPersistedActiveOrg(),
  );

  /** The currently active organization id, or `null` before it is known
   * (e.g. right after login, before `GET /organizations/mine` resolves). */
  readonly activeOrgId = this._activeOrgId.asReadonly();

  /** Persist `id` as the active organization and reload the app. */
  setActiveOrg(id: string): void {
    persistActiveOrg(id);
    this._activeOrgId.set(id);
    window.location.reload();
  }
}

/** Reads the persisted active org id; storage failures fall back to `null`. */
function readPersistedActiveOrg(): string | null {
  try {
    return localStorage.getItem(ACTIVE_ORG_KEY);
  } catch {
    return null;
  }
}

/** Persists the active org id; storage failures are silently ignored. */
function persistActiveOrg(id: string): void {
  try {
    localStorage.setItem(ACTIVE_ORG_KEY, id);
  } catch {
    // Storage no disponible (modo privado/quota): el estado queda en memoria.
  }
}
