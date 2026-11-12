import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { filter, interval, map } from 'rxjs';
import { breadcrumbTrail } from '@entities/menu';
import { NotificationsService } from '@entities/notification/notifications.service';
import { AuthService } from '@features/auth/auth.service';
import { MenuService, isOwnRouteLeaf } from '@features/navigation/menu.service';
import { OrgSwitcherComponent } from '@features/organizations/org-switcher.component';
import { TenantThemeService } from '@features/theme/tenant-theme.service';
import { I18nService } from '@shared/i18n';
import { SolIconComponent } from '@shared/ui';
import type { BreadcrumbItem } from '@widgets/breadcrumb';
import { SolHelpDrawerComponent } from '@widgets/help-drawer';
import { SolLayoutShellComponent } from '@widgets/layout-shell';
import { NotificationPanelComponent } from '@widgets/notification-panel/notification-panel.component';
import { getNavIconName, type SidebarItem, type SidebarState } from '@widgets/sidebar';
import {
  SolUserMenuComponent,
  type UserMenuAction,
  type UserMenuNameLines,
} from '@widgets/user-menu';

/** Zona IANA del reloj de soporte del menú de usuario (hora del navegador en esa zona). */
const SUPPORT_TIME_ZONE = 'America/Bogota';

/** Canal externo de soporte que ofrece el panel de ayuda; `null` = no se ofrece enlace. */
const SUPPORT_URL: string | null = null;

/** Cada cuánto se refresca el contador de notificaciones sin leer. */
const UNREAD_POLL_INTERVAL_MS = 60_000;

/** Las migas solo aportan cuando hay un camino: un único tramo repetiría el título de la página. */
const MIN_BREADCRUMB_SEGMENTS = 2;

/**
 * Layout autenticado de Solercia Command: header + sidebar colapsable + contenido de la ruta, con
 * el selector de organización, la campana de notificaciones y el menú de usuario en las acciones
 * del header (el botón de tema ya lo pone `sol-layout-shell` antes de proyectar
 * `[header-actions]`).
 *
 * Esta página vive detrás de `authGuard` en app.routes.ts, así que al renderizar ya se sabe que
 * existe una sesión. Le corresponde al shell, y no a cada página:
 *
 *   - hidratar la sesión al entrar (usuario, menú por permisos, tema de la organización y contador
 *     de notificaciones) y limpiarla al salir;
 *   - el sondeo periódico del contador de notificaciones;
 *   - decidir qué navegación se muestra: el menú del backend, o los enlaces fijos de respaldo
 *     cuando el catálogo llega vacío.
 */
@Component({
  standalone: true,
  selector: 'sol-shell-page',
  imports: [
    SolLayoutShellComponent,
    OrgSwitcherComponent,
    NotificationPanelComponent,
    SolIconComponent,
    SolUserMenuComponent,
    SolHelpDrawerComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '(document:keydown.escape)': 'closeNotifications()' },
  template: `
    <sol-layout-shell
      [sidebarItems]="sidebarItems()"
      [sidebarState]="sidebarState()"
      [sidebarErrorMessage]="menu.errorDetail()"
      [breadcrumbItems]="breadcrumbItems()"
      [showSidebar]="auth.isAuthenticated()"
      (sidebarRetry)="menu.load()"
    >
      <div class="sol-shell-page__user-actions" header-actions>
        <!-- Selector de organización activa -->
        <sol-org-switcher />

        <!-- Campana de notificaciones con su panel desplegable -->
        <div class="sol-shell-page__notifications">
          <button
            type="button"
            class="sol-shell-page__bell"
            aria-haspopup="dialog"
            [attr.aria-expanded]="notificationsOpen()"
            [attr.aria-label]="notificationsLabel()"
            (click)="toggleNotifications()"
          >
            <sol-icon name="bell" class="sol-shell-page__bell-icon" />
            @if (notifications.unreadCount() > 0) {
              <span class="sol-shell-page__bell-badge" aria-hidden="true">
                {{ notifications.unreadCount() > 99 ? '99+' : notifications.unreadCount() }}
              </span>
            }
          </button>

          @if (notificationsOpen()) {
            <div class="sol-shell-page__notifications-panel">
              <sol-notification-center (closed)="closeNotifications()" />
            </div>
          }
        </div>

        <sol-user-menu
          [displayName]="displayName()"
          [nameLines]="nameLines()"
          [subtitle]="auth.user()?.email ?? null"
          [badge]="roleName()"
          [actions]="userActions()"
          [supportTimeZone]="supportTimeZone"
          (action)="onUserAction($event)"
          (logout)="logout()"
        />
      </div>
    </sol-layout-shell>

    <!-- Fondo que cierra el panel de notificaciones al hacer clic fuera. -->
    @if (notificationsOpen()) {
      <button
        type="button"
        class="sol-shell-page__notifications-backdrop"
        [attr.aria-label]="closeNotificationsLabel()"
        (click)="closeNotifications()"
      ></button>
    }

    <!-- Ayuda y soporte: se abre desde el menú de usuario. Hoy no hay catálogo de ayuda
         conectado, así que muestra el vacío legítimo; el canal de soporte llega por configuración. -->
    <sol-help-drawer
      [open]="helpOpen()"
      status="empty"
      [supportUrl]="supportUrl"
      (closed)="helpOpen.set(false)"
    />
  `,
  styles: [`
    .sol-shell-page__user-actions { display: flex; align-items: center; gap: var(--sol-space-sm, 8px); }

    .sol-shell-page__notifications { position: relative; display: inline-flex; }

    /* Misma caja y mismos estados que el botón de tema del header (sol-theme-toggle), para que
       las acciones de ícono se lean como un solo grupo. */
    .sol-shell-page__bell {
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      border: none;
      border-radius: var(--sol-border-radius-md, 8px);
      background: transparent;
      color: var(--sol-color-text-secondary, #4B5563);
      cursor: pointer;
      transition: background-color 0.2s, color 0.2s;
    }

    .sol-shell-page__bell:hover,
    .sol-shell-page__bell[aria-expanded="true"] {
      background: color-mix(in srgb, var(--sol-color-primary, #2563EB) 10%, transparent);
      color: var(--sol-color-primary, #2563EB);
    }

    .sol-shell-page__bell-icon { width: 20px; height: 20px; }

    .sol-shell-page__bell-badge {
      position: absolute;
      top: 0;
      right: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 18px;
      height: 18px;
      padding: 0 4px;
      border-radius: var(--sol-border-radius-full, 9999px);
      background: var(--sol-color-danger, #ef4444);
      color: #ffffff;
      font-size: 10px;
      font-weight: 700;
      line-height: 1;
    }

    .sol-shell-page__notifications-panel {
      position: absolute;
      top: calc(100% + var(--sol-space-sm, 8px));
      right: 0;
      z-index: var(--sol-z-dropdown, 100);
    }

    /* Queda por debajo del header (que tiene su propia capa) y por encima del contenido: un clic
       en la página cierra el panel sin tapar las acciones del header. */
    .sol-shell-page__notifications-backdrop {
      position: fixed;
      inset: 0;
      z-index: 20;
      border: none;
      background: transparent;
      cursor: default;
    }

    @media (max-width: 767px) {
      /* Objetivo táctil bajo el breakpoint canónico (ley de Fitts, 44 px): crece la caja del
         botón, el ícono sigue en 20px. */
      .sol-shell-page__bell {
        width: var(--sol-size-control-touch, 44px);
        height: var(--sol-size-control-touch, 44px);
      }

      .sol-shell-page__bell-badge { top: 4px; right: 4px; }

      /* En móvil la campana no es la última acción del header: anclado a ella, el panel se
         saldría por la izquierda. Se ancla al borde derecho de la pantalla, bajo el header. */
      .sol-shell-page__notifications-panel {
        position: fixed;
        top: calc(var(--sol-size-header-height, 56px) + var(--sol-space-sm, 8px));
        right: var(--sol-space-sm, 8px);
        max-width: calc(100vw - 2 * var(--sol-space-sm, 8px));
      }
    }
  `],
})
export class ShellPageComponent {
  protected readonly auth = inject(AuthService);
  protected readonly menu = inject(MenuService);
  protected readonly notifications = inject(NotificationsService);
  private readonly tenantTheme = inject(TenantThemeService);
  private readonly router = inject(Router);
  private readonly i18n = inject(I18nService);

  /** Zona del reloj de soporte del menú de usuario (hora del navegador, no del servidor). */
  protected readonly supportTimeZone = SUPPORT_TIME_ZONE;

  /** Canal de soporte del panel de ayuda; `null` mientras no haya uno configurado. */
  protected readonly supportUrl = SUPPORT_URL;

  protected readonly helpOpen = signal(false);
  protected readonly notificationsOpen = signal(false);

  protected readonly closeNotificationsLabel = this.i18n.t('nav.closeNotifications');
  private readonly helpLabel = this.i18n.t('widgets.userMenu.help');
  private readonly userFallbackName = this.i18n.t('pages.shell.userFallbackName');

  /** Rótulo accesible de la campana; incluye el número de notificaciones sin leer cuando hay. */
  protected readonly notificationsLabel = computed<string>(() => {
    this.i18n.activeLang();
    const count = this.notifications.unreadCount();
    return count > 0
      ? this.i18n.translate('nav.notificationsUnread', { count })
      : this.i18n.translate('nav.notifications');
  });

  /**
   * Opciones del sidebar, la bottom-nav y las migas: el menú por permisos del backend más la
   * acción fija de importación de tareas. Cuando el catálogo llega vacío —o su carga falla y no
   * hay menú previo— se usan los enlaces fijos de respaldo, para que la persona nunca quede sin
   * navegación. En el caso del fallo el sidebar muestra su estado de error con «Reintentar»
   * (ver `sidebarState`); los enlaces de respaldo solo alimentan la barra móvil.
   */
  protected readonly sidebarItems = computed<SidebarItem[]>(() => {
    this.i18n.activeLang();
    // La vista previa exige membresía, no un permiso de escritura inventado: esta acción fija se
    // conserva aunque el menú del backend venga poblado.
    const importAction: SidebarItem = {
      id: 'task-import-preview',
      label: this.i18n.translate('taskImport.title'),
      icon: 'view-columns',
      route: '/tasks/import',
    };
    const menuItems = this.menu.sidebarItems();
    if (menuItems.length > 0) {
      return [...menuItems, importAction];
    }
    const status = this.menu.status();
    if (status !== 'empty' && status !== 'error') {
      return [];
    }
    return [
      importAction,
      {
        id: 'projects',
        label: this.i18n.translate('nav.links.projects'),
        icon: 'view-columns',
        route: '/projects',
      },
      {
        id: 'hierarchy',
        label: this.i18n.translate('nav.links.hierarchy'),
        icon: 'layers',
        route: '/hierarchy',
      },
      {
        id: 'executive',
        label: this.i18n.translate('nav.links.executive'),
        icon: 'eye',
        route: '/executive',
      },
      {
        id: 'performance',
        label: this.i18n.translate('nav.links.performance'),
        icon: 'bar-chart',
        route: '/performance',
      },
      {
        id: 'plans',
        label: this.i18n.translate('nav.links.plans'),
        icon: 'clipboard',
        route: '/plans',
      },
    ];
  });

  /**
   * Traduce el estado del menú al vocabulario del sidebar. `idle` (la carga está por dispararse)
   * se pinta como cargando para que el menú no arranque vacío; `empty` es `ready` porque los
   * enlaces de respaldo ocupan su lugar.
   */
  protected readonly sidebarState = computed<SidebarState>(() => {
    switch (this.menu.status()) {
      case 'idle':
      case 'loading':
        return 'loading';
      case 'error':
        return 'error';
      default:
        return 'ready';
    }
  });

  /** URL activa, para resolver las migas de pan contra el árbol del menú. */
  private readonly currentUrl = toSignal(
    this.router.events.pipe(
      filter((event): event is NavigationEnd => event instanceof NavigationEnd),
      map((event) => event.urlAfterRedirects),
    ),
    { initialValue: this.router.url },
  );

  /**
   * Migas de pan desde el árbol del menú: sección → agrupaciones → opción actual. Una vista sin
   * ítem propio en el menú (un detalle, por ejemplo) no tiene camino y la franja no se pinta.
   */
  protected readonly breadcrumbItems = computed<BreadcrumbItem[]>(() => {
    const trail = breadcrumbTrail(this.sidebarItems(), this.currentUrl());
    // La hoja que conserva la ruta propia de una agrupación repetiría el nombre de su padre.
    const segments = trail.filter((item) => !isOwnRouteLeaf(item));
    if (segments.length < MIN_BREADCRUMB_SEGMENTS) {
      return [];
    }
    return segments.map((item, index) => ({
      label: item.label,
      route: item.route,
      icon: index === 0 ? getNavIconName(item.icon) : undefined,
    }));
  });

  /**
   * Nombre a mostrar: el nombre completo si existe; si no, el correo. Mientras `/auth/me` no
   * responde se usa un genérico, para que el disparador del menú no arranque vacío.
   */
  protected readonly displayName = computed<string>(() => {
    const user = this.auth.user();
    if (!user) return this.userFallbackName();
    const lines = this.nameLines();
    const composed = lines ? `${lines.given} ${lines.family}` : '';
    return user.full_name?.trim() || composed || user.email;
  });

  /** Nombres y apellidos desde los campos explícitos del usuario, nunca partiendo un nombre. */
  protected readonly nameLines = computed<UserMenuNameLines | null>(() => {
    const user = this.auth.user();
    if (!user) return null;
    const join = (...parts: (string | null | undefined)[]) =>
      parts
        .map((part) => part?.trim() ?? '')
        .filter(Boolean)
        .join(' ');
    const given = join(user.primer_nombre, user.segundo_nombre);
    const family = join(user.primer_apellido, user.segundo_apellido);
    return given && family ? { given, family } : null;
  });

  protected readonly roleName = computed(() => this.auth.user()?.roles?.[0]?.name ?? null);

  protected readonly userActions = computed<UserMenuAction[]>(() => [
    { id: 'help', label: this.helpLabel() },
  ]);

  constructor() {
    // Hidrata la sesión (usuario, menú, tema de la organización y contador de notificaciones) en
    // cuanto hay autenticación, y limpia el estado al cerrarla. Las guardas evitan llamadas
    // duplicadas cuando el efecto se vuelve a ejecutar.
    effect(() => {
      if (this.auth.isAuthenticated()) {
        if (!this.auth.user()) {
          this.auth.me().subscribe({ next: () => {}, error: () => {} });
        }
        if (!this.menu.loaded()) {
          this.menu.load();
        }
        // Tema de la organización (multi-tenant): se carga una vez por sesión y se aplica vía
        // ThemeService; null = tema por defecto.
        if (!this.tenantTheme.loaded()) {
          this.tenantTheme.load();
        }
        this.notifications.refreshUnreadCount();
      } else {
        this.clearSessionState();
      }
    });

    // Sondeo del contador de notificaciones mientras el shell esté vivo.
    interval(UNREAD_POLL_INTERVAL_MS)
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        if (this.auth.isAuthenticated()) {
          this.notifications.refreshUnreadCount();
        }
      });

    // Una sesión que se pierde fuera de `logout()` (el interceptor la descarta cuando falla el
    // refresco y navega al inicio de sesión) puede destruir el shell antes de que el efecto de
    // arriba vuelva a correr: sin esto, el siguiente usuario heredaría el menú y el tema.
    inject(DestroyRef).onDestroy(() => {
      if (!this.auth.isAuthenticated()) {
        this.clearSessionState();
      }
    });
  }

  protected toggleNotifications(): void {
    this.notificationsOpen.update((open) => !open);
  }

  protected closeNotifications(): void {
    this.notificationsOpen.set(false);
  }

  protected onUserAction(id: string): void {
    if (id === 'help') this.helpOpen.set(true);
  }

  protected logout(): void {
    this.auth.logout();
    this.clearSessionState();
    void this.router.navigate(['/login']);
  }

  /** Descarta lo que pertenece a la sesión: menú, tema de la organización y paneles abiertos. */
  private clearSessionState(): void {
    this.menu.clear();
    this.tenantTheme.clear();
    this.notificationsOpen.set(false);
    this.helpOpen.set(false);
  }
}
