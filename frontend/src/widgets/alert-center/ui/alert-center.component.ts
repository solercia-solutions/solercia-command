import {
  Component,
  ChangeDetectionStrategy,
  computed,
  inject,
} from '@angular/core';
import { AlertService } from '@shared/lib/alerts';
import type { AlertType } from '@shared/lib/alerts';
import { ThemeService } from '@shared/tokens';
import { SolIconComponent } from '@shared/ui';
import type { SolIconName } from '@shared/ui';

/** Mapa de tipo de alerta → nombre de ícono del registry de `@solercia/ui`. */
const ALERT_ICON_NAMES: Readonly<Record<AlertType, SolIconName>> = {
  success: 'check-circle',
  error: 'x-circle',
  warning: 'exclamation-triangle',
  info: 'information-circle',
};

@Component({
  selector: 'sol-alert-center',
  standalone: true,
  imports: [SolIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div
      class="sol-alert-center"
      [class.sol-alert-center--mobile-right]="mobileTopRight()"
      aria-live="polite"
      aria-relevant="additions removals"
    >
      @for (alert of alertService.alerts(); track alert.id) {
        <div
          class="sol-alert-toast"
          [class]="'sol-alert-toast sol-alert-toast--' + alert.type"
          role="alert"
        >
          <sol-icon class="sol-alert-toast__icon" [name]="getAlertIconName(alert.type)" />
          <span class="sol-alert-toast__message">
            {{ alert.message }}
            @if (alert.action; as action) {
              <button
                type="button"
                class="sol-alert-toast__action"
                (click)="alertService.act(alert.id)"
              >
                {{ action.label }}
              </button>
            }
          </span>
          <button
            type="button"
            class="sol-alert-toast__close"
            aria-label="Cerrar alerta"
            (click)="alertService.dismiss(alert.id)"
          >
            <sol-icon name="x" size="sm" />
          </button>
        </div>
      }
    </div>
  `,
  styles: `
    .sol-alert-center {
      position: fixed;
      top: calc(var(--sol-size-header-height, 56px) + var(--sol-space-md, 1rem));
      right: var(--sol-space-md, 1rem);
      z-index: calc(var(--sol-z-modal, 1000) + 10);
      display: flex;
      flex-direction: column;
      gap: var(--sol-space-sm, 0.5rem);
      max-width: 400px;
      width: 100%;
      pointer-events: none;
    }

    .sol-alert-toast {
      display: flex;
      align-items: flex-start;
      gap: var(--sol-space-sm, 0.5rem);
      padding: var(--sol-space-sm, 0.75rem) var(--sol-space-md, 1rem);
      border-radius: var(--sol-border-radius-md, 8px);
      background: var(--sol-bg-surface, #ffffff);
      box-shadow: var(--sol-shadow-lg, 0 10px 40px rgba(0, 0, 0, 0.12));
      border-left: 4px solid transparent;
      pointer-events: auto;
      animation: sol-alert-slide-in 0.3s ease-out;
    }

    .sol-alert-toast--success {
      border-left-color: var(--sol-color-success, #10b981);
    }

    .sol-alert-toast--error {
      border-left-color: var(--sol-color-danger, #ef4444);
    }

    .sol-alert-toast--warning {
      border-left-color: var(--sol-color-warning, #f59e0b);
    }

    .sol-alert-toast--info {
      border-left-color: var(--sol-color-info, #3b82f6);
    }

    .sol-alert-toast__icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 20px;
      height: 20px;
      flex-shrink: 0;
      margin-top: 1px;
    }

    .sol-alert-toast--success .sol-alert-toast__icon {
      color: var(--sol-color-success, #10b981);
    }

    .sol-alert-toast--error .sol-alert-toast__icon {
      color: var(--sol-color-danger, #ef4444);
    }

    .sol-alert-toast--warning .sol-alert-toast__icon {
      color: var(--sol-color-warning, #f59e0b);
    }

    .sol-alert-toast--info .sol-alert-toast__icon {
      color: var(--sol-color-info, #3b82f6);
    }

    .sol-alert-toast__message {
      flex: 1;
      font-size: var(--sol-font-size-sm, 0.875rem);
      color: var(--sol-color-text-primary, #111827);
      line-height: 1.4;
    }

    /* Acción opcional de la alerta (por ejemplo «Ver detalle»): enlace bajo el mensaje. */
    .sol-alert-toast__action {
      display: block;
      margin-top: var(--sol-space-xs, 0.25rem);
      padding: 0;
      border: none;
      background: transparent;
      color: var(--sol-color-primary, #4f46e5);
      font: inherit;
      font-weight: 600;
      cursor: pointer;
    }

    .sol-alert-toast__action:hover {
      text-decoration: underline;
    }

    .sol-alert-toast__close {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 24px;
      height: 24px;
      border: none;
      border-radius: var(--sol-border-radius-sm, 4px);
      background: transparent;
      color: var(--sol-color-text-muted, #9ca3af);
      cursor: pointer;
      flex-shrink: 0;
      transition: background-color 0.15s ease, color 0.15s ease;
    }

    .sol-alert-toast__close:hover {
      background: color-mix(in srgb, var(--sol-color-text-muted, #9ca3af) 12%, transparent);
      color: var(--sol-color-text-primary, #111827);
    }

    @keyframes sol-alert-slide-in {
      from {
        opacity: 0;
        transform: translateX(100%);
      }
      to {
        opacity: 1;
        transform: translateX(0);
      }
    }

    /* ── Toast móvil tipo push (estructura base v2) ─────────────────
       Bajo el breakpoint el toast se centra bajo el header y entra con
       translateY (nunca translateX). El token aditivo
       alerts.positionMobile = "top-right" conserva el anclaje lateral. */
    @media (max-width: 767px) {
      .sol-alert-center:not(.sol-alert-center--mobile-right) {
        right: auto;
        left: 50%;
        transform: translateX(-50%);
        top: calc(var(--sol-size-header-height, 56px) + 10px);
        width: min(370px, calc(100vw - 28px));
        max-width: none;
      }

      .sol-alert-center:not(.sol-alert-center--mobile-right) .sol-alert-toast {
        animation-name: sol-alert-drop-in;
      }

      .sol-alert-center--mobile-right {
        max-width: min(370px, calc(100vw - 28px));
      }
    }

    @keyframes sol-alert-drop-in {
      from {
        opacity: 0;
        transform: translateY(-16px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
  `,
})
export class SolAlertCenterComponent {
  protected readonly alertService = inject(AlertService);
  private readonly themeService = inject(ThemeService);

  /**
   * Token aditivo `component.alerts.positionMobile` del ThemeFile activo (v2).
   * Default "top-center" (toast tipo push bajo el header); "top-right"
   * conserva el anclaje lateral de desktop también en móvil.
   */
  protected readonly mobileTopRight = computed(() => {
    const file = this.themeService.activeTheme();
    const mode = this.themeService.isDark() ? 'dark' : 'light';
    const position = file?.modes?.[mode]?.component?.alerts?.positionMobile ?? 'top-center';
    return position === 'top-right';
  });

  /** Nombre de ícono del registry para el tipo de alerta. */
  getAlertIconName(type: AlertType): SolIconName {
    return ALERT_ICON_NAMES[type];
  }
}
