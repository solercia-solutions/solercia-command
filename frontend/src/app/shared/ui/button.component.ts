import { ChangeDetectionStrategy, Component, Input } from '@angular/core';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

/** Reusable themed button. Light/dark handled by --sp-* driven colors. */
@Component({
  selector: 'sp-button',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button
      [type]="type"
      [disabled]="disabled"
      [attr.aria-label]="ariaLabel"
      [class]="classes"
    >
      <ng-content></ng-content>
    </button>
  `,
})
export class ButtonComponent {
  @Input() type: 'button' | 'submit' = 'button';
  @Input() variant: ButtonVariant = 'primary';
  @Input() disabled = false;
  @Input() block = false;
  @Input() ariaLabel?: string;

  get classes(): string {
    const base =
      'inline-flex items-center justify-center gap-2 h-10 rounded-lg px-4 text-sm font-medium ' +
      'transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50 ' +
      'disabled:opacity-50 disabled:cursor-not-allowed';
    const width = this.block ? 'w-full' : '';
    const variants: Record<ButtonVariant, string> = {
      primary: 'bg-brand text-brand-fg hover:bg-brand/90',
      secondary:
        'bg-surface text-text border border-border hover:bg-muted/10',
      ghost: 'bg-transparent text-text hover:bg-muted/10',
      danger: 'bg-danger text-white hover:bg-danger/90',
    };
    return `${base} ${width} ${variants[this.variant]}`.trim();
  }
}
