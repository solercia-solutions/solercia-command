import { ChangeDetectionStrategy, Component, Input } from '@angular/core';

type BadgeTone = 'brand' | 'success' | 'muted' | 'danger' | 'warning';

/** Small pill used for roles, codes and status flags. Theme-aware. */
@Component({
  selector: 'sp-badge',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span [class]="classes"><ng-content></ng-content></span>`,
})
export class BadgeComponent {
  @Input() tone: BadgeTone = 'muted';

  get classes(): string {
    const base =
      'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium';
    const tones: Record<BadgeTone, string> = {
      brand: 'bg-brand/10 text-brand',
      success: 'bg-success/10 text-success',
      muted: 'bg-muted/10 text-muted',
      danger: 'bg-danger/10 text-danger',
      warning: 'bg-warning/10 text-warning',
    };
    return `${base} ${tones[this.tone]}`;
  }
}
