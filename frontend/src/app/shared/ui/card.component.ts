import { ChangeDetectionStrategy, Component } from '@angular/core';

/** Surface container with border + subtle shadow, theme-aware. */
@Component({
  selector: 'sp-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div
      class="rounded-xl border border-border bg-surface p-5 shadow-sm transition-colors"
    >
      <ng-content></ng-content>
    </div>
  `,
})
export class CardComponent {}
