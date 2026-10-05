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
import { SolErrorStateComponent } from '@shared/ui';

/**
 * Página `/task/:key` — envoltorio delgado del widget `sol-task-detail-panel`
 * (la misma UI que hospeda el drawer del workspace, en modo página completa).
 * La ruta se mantiene para enlaces directos y marcadores.
 */
@Component({
  selector: 'sol-task-detail-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TaskDetailPanelComponent, SolErrorStateComponent],
  template: `
<section class="tdp-page">
  @if (taskKey(); as key) {
    <sol-task-detail-panel [taskKey]="key" />
  } @else {
    <sol-error-state [code]="404" [title]="notFoundTitle()" [message]="missingKeyError()" />
  }
</section>
  `,
  styles: `
    .tdp-page { display: block; padding-block: var(--sol-space-md, 16px); }
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

  protected readonly notFoundTitle = this.i18n.t(
    'taskDetail.states.notFoundTitle',
  );

  protected readonly missingKeyError = this.i18n.t(
    'taskDetail.errors.missingKey',
  );
}
