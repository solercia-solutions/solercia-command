import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { OrganizationsService } from '@entities/organization/organizations.service';
import { OrganizationMembership } from '@entities/organization/organization.model';
import {
  SolScope,
  SolScopeSwitcherComponent,
  SolScopeSwitcherStatus,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { ActiveOrgStore } from './active-org.store';

/** Ámbito del selector con la membresía completa como carga opaca. */
type OrgScope = SolScope<OrganizationMembership>;

/**
 * Contenedor del selector de empresa activa, proyectado en `[header-actions]`
 * (app.component).
 *
 * La presentación (disparador, panel, estados de carga/vacío/error, teclado y
 * accesibilidad) la resuelve `SolScopeSwitcherComponent` de `@solercia/ui`.
 * Aquí se queda la política de la aplicación, que es todo lo que exige
 * `frontend-org-switcher` y la librería deliberadamente NO hace:
 *
 * - Lista las empresas del usuario (`GET /organizations/mine`) con su rol.
 * - Al elegir una distinta, VERIFICA el acceso con `GET /organizations/{id}`
 *   antes de persistir: ese endpoint solo exige membresía (no depende del
 *   header activo), así que un fallo ahí es señal real de red o de acceso
 *   perdido. Si falla, se muestra el error y el layout conserva el contexto
 *   de la empresa anterior (Scenario "Falla al cambiar de empresa conserva
 *   el contexto anterior").
 * - La persistencia en `localStorage`, el reinicio de los stores de dominio,
 *   la recarga del menú y la reconexión con el nuevo scope las ejecuta
 *   `ActiveOrgStore.setActiveOrg()`.
 *
 * Mejora que aporta la librería: `activeScopeId` se valida contra la lista
 * antes de usarse — un id persistido que ya no corresponde a ninguna membresía
 * cae al primer ámbito disponible en vez de dejar el disparador en blanco.
 * Por eso aquí se pasa el id crudo del store, sin respaldo local.
 */
@Component({
  selector: 'sol-org-switcher',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [SolScopeSwitcherComponent],
  template: `
    <sol-scope-switcher
      [scopes]="scopes()"
      [activeScopeId]="activeScopeId()"
      [status]="status()"
      [disabled]="switching()"
      [errorMessage]="errorMessage()"
      align="end"
      (scopeSelected)="selectOrganization($event)"
    />
  `,
})
export class OrgSwitcherComponent implements OnInit {
  private readonly service = inject(OrganizationsService);
  private readonly activeOrgStore = inject(ActiveOrgStore);
  private readonly i18n = inject(I18nService);

  private readonly memberships = signal<OrganizationMembership[]>([]);
  private readonly loading = signal(true);

  /** Congela el disparador mientras se verifica el acceso a la empresa elegida. */
  protected readonly switching = signal(false);
  /** Mensaje de error ya resuelto; vacío cuando no hay error. */
  protected readonly errorMessage = signal('');

  /**
   * Id de la empresa activa tal como está persistido. La validación contra la
   * lista (y el respaldo a la primera empresa) la hace el selector.
   */
  protected readonly activeScopeId = this.activeOrgStore.activeOrgId;

  /** `OrganizationMembership` → `SolScope`: el rol va en `sublabel`. */
  protected readonly scopes = computed<readonly OrgScope[]>(() => {
    // Se lee el idioma activo para remapear los roles al cambiarlo.
    this.i18n.activeLang();
    return this.memberships().map((membership) => ({
      id: membership.organization.id,
      label: membership.organization.name,
      sublabel: this.i18n.translate(`orgSwitcher.roles.${membership.role}`),
      data: membership,
    }));
  });

  /**
   * Estado excluyente del selector. El vacío legítimo NO se modela aquí: lo
   * deriva la librería de una lista vacía sin error.
   */
  protected readonly status = computed<SolScopeSwitcherStatus>(() => {
    if (this.loading()) return 'loading';
    return this.errorMessage() ? 'error' : 'idle';
  });

  ngOnInit(): void {
    this.load();
  }

  /**
   * Cambio de empresa activa. El selector no emite cuando se vuelve a elegir
   * la que ya está activa, así que aquí solo llegan cambios reales.
   */
  protected selectOrganization(scope: OrgScope): void {
    const membership = scope.data;
    if (!membership) return;

    this.errorMessage.set('');
    this.switching.set(true);

    this.service.get(membership.organization.id).subscribe({
      next: () => {
        this.switching.set(false);
        // Persiste en localStorage y refresca todo el contexto (stores de
        // dominio, menú, tema y conexiones) con el nuevo `X-Organization-Id`.
        this.activeOrgStore.setActiveOrg(membership.organization.id);
      },
      error: (err: HttpErrorResponse) => {
        this.switching.set(false);
        this.errorMessage.set(this.messageFor(err));
      },
    });
  }

  private load(): void {
    this.loading.set(true);
    this.errorMessage.set('');
    this.service.mine().subscribe({
      next: (res) => {
        this.memberships.set(res.data ?? []);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.errorMessage.set(this.messageFor(err, 'orgSwitcher.errors.load'));
      },
    });
  }

  private messageFor(
    err: HttpErrorResponse,
    fallbackKey = 'orgSwitcher.errors.switchFailed',
  ): string {
    if (err.status === 0) {
      return this.i18n.translate('orgSwitcher.errors.network');
    }
    return this.i18n.translate(fallbackKey);
  }
}
