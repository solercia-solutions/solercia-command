import { ChangeDetectionStrategy, Component, Input } from '@angular/core';

type BadgeTone = 'brand' | 'success' | 'muted' | 'danger' | 'warning';

/**
 * Small pill for roles, codes and status flags. Uses solid soft tokens with a
 * matching foreground for proper contrast (not washed-out alpha tints).
 */
@Component({
  selector: 'bk-badge',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span [class]="classes"><ng-content></ng-content></span>`,
})
export class BadgeComponent {
  @Input() tone: BadgeTone = 'muted';

  get classes(): string {
    const base =
      'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold';
    const tones: Record<BadgeTone, string> = {
      brand: 'bg-brand-soft text-brand-soft-fg',
      success: 'bg-success-soft text-success-soft-fg',
      muted: 'bg-sunken text-muted',
      danger: 'bg-danger-soft text-danger-soft-fg',
      warning: 'bg-warning-soft text-warning-soft-fg',
    };
    return `${base} ${tones[this.tone]}`;
  }
}
