import {
  Component,
  ChangeDetectionStrategy,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterModule } from '@angular/router';
import { filter, map } from 'rxjs';
import { I18nService } from '@shared/i18n';
import { SolDrawerComponent, SolIconComponent } from '@shared/ui';
import { filterVisibleItems } from '@entities/menu';
import { SidebarItem } from '../model/sidebar.model';
import { getNavIconName } from './sidebar-icons';

/** Máximo de items visibles en la barra (incluyendo "Más" si hay overflow). */
const MAX_BAR_ITEMS = 5;

/** `rootTriggerId` sentinel del sheet abierto desde el botón "Más" (no colisiona con un id real de
 *  ítem — esos son los identificadores del menú que entrega el backend). */
const OVERFLOW_ROOT_ID = '__overflow__';

/** Una vista apilada del sheet: su título, la lista que muestra y cómo se renderiza esa lista. */
interface SheetView {
  /** Id del disparador raíz del sheet completo (el ítem tocado en la barra, o `OVERFLOW_ROOT_ID`
   *  para "Más") — igual en todas las vistas de una misma pila, sirve para el `aria-expanded` del
   *  botón que la abrió. */
  readonly rootTriggerId: string;
  readonly title: string;
  readonly items: SidebarItem[];
  /** true (ítem de barra): lista plana agrupada — un hijo con hijos se muestra como
   *  encabezado + sus propios hijos debajo, sin acordeón. false ("Más"): lista de un solo
   *  nivel — un ítem con hijos es un disparador de drill (empuja una nueva `SheetView`). */
  readonly flatten: boolean;
}

/** Una fila renderizable dentro del sheet, ya resuelta a partir de una `SheetView`. */
interface SheetRow {
  readonly kind: 'header' | 'link' | 'drill';
  readonly item: SidebarItem;
  readonly depth: number;
}

/** Aplana `items` para el modo `flatten`: un hijo con hijos es un encabezado de sección,
 *  seguido de sus propios hijos indentados un nivel más — recursivo, sin límite de profundidad. */
function flattenSheetRows(items: SidebarItem[], depth: number): SheetRow[] {
  const rows: SheetRow[] = [];
  for (const item of items) {
    if (item.children?.length) {
      rows.push({ kind: 'header', item, depth });
      rows.push(...flattenSheetRows(item.children, depth + 1));
    } else {
      rows.push({ kind: 'link', item, depth });
    }
  }
  return rows;
}

/** Resuelve las filas de una `SheetView`: aplanadas o de un nivel con drill. */
function buildSheetRows(view: SheetView): SheetRow[] {
  if (view.flatten) return flattenSheetRows(view.items, 0);
  return view.items.map((item) => ({
    kind: item.children?.length ? ('drill' as const) : ('link' as const),
    item,
    depth: 0,
  }));
}

/**
 * Navegación inferior fija para viewports móviles (v3 — sheet multinivel).
 *
 * Bajo el breakpoint canónico reemplaza al sidebar: muestra hasta 5 items del menú dinámico; si hay
 * más, los 4 primeros + un botón "Más". La visibilidad la gobierna CSS (display: none en desktop) —
 * estructura idéntica para todos los tenants; los tokens del sidebar (--sol-sidebar-*) solo la
 * estilizan.
 *
 * Un ítem SIN hijos navega directo (`routerLink`), igual que siempre. Un ítem CON hijos — ya sea de
 * la barra o dentro de "Más" — ya no es un tap muerto: abre un `sol-drawer[variant=sheet]` (bottom
 * sheet en móvil) que lista sus opciones. El de un ítem de barra las lista aplanadas con
 * subtítulos de sección para nietos; el de "Más" lista los módulos de overflow y permite
 * "entrar" a uno con hijos (botón volver ← incluido) — un solo `sol-drawer` reutilizado para ambos
 * patrones, con una pila (`sheetStack`) en vez de dos disparadores independientes.
 */
@Component({
  selector: 'sol-bottom-nav',
  standalone: true,
  imports: [RouterModule, SolIconComponent, SolDrawerComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <nav class="sol-bottom-nav" aria-label="Navegación principal">
      @for (item of barItems(); track item.id) {
        @if (item.children?.length) {
          <button
            type="button"
            class="sol-bottom-nav__item"
            [class.sol-bottom-nav__item--active]="isRouteActive(item)"
            [attr.aria-expanded]="isSheetOpenFor(item.id)"
            (click)="openModuleSheet(item)"
          >
            <sol-icon class="sol-bottom-nav__icon" [name]="getIconName(item.icon)" />
            <span class="sol-bottom-nav__label">{{ item.label }}</span>
          </button>
        } @else {
          <a
            class="sol-bottom-nav__item"
            [routerLink]="item.route"
            [queryParams]="item.queryParams"
            routerLinkActive="sol-bottom-nav__item--active"
            (click)="closeSheet()"
          >
            <sol-icon class="sol-bottom-nav__icon" [name]="getIconName(item.icon)" />
            <span class="sol-bottom-nav__label">{{ item.label }}</span>
          </a>
        }
      }

      @if (overflowItems().length) {
        <button
          type="button"
          class="sol-bottom-nav__item sol-bottom-nav__item--more"
          [class.sol-bottom-nav__item--active]="isSheetOpenFor(OVERFLOW_ROOT_ID) || isOverflowActive()"
          [attr.aria-expanded]="isSheetOpenFor(OVERFLOW_ROOT_ID)"
          [attr.aria-label]="moreLabel()"
          (click)="openOverflowSheet()"
          data-testid="bottom-nav-more"
        >
          <sol-icon class="sol-bottom-nav__icon" name="ellipsis-horizontal" />
          <span class="sol-bottom-nav__label">{{ moreLabel() }}</span>
        </button>
      }
    </nav>

    <sol-drawer
      [open]="sheetOpen()"
      [title]="currentSheetView()?.title ?? ''"
      variant="sheet"
      (closed)="closeSheet()"
    >
      @if (canGoBack()) {
        <button
          type="button"
          class="sol-bottom-nav__sheet-back"
          data-testid="bottom-nav-sheet-back"
          (click)="goBack()"
        >
          <sol-icon name="arrow-left" size="sm" />
          <span>{{ backLabel() }}</span>
        </button>
      }

      @if (currentSheetView(); as view) {
        @for (row of sheetRowsFor(view); track row.item.id) {
          @switch (row.kind) {
            @case ('header') {
              <div class="sol-bottom-nav__sheet-section" [style.--sol-sidebar-depth]="row.depth">
                {{ row.item.label }}
              </div>
            }
            @case ('drill') {
              <button
                type="button"
                class="sol-bottom-nav__sheet-item"
                [class.sol-bottom-nav__sheet-item--active]="isRouteActive(row.item)"
                [style.--sol-sidebar-depth]="row.depth"
                (click)="drillInto(row.item)"
              >
                <sol-icon size="md" [name]="getIconName(row.item.icon)" />
                <span class="sol-bottom-nav__sheet-label">{{ row.item.label }}</span>
                <sol-icon class="sol-bottom-nav__sheet-chevron" name="chevron-right" size="sm" />
              </button>
            }
            @default {
              <a
                class="sol-bottom-nav__sheet-item"
                [routerLink]="row.item.route"
                [queryParams]="row.item.queryParams"
                routerLinkActive="sol-bottom-nav__sheet-item--active"
                [style.--sol-sidebar-depth]="row.depth"
                (click)="closeSheet()"
              >
                <sol-icon size="md" [name]="getIconName(row.item.icon)" />
                <span class="sol-bottom-nav__sheet-label">{{ row.item.label }}</span>
              </a>
            }
          }
        }
      }
    </sol-drawer>
  `,
  styles: `
    /* Oculta en desktop: la bottom-nav es exclusiva del viewport móvil.
       Estructura base — un tema JSON no puede alterarla. */
    :host {
      display: none;
    }

    @media (max-width: 767px) {
      :host {
        display: block;
      }
    }

    .sol-bottom-nav {
      position: fixed;
      left: 0;
      right: 0;
      bottom: 0;
      /* Alto estructural + safe-area de dispositivos con notch. El número vive UNA vez, en
         --sol-bottom-nav-h de sol-layout-shell (hereda), porque el contenedor del
         contenido reserva ese mismo alto como padding: dos copias se desincronizan. */
      height: calc(var(--sol-bottom-nav-h, 58px) + env(safe-area-inset-bottom, 0px));
      padding-bottom: env(safe-area-inset-bottom, 0px);
      display: flex;
      align-items: stretch;
      box-sizing: border-box;
      /* Capa base OPACA (fondo de página) + tinte del sidebar encima: temas
         con sidebar-bg transparente (se funde con la página en desktop) no
         pueden dejar ver el contenido a través de una barra FIJA. */
      background-color: var(--sol-bg-page, #ffffff);
      background-image: linear-gradient(
        var(--sol-sidebar-bg, var(--sol-bg-surface, #ffffff)),
        var(--sol-sidebar-bg, var(--sol-bg-surface, #ffffff))
      );
      border-top: var(--sol-border-width-default, 1px) solid var(--sol-border-color-default, #e5e7eb);
      z-index: calc(var(--sol-z-dropdown, 100) + 1);
    }

    .sol-bottom-nav__item {
      flex: 1;
      min-width: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 2px;
      padding: 6px 2px 4px;
      border: none;
      background: transparent;
      color: var(--sol-sidebar-text, var(--sol-color-text-secondary, #6b7280));
      text-decoration: none;
      font-family: inherit;
      cursor: pointer;
      transition: color var(--sol-dur-fast, 120ms) var(--sol-ease, ease);
    }

    .sol-bottom-nav__item--active {
      color: var(--sol-sidebar-active-text, var(--sol-color-primary, #2563EB));
    }

    /* Píldora de fondo del item activo, con los tokens del sidebar. */
    .sol-bottom-nav__item--active .sol-bottom-nav__icon {
      background: var(--sol-sidebar-active-bg, color-mix(in srgb, var(--sol-color-primary, #2563EB) 10%, transparent));
    }

    .sol-bottom-nav__icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      /* Como flex item de una columna estrecha, sin esto el ícono se comprime
         hasta desaparecer y solo queda visible la etiqueta. */
      flex-shrink: 0;
      width: 40px;
      height: 24px;
      border-radius: var(--sol-sidebar-item-radius, var(--sol-border-radius-md, 8px));
      transition: background-color var(--sol-dur-fast, 120ms) var(--sol-ease, ease);
    }

    .sol-bottom-nav__label {
      max-width: 100%;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 0.625rem;
      font-weight: 500;
      line-height: 1.2;
    }

    /* ── Sheet de opciones (sol-drawer variant="sheet") ────────────────── */

    .sol-bottom-nav__sheet-back {
      display: flex;
      align-items: center;
      gap: var(--sol-space-sm, 0.5rem);
      width: 100%;
      min-height: var(--sol-size-control-touch, 44px);
      box-sizing: border-box;
      padding: var(--sol-space-sm, 0.5rem) var(--sol-space-md, 0.75rem);
      margin-bottom: var(--sol-space-xs, 0.25rem);
      border: none;
      border-radius: var(--sol-border-radius-md, 8px);
      background: transparent;
      color: var(--sol-color-text-secondary, #6b7280);
      font: inherit;
      font-weight: 500;
      text-align: left;
      cursor: pointer;
      transition: background-color 0.15s ease, color 0.15s ease;
    }

    .sol-bottom-nav__sheet-back:hover {
      background: color-mix(in srgb, var(--sol-color-primary, #2563eb) 8%, transparent);
      color: var(--sol-color-primary, #2563eb);
    }

    .sol-bottom-nav__sheet-section {
      padding: var(--sol-space-sm, 0.5rem) var(--sol-space-md, 0.75rem) var(--sol-space-xs, 0.25rem);
      padding-left: calc(var(--sol-space-md, 0.75rem) + var(--sol-sidebar-depth, 0) * 1.25rem);
      color: var(--sol-color-text-muted, #9ca3af);
      font-size: var(--sol-font-size-sm, 0.75rem);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    /* Fila táctil ≥44px (ley de Fitts en móvil) — comparte estilo entre el <a> de navegación y el
       <button> de drill; solo cambia qué elemento HTML es cada uno. */
    .sol-bottom-nav__sheet-item {
      display: flex;
      align-items: center;
      gap: var(--sol-space-sm, 0.75rem);
      width: 100%;
      min-height: var(--sol-size-control-touch, 44px);
      box-sizing: border-box;
      padding: var(--sol-space-sm, 0.5rem) var(--sol-space-md, 0.75rem);
      padding-left: calc(var(--sol-space-md, 0.75rem) + var(--sol-sidebar-depth, 0) * 1.25rem);
      border: none;
      border-radius: var(--sol-border-radius-md, 8px);
      background: transparent;
      color: var(--sol-color-text-primary, #111827);
      text-decoration: none;
      font: inherit;
      font-size: var(--sol-font-size-sm, 0.875rem);
      text-align: left;
      cursor: pointer;
      transition: background-color 0.15s ease, color 0.15s ease;
    }

    .sol-bottom-nav__sheet-item:hover {
      background: color-mix(in srgb, var(--sol-color-primary, #2563eb) 8%, transparent);
    }

    .sol-bottom-nav__sheet-item--active {
      background: var(--sol-sidebar-active-bg, color-mix(in srgb, var(--sol-color-primary, #2563EB) 10%, transparent));
      color: var(--sol-sidebar-active-text, var(--sol-color-primary, #2563EB));
      font-weight: 600;
    }

    .sol-bottom-nav__sheet-label {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .sol-bottom-nav__sheet-chevron {
      flex-shrink: 0;
      margin-left: auto;
      color: var(--sol-color-text-muted, #9ca3af);
    }
  `,
})
export class SolBottomNavComponent {
  private readonly i18n = inject(I18nService);
  private readonly router = inject(Router);

  /** Items del menú dinámico (los mismos del sidebar). */
  readonly items = input<SidebarItem[]>([]);

  /** Etiqueta i18n del botón de overflow. */
  protected readonly moreLabel = this.i18n.t('shared.nav.more');

  /** Etiqueta i18n del botón "volver" al hacer drill dentro del sheet de "Más". */
  protected readonly backLabel = this.i18n.t('shared.nav.back');

  /** Sentinel expuesto al template — no puede referenciar la const de módulo directo. */
  protected readonly OVERFLOW_ROOT_ID = OVERFLOW_ROOT_ID;

  /** URL activa, para resaltar un disparador de sheet (botón, no routerLink) por sus descendientes. */
  private readonly currentUrl = toSignal(
    this.router.events.pipe(
      filter((event): event is NavigationEnd => event instanceof NavigationEnd),
      map((event) => event.urlAfterRedirects),
    ),
    { initialValue: this.router.url },
  );

  /**
   * Pila de vistas del sheet abierto — `[]` significa cerrado. El tope (última) es la que se
   * muestra; "volver" hace `pop`, cerrar (backdrop/Escape/navegar) vacía toda la pila.
   */
  private readonly sheetStack = signal<SheetView[]>([]);

  protected readonly sheetOpen = computed(() => this.sheetStack().length > 0);
  protected readonly canGoBack = computed(() => this.sheetStack().length > 1);
  protected readonly currentSheetView = computed<SheetView | null>(() => {
    const stack = this.sheetStack();
    return stack.length ? stack[stack.length - 1] : null;
  });

  /**
   * Mismo filtro que aplican `sol-sidebar` y `sol-layout-shell` (`filterVisibleItems`, de
   * `entities/menu`): los tres ven exactamente las mismas opciones, así que «el menú tiene
   * opciones» no puede significar una cosa acá y otra en quien decide montar la barra.
   */
  private readonly visibleItems = computed(() => filterVisibleItems(this.items()));

  /**
   * Items de la barra: todos si caben (≤5); si hay overflow, los 4 primeros
   * (el quinto puesto lo ocupa el botón "Más").
   */
  readonly barItems = computed(() => {
    const items = this.visibleItems();
    return items.length <= MAX_BAR_ITEMS ? items : items.slice(0, MAX_BAR_ITEMS - 1);
  });

  /** Módulos de overflow (5.° en adelante) — sin aplanar: el sheet de "Más" hace drill, no lista
   *  los hijos de una vez (a diferencia del sheet de un ítem de barra). */
  readonly overflowItems = computed<SidebarItem[]>(() => {
    const items = this.visibleItems();
    if (items.length <= MAX_BAR_ITEMS) return [];
    return items.slice(MAX_BAR_ITEMS - 1);
  });

  /** Abre el sheet de opciones de un módulo de la barra (lista aplanada, sin drill). */
  protected openModuleSheet(item: SidebarItem): void {
    if (!item.children?.length) return;
    this.sheetStack.set([{ rootTriggerId: item.id, title: item.label, items: item.children, flatten: true }]);
  }

  /** Abre el sheet de overflow ("Más") en su raíz. */
  protected openOverflowSheet(): void {
    this.sheetStack.set([
      { rootTriggerId: OVERFLOW_ROOT_ID, title: this.moreLabel(), items: this.overflowItems(), flatten: false },
    ]);
  }

  /** Dentro del sheet de overflow, entra un nivel a los hijos de `item`. */
  protected drillInto(item: SidebarItem): void {
    if (!item.children?.length) return;
    this.sheetStack.update((stack) => {
      const root = stack[0];
      if (!root) return stack;
      return [...stack, { rootTriggerId: root.rootTriggerId, title: item.label, items: item.children!, flatten: false }];
    });
  }

  /** Retrocede un nivel dentro del sheet ("Más" con drill). */
  protected goBack(): void {
    this.sheetStack.update((stack) => stack.slice(0, -1));
  }

  /** Cierra el sheet por completo — backdrop, Escape, botón nativo de sol-drawer, o al navegar. */
  protected closeSheet(): void {
    this.sheetStack.set([]);
  }

  /** true si el sheet actualmente abierto es el que disparó `rootTriggerId` (aria-expanded). */
  protected isSheetOpenFor(rootTriggerId: string): boolean {
    return this.sheetStack()[0]?.rootTriggerId === rootTriggerId;
  }

  /** true si alguno de los módulos de overflow (o sus descendientes) es la ruta activa. */
  protected isOverflowActive(): boolean {
    return this.overflowItems().some((item) => this.isRouteActive(item));
  }

  /**
   * true si la URL actual coincide con la ruta de `item` o la de alguno de sus descendientes
   * (recursivo). Un ítem con hijos se renderiza como `<button>` (barra o drill), nunca como
   * `[routerLink]`, así que no puede depender de `routerLinkActive` para resaltarse — esta es la
   * versión manual de esa misma señal, ignorando queryParams igual que el resto del shell.
   */
  protected isRouteActive(item: SidebarItem): boolean {
    const url = this.currentUrl();
    const matches = (candidate: SidebarItem): boolean => {
      if (candidate.route && (url === candidate.route || url.startsWith(`${candidate.route}/`) || url.startsWith(`${candidate.route}?`))) {
        return true;
      }
      return (candidate.children ?? []).some(matches);
    };
    return matches(item);
  }

  /**
   * Resuelve el nombre de ícono del registry para el item del menú, vía el
   * traductor compartido de navegación (sidebar-icons.ts).
   */
  protected readonly getIconName = getNavIconName;

  /** Resuelve las filas de una `SheetView` — función pura, expuesta como método para el template. */
  protected sheetRowsFor(view: SheetView): SheetRow[] {
    return buildSheetRows(view);
  }
}
