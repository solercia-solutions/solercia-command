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
import { AuthService } from './core/auth.service';
import { MenuService } from './core/menu.service';
import { NotificationsService } from './features/notifications/notifications.service';
import { NotificationPanelComponent } from './features/notifications/notification-panel.component';

/** Application shell: top bar (brand, nav, notification bell, theme toggle, logout) + router outlet. */
@Component({
  selector: 'bk-root',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, NotificationPanelComponent],
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
              aria-label="Solercia PM, inicio"
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
                aria-label="Navegación principal"
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
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="2"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                            aria-hidden="true"
                          >
                            <polyline points="6 9 12 15 18 9" />
                          </svg>
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
                  @for (link of fallbackLinks; track link.path) {
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
                theme.isDark() ? 'Activa el modo claro' : 'Activa el modo oscuro'
              "
              class="grid h-9 w-9 place-items-center rounded-lg border border-border
                     bg-surface text-muted transition-colors hover:bg-sunken hover:text-text
                     focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/55"
            >
              @if (theme.isDark()) {
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  aria-hidden="true"
                >
                  <circle cx="12" cy="12" r="4" />
                  <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
                </svg>
              } @else {
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  aria-hidden="true"
                >
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              }
            </button>

            @if (auth.isAuthenticated()) {
              <!-- Notification bell -->
              <div class="relative">
                <button
                  type="button"
                  (click)="toggleNotif()"
                  [attr.aria-expanded]="notifOpen()"
                  [attr.aria-label]="
                    notifs.unreadCount() > 0
                      ? 'Centro de notificaciones, ' + notifs.unreadCount() + ' sin leer'
                      : 'Centro de notificaciones'
                  "
                  class="relative grid h-9 w-9 place-items-center rounded-lg border border-border
                         bg-surface text-muted transition-colors hover:bg-sunken hover:text-text
                         focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/55"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                  </svg>
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
                    <bk-notification-panel (closed)="closeNotif()" />
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
                <span>Cerrar sesión</span>
              </button>

              <!-- Mobile menu toggle -->
              <button
                type="button"
                (click)="toggleMobile()"
                [attr.aria-expanded]="mobileOpen()"
                aria-label="Abre el menú de navegación"
                class="grid h-9 w-9 place-items-center rounded-lg border border-border
                       bg-surface text-muted transition-colors hover:bg-sunken hover:text-text
                       focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/55 md:hidden"
              >
                @if (mobileOpen()) {
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
                } @else {
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" /></svg>
                }
              </button>
            }
          </div>
        </div>

        <!-- Mobile navigation panel -->
        @if (auth.isAuthenticated() && mobileOpen()) {
          <nav
            class="border-t border-border bg-surface px-4 py-3 md:hidden"
            aria-label="Navegación móvil"
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
                @for (link of fallbackLinks; track link.path) {
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
                Cerrar sesión
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
          aria-label="Cierra el menú"
          class="fixed inset-0 z-20 cursor-default"
        ></button>
      }

      <!-- Click-away backdrop for the notification panel. -->
      @if (notifOpen()) {
        <button
          type="button"
          (click)="closeNotif()"
          aria-label="Cierra las notificaciones"
          class="fixed inset-0 z-20 cursor-default"
        ></button>
      }

      <main class="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <div class="sp-animate-in">
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

  /** Which nav dropdown (by menu id) is open, or null. */
  protected readonly openId = signal<string | null>(null);

  /** Whether the mobile navigation panel is open. */
  protected readonly mobileOpen = signal(false);

  /** Whether the notification panel is open. */
  protected readonly notifOpen = signal(false);

  /** Static fallback nav links when the menu tree is unavailable. */
  protected readonly fallbackLinks = [
    { path: '/projects', label: 'Proyectos' },
    { path: '/executive', label: 'Vista de jefe' },
    { path: '/performance', label: 'Rendimiento' },
  ];

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
