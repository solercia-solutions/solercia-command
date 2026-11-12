import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { SolIconComponent, SolRevealDirective } from '@solercia/ui';
import { AlertService } from '@shared/lib/alerts';
import { I18nService } from '@shared/i18n';
import { copyTraceIdToClipboard } from './copy-trace-id.util';

/**
 * Bloque presentacional de error: código, título, mensaje y el código de seguimiento (`traceId`)
 * de la respuesta —visible y copiable con un botón— más una ranura para acciones. No impone altura
 * de página completa: sirve igual para una página de error que dentro de un panel o un overlay.
 * El título por código se resuelve con `errorTitleKey()`.
 */
@Component({
  standalone: true,
  selector: 'sol-error-state',
  imports: [SolIconComponent, SolRevealDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="sol-error-state" solReveal>
      <span class="sol-error-state__code sol-display" aria-hidden="true">{{ code() }}</span>
      <h1 class="sol-error-state__title sol-display">{{ title() }}</h1>
      <p class="sol-error-state__message">{{ message() }}</p>
      @if (traceId(); as id) {
        <div class="sol-error-state__trace">
          <span class="sol-error-state__trace-label">{{ traceIdLabel() }}</span>
          <code class="sol-error-state__trace-value">{{ id }}</code>
          <button
            type="button"
            class="sol-error-state__copy-btn"
            [attr.aria-label]="copyLabel()"
            (click)="copyTraceId(id)"
          >
            <sol-icon name="clipboard" size="sm" />
          </button>
        </div>
      }
      <div class="sol-error-state__actions">
        <ng-content />
      </div>
    </div>
  `,
  styles: [`
    .sol-error-state {
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      gap: var(--sol-space-sm, 8px);
      max-width: 480px;
      margin-inline: auto;
    }

    /* Mismo tratamiento que .sol-not-found__code (not-found-page.component.ts): carácter
       tipográfico display + sombra de card como text-shadow, escalado con clamp para que el
       mismo bloque quepa tanto a pantalla completa como dentro de un panel. */
    .sol-error-state__code {
      display: block;
      font-size: clamp(56px, 10vw, 96px);
      line-height: 1;
      color: var(--sol-color-primary);
      text-shadow: var(--sol-shadow-card, none);
    }

    .sol-error-state__title {
      margin: var(--sol-space-sm, 8px) 0 0;
      font-size: var(--sol-font-size-xl, 20px);
      color: var(--sol-color-text-primary);
    }

    .sol-error-state__message {
      margin: 0;
      font-size: var(--sol-font-size-base, 14px);
      color: var(--sol-color-text-muted);
    }

    .sol-error-state__trace {
      display: flex;
      align-items: center;
      gap: var(--sol-space-sm, 8px);
      margin-top: var(--sol-space-sm, 8px);
      padding: var(--sol-space-sm, 8px) var(--sol-space-md, 16px);
      border-radius: var(--sol-border-radius-md, 8px);
      background: var(--sol-bg-sunken, #e2e8f0);
      font-size: var(--sol-font-size-sm, 0.875rem);
      max-width: 100%;
    }

    .sol-error-state__trace-label {
      color: var(--sol-color-text-muted);
      white-space: nowrap;
    }

    .sol-error-state__trace-value {
      font-family: var(--sol-font-family-mono, monospace);
      color: var(--sol-color-text-primary);
      overflow-wrap: anywhere;
    }

    .sol-error-state__copy-btn {
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

    .sol-error-state__copy-btn:hover {
      color: var(--sol-color-primary);
    }

    /* Objetivo táctil ≥44px solo bajo el breakpoint móvil (aditivo, ley de Fitts):
       desktop conserva la densidad de --sol-size-control-lg. */
    @media (max-width: 767px) {
      .sol-error-state__copy-btn {
        min-width: var(--sol-size-control-touch, 44px);
        min-height: var(--sol-size-control-touch, 44px);
      }
    }

    .sol-error-state__actions {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: var(--sol-space-sm, 8px);
      margin-top: var(--sol-space-md, 16px);
    }
  `],
})
export class SolErrorStateComponent {
  private readonly alert = inject(AlertService);
  private readonly i18n = inject(I18nService);

  readonly code = input.required<number>();
  readonly title = input.required<string>();
  readonly message = input.required<string>();
  readonly traceId = input<string | null>(null);

  protected readonly traceIdLabel = this.i18n.t('shared.errorState.traceId');
  protected readonly copyLabel = this.i18n.t('shared.errorState.copy');

  protected copyTraceId(id: string): void {
    copyTraceIdToClipboard(id, this.alert, this.i18n);
  }
}
