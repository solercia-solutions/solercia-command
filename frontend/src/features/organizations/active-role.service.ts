import { Injectable, computed, inject, signal } from '@angular/core';
import { AuthService } from '@features/auth/auth.service';
import { OrganizationsService } from '@entities/organization/organizations.service';
import { MemberRole, OrganizationMembership } from '@entities/organization/organization.model';
import { ActiveOrgStore } from './active-org.store';

/**
 * Rol del usuario en la organización ACTIVA (la del encabezado `X-Organization-Id`, o el respaldo
 * del backend: la organización de `/auth/me` y luego la primera membresía). Es el mismo criterio
 * de `plans.component.ts`; las pantallas lo usan para mostrar u ocultar acciones que el API
 * igual valida (`require_role`).
 */
@Injectable({ providedIn: 'root' })
export class ActiveRoleService {
  private readonly organizations = inject(OrganizationsService);
  private readonly activeOrg = inject(ActiveOrgStore);
  private readonly auth = inject(AuthService);

  private readonly memberships = signal<OrganizationMembership[] | null>(null);
  private requested = false;

  /** `null` mientras carga o si la consulta falló (las acciones quedan ocultas). */
  readonly role = computed<MemberRole | null>(() => {
    const memberships = this.memberships();
    if (!memberships) {
      return null;
    }
    const orgId = this.activeOrg.activeOrgId() ?? this.auth.user()?.organization_id ?? null;
    const membership =
      memberships.find((m) => m.organization.id === orgId) ?? (orgId ? undefined : memberships[0]);
    return membership?.role ?? null;
  });

  readonly isAdmin = computed(() => this.role() === 'admin');
  readonly isAdminOrManager = computed(() => this.role() === 'admin' || this.role() === 'manager');
  readonly loaded = computed(() => this.memberships() !== null);

  /** Carga las membresías una sola vez por sesión de la app. */
  ensureLoaded(): void {
    if (this.requested) {
      return;
    }
    this.requested = true;
    this.organizations.mine().subscribe({
      next: (res) => this.memberships.set(res.data ?? []),
      error: () => {
        this.requested = false;
        this.memberships.set([]);
      },
    });
  }
}
