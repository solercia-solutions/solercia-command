import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import {
  Router,
  RouterLink,
  RouterLinkActive,
  RouterOutlet,
} from '@angular/router';
import { interval } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ThemeService } from '@solercia/ui';
import { AuthService } from '@features/auth/auth.service';
import { MenuService } from '@features/navigation/menu.service';
import { NotificationsService } from '@entities/notification/notifications.service';
import { NotificationPanelComponent } from '@widgets/notification-panel/notification-panel.component';
import { SolIconComponent } from '@shared/ui';
import { I18nService } from '@shared/i18n';

/** Application shell: top bar (brand, nav, notification bell, theme toggle, logout) + router outlet. */
@Component({
  selector: 'app-root',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    NotificationPanelComponent,
    SolIconComponent,
  ],
  template: `
    <div class="flex min-h-screen flex-col bg-page text-text">
      <header
        class="sticky top-0 z-30 border-b border-border bg-surface/80 backdrop-blur-md"
      >
        <div
          class="mx-auto flex h-16 w-full max-w-7xl items-center justify-between gap-3 px-4 sm:px-6"
        >
          <div class="flex items-center gap-6">
            <a
              class="flex items-center gap-2.5"
              routerLink="/projects"
              [attr.aria-label]="text.brandAria()"
            >
              <span
                class="grid h-8 w-8 place-items-center rounded-xl bg-brand text-brand-fg text-sm font-bold shadow-sm"
                aria-hidden="true"
                >S</span
              >
              <span
                class="font-display text-[15px] font-bold tracking-tight text-text"
                >Solercia PM</span
              >
            </a>

            @if (auth.isAuthenticated()) {
              <nav
                class="hidden items-center gap-1 md:flex"
                [attr.aria-label]="text.primaryNavAria()"
              >
                @if (useMenuNav()) {
                  @for (item of menu.menus(); track item.id) {
                    @if (item.children.length > 0) {
                      <div class="relative">
                        <button
                          type="button"
                          (click)="toggleDropdown(item.id)"
                          [attr.aria-expanded]="openId() === item.id"
                          class="inline-flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-sunken hover:text-text"
                        >
                          {{ item.name }}
                          <sol-icon name="chevron-down" size="sm" />
                        </button>
                        @if (openId() === item.id) {
                          <div
                            class="absolute left-0 top-full z-30 mt-1.5 min-w-52 rounded-xl border border-border bg-elevated p-1.5 shadow-lg"
                          >
                            @for (child of item.children; track child.id) {
                              @if (child.path) {
                                <a
                                  [routerLink]="child.path"
                                  routerLinkActive="bg-brand-soft !text-brand-soft-fg"
                                  (click)="closeDropdown()"
                                  class="block rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-sunken hover:text-text"
                                >
                                  {{ child.name }}
                                </a>
                              }
                            }
                          </div>
                        }
                      </div>
                    } @else if (item.path) {
                      <a
                        [routerLink]="item.path"
                        routerLinkActive="bg-brand-soft !text-brand-soft-fg"
                        class="rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-sunken hover:text-text"
                      >
                        {{ item.name }}
                      </a>
                    }
                  }
                } @else {
                  @for (link of fallbackLinks(); track link.path) {
                    <a
                      [routerLink]="link.path"
                      routerLinkActive="bg-brand-soft !text-brand-soft-fg"
                      class="rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-sunken hover:text-text"
                    >
                      {{ link.label }}
                    </a>
                  }
                }
              </nav>
            }
          </div>

          <div class="flex items-center gap-2">
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
                    <sol-notification-panel (closed)="closeNotif()" />
                  </div>
                }
              </div>

              <!-- Logout button -->
              <button
                type="button"
                (click)="logout()"
                class="hidden h-9 items-center gap-2 rounded-lg border border-border
                       bg-surface px-3 text-sm font-medium text-text transition-colors
                       hover:bg-sunken focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/55 sm:inline-flex"
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
                <span>{{ text.logout() }}</span>
              </button>

              <!-- Mobile menu toggle -->
              <button
                type="button"
                (click)="toggleMobile()"
                [attr.aria-expanded]="mobileOpen()"
                [attr.aria-label]="text.mobileMenuAria()"
                class="grid h-9 w-9 place-items-center rounded-lg border border-border
                       bg-surface text-muted transition-colors hover:bg-sunken hover:text-text
                       focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/55 md:hidden"
              >
                @if (mobileOpen()) {
                  <sol-icon name="x" size="md" />
                } @else {
                  <sol-icon name="menu" size="md" />
                }
              </button>
            }
          </div>
        </div>

        <!-- Mobile navigation panel -->
        @if (auth.isAuthenticated() && mobileOpen()) {
          <nav
            class="border-t border-border bg-surface px-4 py-3 md:hidden"
            [attr.aria-label]="text.mobileNavAria()"
          >
            <div class="flex flex-col gap-0.5">
              @if (useMenuNav()) {
                @for (item of menu.menus(); track item.id) {
                  @if (item.children.length > 0) {
                    <p class="px-3 pb-1 pt-2 text-xs font-semibold uppercase tracking-wide text-subtle">
                      {{ item.name }}
                    </p>
                    @for (child of item.children; track child.id) {
                      @if (child.path) {
                        <a
                          [routerLink]="child.path"
                          routerLinkActive="bg-brand-soft !text-brand-soft-fg"
                          (click)="closeMobile()"
                          class="rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-sunken hover:text-text"
                        >
                          {{ child.name }}
                        </a>
                      }
                    }
                  } @else if (item.path) {
                    <a
                      [routerLink]="item.path"
                      routerLinkActive="bg-brand-soft !text-brand-soft-fg"
                      (click)="closeMobile()"
                      class="rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-sunken hover:text-text"
                    >
                      {{ item.name }}
                    </a>
                  }
                }
              } @else {
                @for (link of fallbackLinks(); track link.path) {
                  <a
                    [routerLink]="link.path"
                    routerLinkActive="bg-brand-soft !text-brand-soft-fg"
                    (click)="closeMobile()"
                    class="rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-sunken hover:text-text"
                  >
                    {{ link.label }}
                  </a>
                }
              }
              <button
                type="button"
                (click)="logout()"
                class="mt-1 inline-flex items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium text-danger transition-colors hover:bg-danger-soft"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" /></svg>
                {{ text.logout() }}
              </button>
            </div>
          </nav>
        }
      </header>

      <!-- Click-away backdrop for nav dropdowns. -->
      @if (openId()) {
        <button
          type="button"
          (click)="closeDropdown()"
          [attr.aria-label]="text.closeMenu()"
          class="fixed inset-0 z-20 cursor-default"
        ></button>
      }

      <!-- Click-away backdrop for the notification panel. -->
      @if (notifOpen()) {
        <button
          type="button"
          (click)="closeNotif()"
          [attr.aria-label]="text.closeNotifications()"
          class="fixed inset-0 z-20 cursor-default"
        ></button>
      }

      <main class="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <div class="sol-animate-in">
          <router-outlet></router-outlet>
        </div>
      </main>
    </div>
  `,
})
export class AppComponent {
  protected readonly theme = inject(ThemeService);
  protected readonly auth = inject(AuthService);
  protected readonly menu = inject(MenuService);
  protected readonly notifs = inject(NotificationsService);
  private readonly router = inject(Router);
  private readonly i18n = inject(I18nService);

  /** Static UI text resolved via i18n (reactive to language change). */
  protected readonly text = {
    brandAria: this.i18n.t('nav.brandAria'),
    primaryNavAria: this.i18n.t('nav.primaryNavAria'),
    mobileNavAria: this.i18n.t('nav.mobileNavAria'),
    themeToLight: this.i18n.t('nav.themeToLight'),
    themeToDark: this.i18n.t('nav.themeToDark'),
    logout: this.i18n.t('nav.logout'),
    mobileMenuAria: this.i18n.t('nav.mobileMenuAria'),
    closeMenu: this.i18n.t('nav.closeMenu'),
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

  /** Which nav dropdown (by menu id) is open, or null. */
  protected readonly openId = signal<string | null>(null);

  /** Whether the mobile navigation panel is open. */
  protected readonly mobileOpen = signal(false);

  /** Whether the notification panel is open. */
  protected readonly notifOpen = signal(false);

  /** Static fallback nav links when the menu tree is unavailable. */
  protected readonly fallbackLinks = computed(() => {
    this.i18n.activeLang();
    return [
      { path: '/projects', label: this.i18n.translate('nav.links.projects') },
      { path: '/hierarchy', label: this.i18n.translate('nav.links.hierarchy') },
      { path: '/executive', label: this.i18n.translate('nav.links.executive') },
      { path: '/performance', label: this.i18n.translate('nav.links.performance') },
    ];
  });

  /** Use the menu-driven nav only when a non-empty tree has loaded. */
  protected readonly useMenuNav = computed<boolean>(
    () => this.menu.loaded() && this.menu.menus().length > 0,
  );

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
        // Seed the notification badge as soon as the user is authenticated.
        this.notifs.refreshUnreadCount();
      } else {
        this.menu.clear();
        this.openId.set(null);
        this.notifOpen.set(false);
        this.mobileOpen.set(false);
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

  /** Close all overlays when the user presses Escape. */
  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.closeNotif();
    this.closeDropdown();
  }

  protected toggleDropdown(id: string): void {
    this.notifOpen.set(false);
    this.openId.update((current) => (current === id ? null : id));
  }

  protected closeDropdown(): void {
    this.openId.set(null);
  }

  protected toggleNotif(): void {
    this.openId.set(null);
    this.notifOpen.update((v) => !v);
  }

  protected closeNotif(): void {
    this.notifOpen.set(false);
  }

  protected toggleMobile(): void {
    this.mobileOpen.update((v) => !v);
  }

  protected closeMobile(): void {
    this.mobileOpen.set(false);
  }

  protected logout(): void {
    this.closeDropdown();
    this.closeNotif();
    this.closeMobile();
    this.auth.logout();
    void this.router.navigate(['/login']);
  }
}
