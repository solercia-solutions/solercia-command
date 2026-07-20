import {
  Component,
  ChangeDetectionStrategy,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { RouterModule } from '@angular/router';
import { I18nService } from '@shared/i18n';
import { SolIconComponent } from '@shared/ui';
import { SidebarItem } from '../model/sidebar.model';
import { getNavIconName } from './sidebar-icons';

/** Máximo de items visibles en la barra (incluyendo "Más" si hay overflow). */
const MAX_BAR_ITEMS = 5;

/**
 * Fixed bottom navigation for mobile viewports (ported from boki-front).
 *
 * Under the canonical breakpoint it replaces the sidebar: shows up to 5 items
 * from the dynamic menu; on overflow, the first 4 plus a "More" button that
 * opens a panel with the rest. Visibility is CSS-governed (display: none on
 * desktop).
 *
 * Host adaptation over boki: root items WITHOUT a route (pure groups, e.g.
 * "Administración") are never placed on the bar — a group item on the bar
 * would be a dead tap target on mobile. They always go to the "More" panel,
 * flattened together with their children, so every child route stays
 * reachable on mobile.
 */
@Component({
  selector: 'sol-bottom-nav',
  standalone: true,
  imports: [RouterModule, SolIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <!-- Panel de overflow ("Más"): lista los items que no caben en la barra. -->
    @if (moreOpen() && overflowItems().length) {
      <div class="sol-bottom-nav__overlay" (click)="closeMore()"></div>
      <div class="sol-bottom-nav__more-panel" role="menu">
        @for (item of overflowItems(); track item.id) {
          <a
            class="sol-bottom-nav__more-item"
            role="menuitem"
            [routerLink]="item.route ?? null"
            routerLinkActive="sol-bottom-nav__more-item--active"
            (click)="closeMore()"
          >
            <sol-icon class="sol-bottom-nav__more-icon" size="sm" [name]="getIconName(item.icon)" />
            <span class="sol-bottom-nav__more-label">{{ item.label }}</span>
          </a>
        }
      </div>
    }

    <nav class="sol-bottom-nav" [attr.aria-label]="text.navAria()">
      @for (item of barItems(); track item.id) {
        <a
          class="sol-bottom-nav__item"
          [routerLink]="item.route ?? null"
          routerLinkActive="sol-bottom-nav__item--active"
          (click)="closeMore()"
        >
          <sol-icon class="sol-bottom-nav__icon" [name]="getIconName(item.icon)" />
          <span class="sol-bottom-nav__label">{{ item.label }}</span>
        </a>
      }

      @if (overflowItems().length) {
        <button
          type="button"
          class="sol-bottom-nav__item sol-bottom-nav__item--more"
          [class.sol-bottom-nav__item--active]="moreOpen()"
          [attr.aria-expanded]="moreOpen()"
          [attr.aria-label]="moreLabel()"
          (click)="toggleMore()"
          data-testid="bottom-nav-more"
        >
          <sol-icon class="sol-bottom-nav__icon" name="ellipsis-vertical" />
          <span class="sol-bottom-nav__label">{{ moreLabel() }}</span>
        </button>
      }
    </nav>
  `,
  styles: `
    /* Oculta en desktop: la bottom-nav es exclusiva del viewport móvil. */
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
      /* Altura estructural 58px + safe-area de dispositivos con notch. */
      height: calc(58px + env(safe-area-inset-bottom, 0px));
      padding-bottom: env(safe-area-inset-bottom, 0px);
      display: flex;
      align-items: stretch;
      box-sizing: border-box;
      /* Capa base OPACA (fondo de página) + tinte del sidebar encima: temas
         con sidebar-bg transparente no pueden dejar ver el contenido a
         través de una barra fija. */
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

    .sol-bottom-nav__overlay {
      position: fixed;
      inset: 0;
      bottom: calc(58px + env(safe-area-inset-bottom, 0px));
      background: transparent;
      z-index: calc(var(--sol-z-dropdown, 100) + 1);
    }

    .sol-bottom-nav__more-panel {
      position: fixed;
      right: 10px;
      bottom: calc(58px + env(safe-area-inset-bottom, 0px) + 8px);
      min-width: 200px;
      max-width: calc(100vw - 20px);
      padding: var(--sol-space-xs, 0.25rem);
      box-sizing: border-box;
      /* Misma capa base opaca que la barra: el panel flota sobre contenido. */
      background-color: var(--sol-bg-page, #ffffff);
      background-image: linear-gradient(
        var(--sol-sidebar-bg, var(--sol-bg-surface, #ffffff)),
        var(--sol-sidebar-bg, var(--sol-bg-surface, #ffffff))
      );
      border: var(--sol-border-width-default, 1px) solid var(--sol-border-color-default, #e5e7eb);
      border-radius: var(--sol-border-radius-lg, 12px);
      box-shadow: var(--sol-shadow-lg, 0 10px 40px rgba(0, 0, 0, 0.12));
      z-index: calc(var(--sol-z-dropdown, 100) + 2);
      /* Entrada con los tokens de motion del tema (keyframes globales). */
      animation: solRevealRise var(--sol-dur-base, 240ms) var(--sol-ease-entrance, ease-out) backwards;
    }

    .sol-bottom-nav__more-item {
      display: flex;
      align-items: center;
      gap: var(--sol-space-sm, 0.5rem);
      padding: var(--sol-space-sm, 0.5rem) var(--sol-space-md, 0.75rem);
      border-radius: var(--sol-sidebar-item-radius, var(--sol-border-radius-md, 8px));
      color: var(--sol-sidebar-text, var(--sol-color-text-secondary, #6b7280));
      text-decoration: none;
      font-size: var(--sol-font-size-sm, 0.875rem);
      font-weight: 500;
    }

    .sol-bottom-nav__more-item--active {
      background: var(--sol-sidebar-active-bg, color-mix(in srgb, var(--sol-color-primary, #2563EB) 10%, transparent));
      color: var(--sol-sidebar-active-text, var(--sol-color-primary, #2563EB));
      font-weight: 600;
    }

    .sol-bottom-nav__more-icon {
      display: inline-flex;
      width: 16px;
      height: 16px;
      flex-shrink: 0;
    }

    .sol-bottom-nav__more-label {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  `,
})
export class SolBottomNavComponent {
  private readonly i18n = inject(I18nService);

  /** Items del menú dinámico (los mismos del sidebar). */
  readonly items = input<SidebarItem[]>([]);

  /** Etiqueta i18n del botón de overflow. */
  protected readonly moreLabel = this.i18n.t('shared.nav.more');

  /** Static UI text resolved via i18n (reactive to language change). */
  protected readonly text = {
    navAria: this.i18n.t('nav.mobileNavAria'),
  } as const;

  /** Panel de overflow abierto. */
  readonly moreOpen = signal(false);

  private readonly visibleItems = computed(() =>
    this.items().filter(item => item.visible !== false),
  );

  /** Root items that navigate directly (have a route). */
  private readonly navigableItems = computed(() =>
    this.visibleItems().filter(item => !!item.route),
  );

  /** True when the "More" button is needed (groups or too many items). */
  private readonly hasOverflow = computed(() => {
    const items = this.visibleItems();
    return (
      items.length > MAX_BAR_ITEMS ||
      this.navigableItems().length < items.length
    );
  });

  /**
   * Items de la barra: todos si caben (≤5) y todos navegan; si hay overflow,
   * los primeros 4 navegables (el quinto puesto lo ocupa el botón "Más").
   */
  readonly barItems = computed(() => {
    if (!this.hasOverflow()) {
      return this.visibleItems();
    }
    return this.navigableItems().slice(0, MAX_BAR_ITEMS - 1);
  });

  /** Items que van al panel "Más" (hijos aplanados junto a su padre). */
  readonly overflowItems = computed<SidebarItem[]>(() => {
    if (!this.hasOverflow()) {
      return [];
    }
    const inBar = new Set(this.barItems().map(item => item.id));
    return this.visibleItems()
      .filter(item => !inBar.has(item.id))
      .flatMap(item => [item, ...(item.children ?? [])]);
  });

  toggleMore(): void {
    this.moreOpen.update(open => !open);
  }

  closeMore(): void {
    this.moreOpen.set(false);
  }

  /**
   * Resuelve el nombre de ícono del registry para el item del menú, vía el
   * traductor compartido de navegación (sidebar-icons.ts).
   */
  protected readonly getIconName = getNavIconName;
}
