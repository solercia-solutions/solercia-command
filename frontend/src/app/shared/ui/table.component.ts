import { ChangeDetectionStrategy, Component } from '@angular/core';

/**
 * Presentational table shell: a bordered, scrollable surface wrapping a styled
 * <table>. Consumers project <thead>/<tbody>. Keeps admin lists consistent.
 */
@Component({
  selector: 'sp-table',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="overflow-x-auto rounded-xl border border-border bg-surface">
      <table class="w-full border-collapse text-left text-sm text-text">
        <ng-content></ng-content>
      </table>
    </div>
  `,
})
export class TableComponent {}
