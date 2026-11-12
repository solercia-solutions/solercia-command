import { Component, ChangeDetectionStrategy, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AuthService } from '@features/auth/auth.service';
import { ErrorDiagnosticsService } from '@shared/api/error-diagnostics.service';
import { I18nService } from '@shared/i18n';
import { AlertService } from '@shared/lib/alerts';
import { copyTraceIdToClipboard, SolIconComponent, SolRevealDirective } from '@shared/ui';

/**
 * Página 404 (theming v2, Paso 6): "404" gigante en la fuente display del
 * tema, color primary y text-shadow con --sol-shadow-card (en Tinta produce
 * la sombra dura desplazada). El botón vuelve al panel si hay sesión o al
 * login si no la hay.
 */
@Component({
  standalone: true,
  selector: 'sol-not-found-page',
  imports: [RouterLink, SolRevealDirective, SolIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="sol-not-found">
      <div class="sol-not-found__content" solReveal>
        <span class="sol-not-found__code sol-display" aria-hidden="true">404</span>
        <h1 class="sol-not-found__title sol-display">{{ title() }}</h1>
        <p class="sol-not-found__message">{{ message() }}</p>
        @if (traceId(); as id) {
          <div class="sol-not-found__trace">
            <span class="sol-not-found__trace-label">{{ traceIdLabel() }}</span>
            <code class="sol-not-found__trace-value">{{ id }}</code>
            <button
              type="button"
              class="sol-not-found__copy-btn"
              [attr.aria-label]="copyLabel()"
              (click)="copyTraceId(id)"
            >
              <sol-icon name="clipboard" size="sm" />
            </button>
          </div>
        }
        <a [routerLink]="backTarget()" class="sol-not-found__link">
          {{ backLabel() }}
        </a>
      </div>
    </div>
  `,
  styles: [`
    .sol-not-found {
      position: relative;
      isolation: isolate;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      min-height: 100dvh;
      background-color: var(--sol-bg-page);
      padding: var(--sol-space-lg, 24px);
    }

    /* Textura de página del tema en una capa FIJA al viewport: .sol-not-found usa min-height
       (puede crecer más alto que el viewport con mensajes largos) y el background-image pintado
       sobre el propio contenedor se repetía por cada franja de scroll. position:fixed la
       desacopla de ese alto real. */
    .sol-not-found::before {
      content: '';
      position: fixed;
      inset: 0;
      z-index: -1;
      pointer-events: none;
      background-image: var(--sol-bg-page-texture, none);
      background-repeat: no-repeat;
      background-size: cover;
      background-position: center;
    }

    .sol-not-found__content {
      text-align: center;
      max-width: 480px;
    }

    /* "404" gigante: carácter tipográfico del tema (display) + sombra de
       card como text-shadow — en Tinta produce la sombra dura desplazada. */
    .sol-not-found__code {
      display: block;
      font-size: clamp(96px, 20vw, 160px);
      line-height: 1;
      color: var(--sol-color-primary);
      text-shadow: var(--sol-shadow-card, none);
    }

    .sol-not-found__title {
      margin: var(--sol-space-md, 16px) 0 0;
      font-size: var(--sol-font-size-xl, 20px);
      color: var(--sol-color-text-primary);
    }

    .sol-not-found__message {
      margin: var(--sol-space-sm, 8px) 0 var(--sol-space-lg, 24px);
      font-size: var(--sol-font-size-base, 14px);
      color: var(--sol-color-text-muted);
    }

    /* Bloque del código de seguimiento (mismo lenguaje visual que error-state.component.ts):
       solo aparece cuando ErrorDiagnosticsService trae un último error registrado. */
    .sol-not-found__trace {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: var(--sol-space-sm, 8px);
      margin: 0 0 var(--sol-space-lg, 24px);
      padding: var(--sol-space-sm, 8px) var(--sol-space-md, 16px);
      border-radius: var(--sol-border-radius-md, 8px);
      background: var(--sol-bg-sunken, #e2e8f0);
      font-size: var(--sol-font-size-sm, 0.875rem);
    }

    .sol-not-found__trace-label {
      color: var(--sol-color-text-muted);
      white-space: nowrap;
    }

    .sol-not-found__trace-value {
      font-family: var(--sol-font-family-mono, monospace);
      color: var(--sol-color-text-primary);
      overflow-wrap: anywhere;
    }

    .sol-not-found__copy-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      min-width: var(--sol-size-control-lg, 40px);
      min-height: var(--sol-size-control-lg, 40px);
      border: none;
      border-radius: var(--sol-border-radius-sm, 6px);
      background: transparent;
      color: var(--sol-color-text-muted);
      cursor: pointer;
    }

    .sol-not-found__copy-btn:hover {
      color: var(--sol-color-primary);
    }

    @media (max-width: 767px) {
      .sol-not-found__copy-btn {
        min-width: var(--sol-size-control-touch, 44px);
        min-height: var(--sol-size-control-touch, 44px);
      }
    }

    /* Enlace con forma de botón primario: consume los tokens de botón del
       tema (radio, sombra, peso, mayúsculas y press-scale). */
    .sol-not-found__link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      height: var(--sol-size-button-height, 40px);
      padding: 0 var(--sol-space-lg, 24px);
      background-color: var(--sol-color-primary);
      color: var(--sol-color-primary-contrast, #fff);
      border-radius: var(--sol-button-radius, var(--sol-border-radius-md));
      box-shadow: var(--sol-button-shadow, none);
      font-family: var(--sol-font-family);
      font-weight: var(--sol-button-weight, 500);
      text-transform: var(--sol-button-transform, none);
      text-decoration: none;
      transition:
        filter var(--sol-dur-fast, 150ms) var(--sol-ease, ease),
        transform var(--sol-dur-fast, 150ms) var(--sol-ease, ease);
    }

    .sol-not-found__link:hover {
      filter: brightness(1.1);
    }

    .sol-not-found__link:active {
      transform: scale(var(--sol-press-scale, 0.98));
    }
  `],
})
export class NotFoundPageComponent {
  private readonly auth = inject(AuthService);
  private readonly i18n = inject(I18nService);
  private readonly alert = inject(AlertService);
  private readonly diagnostics = inject(ErrorDiagnosticsService);

  readonly title = this.i18n.t('pages.notFound.title');
  readonly message = this.i18n.t('pages.notFound.message');
  private readonly backPanelLabel = this.i18n.t('pages.notFound.backPanel');
  private readonly backLoginLabel = this.i18n.t('pages.notFound.backLogin');

  /** Código de seguimiento del último error registrado por `error.interceptor.ts`, si hay uno —
   *  un 404 puede llegar aquí sin pasar por el interceptor (enlace roto tecleado a mano), así que
   *  el bloque solo aparece cuando de verdad hay algo que correlacionar con soporte. */
  protected readonly traceId = computed<string | null>(() => this.diagnostics.last()?.traceId ?? null);
  protected readonly traceIdLabel = this.i18n.t('shared.errorState.traceId');
  protected readonly copyLabel = this.i18n.t('shared.errorState.copy');

  protected copyTraceId(id: string): void {
    copyTraceIdToClipboard(id, this.alert, this.i18n);
  }

  /** Con sesión → inicio; sin sesión → login (la ruta segura existente). */
  protected readonly backTarget = computed<string>(() =>
    this.auth.isAuthenticated() ? '/' : '/login',
  );

  protected readonly backLabel = computed<string>(() =>
    this.auth.isAuthenticated() ? this.backPanelLabel() : this.backLoginLabel(),
  );
}
