import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import {
  SolBadgeComponent,
  SolButtonComponent,
  SolCardComponent,
  SolConfirmDialogComponent,
  SolEmptyStateComponent,
  SolPaginationComponent,
  SolSkeletonComponent,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { AlertService } from '@shared/lib/alerts';
import { readApiError } from '@shared/lib/api-error';
import {
  bogotaDayKey,
  formatBogotaDateTime,
  formatBogotaTime,
} from '@shared/lib/utils/bogota-date.util';
import { ActiveRoleService } from '@features/organizations/active-role.service';
import { SyncRunsService } from '@entities/sync-run/sync-runs.service';
import { SYNC_SCHEDULE, SyncRun, SyncStep, nextSyncRuns } from '@entities/sync-run/sync-run.model';

type Variant = 'success' | 'warning' | 'danger' | 'info' | 'neutral';

const PAGE_SIZE = 10;
const RUN_VARIANT: Record<string, Variant> = { success: 'success', partial: 'warning', failed: 'danger' };
const STEP_VARIANT: Record<string, Variant> = { ok: 'success', error: 'danger', skipped: 'neutral' };
/** Conteos que se muestran por paso, en este orden; el resto se muestra con su clave. */
const COUNT_ORDER = [
  'created',
  'updated',
  'unchanged',
  'accounts',
  'items_fetched',
  'items_new',
  'items_duplicated',
  'items_converted',
  'errored',
  'processed',
  'classified',
  'key_candidates',
  'thread_errors',
  'since',
  'llm_error',
  'embedding_error',
];

interface CountChip {
  key: string;
  label: string;
  value: string;
}

/**
 * `/sync` «Sincronización» (C06): cuándo corre sola, qué hizo cada corrida (checklist → correo →
 * clasificación, con conteos y errores legibles) y «Ejecutar ahora» para admin. El API no expone
 * el horario: se muestra el configurado por defecto en el servidor (`SYNC_SCHEDULE`).
 */
@Component({
  selector: 'sol-sync-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    SolBadgeComponent,
    SolButtonComponent,
    SolCardComponent,
    SolConfirmDialogComponent,
    SolEmptyStateComponent,
    SolPaginationComponent,
    SolSkeletonComponent,
  ],
  styleUrls: ['../page-layout.scss', './sync.component.scss'],
  template: `
    <section class="pg-page">
      <header class="pg-header">
        <div class="pg-header__text">
          <h1 class="pg-title sol-display">{{ t('syncRuns.title') }}</h1>
          <p class="pg-muted">{{ t('syncRuns.subtitle') }}</p>
        </div>
        @if (roles.isAdmin()) {
          <sol-button type="button" variant="primary" [loading]="running()" [disabled]="running()" (clicked)="confirmOpen.set(true)">
            {{ running() ? t('syncRuns.run.running') : t('syncRuns.run.action') }}
          </sol-button>
        }
      </header>

      @if (running()) {
        <p class="sy-banner" role="status">{{ t('syncRuns.run.wait') }}</p>
      }
      @if (runNotice(); as notice) {
        <div class="sy-notice" [class.sy-notice--warning]="notice.kind === 'warning'" role="alert">
          <span>{{ notice.message }}</span>
          <sol-button type="button" variant="ghost" size="sm" (clicked)="runNotice.set(null)">
            {{ t('syncRuns.run.close') }}
          </sol-button>
        </div>
      }

      <!-- Próximas ejecuciones -->
      <sol-card>
        <div class="sy-next">
          <h2 class="pg-subtitle">{{ t('syncRuns.next.title') }}</h2>
          <ul class="sy-next__list">
            @for (item of nextRuns(); track item.at) {
              <li class="sy-next__item">
                <span class="sy-next__when">{{ item.day }}</span>
                <span class="sy-next__time">{{ item.time }}</span>
              </li>
            }
          </ul>
          <p class="pg-small">{{ t('syncRuns.next.configured', { times: scheduleTimes, zone: t('syncRuns.next.zone') }) }}</p>
          @if (!loading() && !loadError()) {
            <p class="pg-small">
              @if (lastScheduled(); as last) {
                {{ t('syncRuns.next.lastScheduled', { date: date(last.started_at), status: t('syncRuns.status.' + last.status) }) }}
              } @else {
                {{ t('syncRuns.next.noScheduled') }}
              }
            </p>
          }
        </div>
      </sol-card>

      <h2 class="pg-subtitle">{{ t('syncRuns.history.title') }}</h2>

      @if (loading()) {
        <div role="status" aria-live="polite" [attr.aria-label]="t('syncRuns.loading')">
          <sol-skeleton variant="card" [count]="3" />
        </div>
      } @else if (loadError(); as message) {
        <div class="pg-alert" role="alert">
          <span>{{ message }}</span>
          @if (canRetry()) {
            <sol-button type="button" variant="secondary" size="sm" (clicked)="load()">
              {{ t('syncRuns.retry') }}
            </sol-button>
          } @else {
            <a class="pg-link" routerLink="/projects">{{ t('syncRuns.goHome') }}</a>
          }
        </div>
      } @else if (runs().length === 0) {
        <sol-empty-state icon="refresh" titleKey="syncRuns.empty.title" descriptionKey="syncRuns.empty.description" />
      } @else {
        <div class="sy-runs">
          @for (run of runs(); track run.started_at) {
            <sol-card>
              <article class="sy-run">
                <div class="sy-run__head">
                  <sol-badge [variant]="runVariant(run.status)" size="sm">{{ label('syncRuns.status.', run.status) }}</sol-badge>
                  <span class="sy-run__date">{{ date(run.started_at) }}</span>
                  <span class="pg-small">{{ label('syncRuns.trigger.', run.trigger) }} · {{ duration(run) }}</span>
                </div>
                <ol class="sy-steps">
                  @for (step of run.steps; track step.name) {
                    <li class="sy-step">
                      <div class="sy-step__head">
                        <span class="sy-step__name">{{ label('syncRuns.steps.', step.name) }}</span>
                        <sol-badge [variant]="stepVariant(step.status)" size="sm">{{ label('syncRuns.stepStatus.', step.status) }}</sol-badge>
                      </div>
                      @if (chips(step); as list) {
                        @if (list.length > 0) {
                          <ul class="sy-chips">
                            @for (chip of list; track chip.key) {
                              <li class="sy-chip"><span>{{ chip.label }}</span> <strong>{{ chip.value }}</strong></li>
                            }
                          </ul>
                        }
                      }
                      @if (step.error?.detail; as detail) {
                        <p class="sy-step__error">{{ detail }}</p>
                      } @else if (step.detail) {
                        <p class="pg-small">{{ step.detail }}</p>
                      }
                    </li>
                  }
                </ol>
              </article>
            </sol-card>
          }
        </div>
        @if (total() > pageSize) {
          <sol-pagination
            [totalItems]="total()"
            [pageSize]="pageSize"
            [currentPage]="page()"
            [pageSizeOptions]="[pageSize]"
            (pageChanged)="goToPage($event)"
          />
        }
      }
    </section>

    <sol-confirm-dialog
      [open]="confirmOpen()"
      variant="info"
      [title]="t('syncRuns.run.confirmTitle')"
      [message]="t('syncRuns.run.confirmMessage')"
      [confirmLabel]="t('syncRuns.run.action')"
      [cancelLabel]="t('syncRuns.run.cancel')"
      (confirm)="runNow()"
      (cancel)="confirmOpen.set(false)"
    />
  `,
})
export class SyncComponent implements OnInit {
  private readonly service = inject(SyncRunsService);
  private readonly i18n = inject(I18nService);
  private readonly alerts = inject(AlertService);
  protected readonly roles = inject(ActiveRoleService);

  protected readonly pageSize = PAGE_SIZE;
  protected readonly scheduleTimes = SYNC_SCHEDULE.times.join(' y ');

  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);
  protected readonly canRetry = signal(true);
  protected readonly runs = signal<SyncRun[]>([]);
  protected readonly total = signal(0);
  protected readonly page = signal(1);
  protected readonly running = signal(false);
  protected readonly confirmOpen = signal(false);
  protected readonly runNotice = signal<{ kind: 'warning' | 'error'; message: string } | null>(null);
  private readonly now = signal(new Date());
  private sub: Subscription | null = null;

  protected readonly nextRuns = computed(() => {
    const now = this.now();
    const today = bogotaDayKey(now);
    const tomorrow = bogotaDayKey(new Date(now.getTime() + 86_400_000));
    return nextSyncRuns(now, 2).map((at) => {
      const key = bogotaDayKey(at);
      return {
        at: at.toISOString(),
        day:
          key === today
            ? this.t('syncRuns.next.today')
            : key === tomorrow
              ? this.t('syncRuns.next.tomorrow')
              : formatBogotaDateTime(at),
        time: formatBogotaTime(at),
      };
    });
  });

  protected readonly lastScheduled = computed(
    () => this.runs().find((run) => run.trigger === 'scheduled') ?? null,
  );

  ngOnInit(): void {
    this.roles.ensureLoaded();
    this.load();
  }

  protected t(key: string, params?: Record<string, unknown>): string {
    return this.i18n.translate(key, params);
  }

  /** Etiqueta traducida o, si el backend trae un valor nuevo, el valor tal cual. */
  protected label(prefix: string, value: string): string {
    const key = `${prefix}${value}`;
    const text = this.i18n.translate(key);
    return text === key ? value : text;
  }

  protected date(value: string): string {
    return formatBogotaDateTime(value);
  }

  protected runVariant(status: string): Variant {
    return RUN_VARIANT[status] ?? 'neutral';
  }

  protected stepVariant(status: string): Variant {
    return STEP_VARIANT[status] ?? 'neutral';
  }

  protected duration(run: SyncRun): string {
    const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
    if (!Number.isFinite(ms) || ms < 0) {
      return '—';
    }
    const seconds = Math.round(ms / 1000);
    if (seconds < 60) {
      return this.t('syncRuns.duration.seconds', { s: seconds });
    }
    return this.t('syncRuns.duration.minutes', { m: Math.floor(seconds / 60), s: seconds % 60 });
  }

  protected chips(step: SyncStep): CountChip[] {
    const counts = step.counts ?? {};
    const keys = Object.keys(counts).sort((a, b) => {
      const ia = COUNT_ORDER.indexOf(a);
      const ib = COUNT_ORDER.indexOf(b);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });
    const chips: CountChip[] = [];
    for (const key of keys) {
      const raw = counts[key];
      if (raw === null || raw === undefined || raw === '') {
        continue;
      }
      const value =
        key === 'since' && typeof raw === 'string' ? formatBogotaDateTime(raw) : String(raw);
      chips.push({ key, label: this.label('syncRuns.counts.', key), value });
    }
    return chips;
  }

  protected goToPage(page: number): void {
    this.page.set(page);
    this.load();
  }

  protected load(): void {
    this.sub?.unsubscribe();
    this.loading.set(true);
    this.loadError.set(null);
    this.now.set(new Date());
    this.sub = this.service.list(this.page(), PAGE_SIZE).subscribe({
      next: (res) => {
        this.runs.set(res.data ?? []);
        this.total.set(res.meta?.total ?? 0);
        this.loading.set(false);
      },
      error: (err) => {
        const api = readApiError(err);
        this.loading.set(false);
        this.canRetry.set(api.status !== 403);
        this.loadError.set(
          api.status === 403
            ? this.t('syncRuns.errors.forbidden')
            : api.status === 0
              ? this.t('syncRuns.errors.network')
              : this.t('syncRuns.errors.load'),
        );
      },
    });
  }

  protected runNow(): void {
    this.confirmOpen.set(false);
    this.runNotice.set(null);
    this.running.set(true);
    this.service.runNow().subscribe({
      next: (res) => {
        this.running.set(false);
        const status = this.label('syncRuns.status.', res.data.status);
        if (res.data.status === 'success') {
          this.alerts.showSuccess(this.t('syncRuns.run.done', { status }));
        } else {
          this.runNotice.set({ kind: 'warning', message: this.t('syncRuns.run.doneWithErrors', { status }) });
        }
        this.page.set(1);
        this.load();
      },
      error: (err) => {
        this.running.set(false);
        const api = readApiError(err);
        if (api.status === 409) {
          this.runNotice.set({
            kind: 'warning',
            message: api.detail ?? this.t('syncRuns.run.alreadyRunning'),
          });
          return;
        }
        this.runNotice.set({
          kind: 'error',
          message:
            api.status === 0
              ? this.t('syncRuns.errors.network')
              : api.status === 403
                ? this.t('syncRuns.errors.forbidden')
                : (api.detail ?? this.t('syncRuns.errors.run')),
        });
      },
    });
  }
}
