import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { Router } from '@angular/router';
import { interval } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ThemeService } from '@solercia/ui';
import { AuthService } from '@features/auth/auth.service';
import { MenuService, MenuNode } from '@features/navigation/menu.service';
import { TenantThemeService } from '@features/theme/tenant-theme.service';
import { NotificationsService } from '@entities/notification/notifications.service';
import { NotificationPanelComponent } from '@widgets/notification-panel/notification-panel.component';
import { SolLayoutShellComponent } from '@widgets/layout-shell';
import { SidebarItem } from '@widgets/sidebar';
import { SolIconComponent } from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { ToastHostComponent } from '@shared/lib/toast';
import { OrgSwitcherComponent } from '@features/organizations/org-switcher.component';

/**
 * Application shell: layout-shell (header + collapsible sidebar + mobile
 * bottom-nav + routed content) with the session actions (theme toggle,
 * notification bell, logout) projected into the header actions slot.
 *
 * The sidebar and bottom-nav render only for the authenticated app; login
 * and /auth/callback keep the bare header (same `auth.isAuthenticated()`
 * condition the previous horizontal nav used).
 */
@Component({
  selector: 'app-root',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    SolLayoutShellComponent,
    NotificationPanelComponent,
    SolIconComponent,
    OrgSwitcherComponent,
    ToastHostComponent,
  ],
  template: `
    <sol-layout-shell
      [sidebarItems]="sidebarItems()"
      [showSidebar]="auth.isAuthenticated()"
    >
      <div header-actions class="flex items-center gap-2">
        @if (auth.isAuthenticated()) {
          <!-- Selector de empresa activa -->
          <sol-org-switcher />
        }

        <!-- Theme toggle -->
        <button
          type="button"
          (click)="theme.toggleMode()"
          [attr.aria-label]="
            theme.isDark() ? text.themeToLight() : text.themeToDark()
          "
          class="grid h-9 w-9 place-items-center rounded-lg border border-border
                 bg-surface text-muted transition-colors hover:bg-sunken hover:text-text
                 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/55"
        >
          @if (theme.isDark()) {
            <sol-icon name="sun" size="md" />
          } @else {
            <sol-icon name="moon" size="md" />
          }
        </button>

        @if (auth.isAuthenticated()) {
          <!-- Notification bell -->
          <div class="relative">
            <button
              type="button"
              (click)="toggleNotif()"
              [attr.aria-expanded]="notifOpen()"
              [attr.aria-label]="notifAria()"
              class="relative grid h-9 w-9 place-items-center rounded-lg border border-border
                     bg-surface text-muted transition-colors hover:bg-sunken hover:text-text
                     focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/55"
            >
              <sol-icon name="bell" size="md" />
              @if (notifs.unreadCount() > 0) {
                <span
                  aria-hidden="true"
                  class="absolute -right-1 -top-1 flex min-h-[18px] min-w-[18px] items-center
                         justify-center rounded-full bg-danger px-1
                         text-[10px] font-bold leading-none text-white"
                >
                  {{ notifs.unreadCount() > 99 ? '99+' : notifs.unreadCount() }}
                </span>
              }
            </button>

            <!-- Notification panel dropdown -->
            @if (notifOpen()) {
              <div class="absolute right-0 top-full z-40 mt-2">
                <sol-notification-center (closed)="closeNotif()" />
              </div>
            }
          </div>

          <!-- Logout button (icon-only on mobile, icon + text from sm up) -->
          <button
            type="button"
            (click)="logout()"
            [attr.aria-label]="text.logout()"
            class="inline-flex h-9 items-center gap-2 rounded-lg border border-border
                   bg-surface px-3 text-sm font-medium text-text transition-colors
                   hover:bg-sunken focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/55"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            <span class="hidden sm:inline">{{ text.logout() }}</span>
          </button>
        }
      </div>
    </sol-layout-shell>

    <!-- Click-away backdrop for the notification panel. -->
    @if (notifOpen()) {
      <button
        type="button"
        (click)="closeNotif()"
        [attr.aria-label]="text.closeNotifications()"
        class="fixed inset-0 z-20 cursor-default"
      ></button>
    }

    <!-- Transient feedback (toasts) for the whole app; pages only call ToastStore. -->
    <sol-toast-host />
  `,
})
export class AppComponent {
  protected readonly theme = inject(ThemeService);
  protected readonly auth = inject(AuthService);
  protected readonly menu = inject(MenuService);
  private readonly tenantTheme = inject(TenantThemeService);
  protected readonly notifs = inject(NotificationsService);
  private readonly router = inject(Router);
  private readonly i18n = inject(I18nService);

  /** Static UI text resolved via i18n (reactive to language change). */
  protected readonly text = {
    themeToLight: this.i18n.t('nav.themeToLight'),
    themeToDark: this.i18n.t('nav.themeToDark'),
    logout: this.i18n.t('nav.logout'),
    closeNotifications: this.i18n.t('nav.closeNotifications'),
  } as const;

  /** Notification bell aria-label; includes the unread count when > 0. */
  protected readonly notifAria = computed<string>(() => {
    this.i18n.activeLang();
    const count = this.notifs.unreadCount();
    return count > 0
      ? this.i18n.translate('nav.notificationsUnread', { count })
      : this.i18n.translate('nav.notifications');
  });

  /** Whether the notification panel is open. */
  protected readonly notifOpen = signal(false);

  /** Use the menu-driven nav only when a non-empty tree has loaded. */
  protected readonly useMenuNav = computed<boolean>(
    () => this.menu.loaded() && this.menu.menus().length > 0,
  );

  /**
   * Items for the sidebar/bottom-nav: the permission-driven menu tree when
   * available, otherwise the static fallback links (same fallback the old
   * horizontal nav had).
   */
  protected readonly sidebarItems = computed<SidebarItem[]>(() => {
    if (this.useMenuNav()) {
      return menuNodesToSidebarItems(this.menu.menus());
    }
    this.i18n.activeLang();
    return [
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
    ];
  });

  constructor() {
    // Hydrate the session (user + menus) whenever authentication turns on,
    // and clear state on logout. Guards prevent duplicate calls.
    effect(() => {
      if (this.auth.isAuthenticated()) {
        if (!this.auth.user()) {
          this.auth.me().subscribe({ next: () => {}, error: () => {} });
        }
        if (!this.menu.loaded()) {
          this.menu.load();
        }
        // Tema de la organización (multi-tenant): se carga una vez por
        // sesión y se aplica vía ThemeService; null = tema por defecto.
        if (!this.tenantTheme.loaded()) {
          this.tenantTheme.load();
        }
        // Seed the notification badge as soon as the user is authenticated.
        this.notifs.refreshUnreadCount();
      } else {
        this.menu.clear();
        this.tenantTheme.clear();
        this.notifOpen.set(false);
      }
    });

    // Poll unread count every 60 seconds while the component is alive.
    interval(60_000)
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        if (this.auth.isAuthenticated()) {
          this.notifs.refreshUnreadCount();
        }
      });
  }

  /** Close the notification panel when the user presses Escape. */
  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.closeNotif();
  }

  protected toggleNotif(): void {
    this.notifOpen.update((v) => !v);
  }

  protected closeNotif(): void {
    this.notifOpen.set(false);
  }

  protected logout(): void {
    this.closeNotif();
    this.auth.logout();
    void this.router.navigate(['/login']);
  }
}

/**
 * Maps the permission-driven menu tree (`MenuNode`) to the shape the
 * sidebar/bottom-nav widgets consume (`SidebarItem`): name → label,
 * path → route.
 */
function menuNodesToSidebarItems(nodes: MenuNode[]): SidebarItem[] {
  return nodes.map((node) => ({
    id: node.id,
    label: node.name,
    icon: node.icon,
    route: node.path,
    children: node.children.length
      ? menuNodesToSidebarItems(node.children)
      : undefined,
  }));
}
