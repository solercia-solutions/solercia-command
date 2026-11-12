import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { SolBadgeComponent, SolCardComponent } from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { formatBogotaDateTime } from '@shared/lib/utils/bogota-date.util';
import {
  IntakeProposal,
  confidenceLevel,
} from '@entities/intake-proposal/intake-proposal.model';
import { ProposalActionsComponent } from './proposal-actions.component';
import { ProposalTaskRef } from './proposal-task-resolver';
import { CONFIDENCE_VARIANT, RELATION_VARIANT, STATUS_VARIANT } from './proposal-labels';

/** Una propuesta en la bandeja: qué hilo, quién pide, qué se propone y las acciones. */
@Component({
  selector: 'sol-proposal-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, SolBadgeComponent, SolCardComponent, ProposalActionsComponent],
  styleUrls: ['../page-layout.scss', './proposals.scss'],
  template: `
    <sol-card>
      <article class="pp-card" [attr.aria-labelledby]="'pp-' + proposal().id">
        <div class="pp-card__head">
          <a class="pp-card__subject" [id]="'pp-' + proposal().id" [routerLink]="['/intake/proposals', proposal().id]">
            {{ proposal().subject || t('proposals.noSubject') }}
          </a>
          <div class="pp-badges">
            @if (proposal().relation; as relation) {
              <sol-badge [variant]="relationVariant[relation]" size="sm">
                {{ t('proposals.relation.' + relation) }}
              </sol-badge>
            }
            @if (confidence(); as level) {
              <sol-badge [variant]="confidenceVariant[level]" size="sm">
                {{ t('proposals.confidence.' + level) }}
              </sol-badge>
            }
            @if (proposal().status !== 'propuesta') {
              <sol-badge [variant]="statusVariant[proposal().status]" size="sm">
                {{ t('proposals.status.' + proposal().status) }}
              </sol-badge>
            }
          </div>
        </div>

        <p class="pp-meta">
          @if (proposal().result?.solicitante; as who) {
            <span>{{ who }}</span>
            <span aria-hidden="true">·</span>
          }
          <span>{{ date() }}</span>
          <span aria-hidden="true">·</span>
          <span>{{ proposal().message_count === 1 ? t('proposals.messagesOne') : t('proposals.messages', { count: proposal().message_count }) }}</span>
        </p>

        @if (proposal().result?.resumen; as summary) {
          <p class="pp-summary">{{ summary }}</p>
        }

        <p class="pp-task">
          @if (task() || proposal().relation === 'tarea_nueva') {
            <span class="pp-task__label">{{ taskLabel() }}</span>
          }
          @if (task(); as ref) {
            @if (ref.key) {
              <a class="pg-link" [routerLink]="['/task', ref.key]">
                <span class="pp-task__code">{{ ref.ref ?? ref.key }}</span> {{ ref.title }}
              </a>
            } @else {
              <span><span class="pp-task__code">{{ ref.ref ?? '' }}</span> {{ ref.title }}</span>
            }
          } @else if (proposal().relation === 'tarea_nueva' && proposal().result?.accion) {
            <span>«{{ proposal().result?.accion }}»</span>
          } @else {
            <span class="pg-small">{{ t('proposals.task.none') }}</span>
          }
        </p>

        @if (proposal().classification_error; as code) {
          <p class="pp-warning" role="note">{{ t('proposals.classificationError', { code }) }}</p>
        }

        @if (proposal().status === 'propuesta') {
          <sol-proposal-actions [proposal]="proposal()" [task]="task()" (decided)="decided.emit($event)" />
        }
      </article>
    </sol-card>
  `,
})
export class ProposalCardComponent {
  private readonly i18n = inject(I18nService);

  readonly proposal = input.required<IntakeProposal>();
  readonly task = input<ProposalTaskRef | null>(null);
  readonly decided = output<IntakeProposal | null>();

  protected readonly relationVariant = RELATION_VARIANT;
  protected readonly confidenceVariant = CONFIDENCE_VARIANT;
  protected readonly statusVariant = STATUS_VARIANT;

  protected readonly confidence = computed(() => confidenceLevel(this.proposal().confidence));
  protected readonly date = computed(() => formatBogotaDateTime(this.proposal().last_message_at));
  protected readonly taskLabel = computed(() => {
    const proposal = this.proposal();
    if (proposal.created_task_id) {
      return this.t('proposals.task.created');
    }
    if (proposal.status === 'aceptada') {
      return this.t('proposals.task.linked');
    }
    return proposal.relation === 'tarea_nueva' && !proposal.task_id
      ? this.t('proposals.task.new')
      : this.t('proposals.task.proposed');
  });

  protected t(key: string, params?: Record<string, unknown>): string {
    return this.i18n.translate(key, params);
  }
}
