import {
  Component,
  ChangeDetectionStrategy,
  inject,
  input,
  output,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { ThemeService } from '@shared/ui';
import { I18nService } from '@shared/i18n';

/**
 * Fixed top bar (ported from boki-front `widgets/header`).
 *
 * Left side: sidebar toggle (hamburger, desktop only), tenant logo from
 * `ThemeService` when the active theme provides one — otherwise the host
 * brand ("S" badge + "Solercia Command") — and an optional title. Right side:
 * a projected actions slot (theme toggle, notification bell, logout...).
 */
@Component({
  selector: 'sol-header',
  standalone: true,
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="sol-header">
      <div class="sol-header__left">
        @if (showSidebarToggle()) {
          <button
            type="button"
            class="sol-header__menu-btn"
            [attr.aria-label]="text.sidebarToggle()"
            (click)="sidebarToggle.emit()"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
        }

        <a
          class="sol-header__brand"
          routerLink="/projects"
          [attr.aria-label]="text.brandAria()"
        >
          @if (themeService.logo(); as logo) {
            <img
              class="sol-header__logo"
              [src]="logo.url"
              [alt]="logo.altText"
              [style.width.px]="logo.width ?? 120"
            />
          } @else {
            <span class="sol-header__brand-badge" aria-hidden="true">S</span>
            <span class="sol-header__brand-name">Solercia Command</span>
          }
        </a>

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

    .sol-header__brand {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      text-decoration: none;
      min-width: 0;
    }

    .sol-header__brand-badge {
      display: grid;
      place-items: center;
      width: 32px;
      height: 32px;
      border-radius: var(--sol-border-radius-lg, 12px);
      background: var(--sol-color-primary, #4f46e5);
      color: #ffffff;
      font-size: var(--sol-font-size-sm, 0.875rem);
      font-weight: 700;
      box-shadow: var(--sol-shadow-sm, 0 1px 2px rgba(0, 0, 0, 0.06));
      flex-shrink: 0;
    }

    .sol-header__brand-name {
      font-family: var(--sol-font-display, inherit);
      font-size: 15px;
      font-weight: 700;
      letter-spacing: -0.01em;
      color: var(--sol-color-text-primary, #111827);
      white-space: nowrap;
    }

    .sol-header__logo {
      height: 32px;
      width: auto;
      object-fit: contain;
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
        max-width: 96px;
      }

      .sol-header__title {
        font-size: var(--sol-font-size-base, 1rem);
      }
    }
  `,
})
export class SolHeaderComponent {
  protected readonly themeService = inject(ThemeService);
  private readonly i18n = inject(I18nService);

  /** Title displayed in the header bar. */
  readonly title = input<string>('');

  /** Whether to show the sidebar toggle (hamburger) button. */
  readonly showSidebarToggle = input<boolean>(true);

  /** Emitted when the sidebar toggle button is clicked. */
  readonly sidebarToggle = output<void>();

  /** Static UI text resolved via i18n (reactive to language change). */
  protected readonly text = {
    sidebarToggle: this.i18n.t('nav.sidebarToggle'),
    brandAria: this.i18n.t('nav.brandAria'),
  } as const;
}
