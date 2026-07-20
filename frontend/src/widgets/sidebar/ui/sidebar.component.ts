import {
  Component,
  ChangeDetectionStrategy,
  computed,
  inject,
  input,
  output,
} from '@angular/core';
import { RouterModule } from '@angular/router';
import { SolIconComponent } from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { SidebarItem } from '../model/sidebar.model';
import { getNavIconName } from './sidebar-icons';

/**
 * Collapsible left sidebar (ported from boki-front `widgets/sidebar`).
 *
 * Fixed below the header; collapses to a 64px icon-only rail. Items with
 * children render as a nested group when expanded; when collapsed only the
 * root-level icons remain visible. Hidden under the 767px breakpoint, where
 * the fixed bottom-nav (`sol-bottom-nav`) takes over navigation.
 */
@Component({
  selector: 'sol-sidebar',
  standalone: true,
  imports: [RouterModule, SolIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <aside
      class="sol-sidebar"
      [class.sol-sidebar--collapsed]="collapsed()"
    >
      <nav class="sol-sidebar__nav" [attr.aria-label]="text.navAria()">
        @for (item of visibleItems(); track item.id) {
          <a
            class="sol-sidebar__item"
            [routerLink]="item.route ?? null"
            routerLinkActive="sol-sidebar__item--active"
            [title]="collapsed() ? item.label : ''"
          >
            <sol-icon class="sol-sidebar__icon" [name]="getIconName(item.icon)" />

            @if (!collapsed()) {
              <span class="sol-sidebar__label">{{ item.label }}</span>

              @if (item.badge !== undefined && item.badge !== null) {
                <span class="sol-sidebar__badge">{{ item.badge }}</span>
              }
            }
          </a>

          @if (!collapsed() && item.children?.length) {
            <div class="sol-sidebar__children">
              @for (child of item.children; track child.id) {
                <a
                  class="sol-sidebar__item sol-sidebar__item--child"
                  [routerLink]="child.route ?? null"
                  routerLinkActive="sol-sidebar__item--active"
                >
                  <sol-icon class="sol-sidebar__icon sol-sidebar__icon--sm" size="sm" [name]="getIconName(child.icon)" />
                  <span class="sol-sidebar__label">{{ child.label }}</span>

                  @if (child.badge !== undefined && child.badge !== null) {
                    <span class="sol-sidebar__badge">{{ child.badge }}</span>
                  }
                </a>
              }
            </div>
          }
        }
      </nav>

      <button
        type="button"
        class="sol-sidebar__toggle"
        (click)="onToggleCollapse()"
        [attr.aria-label]="collapsed() ? text.expand() : text.collapse()"
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
      /* v2: el sidebar puede ser oscuro aunque el modo sea light;
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

    /* Estructura base móvil: bajo el breakpoint canónico el sidebar
       desaparece y la navegación pasa a la bottom-nav fija (sol-bottom-nav). */
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

    .sol-sidebar__item {
      display: flex;
      align-items: center;
      gap: var(--sol-space-sm, 0.5rem);
      padding: var(--sol-space-sm, 0.5rem) var(--sol-space-md, 0.75rem);
      border-radius: var(--sol-sidebar-item-radius, var(--sol-border-radius-md, 8px));
      color: var(--sol-sidebar-text, var(--sol-color-text-secondary, #6b7280));
      text-decoration: none;
      font-size: var(--sol-font-size-sm, 0.875rem);
      font-weight: 500;
      white-space: nowrap;
      cursor: pointer;
      transition: background-color 0.15s ease, color 0.15s ease;
    }

    /* El hover deriva del texto activo del tema: funciona igual sobre sidebar
       claro y oscuro (mezcla del primary o del texto claro). */
    .sol-sidebar__item:hover {
      background: color-mix(in srgb, var(--sol-sidebar-active-text, var(--sol-color-primary, #2563EB)) 8%, transparent);
      color: var(--sol-sidebar-active-text, var(--sol-color-primary, #2563EB));
    }

    /* v2: la barra de acento es un box-shadow inset del tema (el default emite
       "inset 3px 0 0 primary" = mismo look v1 sin desplazar el contenido). */
    .sol-sidebar__item--active {
      background: var(--sol-sidebar-active-bg, color-mix(in srgb, var(--sol-color-primary, #2563EB) 10%, transparent));
      color: var(--sol-sidebar-active-text, var(--sol-color-primary, #2563EB));
      font-weight: 600;
      box-shadow: var(--sol-sidebar-indicator, inset 3px 0 0 var(--sol-color-primary, #2563EB));
    }

    .sol-sidebar__item--child {
      padding-left: calc(var(--sol-space-md, 0.75rem) + 1.5rem);
      font-size: var(--sol-font-size-sm, 0.8125rem);
    }

    .sol-sidebar__children {
      display: flex;
      flex-direction: column;
      gap: 1px;
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
      overflow: hidden;
      text-overflow: ellipsis;
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
  private readonly i18n = inject(I18nService);

  /** List of sidebar navigation items. */
  readonly items = input<SidebarItem[]>([]);

  /** Whether the sidebar is in collapsed (icon-only) mode. */
  readonly collapsed = input<boolean>(false);

  /** Emitted when the collapsed state changes. */
  readonly collapsedChange = output<boolean>();

  /** Static UI text resolved via i18n (reactive to language change). */
  protected readonly text = {
    navAria: this.i18n.t('nav.primaryNavAria'),
    expand: this.i18n.t('nav.sidebarExpand'),
    collapse: this.i18n.t('nav.sidebarCollapse'),
  } as const;

  /** Computed list filtering out items where visible === false. */
  readonly visibleItems = computed(() =>
    this.items().filter(item => item.visible !== false),
  );

  onToggleCollapse(): void {
    this.collapsedChange.emit(!this.collapsed());
  }

  /**
   * Resuelve el nombre de ícono del registry para el item del menú, vía el
   * traductor compartido de navegación (sidebar-icons.ts).
   */
  protected readonly getIconName = getNavIconName;
}
