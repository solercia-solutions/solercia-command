import {
  Component,
  ChangeDetectionStrategy,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { filterVisibleItems } from '@entities/menu';
import { observeMobileViewport } from '@shared/lib/utils/breakpoint.util';
import { SolBreadcrumbComponent, type BreadcrumbItem } from '@widgets/breadcrumb';
import { SolHeaderComponent } from '@widgets/header';
import {
  SolSidebarComponent,
  SolBottomNavComponent,
  SidebarItem,
  SidebarState,
} from '@widgets/sidebar';
import { ThemeToggleComponent } from '@features/theme-toggle';

/**
 * Preferencia local del sidebar colapsado ('1') o expandido ('0'). Conveniencia del navegador, no
 * estado de sesión. Se conserva la llave que ya usaba la aplicación para no perder la elección de
 * quien ya la tiene guardada.
 */
const SIDEBAR_COLLAPSED_KEY = 'sp-sidebar-collapsed';

/**
 * Layout autenticado: header fijo, sidebar colapsable (menú móvil inferior bajo el breakpoint),
 * migas de pan y el contenido de la ruta. El botón de tema va antes de las acciones que proyecta
 * la página (`[header-actions]`).
 */
@Component({
  selector: 'sol-layout-shell',
  standalone: true,
  imports: [
    RouterOutlet,
    SolHeaderComponent,
    SolSidebarComponent,
    SolBottomNavComponent,
    SolBreadcrumbComponent,
    ThemeToggleComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <sol-header
      [showSidebarToggle]="showSidebarToggle()"
      (sidebarToggle)="onSidebarToggle()"
    >
      <sol-theme-toggle />
      <ng-content select="[header-actions]" />
    </sol-header>

    @if (showSidebar()) {
      <sol-sidebar
        [items]="sidebarItems()"
        [collapsed]="sidebarCollapsed()"
        [state]="sidebarState()"
        [errorMessage]="sidebarErrorMessage()"
        [emptyMessage]="sidebarEmptyMessage()"
        [autoCloseOnNavigate]="sidebarAutoClose()"
        (collapsedChange)="setSidebarCollapsed($event)"
        (retry)="sidebarRetry.emit()"
      />
      <!-- Navegación móvil (estructura base): bajo el breakpoint el sidebar
           se oculta y esta bottom-nav fija toma su lugar. CSS decide la
           visibilidad por breakpoint — cero lógica condicional por tenant —,
           pero una barra SIN opciones no se monta: sería una franja fija y
           opaca tapando el contenido sin ofrecer nada a cambio. -->
      @if (hasNavItems()) {
        <sol-bottom-nav [items]="sidebarItems()" />
      }
    }

    <main
      class="sol-layout-main"
      [class.sol-layout-main--with-sidebar]="showSidebar()"
      [class.sol-layout-main--collapsed]="showSidebar() && sidebarCollapsed()"
      [class.sol-layout-main--with-bottom-nav]="showBottomNav()"
    >
      <!-- Migas de pan: solo cuando la página entrega un camino. Van fuera del wrapper animado
           para que no vuelvan a entrar en cada navegación. -->
      @if (breadcrumbItems().length) {
        <div class="sol-layout-breadcrumb">
          <sol-breadcrumb [items]="breadcrumbItems()" />
        </div>
      }

      <!-- Transición de ruta (motion v2): el wrapper alterna keyframes base ↔ B
           en cada NavigationEnd para re-disparar la entrada sin @angular/animations. -->
      <div class="sol-route-anim" [class.sol-route-anim--b]="routeAnimToggle()">
        <router-outlet />
      </div>
    </main>
  `,
  styles: `
    :host {
      /* Columna flex: el contenido crece hasta ocupar el alto visible (ver flex:1 en
         .sol-layout-main). header, sidebar y bottom-nav son position:fixed, así que quedan fuera
         de este flujo. */
      display: flex;
      flex-direction: column;
      /* 100dvh (viewport dinámico), no 100vh: 100vh cuenta el área bajo la barra del
         navegador y excede el alto visible por unos píxeles, forzando un scrollbar
         vertical fantasma aunque el contenido quepa. dvh se ajusta al área real. */
      min-height: 100dvh;
      /* Alto estructural de la bottom-nav móvil (sin la safe-area, que se suma aparte).
         Declarado acá y no dentro de sol-bottom-nav porque son DOS los que dependen del
         mismo número: la barra, que lo usa como alto, y .sol-layout-main, que lo reserva
         como padding para que nada quede debajo. */
      --sol-bottom-nav-h: 58px;
    }

    .sol-layout-main {
      /* Alto del header + respiro (space-lg en desktop, space-md en móvil — ver el media query
         de abajo): sin esto el contenido arranca pegado al header, sin holgura. */
      padding-top: calc(var(--sol-size-header-height, 56px) + var(--sol-space-lg, 24px));
      flex: 1;
      transition: margin-left var(--sol-dur-base, 240ms) var(--sol-ease, ease);
      padding-left: 24px;
      padding-right: 24px;
      padding-bottom: 24px;
    }

    /* Franja de las migas de pan, entre el respiro del header y el contenido de la ruta. */
    .sol-layout-breadcrumb {
      margin-bottom: var(--sol-space-sm, 8px);
    }

    .sol-layout-main--with-sidebar {
      margin-left: var(--sol-size-sidebar-width, 260px);
    }

    .sol-layout-main--collapsed {
      margin-left: 64px;
    }

    /* Estructura base móvil: sin sidebar no hay margen izquierdo y el
       contenido reserva espacio para la bottom-nav fija SOLO cuando esa barra
       existe (--with-bottom-nav); sin opciones no se monta y el contenido usa
       todo el alto. */
    @media (max-width: 767px) {
      .sol-layout-main--with-sidebar,
      .sol-layout-main--collapsed {
        margin-left: 0;
      }

      .sol-layout-main {
        padding-top: calc(var(--sol-size-header-height, 56px) + var(--sol-space-md, 16px));
        padding-left: 16px;
        padding-right: 16px;
        padding-bottom: var(--sol-space-md, 16px);
        /* Robustez de fuente (CI): en móvil el contenido de la página nunca
           debe generar scroll horizontal del documento. Los desbordes internos
           legítimos (tablas en modo scroll, etc.) se resuelven dentro de su
           propio contenedor con overflow auto; este clip solo evita que un
           ancho de fuente más generoso (ubuntu vs macOS) empuje el documento
           más allá de 390px. overflow-x clip no crea contexto de scroll ni
           recorta los popovers position fixed (calendario, dropdowns), que
           tienen a la ventana como bloque contenedor y escapan al main. */
        overflow-x: clip;
        max-width: 100%;
      }

      /* La barra es position: fixed, así que lo último del contenido quedaría debajo si no se
         reserva su alto + la safe-area del dispositivo con notch. La clase solo la pone
         el template cuando la barra se monta de verdad. */
      .sol-layout-main--with-bottom-nav {
        padding-bottom: calc(
          var(--sol-bottom-nav-h, 58px) + env(safe-area-inset-bottom, 0px) +
            var(--sol-space-md, 16px)
        );
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

  /** Whether to show the sidebar. */
  readonly showSidebar = input<boolean>(true);

  /** Situación del menú, que el sidebar traduce a sus cinco estados. Pasa tal cual. */
  readonly sidebarState = input<SidebarState>('ready');

  /** Mensaje del estado de error del menú, si quien alimenta el shell tiene uno propio. */
  readonly sidebarErrorMessage = input<string | null>(null);

  /** Mensaje del estado vacío del menú; la página sabe por qué está vacío, el layout no. */
  readonly sidebarEmptyMessage = input<string | null>(null);

  /** Cierre automático del sidebar al elegir una opción (apagado por defecto). */
  readonly sidebarAutoClose = input<boolean>(false);

  /**
   * Tramos de las migas de pan, ya resueltos por la página desde el árbol del menú y la URL
   * actual. Vacío = la franja no se pinta (una vista sin ítem propio en el menú).
   */
  readonly breadcrumbItems = input<BreadcrumbItem[]>([]);

  /** Reenvía el «Reintentar» del sidebar a la página, que es la que sabe cómo recargar. */
  readonly sidebarRetry = output<void>();

  /**
   * ¿El menú tiene al menos una opción visible? Aplica el MISMO filtro que el sidebar y la
   * bottom-nav (`filterVisibleItems`), así los tres coinciden siempre.
   */
  readonly hasNavItems = computed(() => filterVisibleItems(this.sidebarItems()).length > 0);

  /** La bottom-nav se monta solo con menú Y con opciones; el breakpoint lo sigue decidiendo CSS. */
  readonly showBottomNav = computed(() => this.showSidebar() && this.hasNavItems());

  /** Estado colapsado del sidebar; la elección del usuario se recuerda por navegador. */
  readonly sidebarCollapsed = signal(readSidebarCollapsed());

  /** Viewport móvil reactivo (breakpoint canónico; retira su listener sola al destruirse). */
  private readonly isMobileViewport = observeMobileViewport();

  /** El botón hamburguesa solo tiene efecto con el sidebar visible: en móvil `sol-sidebar` cae a
   *  `display:none` (la bottom-nav toma su lugar) y el botón quedaría muerto. */
  readonly showSidebarToggle = computed(() => this.showSidebar() && !this.isMobileViewport());

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
    this.setSidebarCollapsed(!this.sidebarCollapsed());
  }

  setSidebarCollapsed(collapsed: boolean): void {
    this.sidebarCollapsed.set(collapsed);
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? '1' : '0');
    } catch {
      // Sin almacenamiento local (modo privado, política del navegador): la elección vive hasta recargar.
    }
  }
}

/** Preferencia guardada del sidebar; sin preferencia (o sin almacenamiento) arranca expandido. */
function readSidebarCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1';
  } catch {
    return false;
  }
}
