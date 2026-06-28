import {
  ChangeDetectionStrategy,
  Component,
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
import { ThemeService } from './core/theme.service';
import { AuthService } from './core/auth.service';
import { MenuService } from './core/menu.service';

/** Application shell: top bar (brand, nav, theme toggle, logout) + router outlet. */
@Component({
  selector: 'sp-root',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <div class="flex min-h-screen flex-col bg-page text-text transition-colors">
      <header
        class="sticky top-0 z-20 border-b border-border bg-surface/80 backdrop-blur"
      >
        <div
          class="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-4"
        >
          <div class="flex items-center gap-6">
            <a
              class="flex items-center gap-2 font-semibold tracking-tight"
              routerLink="/projects"
              aria-label="Solercia PM, inicio"
            >
              <span
                class="grid h-7 w-7 place-items-center rounded-lg bg-brand text-brand-fg text-sm font-bold"
                aria-hidden="true"
                >S</span
              >
              <span class="text-text">Solercia PM</span>
            </a>

            @if (auth.isAuthenticated()) {
              <nav
                class="hidden items-center gap-1 sm:flex"
                aria-label="Navegación principal"
              >
                @if (useMenuNav()) {
                  @for (item of menu.menus(); track item.id) {
                    @if (item.children.length > 0) {
                      <!-- Parent with children: dropdown -->
                      <div class="relative">
                        <button
                          type="button"
                          (click)="toggleDropdown(item.id)"
                          [attr.aria-expanded]="openId() === item.id"
                          class="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm font-medium text-muted transition-colors hover:bg-muted/10 hover:text-text"
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
                            class="absolute left-0 top-full z-30 mt-1 min-w-48 rounded-lg border border-border bg-surface p-1 shadow-lg"
                          >
                            @for (child of item.children; track child.id) {
                              @if (child.path) {
                                <a
                                  [routerLink]="child.path"
                                  routerLinkActive="bg-brand/10 !text-brand"
                                  (click)="closeDropdown()"
                                  class="block rounded-md px-3 py-1.5 text-sm font-medium text-muted transition-colors hover:bg-muted/10 hover:text-text"
                                >
                                  {{ child.name }}
                                </a>
                              }
                            }
                          </div>
                        }
                      </div>
                    } @else if (item.path) {
                      <!-- Leaf: direct link -->
                      <a
                        [routerLink]="item.path"
                        routerLinkActive="bg-brand/10 !text-brand"
                        class="rounded-lg px-3 py-1.5 text-sm font-medium text-muted transition-colors hover:bg-muted/10 hover:text-text"
                      >
                        {{ item.name }}
                      </a>
                    }
                  }
                } @else {
                  <!-- Fallback static links when the menu tree is unavailable -->
                  <a
                    routerLink="/projects"
                    routerLinkActive="bg-brand/10 !text-brand"
                    class="rounded-lg px-3 py-1.5 text-sm font-medium text-muted transition-colors hover:bg-muted/10 hover:text-text"
                  >
                    Proyectos
                  </a>
                  <a
                    routerLink="/executive"
                    routerLinkActive="bg-brand/10 !text-brand"
                    class="rounded-lg px-3 py-1.5 text-sm font-medium text-muted transition-colors hover:bg-muted/10 hover:text-text"
                  >
                    Vista de jefe
                  </a>
                  <a
                    routerLink="/performance"
                    routerLinkActive="bg-brand/10 !text-brand"
                    class="rounded-lg px-3 py-1.5 text-sm font-medium text-muted transition-colors hover:bg-muted/10 hover:text-text"
                  >
                    Rendimiento
                  </a>
                }
              </nav>
            }
          </div>

          <div class="flex items-center gap-2">
            <button
              type="button"
              (click)="theme.toggle()"
              [attr.aria-label]="
                theme.isDark() ? 'Activa el modo claro' : 'Activa el modo oscuro'
              "
              class="grid h-9 w-9 place-items-center rounded-lg border border-border
                     bg-surface text-text transition-colors hover:bg-muted/10
                     focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
            >
              @if (theme.isDark()) {
                <!-- Sun -->
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
                <!-- Moon -->
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
              <button
                type="button"
                (click)="logout()"
                class="inline-flex h-9 items-center gap-2 rounded-lg border border-border
                       bg-surface px-3 text-sm font-medium text-text transition-colors
                       hover:bg-muted/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
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
            }
          </div>
        </div>
      </header>

      <!-- Click-away backdrop for the open dropdown. -->
      @if (openId()) {
        <button
          type="button"
          (click)="closeDropdown()"
          aria-label="Cierra el menú"
          class="fixed inset-0 z-10 cursor-default"
        ></button>
      }

      <main class="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <router-outlet></router-outlet>
      </main>
    </div>
  `,
})
export class AppComponent {
  protected readonly theme = inject(ThemeService);
  protected readonly auth = inject(AuthService);
  protected readonly menu = inject(MenuService);
  private readonly router = inject(Router);

  /** Which dropdown (by menu id) is open, or null. */
  protected readonly openId = signal<string | null>(null);

  /** Use the menu-driven nav only when a non-empty tree has loaded. */
  protected readonly useMenuNav = computed<boolean>(
    () => this.menu.loaded() && this.menu.menus().length > 0,
  );

  constructor() {
    // Hydrate the session (user + menus) whenever authentication turns on,
    // and clear the menu tree on logout. Guards prevent duplicate calls.
    effect(() => {
      if (this.auth.isAuthenticated()) {
        if (!this.auth.user()) {
          this.auth.me().subscribe({ next: () => {}, error: () => {} });
        }
        if (!this.menu.loaded()) {
          this.menu.load();
        }
      } else {
        this.menu.clear();
        this.openId.set(null);
      }
    });
  }

  protected toggleDropdown(id: string): void {
    this.openId.update((current) => (current === id ? null : id));
  }

  protected closeDropdown(): void {
    this.openId.set(null);
  }

  protected logout(): void {
    this.closeDropdown();
    this.auth.logout();
    void this.router.navigate(['/login']);
  }
}
