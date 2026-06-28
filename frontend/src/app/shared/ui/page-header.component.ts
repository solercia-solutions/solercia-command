import { ChangeDetectionStrategy, Component, Input } from '@angular/core';

/**
 * Page title block: heading + optional subtitle on the left, with a projected
 * actions slot on the right (e.g. a "Crear" button). Theme-aware.
 */
@Component({
  selector: 'sp-page-header',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-bold tracking-tight text-text">
          {{ title }}
        </h1>
        @if (subtitle) {
          <p class="mt-1 text-sm text-muted">{{ subtitle }}</p>
        }
      </div>
      <ng-content></ng-content>
    </div>
  `,
})
export class PageHeaderComponent {
  @Input({ required: true }) title = '';
  @Input() subtitle?: string;
}
