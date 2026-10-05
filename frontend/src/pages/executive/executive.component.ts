import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  OnDestroy,
  TemplateRef,
  effect,
  untracked,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subscription } from 'rxjs';
import { AuthService } from '@features/auth/auth.service';
import { ActiveOrgStore } from '@features/organizations/active-org.store';
import { HttpErrorResponse } from '@angular/common/http';
import {
  DataTableColumn,
  SolAvatarComponent,
  SolBadgeComponent,
  SolButtonComponent,
  SolCardComponent,
  SolChartComponent,
  SolChartData,
  SolDataTableComponent,
  SolEmptyStateComponent,
  SolProgressBarComponent,
  SolSelectComponent,
  SolSelectOption,
  SolSkeletonComponent,
  SolTabItem,
  SolTabsComponent,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import {
  PRIORITY_LABELS,
  Priority,
  formatShortDate,
} from '@entities/workspace/workspace.model';
import { METHODOLOGY_LABELS, Methodology } from '@entities/project/project.model';
import { ExecutiveService } from '@entities/executive/executive.service';
import { DailyDashboard, DailyDatePolicy, ExecutiveDashboard } from '@entities/executive/executive.model';

type ExecTab = 'people' | 'risks' | 'projects' | 'daily';

/** Variante de `sol-badge` por prioridad (mismo criterio que la cuadrícula del workspace). */
const PRIORITY_BADGE: Record<Priority, 'danger' | 'warning' | 'info' | 'neutral'> = {
  critical: 'danger',
  high: 'warning',
  medium: 'info',
  low: 'neutral',
};

/** Tareas en curso visibles por persona antes de resumir el resto en «y N más». */
const IN_PROGRESS_PREVIEW = 3;

/**
 * Vista de jefe con el patrón analítico de PANDORA (telemetría): encabezado `h1.sol-display`,
 * indicadores en `sol-card` y una pregunta por pestaña (personas, riesgos, avance y mi resumen)
 * para que todo quepa en una pantalla sin desplazamiento largo.
 */
@Component({
  selector: 'sol-executive',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    SolAvatarComponent,
    SolBadgeComponent,
    SolButtonComponent,
    SolCardComponent,
    SolChartComponent,
    SolDataTableComponent,
    SolEmptyStateComponent,
    SolProgressBarComponent,
    SolSelectComponent,
    SolSkeletonComponent,
    SolTabsComponent,
  ],
  styleUrl: '../page-layout.scss',
  styles: [
    `
      .ex-person__count {
        margin-left: auto;
      }
      .ex-dot {
        width: 6px;
        height: 6px;
        flex: 0 0 6px;
        border-radius: 50%;
        background: var(--sol-color-primary);
      }
      .ex-daily-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: var(--sol-space-md, 16px);
      }
      .ex-daily-group {
        min-width: 0;
        padding: var(--sol-space-sm, 8px) var(--sol-space-md, 16px);
        border: 1px solid var(--sol-border-color-default, #e5e7eb);
        border-radius: var(--sol-border-radius-md, 8px);
      }
      .pg-filter.ex-wide {
        flex-basis: 340px;
        max-width: none;
      }
      .ex-progress {
        min-width: 140px;
      }
      @media (max-width: 760px) {
        .ex-daily-grid {
          grid-template-columns: 1fr;
        }
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
      </header>

      @if (loading()) {
        <div class="pg-section" role="status" aria-live="polite" [attr.aria-label]="text.loading()">
          <div class="pg-kpis">
            <sol-skeleton variant="stat" [count]="4" />
          </div>
          <sol-skeleton variant="card" />
        </div>
      } @else if (loadError(); as message) {
        <div class="pg-alert" role="alert">
          <span>{{ message }}</span>
          <sol-button type="button" variant="secondary" size="sm" (clicked)="load()">
            {{ text.retry() }}
          </sol-button>
        </div>
      } @else if (data(); as dash) {
        <div class="pg-kpis">
          <sol-card>
            <p class="pg-kpi__label">{{ text.totalProjects() }}</p>
            <p class="pg-kpi__value">{{ dash.totals.projects }}</p>
          </sol-card>
          <sol-card>
            <p class="pg-kpi__label">{{ text.totalTasks() }}</p>
            <p class="pg-kpi__value">{{ dash.totals.tasks }}</p>
          </sol-card>
          <sol-card>
            <p class="pg-kpi__label">{{ text.totalOverdue() }}</p>
            <p class="pg-kpi__value" [class.pg-kpi__value--danger]="dash.totals.overdue > 0">
              {{ dash.totals.overdue }}
            </p>
          </sol-card>
          <sol-card>
            <p class="pg-kpi__label">{{ text.totalAtRisk() }}</p>
            <p class="pg-kpi__value" [class.pg-kpi__value--warning]="dash.totals.at_risk > 0">
              {{ dash.totals.at_risk }}
            </p>
          </sol-card>
        </div>

        <sol-tabs [tabs]="tabs()" [activeTab]="tab()" (tabChange)="selectTab($event)" />

        @switch (tab()) {
          @case ('people') {
            <div class="pg-section">
              <h2 class="pg-subtitle">{{ text.workloadTitle() }}</h2>
              <sol-card>
                @if (busyPeople().length === 0) {
                  <p class="pg-state">{{ text.workloadEmpty() }}</p>
                } @else {
                  <sol-chart
                    type="bar"
                    [data]="workloadChart()"
                    [options]="{ legend: false }"
                    ariaLabelKey="executive.workload.chartAria"
                    height="260px"
                  />
                  @if (idleCount() > 0) {
                    <p class="pg-small">{{ idleLabel(idleCount()) }}</p>
                  }
                }
              </sol-card>
            </div>
            <div class="pg-section">
              <h2 class="pg-subtitle">{{ text.byAssigneeTitle() }}</h2>
              @if (dash.by_assignee.length === 0) {
                <sol-card><p class="pg-state">{{ text.byAssigneeEmpty() }}</p></sol-card>
              } @else {
                <div class="pg-grid">
                  @for (person of dash.by_assignee; track person.user.id) {
                    <sol-card>
                      <div class="pg-row">
                        <sol-avatar [name]="person.user.full_name" size="sm" />
                        <span class="pg-truncate">{{ person.user.full_name }}</span>
                        <sol-badge class="ex-person__count" variant="neutral">
                          {{ activeCountLabel(person.active_count) }}
                        </sol-badge>
                      </div>
                      @if (person.in_progress.length > 0) {
                        <ul class="pg-list">
                          @for (task of preview(person.in_progress); track task.id) {
                            <li class="pg-row">
                              <span class="ex-dot" aria-hidden="true"></span>
                              <span class="pg-grow pg-truncate" [attr.title]="task.title">{{ task.title }}</span>
                              <sol-badge [variant]="priorityVariant(task.priority)" size="sm">
                                {{ priorityLabel(task.priority) }}
                              </sol-badge>
                            </li>
                          }
                        </ul>
                        @if (person.in_progress.length > preview(person.in_progress).length) {
                          <p class="pg-small">
                            {{ moreLabel(person.in_progress.length - preview(person.in_progress).length) }}
                          </p>
                        }
                      } @else {
                        <p class="pg-small">{{ text.noInProgress() }}</p>
                      }
                    </sol-card>
                  }
                </div>
              }
            </div>
          }
          @case ('risks') {
            @if (dash.at_risk.length === 0) {
              <sol-empty-state
                icon="check-circle"
                titleKey="executive.risks.empty"
                descriptionKey="executive.risks.emptyHint"
              />
            } @else {
              <sol-data-table
                [data]="riskRows()"
                [columns]="riskColumns()"
                [searchPlaceholder]="text.search()"
                [emptyMessage]="text.noMatches()"
                [paginated]="true"
                [collapseWidth]="760"
                [showActions]="false"
                trackByKey="id"
              />
            }
          }
          @case ('projects') {
            @if (dash.projects_progress.length === 0) {
              <sol-empty-state
                icon="folder"
                titleKey="executive.progress.empty"
                descriptionKey="executive.progress.emptyHint"
              />
            } @else {
              <sol-data-table
                [data]="progressRows()"
                [columns]="progressColumns()"
                [searchPlaceholder]="text.search()"
                [emptyMessage]="text.noMatches()"
                [paginated]="true"
                [collapseWidth]="760"
                [showActions]="false"
                trackByKey="id"
              />
            }
          }
          @case ('daily') {
            <sol-card>
              <div class="pg-section">
                <p class="pg-muted">{{ dailyText('scope') }}</p>
                <div class="pg-filters">
                  <sol-select
                    class="pg-filter ex-wide"
                    [label]="dailyText('timezone')"
                    [options]="timezoneOptions()"
                    [formControl]="timezoneControl"
                  />
                  <sol-select
                    class="pg-filter ex-wide"
                    [label]="dailyText('policy')"
                    [placeholder]="dailyText('choose')"
                    [options]="policyOptions()"
                    [formControl]="policyControl"
                  />
                  <sol-button
                    type="button"
                    variant="primary"
                    [disabled]="!dailyPolicy() || !dailyContext()"
                    (clicked)="queryDaily()"
                  >
                    {{ dailyText(dailyError() ? 'retry' : 'query') }}
                  </sol-button>
                </div>
                <p id="daily-policy-help" class="pg-small">{{ dailyText('policyHelp') }}</p>
                <div aria-live="polite" [attr.aria-busy]="dailyLoading()">
                  @if (!dailyContext()) {
                    <p class="pg-muted">{{ dailyText('context') }}</p>
                  } @else if (!dailyPolicy()) {
                    <p class="pg-muted">{{ dailyText('configure') }}</p>
                  } @else if (dailyLoading()) {
                    <p class="pg-muted" role="status">{{ dailyText('loading') }}</p>
                  } @else if (dailyError()) {
                    <p class="pg-alert" role="alert">{{ dailyError() }}</p>
                  } @else if (dailyData(); as daily) {
                    <div class="pg-section">
                      <p class="pg-muted">
                        <strong>{{ dailyText('success') }}</strong> · {{ daily.timezone }} ·
                        {{ dailyText(daily.date_policy) }} · {{ dailyText('generated') }}
                        {{ dailyGenerated(daily) }}
                      </p>
                      <p class="pg-small">{{ dailyText('freshness') }} {{ dailyText('overlap') }}</p>
                      @if (daily.coverage_warnings.length) {
                        <h3 class="pg-subtitle">{{ dailyText('warningsTitle') }}</h3>
                        <ul class="pg-list">
                          @for (warning of daily.coverage_warnings; track warning) {
                            <li>{{ dailyWarning(warning) }}</li>
                          }
                        </ul>
                      }
                      @if (dailyEmpty()) {
                        <p class="pg-muted">{{ dailyText('empty') }}</p>
                      }
                      <div class="ex-daily-grid">
                        @for (group of dailyGroups; track group) {
                          <div class="ex-daily-group">
                            <h3 class="pg-subtitle">
                              {{ dailyText(group) }} ({{ daily[group].count }})
                              @if (group === 'today') { · {{ daily.today_date }} }
                              @if (group === 'tomorrow') { · {{ daily.tomorrow_date }} }
                            </h3>
                            @if (!daily[group].items.length) {
                              <p class="pg-small">{{ dailyText('groupEmpty') }}</p>
                            }
                            <ul class="pg-list">
                              @for (item of daily[group].items; track item.id) {
                                <li>
                                  @if (item.task_key !== null) {
                                    <a class="pg-link" [routerLink]="['/task', item.task_key]">{{ item.title }}</a>
                                  } @else {
                                    <span>{{ item.title }}</span>
                                    <span class="pg-small"> · {{ dailyText('noKey') }}</span>
                                  }
                                  <p class="pg-small">
                                    {{ dailyText('due') }}: {{ item.due_date ?? dailyText('noDue') }}
                                  </p>
                                </li>
                              }
                            </ul>
                          </div>
                        }
                      </div>
                    </div>
                  } @else {
                    <p class="pg-muted">{{ dailyText('ready') }}</p>
                  }
                </div>
              </div>
            </sol-card>
          }
        }
      }
    </section>

    <ng-template #riskTitleCell let-row="row">
      @if ($any(row).task_key) {
        <a class="pg-link" [routerLink]="['/task', $any(row).task_key]">{{ $any(row).title }}</a>
      } @else {
        <span>{{ $any(row).title }}</span>
      }
      @if ($any(row).code) {
        <p class="pg-small pg-mono">{{ $any(row).code }}</p>
      }
    </ng-template>
    <ng-template #priorityCell let-row="row">
      <sol-badge [variant]="$any(row).priority_variant">{{ $any(row).priority_label }}</sol-badge>
    </ng-template>
    <ng-template #progressCell let-row="row">
      <div class="ex-progress">
        <sol-progress-bar
          [value]="$any(row).percent_done"
          [variant]="$any(row).percent_done >= 100 ? 'success' : 'primary'"
          [showLabel]="true"
          [ariaLabel]="percentAria($any(row).name, $any(row).percent_done)"
        />
      </div>
    </ng-template>
    <ng-template #projectCell let-row="row">
      <a class="pg-link" [routerLink]="['/projects', $any(row).id]">{{ $any(row).name }}</a>
    </ng-template>
    <ng-template #methodologyCell let-row="row">
      <sol-badge variant="info">{{ $any(row).methodology_label }}</sol-badge>
    </ng-template>
  `,
})
export class ExecutiveComponent implements OnInit, OnDestroy {
  private readonly executiveService = inject(ExecutiveService);
  private readonly i18n = inject(I18nService);

  private readonly auth = inject(AuthService);
  private readonly activeOrg = inject(ActiveOrgStore);
  protected readonly dailyTimezone = signal('America/Bogota');
  protected readonly dailyPolicy = signal<DailyDatePolicy | ''>('');
  protected readonly dailyData = signal<DailyDashboard | null>(null);
  protected readonly dailyLoading = signal(false);
  protected readonly dailyError = signal<string | null>(null);
  protected readonly dailyGroups = ['today', 'tomorrow', 'overdue', 'blocked'] as const;
  protected readonly dailyEmpty = computed(() => {
    const data = this.dailyData();
    return data !== null && this.dailyGroups.every(group => data[group].count === 0);
  });
  protected readonly dailyContext = computed(() => {
    const user = this.auth.user();
    const org = this.activeOrg.activeOrgId() ?? user?.organization_id;
    return this.auth.isAuthenticated() && user && org ? `${user.id}:${org}` : null;
  });
  private dailyRequest?: Subscription;
  private dailyGeneration = 0;
  private destroyed = false;
  private readonly dailyContextReset = effect(() => {
    this.dailyContext();
    untracked(() => this.clearDaily());
  });

  /** Controles de `sol-select` del resumen diario; la lógica sigue en `changeDaily*`. */
  protected readonly timezoneControl = new FormControl<string>('America/Bogota', { nonNullable: true });
  protected readonly policyControl = new FormControl<string>('', { nonNullable: true });

  constructor() {
    this.timezoneControl.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe(value => this.changeDailyTimezone(value));
    this.policyControl.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe(value => this.changeDailyPolicy(value ?? ''));
  }

  protected dailyText(key: string): string {
    return this.i18n.translate(`daily.${key}`);
  }

  protected changeDailyTimezone(value: string): void {
    if (value !== 'America/Bogota' && value !== 'UTC') return;
    this.clearDaily();
    this.dailyTimezone.set(value);
  }

  protected changeDailyPolicy(value: string): void {
    if (value !== '' && value !== 'stored_calendar_date' && value !== 'instant') return;
    this.clearDaily();
    this.dailyPolicy.set(value);
  }

  private clearDaily(): void {
    this.dailyGeneration++;
    this.dailyRequest?.unsubscribe();
    this.dailyData.set(null);
    this.dailyLoading.set(false);
    this.dailyError.set(null);
  }

  protected queryDaily(): void {
    this.clearDaily();
    const context = this.dailyContext();
    const policy = this.dailyPolicy();
    if (!context || !policy || this.destroyed) return;
    const generation = this.dailyGeneration;
    const timezone = this.dailyTimezone();
    const current = () => !this.destroyed && generation === this.dailyGeneration && context === this.dailyContext();
    this.dailyLoading.set(true);
    this.dailyRequest = this.executiveService.daily(timezone, policy).subscribe({
      next: res => {
        if (!current()) return;
        this.dailyData.set(res.data);
        this.dailyLoading.set(false);
      },
      error: (error: HttpErrorResponse) => {
        if (!current()) return;
        this.dailyLoading.set(false);
        const code = error.error?.code;
        const known = ['daily_disabled', 'organization_unavailable', 'invalid_daily_parameters', 'input_limit', 'timeout', 'daily_unavailable'];
        this.dailyError.set(this.dailyText(`errors.${error.status === 0 ? 'network' : known.includes(code) ? code : 'load'}`));
      },
    });
  }

  protected dailyWarning(code: string): string {
    const known = ['cancellation_unsupported', 'unknown_board', 'unknown_status', 'completion_conflict', 'missing_due_date', 'naive_due_date', 'naive_updated_at', 'groups_overlap', 'missing_task_key'];
    return this.dailyText(`warnings.${known.includes(code) ? code : 'unknown'}`);
  }

  protected dailyGenerated(data: DailyDashboard): string {
    return new Intl.DateTimeFormat('es-CO', {
      timeZone: data.timezone, dateStyle: 'medium', timeStyle: 'short',
    }).format(new Date(data.generated_at));
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    this.clearDaily();
  }

  /** Textos estáticos de la vista resueltos por i18n (reactivos al idioma). */
  protected readonly text = {
    title: this.i18n.t('executive.title'),
    subtitle: this.i18n.t('executive.subtitle'),
    loading: this.i18n.t('executive.loading'),
    retry: this.i18n.t('executive.retry'),
    search: this.i18n.t('executive.search'),
    noMatches: this.i18n.t('executive.noMatches'),
    totalProjects: this.i18n.t('executive.totals.projects'),
    totalTasks: this.i18n.t('executive.totals.tasks'),
    totalOverdue: this.i18n.t('executive.totals.overdue'),
    totalAtRisk: this.i18n.t('executive.totals.atRisk'),
    byAssigneeTitle: this.i18n.t('executive.byAssignee.title'),
    byAssigneeEmpty: this.i18n.t('executive.byAssignee.empty'),
    noInProgress: this.i18n.t('executive.byAssignee.noInProgress'),
    workloadTitle: this.i18n.t('executive.workload.title'),
    workloadEmpty: this.i18n.t('executive.workload.empty'),
    workloadSeries: this.i18n.t('executive.workload.series'),
    tabPeople: this.i18n.t('executive.tabs.people'),
    tabDaily: this.i18n.t('daily.title'),
    colTask: this.i18n.t('executive.columns.task'),
    colAssignee: this.i18n.t('executive.columns.assignee'),
    colDue: this.i18n.t('executive.columns.due'),
    colPriority: this.i18n.t('executive.columns.priority'),
    colStatus: this.i18n.t('executive.columns.status'),
    colProject: this.i18n.t('executive.columns.project'),
    colMethodology: this.i18n.t('executive.columns.methodology'),
    colProgress: this.i18n.t('executive.columns.progress'),
    colDone: this.i18n.t('executive.columns.done'),
    colInProgress: this.i18n.t('executive.columns.inProgress'),
    noAssignee: this.i18n.t('executive.risks.noAssignee'),
  } as const;

  protected readonly data = signal<ExecutiveDashboard | null>(null);
  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);
  protected readonly tab = signal<ExecTab>('people');

  protected readonly tabs = computed<SolTabItem[]>(() => {
    const dash = this.data();
    return [
      { id: 'people', label: this.text.tabPeople() },
      {
        id: 'risks',
        label: this.i18n.translate('executive.tabs.risks', { count: dash?.at_risk.length ?? 0 }),
      },
      {
        id: 'projects',
        label: this.i18n.translate('executive.tabs.projects', {
          count: dash?.projects_progress.length ?? 0,
        }),
      },
      { id: 'daily', label: this.text.tabDaily() },
    ];
  });

  protected readonly timezoneOptions = computed<SolSelectOption[]>(() => [
    { value: 'America/Bogota', label: this.dailyText('bogota') },
    { value: 'UTC', label: this.dailyText('utc') },
  ]);

  protected readonly policyOptions = computed<SolSelectOption[]>(() => [
    { value: 'stored_calendar_date', label: this.dailyText('stored_calendar_date') },
    { value: 'instant', label: this.dailyText('instant') },
  ]);

  /** Solo las personas con carga: las que tienen cero se resumen en una línea. */
  protected readonly busyPeople = computed(() =>
    (this.data()?.workload ?? []).filter(item => item.active_count > 0),
  );

  protected readonly idleCount = computed(
    () => (this.data()?.workload.length ?? 0) - this.busyPeople().length,
  );

  protected readonly workloadChart = computed<SolChartData>(() => {
    const people = this.busyPeople();
    return {
      labels: people.map(item => item.user.full_name),
      series: [{ label: this.text.workloadSeries(), data: people.map(item => item.active_count) }],
    };
  });

  private readonly riskTitleTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('riskTitleCell');
  private readonly priorityTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('priorityCell');
  private readonly progressTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('progressCell');
  private readonly projectTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('projectCell');
  private readonly methodologyTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('methodologyCell');

  protected readonly riskRows = computed<Record<string, unknown>[]>(() =>
    (this.data()?.at_risk ?? []).map(task => ({
      id: task.id,
      title: task.title,
      task_key: task.task_key ?? null,
      code: task.task_key ?? task.external_key ?? '',
      assignee: task.assignee_name || this.text.noAssignee(),
      due: formatShortDate(task.due_date),
      due_sort: task.due_date ?? '',
      status: task.status,
      priority_label: PRIORITY_LABELS[task.priority] ?? task.priority,
      priority_variant: PRIORITY_BADGE[task.priority] ?? 'neutral',
    })),
  );

  protected readonly riskColumns = computed<DataTableColumn[]>(() => [
    { key: 'title', label: this.text.colTask(), sortable: true, cellTemplate: this.riskTitleTpl() },
    { key: 'assignee', label: this.text.colAssignee(), sortable: true },
    { key: 'due', label: this.text.colDue() },
    { key: 'status', label: this.text.colStatus(), sortable: true },
    { key: 'priority_label', label: this.text.colPriority(), cellTemplate: this.priorityTpl() },
  ]);

  /** Proyectos con menos avance primero: es donde el jefe tiene que mirar. */
  protected readonly progressRows = computed<Record<string, unknown>[]>(() =>
    [...(this.data()?.projects_progress ?? [])]
      .sort((a, b) => (b.total > 0 ? 1 : 0) - (a.total > 0 ? 1 : 0) || a.percent_done - b.percent_done)
      .map(item => ({
        id: item.project.id,
        name: item.project.name,
        methodology_label: METHODOLOGY_LABELS[item.project.methodology as Methodology] ?? item.project.methodology,
        percent_done: item.percent_done,
        done: this.i18n.translate('executive.progress.doneOfTotal', { done: item.done, total: item.total }),
        in_progress: item.in_progress,
      })),
  );

  protected readonly progressColumns = computed<DataTableColumn[]>(() => [
    { key: 'name', label: this.text.colProject(), sortable: true, cellTemplate: this.projectTpl() },
    { key: 'methodology_label', label: this.text.colMethodology(), cellTemplate: this.methodologyTpl() },
    { key: 'percent_done', label: this.text.colProgress(), sortable: true, cellTemplate: this.progressTpl() },
    { key: 'done', label: this.text.colDone() },
    { key: 'in_progress', label: this.text.colInProgress(), sortable: true },
  ]);

  ngOnInit(): void {
    this.load();
  }

  protected selectTab(id: string): void {
    if (id === 'people' || id === 'risks' || id === 'projects' || id === 'daily') {
      this.tab.set(id);
    }
  }

  protected preview<T>(items: T[]): T[] {
    return items.slice(0, IN_PROGRESS_PREVIEW);
  }

  protected priorityVariant(priority: Priority): (typeof PRIORITY_BADGE)[Priority] {
    return PRIORITY_BADGE[priority] ?? 'neutral';
  }

  protected priorityLabel(priority: Priority): string {
    return PRIORITY_LABELS[priority] ?? priority;
  }

  protected activeCountLabel(count: number): string {
    return this.i18n.translate('executive.byAssignee.activeCount', { count });
  }

  protected moreLabel(count: number): string {
    return this.i18n.translate('executive.byAssignee.more', { count });
  }

  protected idleLabel(count: number): string {
    return this.i18n.translate('executive.workload.idle', { count });
  }

  protected percentAria(name: string, percent: number): string {
    return this.i18n.translate('executive.progress.projectAria', { name, percent });
  }

  protected load(): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.executiveService.dashboard().subscribe({
      next: (res) => {
        this.data.set(res.data);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.loadError.set(
          err.status === 0
            ? this.i18n.translate('executive.errors.network')
            : this.i18n.translate('executive.errors.load'),
        );
      },
    });
  }
}
