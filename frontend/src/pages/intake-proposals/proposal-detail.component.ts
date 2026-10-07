import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { SolBadgeComponent, SolButtonComponent, SolCardComponent, SolSkeletonComponent } from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { readApiError } from '@shared/lib/api-error';
import { formatBogotaDateTime, formatIsoDay } from '@shared/lib/utils/bogota-date.util';
import { IntakeProposalsService } from '@entities/intake-proposal/intake-proposals.service';
import { IntakeProposal, confidenceLevel } from '@entities/intake-proposal/intake-proposal.model';
import { ProposalActionsComponent } from './proposal-actions.component';
import { ProposalTaskResolver } from './proposal-task-resolver';
import { CONFIDENCE_VARIANT, RELATION_VARIANT, STATUS_VARIANT } from './proposal-labels';

/**
 * `/intake/proposals/:id` — detalle de una propuesta (el comentario que deja «Aceptar» en la
 * tarea enlaza aquí). Muestra todo lo que el clasificador vio y decidió, y las mismas acciones
 * de la bandeja mientras siga abierta.
 */
@Component({
  selector: 'sol-proposal-detail-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [ProposalTaskResolver],
  imports: [
    RouterLink,
    SolBadgeComponent,
    SolButtonComponent,
    SolCardComponent,
    SolSkeletonComponent,
    ProposalActionsComponent,
  ],
  styleUrls: ['../page-layout.scss', './proposals.scss'],
  template: `
    <section class="pg-page">
      <a class="pg-link pp-back" routerLink="/intake/proposals">← {{ t('proposals.detail.back') }}</a>

      @if (loading()) {
        <div role="status" aria-live="polite" [attr.aria-label]="t('proposals.loading')">
          <sol-skeleton variant="title" />
          <sol-skeleton variant="card" [count]="2" />
        </div>
      } @else if (loadError(); as message) {
        <div class="pg-alert" role="alert">
          <span>{{ message }}</span>
          @if (canRetry()) {
            <sol-button type="button" variant="secondary" size="sm" (clicked)="load()">
              {{ t('proposals.retry') }}
            </sol-button>
          }
        </div>
      } @else if (proposal(); as p) {
        <header class="pg-header">
          <div class="pg-header__text">
            <p class="pg-small">{{ t('proposals.thread.' + p.thread_state) }}</p>
            <h1 class="pg-title sol-display pp-detail__title">{{ p.subject || t('proposals.noSubject') }}</h1>
            <div class="pp-badges">
              <sol-badge [variant]="statusVariant[p.status]" size="sm">{{ t('proposals.status.' + p.status) }}</sol-badge>
              @if (p.relation; as relation) {
                <sol-badge [variant]="relationVariant[relation]" size="sm">{{ t('proposals.relation.' + relation) }}</sol-badge>
              }
              @if (confidence(); as level) {
                <sol-badge [variant]="confidenceVariant[level]" size="sm">
                  {{ t('proposals.confidence.' + level) }} · {{ percent(p.confidence) }}
                </sol-badge>
              }
            </div>
          </div>
        </header>

        @if (p.classification_error; as code) {
          <p class="pp-warning" role="note">{{ t('proposals.classificationError', { code }) }}</p>
        }

        <sol-card>
          <dl class="pp-facts">
            <div><dt>{{ t('proposals.detail.requester') }}</dt><dd>{{ p.result?.solicitante || '—' }}</dd></div>
            <div><dt>{{ t('proposals.detail.lastMessage') }}</dt><dd>{{ date(p.last_message_at) }}</dd></div>
            <div><dt>{{ t('proposals.detail.messages') }}</dt><dd>{{ p.message_count }}</dd></div>
            <div>
              <dt>{{ t('proposals.detail.attended') }}</dt>
              <dd>{{ p.result?.atendida ? t('proposals.attended.' + p.result?.atendida) : '—' }}</dd>
            </div>
            <div><dt>{{ t('proposals.detail.due') }}</dt><dd>{{ p.result?.fecha_limite ? day(p.result?.fecha_limite) : '—' }}</dd></div>
            <div><dt>{{ t('proposals.detail.model') }}</dt><dd class="pg-mono">{{ p.model || '—' }}</dd></div>
          </dl>
        </sol-card>

        <sol-card>
          <div class="pp-block">
            <h2 class="pg-subtitle">{{ t('proposals.detail.summary') }}</h2>
            <p class="pp-text">{{ p.result?.resumen || t('proposals.detail.noSummary') }}</p>
            @if (p.result?.accion; as action) {
              <h3 class="pp-block__label">{{ t('proposals.detail.action') }}</h3>
              <p class="pp-text">{{ action }}</p>
            }
            @if (p.result?.motivo; as reason) {
              <h3 class="pp-block__label">{{ t('proposals.detail.reason') }}</h3>
              <p class="pp-text">{{ reason }}</p>
            }
          </div>
        </sol-card>

        <sol-card>
          <div class="pp-block">
            <h2 class="pg-subtitle">{{ t('proposals.detail.task') }}</h2>
            @if (task(); as ref) {
              @if (ref.key) {
                <a class="pg-link" [routerLink]="['/task', ref.key]">
                  <span class="pp-task__code">{{ ref.ref ?? ref.key }}</span> {{ ref.title }}
                </a>
              } @else {
                <p class="pp-text"><span class="pp-task__code">{{ ref.ref ?? '' }}</span> {{ ref.title }}</p>
              }
            } @else {
              <p class="pp-text">{{ t('proposals.task.none') }}</p>
            }
            @if (p.result?.degradada) {
              <p class="pg-small">{{ t('proposals.detail.degraded', { ref: p.result?.task_ref ?? '—' }) }}</p>
            }

            @if (p.candidates.length > 0) {
              <h3 class="pp-block__label">{{ t('proposals.detail.candidates') }}</h3>
              <ul class="pg-list">
                @for (c of p.candidates; track c.task_id) {
                  <li class="pp-candidate">
                    <span class="pp-task__code">{{ c.ref }}</span>
                    <span class="pg-grow">{{ c.title }}</span>
                    <span class="pg-small">{{ t('proposals.via.' + c.via) }} · {{ percent(c.score) }}</span>
                  </li>
                }
              </ul>
            }
          </div>
        </sol-card>

        @if (p.status === 'propuesta') {
          <sol-card>
            <sol-proposal-actions [proposal]="p" [task]="task()" (decided)="onDecided($event)" />
          </sol-card>
        } @else if (p.decided_at) {
          <p class="pg-small">{{ t('proposals.detail.decidedAt', { date: date(p.decided_at) }) }}</p>
        }
      }
    </section>
  `,
})
export class ProposalDetailComponent implements OnInit {
  private readonly service = inject(IntakeProposalsService);
  private readonly resolver = inject(ProposalTaskResolver);
  private readonly i18n = inject(I18nService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly relationVariant = RELATION_VARIANT;
  protected readonly confidenceVariant = CONFIDENCE_VARIANT;
  protected readonly statusVariant = STATUS_VARIANT;

  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);
  protected readonly canRetry = signal(true);
  protected readonly proposal = signal<IntakeProposal | null>(null);
  private id = '';
  private sub: Subscription | null = null;

  protected readonly confidence = computed(() => confidenceLevel(this.proposal()?.confidence));
  protected readonly task = computed(() => {
    this.resolver.refs();
    const proposal = this.proposal();
    return proposal ? this.resolver.refFor(proposal) : null;
  });

  ngOnInit(): void {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      this.id = params.get('id') ?? '';
      this.load();
    });
  }

  protected t(key: string, params?: Record<string, unknown>): string {
    return this.i18n.translate(key, params);
  }

  protected date(value: string | null | undefined): string {
    return formatBogotaDateTime(value);
  }

  protected day(value: string | null | undefined): string {
    return formatIsoDay(value);
  }

  protected percent(value: number | null | undefined): string {
    return value === null || value === undefined ? '—' : `${Math.round(value * 100)} %`;
  }

  protected onDecided(updated: IntakeProposal | null): void {
    if (updated) {
      this.resolver.forget(updated.task_id);
      this.proposal.set(updated);
      this.resolver.resolve([updated]);
    } else {
      this.load();
    }
  }

  protected load(): void {
    this.sub?.unsubscribe();
    this.loading.set(true);
    this.loadError.set(null);
    this.sub = this.service.get(this.id).subscribe({
      next: (res) => {
        this.proposal.set(res.data);
        this.resolver.resolve([res.data]);
        this.loading.set(false);
      },
      error: (err) => {
        const api = readApiError(err);
        this.loading.set(false);
        this.canRetry.set(![403, 404, 422].includes(api.status));
        this.loadError.set(
          api.status === 404 || api.status === 422
            ? this.t('proposals.errors.notFound')
            : api.status === 403
              ? this.t('proposals.errors.forbidden')
              : api.status === 0
                ? this.t('proposals.errors.network')
                : this.t('proposals.errors.load'),
        );
      },
    });
  }
}
