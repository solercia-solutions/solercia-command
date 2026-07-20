import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { TaskDetailPanelComponent } from '@widgets/task-detail-panel/task-detail-panel.component';
import { I18nService } from '@shared/i18n';

/**
 * Página `/task/:key` — envoltorio delgado del widget `sol-task-detail-panel`
 * (la misma UI que hospeda el drawer del workspace, en modo página completa).
 * La ruta se mantiene para enlaces directos y marcadores.
 */
@Component({
  selector: 'sol-task-detail-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TaskDetailPanelComponent],
  template: `
<div class="min-h-screen bg-page px-4 py-6 md:px-8">
  @if (taskKey(); as key) {
    <sol-task-detail-panel [taskKey]="key" />
  } @else {
    <div class="rounded-lg border border-danger/30 bg-danger/10 p-4 text-danger">
      {{ missingKeyError() }}
    </div>
  }
</div>
  `,
})
export class TaskDetailPageComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly i18n = inject(I18nService);

  /** Param reactivo: navegar de /task/A a /task/B recarga el panel. */
  private readonly params = toSignal(this.route.paramMap);
  protected readonly taskKey = computed(
    () => this.params()?.get('key') ?? null,
  );

  protected readonly missingKeyError = this.i18n.t(
    'taskDetail.errors.missingKey',
  );
}
