import {
  Component,
  ChangeDetectionStrategy,
  input,
  output,
  inject,
} from '@angular/core';
import { ThemeService } from '@shared/tokens';
import { SolBrandLogoComponent, SolIconComponent } from '@shared/ui';

@Component({
  selector: 'sol-header',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [SolBrandLogoComponent, SolIconComponent],
  template: `
    <header class="sol-header">
      <div class="sol-header__left">
        @if (showSidebarToggle()) {
          <button
            type="button"
            class="sol-header__menu-btn"
            aria-label="Alternar menú lateral"
            (click)="sidebarToggle.emit()"
          >
            <sol-icon name="menu" />
          </button>
        }

        @if (themeService.logo(); as logo) {
          <sol-brand-logo class="sol-header__logo" [logo]="logo" />
        }

        @if (title()) {
          <h1 class="sol-header__title">{{ title() }}</h1>
        }
      </div>

      <div class="sol-header__actions">
        <ng-content />
      </div>
    </header>
  `,
  styles: `
    .sol-header {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      height: var(--sol-size-header-height, 56px);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 var(--sol-space-md, 1rem);
      /* v2: header translúcido con blur cuando el tema lo pide (rgba + blur). */
      background: var(--sol-header-bg, var(--sol-bg-surface, #ffffff));
      -webkit-backdrop-filter: var(--sol-header-blur, none);
      backdrop-filter: var(--sol-header-blur, none);
      border-bottom: 1px solid var(--sol-border-color-default, #e5e7eb);
      z-index: calc(var(--sol-z-dropdown, 100) + 1);
    }

    .sol-header__left {
      display: flex;
      align-items: center;
      gap: var(--sol-space-sm, 0.5rem);
      min-width: 0;
    }

    .sol-header__menu-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      border: none;
      border-radius: var(--sol-border-radius-md, 8px);
      background: transparent;
      color: var(--sol-color-text-secondary, #6b7280);
      cursor: pointer;
      transition: background-color 0.15s ease, color 0.15s ease;
    }

    .sol-header__menu-btn:hover {
      background: color-mix(in srgb, var(--sol-color-primary, #6366f1) 10%, transparent);
      color: var(--sol-color-primary, #6366f1);
    }

    .sol-header__logo {
      /* Solo el ALTO disponible: el ancho lo deriva sol-brand-logo de su
         propia proporción (ver su hoja de estilos) — fijarlo aquí encima
         reintroducía la caja fantasma que ese componente ya resuelve. */
      height: 32px;
    }

    .sol-header__title {
      margin: 0;
      font-size: var(--sol-font-size-lg, 1.125rem);
      font-weight: 600;
      color: var(--sol-color-text-primary, #111827);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .sol-header__actions {
      display: flex;
      align-items: center;
      gap: var(--sol-space-sm, 0.5rem);
      flex-shrink: 0;
      min-width: 0;
    }

    /* Header móvil (estructura base): sin botón de menú (la navegación vive
       en la bottom-nav), logo compacto y solo título + acciones compactas. */
    @media (max-width: 767px) {
      .sol-header {
        padding: 0 var(--sol-space-sm, 0.5rem);
        gap: var(--sol-space-sm, 0.5rem);
      }

      .sol-header__menu-btn {
        display: none;
      }

      .sol-header__logo {
        height: 26px;
        /* Tope responsive que sol-brand-logo combina (el MENOR gana) con el
           ancho elegido en el Theme Studio — ver --sol-brand-logo-max-width
           en su hoja de estilos. Puesto en el host, no en el propio <img>/
           <svg>, porque el encabezado móvil es quien decide este límite. */
        --sol-brand-logo-max-width: 96px;
      }

      .sol-header__title {
        font-size: var(--sol-font-size-base, 1rem);
      }
    }
  `,
})
export class SolHeaderComponent {
  protected readonly themeService = inject(ThemeService);

  /** Title displayed in the header bar. */
  readonly title = input<string>('');

  /** Whether to show the sidebar toggle (hamburger) button. */
  readonly showSidebarToggle = input<boolean>(true);

  /** Emitted when the sidebar toggle button is clicked. */
  readonly sidebarToggle = output<void>();

  /** Resolved logo URL from ThemeService. */
  protected readonly logoUrl = this.themeService.logo;
}
