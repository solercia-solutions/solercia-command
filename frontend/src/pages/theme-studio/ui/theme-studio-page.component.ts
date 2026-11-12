import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { catchError, map, of } from 'rxjs';
import {
  SolThemeStudioComponent,
  THEME_STUDIO_STORE,
  type SolThemeStudioFeatures,
  type SolThemeStudioNotice,
} from '@solercia/ui/theme-studio';
import { OrganizationsService } from '@entities/organization/organizations.service';
import { ActiveOrgStore } from '@features/organizations/active-org.store';
import { OrgThemeStudioStore } from '@features/theme/theme-studio-store.adapter';
import { I18nService } from '@shared/i18n';
import { AlertService } from '@shared/lib/alerts';
import { ThemeService } from '@shared/tokens';

/**
 * Theme Studio de Solercia Command: `<sol-theme-studio>` de `@solercia/ui/theme-studio` con la
 * configuración equivalente a PANDORA (THEME-STUDIO.md §3.2 de la librería). Reemplaza la pantalla
 * propia de «Apariencia» y conserva su ruta, `/settings/appearance`.
 *
 * - `features`: sin nombre de tema editable, con indicador de carga, preset de tabla también en
 *   `meta.tableStyle` (lo lee `AppComponent`) y el modo por defecto persistido al aplicar.
 * - `metaExtrasSchema`: campos de `meta` que se conservan sin editarlos en el Studio; el shell lee
 *   `meta.sidebar.autoCloseOnNavigate`.
 * - `baseTheme`: sin tema guardado se parte del tema activo del shell, nunca de un formulario vacío.
 * - El store se provee aquí y no en la raíz: solo esta ruta lo necesita.
 *
 * Solo administradores: la entrada de menú se otorga a ese rol y el backend rechaza con 403 el
 * historial y la aplicación del tema para los demás.
 */
@Component({
  standalone: true,
  selector: 'sol-theme-studio-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [SolThemeStudioComponent],
  providers: [{ provide: THEME_STUDIO_STORE, useExisting: OrgThemeStudioStore }],
  template: `
    <sol-theme-studio
      [features]="features"
      [metaExtrasSchema]="metaExtrasSchema"
      [baseTheme]="baseTheme()"
      [footerPlaceholder]="footerPlaceholder()"
      exportFileName="solercia-command-tema.json"
      versionTimeZone="America/Bogota"
      versionTimeZoneLabel="(Bogotá)"
      (notify)="onNotify($event)"
    />
  `,
  styles: `
    /* Lo que queda fijo al borde inferior de la pantalla y la vista previa del Studio debe
       descontar. En escritorio no hay nada; bajo el breakpoint móvil está el menú inferior
       (--sol-bottom-nav-h lo declara sol-layout-shell). */
    :host {
      --sol-theme-studio-bottom-inset: 0px;
    }

    @media (max-width: 767px) {
      :host {
        --sol-theme-studio-bottom-inset: calc(
          var(--sol-bottom-nav-h, 58px) + env(safe-area-inset-bottom, 0px)
        );
      }
    }
  `,
})
export class ThemeStudioPageComponent {
  private readonly alerts = inject(AlertService);
  private readonly i18n = inject(I18nService);
  private readonly themeService = inject(ThemeService);
  private readonly organizations = inject(OrganizationsService);
  private readonly activeOrg = inject(ActiveOrgStore);

  protected readonly features: SolThemeStudioFeatures = {
    themeName: false,
    loader: true,
    tableVariantMetaKey: 'tableStyle',
    persistDefaultModeOnApply: true,
  };

  protected readonly metaExtrasSchema = { themeName: '', sidebar: { autoCloseOnNavigate: true } };

  protected readonly baseTheme = computed(() => this.themeService.activeTheme() ?? undefined);

  /**
   * Nombre de la organización activa, con el mismo respaldo que el selector del header (la primera
   * membresía cuando aún no hay una activa guardada). Solo alimenta un texto de ejemplo: si la
   * consulta falla se usa un nombre genérico y el Studio sigue funcionando.
   */
  private readonly organizationName = toSignal(
    this.organizations.mine().pipe(
      map((res) => {
        const memberships = res.data ?? [];
        const active =
          memberships.find((m) => m.organization.id === this.activeOrg.activeOrgId()) ??
          memberships[0];
        return active?.organization.name ?? null;
      }),
      catchError(() => of(null)),
    ),
    { initialValue: null },
  );

  protected readonly footerPlaceholder = computed<string>(() => {
    this.i18n.activeLang();
    return this.i18n.translate('pages.themeStudio.footerPlaceholder', {
      year: new Date().getFullYear(),
      organization:
        this.organizationName() ??
        this.i18n.translate('pages.themeStudio.organizationFallback'),
    });
  });

  protected onNotify(notice: SolThemeStudioNotice): void {
    if (notice.kind === 'success') this.alerts.showSuccess(notice.message);
    else if (notice.kind === 'error') this.alerts.showError(notice.message);
    else if (notice.kind === 'warning') this.alerts.showWarning(notice.message);
    else this.alerts.showInfo(notice.message);
  }
}
