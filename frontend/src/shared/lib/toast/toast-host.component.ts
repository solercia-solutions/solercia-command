import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { SolIconComponent } from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { ToastKind, ToastStore } from './toast.store';

/**
 * Stacked toasts, mounted ONCE in the app shell. `role="status"` +
 * `aria-live="polite"` so screen readers announce new toasts without
 * interrupting; every toast is closable and pauses its timer on hover/focus.
 *
 * Position: top-center on narrow viewports (push-like, under the header),
 * bottom-end from `sm` up. Motion respects `prefers-reduced-motion` through
 * Tailwind's `motion-reduce` variant.
 */
@Component({
  selector: 'sol-toast-host',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [SolIconComponent],
  template: `
    <div
      role="status"
      aria-live="polite"
      [attr.aria-label]="text.region()"
      class="pointer-events-none fixed inset-x-3 top-16 z-50 flex flex-col items-center gap-2
             sm:inset-x-auto sm:bottom-4 sm:right-4 sm:top-auto sm:items-end"
    >
      @for (toast of store.toasts(); track toast.id) {
        <div
          class="pointer-events-auto flex w-full max-w-md items-start gap-3 rounded-lg border
                 bg-surface px-4 py-3 text-sm text-text shadow-lg transition-opacity
                 motion-reduce:transition-none"
          [class]="toneClass(toast.kind)"
          (mouseenter)="store.pause(toast.id)"
          (mouseleave)="store.resume(toast.id)"
          (focusin)="store.pause(toast.id)"
          (focusout)="store.resume(toast.id)"
        >
          <sol-icon
            [name]="iconOf(toast.kind)"
            size="sm"
            class="mt-0.5 shrink-0"
            [class]="iconClass(toast.kind)"
          />
          <div class="flex min-w-0 flex-1 flex-col gap-2">
            <p class="break-words">{{ toast.text }}</p>
            @if (toast.action; as action) {
              <button
                type="button"
                class="self-start text-sm font-semibold text-brand underline-offset-2 hover:underline
                       focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/55"
                (click)="store.act(toast.id)"
              >
                {{ action.label }}
              </button>
            }
          </div>
          <button
            type="button"
            class="-mr-1 -mt-1 inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-md
                   text-muted hover:bg-sunken hover:text-text focus:outline-none
                   focus-visible:ring-2 focus-visible:ring-ring/55 sm:h-8 sm:w-8"
            [attr.aria-label]="text.close()"
            (click)="store.dismiss(toast.id)"
          >
            <sol-icon name="x-mark" size="sm" />
          </button>
        </div>
      }
    </div>
  `,
})
export class ToastHostComponent {
  protected readonly store = inject(ToastStore);
  private readonly i18n = inject(I18nService);

  protected readonly text = {
    region: this.i18n.t('shared.toast.region'),
    close: this.i18n.t('shared.toast.close'),
  } as const;

  protected iconOf(kind: ToastKind): string {
    switch (kind) {
      case 'success':
        return 'check-circle';
      case 'error':
        return 'x-circle';
      case 'warning':
        return 'exclamation-triangle';
      default:
        return 'information-circle';
    }
  }

  protected toneClass(kind: ToastKind): string {
    switch (kind) {
      case 'success':
        return 'border-success/40';
      case 'error':
        return 'border-danger/40';
      case 'warning':
        return 'border-warning/50';
      default:
        return 'border-border';
    }
  }

  protected iconClass(kind: ToastKind): string {
    switch (kind) {
      case 'success':
        return 'text-success';
      case 'error':
        return 'text-danger';
      case 'warning':
        return 'text-warning';
      default:
        return 'text-info';
    }
  }
}
