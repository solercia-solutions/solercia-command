import {
  Component,
  ChangeDetectionStrategy,
  inject,
  input,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { SolHeaderComponent } from '@widgets/header';
import { SolSidebarComponent, SolBottomNavComponent, SidebarItem } from '@widgets/sidebar';

/** localStorage key for the persisted sidebar collapsed state. */
const SIDEBAR_COLLAPSED_KEY = 'sp-sidebar-collapsed';

/**
 * Application layout shell (ported from boki-front `widgets/layout-shell`).
 *
 * Composes the fixed header, the collapsible sidebar, the mobile bottom-nav
 * and the routed content. The host projects its header actions (theme
 * toggle, notification bell, logout...) through the `[header-actions]` slot.
 *
 * Host improvement over boki: the collapsed state persists in localStorage
 * (`sp-sidebar-collapsed`) so it survives reloads.
 */
@Component({
  selector: 'sol-layout-shell',
  standalone: true,
  imports: [RouterOutlet, SolHeaderComponent, SolSidebarComponent, SolBottomNavComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <sol-header
      [showSidebarToggle]="showSidebar()"
      (sidebarToggle)="onSidebarToggle()"
    >
      <ng-content select="[header-actions]" />
    </sol-header>

    @if (showSidebar()) {
      <sol-sidebar
        [items]="sidebarItems()"
        [collapsed]="sidebarCollapsed()"
        (collapsedChange)="setCollapsed($event)"
      />
      <!-- Navegación móvil (estructura base): bajo el breakpoint el sidebar
           se oculta y esta bottom-nav fija toma su lugar. CSS decide la
           visibilidad — cero lógica condicional por tenant. -->
      <sol-bottom-nav [items]="sidebarItems()" />
    }

    <main
      class="sol-layout-main"
      [class.sol-layout-main--with-sidebar]="showSidebar()"
      [class.sol-layout-main--collapsed]="showSidebar() && sidebarCollapsed()"
    >
      <!-- Transición de ruta (motion v2): el wrapper alterna keyframes base ↔ B
           en cada NavigationEnd para re-disparar la entrada sin @angular/animations. -->
      <div class="sol-route-anim sol-layout-content" [class.sol-route-anim--b]="routeAnimToggle()">
        <router-outlet />
      </div>
    </main>
  `,
  styles: `
    :host {
      display: block;
      min-height: 100vh;
    }

    .sol-layout-main {
      padding-top: var(--sol-size-header-height, 56px);
      /* 100dvh (no 100vh): en móvil Safari 100vh mide el viewport SIN
         descontar la barra dinámica del navegador — 100dvh sí refleja el
         alto real visible en cada momento. */
      min-height: 100dvh;
      transition: margin-left var(--sol-dur-base, 240ms) var(--sol-ease, ease);
      padding-left: 24px;
      padding-right: 24px;
      padding-bottom: 24px;
    }

    .sol-layout-main--with-sidebar {
      margin-left: var(--sol-size-sidebar-width, 260px);
    }

    .sol-layout-main--collapsed {
      margin-left: 64px;
    }

    /* El contenido conserva el contenedor centrado del shell anterior. */
    .sol-layout-content {
      width: 100%;
      max-width: 80rem;
      margin-left: auto;
      margin-right: auto;
      padding-top: 1.5rem;
    }

    /* Estructura base móvil: sin sidebar no hay margen izquierdo y el
       contenido reserva espacio para la bottom-nav fija (58px + safe-area)
       para que nada quede tapado. */
    @media (max-width: 767px) {
      .sol-layout-main--with-sidebar,
      .sol-layout-main--collapsed {
        margin-left: 0;
      }

      .sol-layout-main {
        padding-left: 16px;
        padding-right: 16px;
        padding-bottom: calc(58px + env(safe-area-inset-bottom, 0px) + 16px);
        /* En móvil el contenido de la página nunca debe generar scroll
           horizontal del documento. overflow-x clip no crea contexto de
           scroll ni recorta los popovers position:fixed. */
        overflow-x: clip;
        max-width: 100%;
      }
    }

    /* Entrada del contenido de la ruta con los tokens de motion del tema.
       Keyframes globales solRevealRise/B (styles.scss): opacity +
       translateY(var(--sol-reveal-dist)). Fill "backwards" y NO "both": un
       transform residual convertiría al wrapper en containing block de los
       position:fixed de las páginas (modales, dropdowns). */
    .sol-route-anim {
      animation: solRevealRise var(--sol-dur-base, 240ms) var(--sol-ease-entrance, ease-out) backwards;
    }

    .sol-route-anim--b {
      animation-name: solRevealRiseB;
    }
  `,
})
export class SolLayoutShellComponent {
  private readonly router = inject(Router);

  /** List of sidebar navigation items. */
  readonly sidebarItems = input<SidebarItem[]>([]);

  /** Whether to show the sidebar (and the mobile bottom-nav). */
  readonly showSidebar = input<boolean>(true);

  /** Collapsed state for the sidebar, hydrated from localStorage. */
  readonly sidebarCollapsed = signal(readPersistedCollapsed());

  /** Alterna en cada navegación para reiniciar la animación de entrada. */
  readonly routeAnimToggle = signal(false);

  constructor() {
    this.router.events
      .pipe(
        filter(event => event instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe(() => this.routeAnimToggle.update(value => !value));
  }

  onSidebarToggle(): void {
    this.setCollapsed(!this.sidebarCollapsed());
  }

  setCollapsed(collapsed: boolean): void {
    this.sidebarCollapsed.set(collapsed);
    persistCollapsed(collapsed);
  }
}

/** Reads the persisted collapsed state; storage failures fall back to expanded. */
function readPersistedCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1';
  } catch {
    return false;
  }
}

/** Persists the collapsed state; storage failures are silently ignored. */
function persistCollapsed(collapsed: boolean): void {
  try {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? '1' : '0');
  } catch {
    // Storage no disponible (modo privado/quota): el estado queda en memoria.
  }
}
