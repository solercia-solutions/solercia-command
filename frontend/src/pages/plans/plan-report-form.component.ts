import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { SolButtonComponent, SolFormFieldComponent } from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { readApiError } from '@shared/lib/api-error';
import { PlansService } from '@entities/plan/plans.service';
import { PlanActivityReport, ReportPeriod } from '@entities/plan/plan.model';
import {
  TriState,
  checkProgress,
  fromTriState,
  parseEvidence,
  parseProgress,
  toNumber,
  toTriState,
} from './plans-view';

const QUICK_VALUES = [0, 25, 50, 75, 100] as const;

/**
 * Self-report of one activity for one period (admin/manager, task N3).
 *
 * `PUT` REPLACES the whole row, so the form always sends the five fields,
 * prefilled from the existing report. Reported progress starts from the best
 * known value (this period's report → previous period → calculated) and the
 * previous-period value and the calculated progress stay visible as reference.
 */
@Component({
  selector: 'sol-plan-report-form',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [SolButtonComponent, SolFormFieldComponent],
  styles: [
    `
      /* Campos con tokens --sol-* (patrón de formulario de PANDORA dentro del drawer). */
      .prf-form {
        display: flex;
        flex-direction: column;
        gap: var(--sol-space-md, 16px);
        padding: var(--sol-space-md, 12px);
        border: 1px solid var(--sol-border-color-default);
        border-radius: var(--sol-border-radius-md, 8px);
      }

      .prf-control {
        min-height: var(--sol-size-control-touch, 44px);
        padding: var(--sol-space-sm, 8px) var(--sol-space-md, 12px);
        border: 1px solid var(--sol-border-color-default);
        border-radius: var(--sol-border-radius-md, 8px);
        background: var(--sol-bg-surface);
        color: var(--sol-color-text-primary);
        font: inherit;
        font-size: var(--sol-font-size-sm, 0.875rem);
      }

      .prf-control:focus-visible {
        outline: 2px solid var(--sol-color-primary);
        outline-offset: 1px;
      }

      .prf-control--invalid {
        border-color: var(--sol-color-danger);
      }

      .prf-control--number {
        width: 6rem;
        text-align: right;
      }

      .prf-row {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: var(--sol-space-sm, 8px);
      }

      .prf-hint {
        margin: 0;
        font-size: var(--sol-font-size-xs, 0.75rem);
        color: var(--sol-color-text-secondary);
      }

      .prf-hint--error {
        color: var(--sol-color-danger);
      }

      .prf-two {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: var(--sol-space-md, 12px);
      }
    `,
  ],
  template: `
    <form class="prf-form" (submit)="save($event)" novalidate>
      <!-- Avance reportado (sol-form-field no asocia su etiqueta: el control lleva aria-label). -->
      <sol-form-field [label]="t('plans.reportForm.progress')">
        <div class="prf-row">
          <div class="prf-row">
            <input
              [id]="inputId"
              type="text"
              inputmode="decimal"
              class="prf-control prf-control--number"
              [class.prf-control--invalid]="progressError() !== null"
              [attr.aria-label]="t('plans.reportForm.progress')"
              [value]="progress()"
              [attr.aria-invalid]="progressError() !== null"
              [attr.aria-describedby]="hintId"
              (input)="progress.set($any($event.target).value)"
            />
            <span class="text-sm text-muted">%</span>
          </div>
          <div class="flex flex-wrap gap-1.5" role="group" [attr.aria-label]="t('plans.reportForm.quick')">
            @for (value of quickValues; track value) {
              <button
                type="button"
                class="min-h-11 min-w-11 rounded-full border px-2.5 text-sm transition-colors"
                [class]="chipClass(parsed() === value)"
                [attr.aria-pressed]="parsed() === value"
                (click)="progress.set('' + value)"
              >
                {{ value }}
              </button>
            }
          </div>
        </div>
        <p [id]="hintId" class="prf-hint" [class.prf-hint--error]="progressError() !== null" aria-live="polite">
          {{ progressError() ?? sourceHint() }}
        </p>

        <!-- Referencias: periodo anterior y calculado -->
        <div class="grid grid-cols-2 gap-2 text-xs">
          <div class="rounded-lg bg-muted/10 px-3 py-2">
            <p class="text-muted">{{ previousTitle() }}</p>
            <p class="font-medium text-text">{{ previousLabel() }}</p>
          </div>
          <div class="flex items-start justify-between gap-2 rounded-lg bg-muted/10 px-3 py-2">
            <div>
              <p class="text-muted">{{ t('plans.progress.calculated') }}</p>
              <p class="font-medium text-text">
                {{ calculatedPercent() === null ? t('plans.progress.noTasks') : calculatedPercent() + '%' }}
              </p>
            </div>
            @if (calculatedPercent() !== null && parsed() !== calculatedPercent()) {
              <button
                type="button"
                class="min-h-11 shrink-0 rounded-full border border-border px-2.5 text-xs text-brand hover:border-brand"
                (click)="progress.set('' + calculatedPercent())"
              >
                {{ t('plans.reportForm.useCalculated') }}
              </button>
            }
          </div>
        </div>
      </sol-form-field>

      <!-- Cumplida / A tiempo -->
      <div class="prf-two">
        @for (field of triFields; track field.key) {
          <sol-form-field [label]="t(field.label)">
            <div class="prf-row" role="radiogroup" [attr.aria-label]="t(field.label)">
              @for (option of triOptions; track option) {
                <button
                  type="button"
                  role="radio"
                  class="min-h-11 rounded-full border px-3 text-sm transition-colors"
                  [class]="chipClass(field.value() === option)"
                  [attr.aria-checked]="field.value() === option"
                  (click)="field.value.set(option)"
                >
                  {{ t('plans.reportForm.tri.' + option) }}
                </button>
              }
            </div>
          </sol-form-field>
        }
      </div>

      <sol-form-field [label]="t('plans.reportForm.summary')">
        <textarea
          [id]="inputId + '-summary'"
          rows="3"
          class="prf-control"
          [attr.aria-label]="t('plans.reportForm.summary')"
          [placeholder]="t('plans.reportForm.summaryPlaceholder')"
          [value]="summary()"
          (input)="summary.set($any($event.target).value)"
        ></textarea>
      </sol-form-field>

      <sol-form-field [label]="t('plans.reportForm.evidence')">
        <textarea
          [id]="inputId + '-evidence'"
          rows="2"
          class="prf-control"
          [attr.aria-label]="t('plans.reportForm.evidence')"
          [placeholder]="t('plans.reportForm.evidencePlaceholder')"
          [value]="evidence()"
          (input)="evidence.set($any($event.target).value)"
        ></textarea>
      </sol-form-field>

      @if (error(); as message) {
        <p role="alert" class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
          {{ message }}
        </p>
      }

      <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p class="text-xs text-muted">
          @if (progressError() !== null) {
            {{ t('plans.reportForm.fixToSave') }}
          } @else if (!dirty() && report()) {
            {{ t('plans.reportForm.noChanges') }}
          } @else if (report()) {
            {{ t('plans.reportForm.willReplace') }}
          } @else {
            {{ t('plans.reportForm.willCreate') }}
          }
        </p>
        <sol-button
          type="submit"
          size="sm"
          [loading]="saving()"
          [disabled]="saving() || progressError() !== null || (!dirty() && !!report())"
        >
          {{ saving() ? t('plans.reportForm.saving') : t('plans.reportForm.save') }}
        </sol-button>
      </div>
    </form>
  `,
})
export class PlanReportFormComponent {
  private readonly plansService = inject(PlansService);
  private readonly i18n = inject(I18nService);
  private readonly destroyRef = inject(DestroyRef);

  readonly activityId = input.required<string>();
  readonly period = input.required<ReportPeriod>();
  /** Report of `period`, if it exists (prefills and becomes "replace"). */
  readonly report = input<PlanActivityReport | null>(null);
  /** Report of the previous period (reference + fallback default). */
  readonly previousReport = input<PlanActivityReport | null>(null);
  readonly previousPeriod = input<ReportPeriod | null>(null);
  readonly calculatedPercent = input<number | null>(null);

  readonly saved = output<PlanActivityReport>();

  protected readonly quickValues = QUICK_VALUES;
  protected readonly triOptions: readonly TriState[] = ['yes', 'no', 'unknown'];
  protected readonly inputId = `plan-report-${Math.random().toString(36).slice(2, 9)}`;
  protected readonly hintId = `${this.inputId}-hint`;

  protected readonly progress = signal('');
  protected readonly summary = signal('');
  protected readonly evidence = signal('');
  protected readonly isMet = signal<TriState>('unknown');
  protected readonly onTime = signal<TriState>('unknown');
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  /** Where the initial progress value came from (shown as hint). */
  private readonly source = signal<'report' | 'previous' | 'calculated' | 'none'>('none');
  private readonly initial = signal('');

  protected readonly triFields = [
    { key: 'met', label: 'plans.report.met', value: this.isMet },
    { key: 'onTime', label: 'plans.report.onTime', value: this.onTime },
  ] as const;

  protected readonly parsed = computed(() => parseProgress(this.progress()));

  protected readonly progressError = computed(() => {
    switch (checkProgress(this.progress())) {
      case 'invalid':
        return this.t('plans.reportForm.errors.notNumber');
      case 'outOfRange':
        return this.t('plans.reportForm.errors.range');
      default:
        return null;
    }
  });

  protected readonly dirty = computed(() => this.snapshot() !== this.initial());

  protected readonly previousTitle = computed(() => {
    const prev = this.previousPeriod();
    return prev
      ? this.t('plans.reportForm.previous', { period: this.t(`plans.periods.${prev}.short`) })
      : this.t('plans.reportForm.previousNone');
  });

  protected readonly previousLabel = computed(() => {
    if (!this.previousPeriod()) {
      return '—';
    }
    const value = toNumber(this.previousReport()?.reported_progress);
    return value === null ? this.t('plans.progress.noReport') : `${Math.round(value)}%`;
  });

  protected readonly sourceHint = computed(() => {
    switch (this.source()) {
      case 'report':
        return this.t('plans.reportForm.source.report');
      case 'previous':
        return this.t('plans.reportForm.source.previous');
      case 'calculated':
        return this.t('plans.reportForm.source.calculated');
      default:
        return this.t('plans.reportForm.source.none');
    }
  });

  constructor() {
    // Reset the form whenever the activity, the period or its report change.
    effect(() => {
      const report = this.report();
      const previous = this.previousReport();
      const calculated = this.calculatedPercent();
      this.activityId();
      this.period();
      untracked(() => this.reset(report, previous, calculated));
    });
  }

  protected t(key: string, params?: Record<string, unknown>): string {
    this.i18n.activeLang();
    return this.i18n.translate(key, params);
  }

  protected chipClass(active: boolean): string {
    return active
      ? 'border-brand bg-brand text-brand-fg'
      : 'border-border bg-surface text-text hover:border-brand';
  }

  protected save(event: Event): void {
    event.preventDefault();
    if (this.saving() || this.progressError() !== null) {
      return;
    }
    this.saving.set(true);
    this.error.set(null);
    this.plansService
      .saveReport(this.activityId(), this.period(), {
        reported_progress: this.parsed(),
        qualitative_summary: this.summary().trim() || null,
        evidence_refs: parseEvidence(this.evidence()),
        is_met: fromTriState(this.isMet()),
        met_on_time: fromTriState(this.onTime()),
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.saving.set(false);
          // The parent reloads and feeds the new report back through `report`.
          this.saved.emit(res.data);
        },
        error: (err: unknown) => {
          this.saving.set(false);
          // What the user typed stays in the form.
          const api = readApiError(err);
          if (api.status === 0) {
            this.error.set(this.t('plans.errors.network'));
          } else if (api.status === 403) {
            this.error.set(this.t('plans.reportForm.errors.forbidden'));
          } else {
            this.error.set(api.detail ?? this.t('plans.reportForm.errors.saveFailed'));
          }
        },
      });
  }

  private reset(
    report: PlanActivityReport | null,
    previous: PlanActivityReport | null,
    calculated: number | null,
  ): void {
    const own = toNumber(report?.reported_progress);
    const prev = toNumber(previous?.reported_progress);
    if (report) {
      this.source.set('report');
      this.progress.set(own === null ? '' : String(own));
    } else if (prev !== null) {
      this.source.set('previous');
      this.progress.set(String(prev));
    } else if (calculated !== null) {
      this.source.set('calculated');
      this.progress.set(String(calculated));
    } else {
      this.source.set('none');
      this.progress.set('');
    }
    this.summary.set(report?.qualitative_summary ?? '');
    this.evidence.set((report?.evidence_refs ?? []).join('\n'));
    this.isMet.set(toTriState(report?.is_met));
    this.onTime.set(toTriState(report?.met_on_time));
    this.error.set(null);
    this.initial.set(this.snapshot());
  }

  private snapshot(): string {
    return JSON.stringify([
      this.parsed(),
      this.summary().trim(),
      parseEvidence(this.evidence()),
      this.isMet(),
      this.onTime(),
    ]);
  }
}
