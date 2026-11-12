import {
  Component,
  ChangeDetectionStrategy,
  inject,
  input,
  output,
  computed,
  signal,
} from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { RouterModule } from '@angular/router';
import { itemKey, descendantKeys, filterVisibleItems } from '@entities/menu';
import { I18nService } from '@shared/i18n';
import { SolIconComponent } from '@shared/ui';
import { SidebarItem } from '../model/sidebar.model';
import { getNavIconName } from './sidebar-icons';

/**
 * Situación en la que está el menú, decidida por quien lo alimenta (la página del shell a partir
 * de `MenuService.status`). El quinto estado —"sin resultados"— no se pasa por aquí: se deduce
 * dentro del componente, porque solo él sabe cuántos ítems sobrevivieron a su propio filtro de
 * visibilidad. Ver `viewState` más abajo.
 */
export type SidebarState = 'loading' | 'ready' | 'empty' | 'error';

/** Los cinco estados que el menú puede mostrar, ya resueltos para el template. */
type SidebarViewState = 'loading' | 'empty' | 'no-results' | 'error' | 'success';

/** Número de filas del esqueleto de carga: suficientes para insinuar una lista, no una pantalla llena. */
const SKELETON_ROWS = [0, 1, 2, 3, 4];

@Component({
  selector: 'sol-sidebar',
  standalone: true,
  imports: [RouterModule, SolIconComponent, NgTemplateOutlet],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <aside
      class="sol-sidebar"
      [class.sol-sidebar--collapsed]="collapsed()"
    >
      <nav
        class="sol-sidebar__nav"
        [attr.aria-label]="navLabel()"
        [attr.aria-busy]="viewState() === 'loading'"
      >
        @switch (viewState()) {
          @case ('loading') {
            <!-- Esqueleto: ocupa el sitio de la lista para que el menú no salte al llegar. El
                 texto solo lo anuncian los lectores de pantalla; visualmente basta el esqueleto. -->
            <p class="sol-sidebar__sr-only" role="status">{{ loadingLabel() }}</p>
            @for (fila of skeletonRows; track fila) {
              <span class="sol-sidebar__skeleton" aria-hidden="true"></span>
            }
          }
          @case ('empty') {
            @if (!collapsed()) {
              <p class="sol-sidebar__state">{{ emptyMessage() ?? defaultEmptyMessage() }}</p>
            }
          }
          @case ('no-results') {
            @if (!collapsed()) {
              <p class="sol-sidebar__state">{{ noResultsLabel() }}</p>
            }
          }
          @case ('error') {
            @if (!collapsed()) {
              <div class="sol-sidebar__state" role="alert">
                <p class="sol-sidebar__state-text">{{ errorMessage() ?? defaultErrorMessage() }}</p>
                <button type="button" class="sol-sidebar__retry" (click)="retry.emit()">
                  {{ retryLabel() }}
                </button>
              </div>
            }
          }
          @default {
            <ng-container
              *ngTemplateOutlet="levelTpl; context: { $implicit: visibleItems(), depth: 0 }"
            />
          }
        }
      </nav>

      <!--
        Recursive level template (self-referencing via ngTemplateOutlet): renders one depth of the
        menu tree and, for every group item, outlets itself again one level deeper. This is what
        lets the sidebar support N levels instead of the previous hardcoded 2 (parent + child).
        "items" (the level's own list) is what toggle() needs to run the accordion among
        siblings — the template is the only place that knows who the siblings are.
      -->
      <ng-template #levelTpl let-items let-depth="depth">
        @for (item of items; track item.id ?? item.label) {
          @if (item.children?.length) {
            <!--
              Group: a pure expand/collapse toggle, never a link — no routerLink/routerLinkActive,
              so it can never receive the "active button" style (background + box-shadow) that a
              real navigation target gets. Only the shared hover from .sol-sidebar__item applies.
            -->
            <button
              type="button"
              class="sol-sidebar__item sol-sidebar__item--group"
              [attr.aria-expanded]="isExpanded(item)"
              [attr.aria-label]="collapsed() ? item.label : null"
              [title]="collapsed() ? item.label : ''"
              (click)="toggle(item, items)"
            >
              <sol-icon class="sol-sidebar__icon" [name]="getIconName(item.icon)" />

              @if (!collapsed()) {
                <span class="sol-sidebar__label">{{ item.label }}</span>
                <sol-icon
                  class="sol-sidebar__chevron"
                  name="chevron-right"
                  size="sm"
                  [class.sol-sidebar__chevron--expanded]="isExpanded(item)"
                />
              }
            </button>

            @if (!collapsed()) {
              <div
                class="sol-sidebar__children-wrap"
                [class.sol-sidebar__children-wrap--expanded]="isExpanded(item)"
              >
                <div class="sol-sidebar__children-inner">
                  <ng-container
                    *ngTemplateOutlet="levelTpl; context: { $implicit: item.children, depth: depth + 1 }"
                  />
                </div>
              </div>
            }
          } @else {
            <a
              class="sol-sidebar__item"
              [routerLink]="item.route"
              [queryParams]="item.queryParams"
              routerLinkActive="sol-sidebar__item--active"
              [attr.aria-label]="collapsed() ? item.label : null"
              [title]="collapsed() ? item.label : ''"
              (click)="onLeafClick(item)"
            >
              <sol-icon class="sol-sidebar__icon" [name]="getIconName(item.icon)" />

              @if (!collapsed()) {
                <span class="sol-sidebar__label">{{ item.label }}</span>

                @if (item.badge !== undefined && item.badge !== null) {
                  <span class="sol-sidebar__badge">{{ item.badge }}</span>
                }
              }
            </a>
          }
        }
      </ng-template>

      <button
        type="button"
        class="sol-sidebar__toggle"
        (click)="onToggleCollapse()"
        [attr.aria-label]="collapsed() ? expandLabel() : collapseLabel()"
      >
        <sol-icon
          name="chevron-left"
          size="sm"
          [class.sol-sidebar__toggle-icon--flipped]="collapsed()"
        />
      </button>
    </aside>
  `,
  styles: `
    .sol-sidebar {
      position: fixed;
      top: var(--sol-size-header-height, 56px);
      left: 0;
      bottom: 0;
      width: var(--sol-size-sidebar-width, 260px);
      display: flex;
      flex-direction: column;
      /* v2: el sidebar puede ser oscuro aunque el modo sea light (Vértice/Tinta);
         sus textos usan sidebar-text, nunca text-primary. */
      background: var(--sol-sidebar-bg, var(--sol-bg-surface, #ffffff));
      border-right: var(--sol-border-width-default, 1px) solid var(--sol-border-color-default, #e5e7eb);
      transition: width 0.25s ease;
      z-index: var(--sol-z-dropdown, 100);
      overflow: hidden;
    }

    .sol-sidebar--collapsed {
      width: 64px;
    }

    /* Estructura base móvil (idéntica para todos los tenants): bajo el
       breakpoint canónico el sidebar desaparece y la navegación pasa a la
       bottom-nav fija (sol-bottom-nav). Un tema JSON no puede alterarlo. */
    @media (max-width: 767px) {
      .sol-sidebar {
        display: none;
      }
    }

    .sol-sidebar__nav {
      flex: 1;
      overflow-y: auto;
      padding: var(--sol-space-sm, 0.5rem);
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    /* ── Estados del menú (cargando, vacío, sin resultados, error) ─────── */

    /* Visible solo para lectores de pantalla: el esqueleto ya comunica la espera a la vista. */
    .sol-sidebar__sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      margin: -1px;
      padding: 0;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }

    .sol-sidebar__skeleton {
      display: block;
      height: var(--sol-size-control-sm, 32px);
      margin: 0 var(--sol-space-sm, 0.5rem);
      border-radius: var(--sol-sidebar-item-radius, var(--sol-border-radius-md, 8px));
      background: color-mix(in srgb, var(--sol-sidebar-text, #6b7280) 12%, transparent);
      animation: sol-sidebar-pulse 1.4s ease-in-out infinite;
    }

    @keyframes sol-sidebar-pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.45; }
    }

    @media (prefers-reduced-motion: reduce) {
      .sol-sidebar__skeleton {
        animation: none;
      }
    }

    .sol-sidebar__state {
      margin: var(--sol-space-sm, 0.5rem);
      padding: var(--sol-space-md, 0.75rem);
      border-radius: var(--sol-sidebar-item-radius, var(--sol-border-radius-md, 8px));
      background: color-mix(in srgb, var(--sol-sidebar-text, #6b7280) 6%, transparent);
      color: var(--sol-sidebar-text, var(--sol-color-text-secondary, #6b7280));
      font-size: var(--sol-font-size-sm, 0.875rem);
      line-height: 1.4;
    }

    .sol-sidebar__state-text {
      margin: 0 0 var(--sol-space-sm, 0.5rem);
    }

    .sol-sidebar__retry {
      min-height: var(--sol-size-control-sm, 32px);
      padding: 0 var(--sol-space-md, 0.75rem);
      border: var(--sol-border-width-default, 1px) solid color-mix(in srgb, var(--sol-sidebar-text, #6b7280) 30%, transparent);
      border-radius: var(--sol-sidebar-item-radius, var(--sol-border-radius-md, 8px));
      background: transparent;
      color: var(--sol-sidebar-active-text, var(--sol-color-primary, #2563EB));
      font: inherit;
      font-size: var(--sol-font-size-sm, 0.875rem);
      font-weight: 600;
      cursor: pointer;
      transition: background-color 0.15s ease;
    }

    .sol-sidebar__retry:hover {
      background: color-mix(in srgb, var(--sol-sidebar-active-text, var(--sol-color-primary, #2563EB)) 8%, transparent);
    }

    /* Bajo el breakpoint móvil el control sube al mínimo táctil (ley de Fitts). */
    @media (max-width: 767px) {
      .sol-sidebar__retry {
        min-height: var(--sol-size-control-touch, 44px);
      }
    }

    .sol-sidebar__item {
      display: flex;
      align-items: center;
      gap: var(--sol-space-sm, 0.5rem);
      /* Sangría CONSTANTE por ítem: la jerarquía la marca .sol-sidebar__children-inner (una guía
         vertical y una sangría mínima por nivel), no un padding que crece con la profundidad —
         con 1.5rem por nivel, a partir del cuarto el texto quedaba partido en sílabas. */
      padding: var(--sol-space-sm, 0.5rem) var(--sol-space-md, 0.75rem);
      border-radius: var(--sol-sidebar-item-radius, var(--sol-border-radius-md, 8px));
      color: var(--sol-sidebar-text, var(--sol-color-text-secondary, #6b7280));
      text-decoration: none;
      font-size: var(--sol-font-size-sm, 0.875rem);
      font-weight: 500;
      /* UI-1 (ciclo 2a): el texto largo del ítem del menú NO se trunca — hace wrap
         a la línea siguiente. El align-items center (heredado de arriba) mantiene el
         icono centrado contra el bloque de texto, de una o varias líneas. */
      white-space: normal;
      cursor: pointer;
      transition: background-color 0.15s ease, color 0.15s ease;
    }

    /* El hover deriva del texto activo del tema: funciona igual sobre sidebar
       claro (mezcla del primary) y oscuro (mezcla del texto claro). */
    .sol-sidebar__item:hover {
      background: color-mix(in srgb, var(--sol-sidebar-active-text, var(--sol-color-primary, #2563EB)) 8%, transparent);
      color: var(--sol-sidebar-active-text, var(--sol-color-primary, #2563EB));
    }

    /* v2: la barra de acento es un box-shadow inset del tema (el default emite
       "inset 3px 0 0 primary" = mismo look v1 sin desplazar el contenido).
       Solo llega a un <a> real (routerLinkActive) — un ítem grupo (<button>) nunca la recibe. */
    .sol-sidebar__item--active {
      background: var(--sol-sidebar-active-bg, color-mix(in srgb, var(--sol-color-primary, #2563EB) 10%, transparent));
      color: var(--sol-sidebar-active-text, var(--sol-color-primary, #2563EB));
      font-weight: 600;
      box-shadow: var(--sol-sidebar-indicator, inset 3px 0 0 var(--sol-color-primary, #2563EB));
    }

    /* Group items render as <button>, which needs its own box/typography reset — the shared
       visual styling (padding, hover, color, radius) still comes from .sol-sidebar__item above. */
    .sol-sidebar__item--group {
      width: 100%;
      border: none;
      background: none;
      font: inherit;
      text-align: left;
    }

    .sol-sidebar__icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 20px;
      height: 20px;
      flex-shrink: 0;
    }

    .sol-sidebar__icon--sm {
      width: 16px;
      height: 16px;
    }

    .sol-sidebar__label {
      flex: 1;
      min-width: 0;
      /* UI-1: wrap legible en vez de recortar con ellipsis. overflow-wrap anywhere
         parte también una palabra muy larga (una URL o un código sin espacios) antes
         de desbordar el ancho del sidebar. */
      white-space: normal;
      overflow-wrap: anywhere;
      line-height: 1.3;
    }

    .sol-sidebar__badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 20px;
      height: 20px;
      padding: 0 6px;
      border-radius: var(--sol-border-radius-full, 9999px);
      background: var(--sol-color-primary, #6366f1);
      color: #ffffff;
      font-size: 0.6875rem;
      font-weight: 600;
      line-height: 1;
    }

    /* Trailing expand/collapse indicator on a group item. Same rotate-a-chevron technique as
       .sol-sidebar__toggle-icon--flipped below, just a different resting/rotated pair. */
    .sol-sidebar__chevron {
      flex-shrink: 0;
      color: var(--sol-sidebar-text, var(--sol-color-text-secondary, #6b7280));
      transition: transform 0.2s ease;
    }

    .sol-sidebar__chevron--expanded {
      transform: rotate(90deg);
    }

    /* Expand/collapse animation via the CSS grid "0fr -> 1fr" trick: animating grid-template-rows
       is height-agnostic (no fixed max-height guess needed) and, unlike max-height, doesn't leave
       dead transition time once content is fully shown. The inner wrapper's overflow:hidden is
       what actually clips the content during the transition; min-height:0 stops it from
       overriding the grid item's own collapsed size. */
    .sol-sidebar__children-wrap {
      display: grid;
      grid-template-rows: 0fr;
      transition: grid-template-rows 0.22s ease;
    }

    .sol-sidebar__children-wrap--expanded {
      grid-template-rows: 1fr;
    }

    /* Un nivel de anidación = una sangría mínima (--sol-sidebar-indent) más una guía vertical que
       une a los hermanos con su padre. Como cada nivel anida su propio wrapper, la sangría se
       acumula sola de nivel en nivel (14px × profundidad) y cuatro niveles siguen cabiendo en el
       ancho del sidebar con el texto entero. */
    .sol-sidebar__children-inner {
      overflow: hidden;
      min-height: 0;
      display: flex;
      flex-direction: column;
      gap: 1px;
      margin-left: var(--sol-sidebar-indent, 14px);
      padding-left: 2px;
      border-left: var(--sol-border-width-default, 1px) solid color-mix(in srgb, var(--sol-sidebar-text, #6b7280) 22%, transparent);
    }

    @media (prefers-reduced-motion: reduce) {
      .sol-sidebar__children-wrap,
      .sol-sidebar__chevron {
        transition: none;
      }
    }

    .sol-sidebar__toggle {
      display: flex;
      align-items: center;
      justify-content: center;
      height: 40px;
      margin: var(--sol-space-xs, 0.25rem) var(--sol-space-sm, 0.5rem);
      border: var(--sol-border-width-default, 1px) solid color-mix(in srgb, var(--sol-sidebar-text, #6b7280) 25%, transparent);
      border-radius: var(--sol-sidebar-item-radius, var(--sol-border-radius-md, 8px));
      background: transparent;
      color: var(--sol-sidebar-text, var(--sol-color-text-secondary, #6b7280));
      cursor: pointer;
      transition: background-color 0.15s ease, color 0.15s ease;
    }

    .sol-sidebar__toggle:hover {
      background: color-mix(in srgb, var(--sol-sidebar-active-text, var(--sol-color-primary, #6366f1)) 8%, transparent);
      color: var(--sol-sidebar-active-text, var(--sol-color-primary, #6366f1));
    }

    .sol-sidebar__toggle-icon--flipped {
      transform: rotate(180deg);
    }
  `,
})
export class SolSidebarComponent {
  /** List of sidebar navigation items. */
  readonly items = input<SidebarItem[]>([]);

  /** Whether the sidebar is in collapsed (icon-only) mode. */
  readonly collapsed = input<boolean>(false);

  /**
   * Situación del menú según quien lo alimenta. Por defecto `'ready'`: un consumidor que solo
   * pasa `items` sigue comportándose igual que antes de existir este input.
   */
  readonly state = input<SidebarState>('ready');

  /** Mensaje del estado de error; si falta, se muestra el genérico. */
  readonly errorMessage = input<string | null>(null);

  /**
   * Mensaje del estado vacío. Lo decide el contenedor porque "no hay nada que mostrar" puede
   * tener más de una causa, y decir la equivocada deja al usuario buscando un problema que no
   * existe.
   */
  readonly emptyMessage = input<string | null>(null);

  /**
   * Al elegir una opción (hoja) el sidebar vuelve al riel de íconos, para devolverle el ancho al
   * contenido. Apagado por defecto: el layout lo activa cuando la vista necesita todo el ancho.
   */
  readonly autoCloseOnNavigate = input<boolean>(false);

  /** Emitted when the collapsed state changes. */
  readonly collapsedChange = output<boolean>();

  /** Emitted when a navigation item is clicked. */
  readonly navigate = output<string>();

  /** El usuario pidió volver a intentar la carga del menú desde el estado de error. */
  readonly retry = output<void>();

  private readonly i18n = inject(I18nService);

  protected readonly skeletonRows = SKELETON_ROWS;

  protected readonly navLabel = this.i18n.t('widgets.sidebar.navLabel');
  protected readonly expandLabel = this.i18n.t('widgets.sidebar.expand');
  protected readonly collapseLabel = this.i18n.t('widgets.sidebar.collapse');
  protected readonly loadingLabel = this.i18n.t('widgets.sidebar.loading');
  protected readonly noResultsLabel = this.i18n.t('widgets.sidebar.noResults');
  protected readonly retryLabel = this.i18n.t('widgets.sidebar.retry');
  protected readonly defaultErrorMessage = this.i18n.t('widgets.sidebar.error');
  protected readonly defaultEmptyMessage = this.i18n.t('widgets.sidebar.empty');

  /**
   * Resuelve el nombre de ícono del registry para el item del menú, vía el
   * traductor compartido de navegación (sidebar-icons.ts).
   */
  protected readonly getIconName = getNavIconName;

  /**
   * Claves (`item.id ?? item.label`) de las agrupaciones ABIERTAS. Se guarda lo abierto, no lo
   * cerrado: así el menú nace totalmente colapsado y un ítem recién remapeado por el
   * refresco periódico del menú aparece cerrado, nunca abierto por accidente. Es un conjunto y no
   * una sola clave porque el acordeón es entre HERMANOS: una rama abierta puede tener, dentro, una
   * sub-agrupación abierta.
   */
  private readonly expanded = signal<Set<string>>(new Set());

  /** Computed list filtering out items where visible === false, recursively at every depth. */
  readonly visibleItems = computed(() => filterVisibleItems(this.items()));

  /**
   * Los cinco estados, resueltos en un solo lugar. `'empty'` y `'no-results'` se ven parecidos
   * pero no significan lo mismo, y el usuario merece saber cuál de los dos le tocó:
   *
   *   - `'empty'`: el API no devolvió ninguna opción. No hay nada que mostrar porque no hay nada
   *     asignado.
   *   - `'no-results'`: sí llegaron opciones, pero todas quedaron fuera al filtrar por
   *     visibilidad (`visible: false`). Ahí el problema es de permisos o de configuración, no de
   *     datos ausentes.
   */
  protected readonly viewState = computed<SidebarViewState>(() => {
    const state = this.state();
    if (state !== 'ready') return state;
    if (this.items().length === 0) return 'empty';
    return this.visibleItems().length === 0 ? 'no-results' : 'success';
  });

  onToggleCollapse(): void {
    this.collapsedChange.emit(!this.collapsed());
  }

  /** Whether a group's children are currently shown — false until the user opens it. */
  protected isExpanded(item: SidebarItem): boolean {
    return this.expanded().has(itemKey(item));
  }

  /**
   * Abre o cierra una agrupación en modo acordeón: abrirla cierra a sus hermanas (`siblings`, la
   * lista del mismo nivel que pasa el template) y a todo lo que estas tuvieran abierto dentro;
   * cerrarla cierra también a sus descendientes, para que al reabrirla vuelva a nacer colapsada.
   */
  protected toggle(item: SidebarItem, siblings: SidebarItem[]): void {
    const key = itemKey(item);

    if (this.collapsed()) {
      // Rail mode (icon-only, 64px): a group's children never render while collapsed (see the
      // `@if (!collapsed())` guard around .sol-sidebar__children-wrap in the template), so a
      // plain toggle here would be invisible — the user just sees nothing happen. Expand the
      // sidebar instead, making sure this group opens along with it, and stop: this click never
      // also collapses the group, or the user would land on an expanded-but-empty group.
      this.collapsedChange.emit(false);
      this.expanded.set(this.abrirEntreHermanos(item, siblings));
      return;
    }

    if (this.expanded().has(key)) {
      const next = new Set(this.expanded());
      next.delete(key);
      for (const descendiente of descendantKeys(item)) next.delete(descendiente);
      this.expanded.set(next);
      return;
    }

    this.expanded.set(this.abrirEntreHermanos(item, siblings));
  }

  /**
   * Una hoja se eligió: se avisa la ruta y, si el tema lo pide, el sidebar vuelve al riel. La
   * navegación real la hace el `routerLink` del propio enlace; aquí no se intercepta ni se cancela.
   */
  protected onLeafClick(item: SidebarItem): void {
    this.navigate.emit(item.route ?? '');
    if (this.autoCloseOnNavigate() && !this.collapsed()) {
      this.collapsedChange.emit(true);
    }
  }

  /** Conjunto de abiertos con `item` abierto y sus hermanas (y lo que estas contenían) cerradas. */
  private abrirEntreHermanos(item: SidebarItem, siblings: SidebarItem[]): Set<string> {
    const next = new Set(this.expanded());
    for (const hermano of siblings) {
      if (hermano === item) continue;
      next.delete(itemKey(hermano));
      for (const descendiente of descendantKeys(hermano)) next.delete(descendiente);
    }
    next.add(itemKey(item));
    return next;
  }
}
