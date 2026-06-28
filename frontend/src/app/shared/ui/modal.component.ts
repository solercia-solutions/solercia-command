import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  Output,
} from '@angular/core';

/**
 * Centered modal dialog with a dimmed backdrop. Clicking the backdrop or the
 * close button emits `close`. The body is projected via <ng-content>.
 */
@Component({
  selector: 'bk-modal',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
      (click)="close.emit()"
    >
      <div
        role="dialog"
        aria-modal="true"
        [attr.aria-label]="title"
        (click)="$event.stopPropagation()"
        [class]="panelClasses"
      >
        <div class="mb-4 flex items-center justify-between gap-2">
          <h2 class="text-lg font-semibold text-text">{{ title }}</h2>
          <button
            type="button"
            (click)="close.emit()"
            class="grid h-8 w-8 place-items-center rounded-lg text-muted transition-colors
                   hover:bg-muted/10 hover:text-text focus:outline-none focus-visible:ring-2
                   focus-visible:ring-brand/50"
            aria-label="Cierra la ventana"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <ng-content></ng-content>
      </div>
    </div>
  `,
})
export class ModalComponent {
  @Input({ required: true }) title = '';
  @Input() size: 'sm' | 'md' | 'lg' = 'md';
  @Output() close = new EventEmitter<void>();

  get panelClasses(): string {
    const base =
      'max-h-[90vh] w-full overflow-y-auto rounded-xl border border-border bg-surface p-5 shadow-lg';
    const widths: Record<'sm' | 'md' | 'lg', string> = {
      sm: 'max-w-sm',
      md: 'max-w-md',
      lg: 'max-w-lg',
    };
    return `${base} ${widths[this.size]}`;
  }
}
