import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  TemplateRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { toSignal } from '@angular/core/rxjs-interop';
import {
  DataTableColumn,
  SolAvatarComponent,
  SolBadgeComponent,
  SolButtonComponent,
  SolCardComponent,
  SolDataTableComponent,
  SolEmptyStateComponent,
  SolProgressBarComponent,
  SolSelectComponent,
  SolSelectOption,
  SolSkeletonComponent,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { PerformanceService } from '@entities/performance/performance.service';
import { PerfCollaborator, PerformanceData } from '@entities/performance/performance.model';

type PerfFilter = 'all' | 'overdue' | 'active' | 'delivered';

/**
 * «Rendimiento» con el patrón de listado de PANDORA: encabezado `h1.sol-display`, totales del
 * equipo en `sol-card` y una fila por colaborador en `sol-data-table` (ordenable y con búsqueda),
 * con el cumplimiento a tiempo en `sol-progress-bar`. El API no filtra por año: solo por sprint.
 */
@Component({
  selector: 'sol-performance',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    SolAvatarComponent,
    SolBadgeComponent,
    SolButtonComponent,
    SolCardComponent,
    SolDataTableComponent,
    SolEmptyStateComponent,
    SolProgressBarComponent,
    SolSelectComponent,
    SolSkeletonComponent,
  ],
  styleUrl: '../page-layout.scss',
  styles: [
    `
      .pf-ontime {
        min-width: 140px;
      }
    `,
  ],
  template: `
    <section class="pg-page">
      <header class="pg-header">
        <div class="pg-header__text">
          <h1 class="pg-title sol-display">{{ text.title() }}</h1>
          <p class="pg-muted">{{ text.subtitle() }}</p>
        </div>
        @if (generatedAt()) {
          <p class="pg-small">{{ text.updatedAt() }} {{ generatedAt() }}</p>
        }
      </header>

      @if (loading()) {
        <div class="pg-section" role="status" aria-live="polite" [attr.aria-label]="text.loading()">
          <div class="pg-kpis"><sol-skeleton variant="stat" [count]="4" /></div>
          <sol-skeleton variant="row" [count]="6" />
        </div>
      } @else if (loadError(); as message) {
        <div class="pg-alert" role="alert">
          <span>{{ message }}</span>
          <sol-button type="button" variant="secondary" size="sm" (clicked)="load()">
            {{ text.retry() }}
          </sol-button>
        </div>
      } @else if (collaborators().length === 0) {
        <sol-empty-state
          icon="users"
          titleKey="performance.empty"
          descriptionKey="performance.emptyHint"
        />
      } @else {
        <div class="pg-kpis">
          <sol-card>
            <p class="pg-kpi__label">{{ text.completedTasks() }}</p>
            <p class="pg-kpi__value">{{ totals().completed }}</p>
          </sol-card>
          <sol-card>
            <p class="pg-kpi__label">{{ text.completedPoints() }}</p>
            <p class="pg-kpi__value">{{ totals().points }}</p>
          </sol-card>
          <sol-card>
            <p class="pg-kpi__label">{{ text.active() }}</p>
            <p class="pg-kpi__value">{{ totals().active }}</p>
          </sol-card>
          <sol-card>
            <p class="pg-kpi__label">{{ text.overdue() }}</p>
            <p class="pg-kpi__value" [class.pg-kpi__value--danger]="totals().overdue > 0">
              {{ totals().overdue }}
            </p>
          </sol-card>
        </div>

        <sol-data-table
          [data]="rows()"
          [columns]="columns()"
          [searchPlaceholder]="text.search()"
          [emptyMessage]="filter() === 'all' ? text.noSearchMatches() : text.noFilterMatches()"
          [paginated]="true"
          [showActions]="false"
          [collapseWidth]="760"
          trackByKey="id"
        >
          <div tableActions class="pg-filters">
            <sol-select
              class="pg-filter"
              [label]="text.show()"
              [options]="filterOptions()"
              [formControl]="filterControl"
            />
            @if (filter() !== 'all') {
              <sol-button type="button" variant="ghost" size="sm" (clicked)="filterControl.setValue('all')">
                {{ text.clearFilters() }}
              </sol-button>
            }
          </div>
        </sol-data-table>
      }
    </section>

    <ng-template #personCell let-row="row">
      <div class="pg-row">
        <sol-avatar [name]="$any(row).name" size="sm" />
        <span>{{ $any(row).name }}</span>
      </div>
    </ng-template>
    <ng-template #overdueCell let-row="row">
      @if ($any(row).overdue > 0) {
        <sol-badge variant="danger">{{ $any(row).overdue }}</sol-badge>
      } @else {
        <span>0</span>
      }
    </ng-template>
    <ng-template #onTimeCell let-row="row">
      @if ($any(row).on_time === null) {
        <span class="pg-small">{{ text.noData() }}</span>
      } @else {
        <div class="pf-ontime">
          <sol-progress-bar
            [value]="$any(row).on_time"
            [variant]="$any(row).on_time_variant"
            [showLabel]="true"
            [ariaLabel]="onTimeAria($any(row).name, $any(row).on_time)"
          />
        </div>
      }
    </ng-template>
  `,
})
export class PerformanceComponent implements OnInit {
  private readonly performanceService = inject(PerformanceService);
  private readonly i18n = inject(I18nService);

  /** Textos estáticos de la vista resueltos por i18n (reactivos al idioma). */
  protected readonly text = {
    title: this.i18n.t('performance.title'),
    subtitle: this.i18n.t('performance.subtitle'),
    loading: this.i18n.t('performance.loading'),
    retry: this.i18n.t('performance.retry'),
    search: this.i18n.t('performance.search'),
    show: this.i18n.t('performance.filter.label'),
    clearFilters: this.i18n.t('performance.filter.clear'),
    noSearchMatches: this.i18n.t('performance.noSearchMatches'),
    noFilterMatches: this.i18n.t('performance.noFilterMatches'),
    completedTasks: this.i18n.t('performance.metrics.completedTasks'),
    completedPoints: this.i18n.t('performance.metrics.completedPoints'),
    active: this.i18n.t('performance.metrics.active'),
    overdue: this.i18n.t('performance.metrics.overdue'),
    onTimeBar: this.i18n.t('performance.bars.onTime'),
    person: this.i18n.t('performance.columns.person'),
    noData: this.i18n.t('performance.states.noData'),
    updatedAt: this.i18n.t('performance.updatedAt'),
  } as const;

  protected readonly data = signal<PerformanceData | null>(null);
  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);

  protected readonly filterControl = new FormControl<PerfFilter>('all', { nonNullable: true });
  protected readonly filter = toSignal(this.filterControl.valueChanges, {
    initialValue: 'all' as PerfFilter,
  });

  protected readonly collaborators = computed<PerfCollaborator[]>(
    () => this.data()?.collaborators ?? [],
  );

  protected readonly totals = computed(() =>
    this.collaborators().reduce(
      (acc, p) => ({
        completed: acc.completed + p.completed_tasks,
        points: acc.points + p.completed_points,
        active: acc.active + p.active_count,
        overdue: acc.overdue + p.overdue_count,
      }),
      { completed: 0, points: 0, active: 0, overdue: 0 },
    ),
  );

  /** Opciones con su conteo real, para que la persona sepa qué va a encontrar. */
  protected readonly filterOptions = computed<SolSelectOption[]>(() => {
    const people = this.collaborators();
    const count = (f: PerfFilter) => people.filter(p => this.matches(p, f)).length;
    return (['all', 'overdue', 'active', 'delivered'] as const).map(f => ({
      value: f,
      label: this.i18n.translate(`performance.filter.${f}`, { count: count(f) }),
    }));
  });

  protected readonly rows = computed<Record<string, unknown>[]>(() =>
    this.collaborators()
      .filter(p => this.matches(p, this.filter()))
      .map(p => {
        const onTime =
          p.on_time_rate === null || p.on_time_rate === undefined
            ? null
            : Math.round(p.on_time_rate * 100);
        return {
          id: p.user.id,
          name: p.user.full_name,
          completed: p.completed_tasks,
          points: p.completed_points,
          active: p.active_count,
          overdue: p.overdue_count,
          on_time: onTime,
          on_time_variant:
            onTime === null ? 'primary' : onTime >= 80 ? 'success' : onTime >= 50 ? 'warning' : 'danger',
        };
      }),
  );

  private readonly personTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('personCell');
  private readonly overdueTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('overdueCell');
  private readonly onTimeTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('onTimeCell');

  protected readonly columns = computed<DataTableColumn[]>(() => [
    { key: 'name', label: this.text.person(), sortable: true, cellTemplate: this.personTpl() },
    { key: 'completed', label: this.text.completedTasks(), sortable: true },
    { key: 'points', label: this.text.completedPoints(), sortable: true },
    { key: 'active', label: this.text.active(), sortable: true },
    { key: 'overdue', label: this.text.overdue(), sortable: true, cellTemplate: this.overdueTpl() },
    { key: 'on_time', label: this.text.onTimeBar(), sortable: true, cellTemplate: this.onTimeTpl() },
  ]);

  ngOnInit(): void {
    this.load();
  }

  private matches(person: PerfCollaborator, filter: PerfFilter): boolean {
    switch (filter) {
      case 'overdue':
        return person.overdue_count > 0;
      case 'active':
        return person.active_count > 0;
      case 'delivered':
        return person.completed_tasks > 0;
      default:
        return true;
    }
  }

  protected onTimeAria(name: string, percent: number): string {
    return this.i18n.translate('performance.aria.onTimePerson', { name, n: percent });
  }

  protected generatedAt(): string {
    const value = this.data()?.generated_at;
    if (!value) {
      return '';
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return '';
    }
    return date.toLocaleString('es-CO', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  protected load(): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.performanceService.performance().subscribe({
      next: (res) => {
        this.data.set(res.data);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.loadError.set(
          err.status === 0
            ? this.i18n.translate('performance.errors.network')
            : this.i18n.translate('performance.errors.loadFailed'),
        );
      },
    });
  }
}
