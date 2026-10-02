import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { Observable, Subscription, catchError, forkJoin, of } from 'rxjs';
import {
  SolBadgeComponent,
  SolButtonComponent,
  SolCardComponent,
  SolDrawerComponent,
  SolEmptyStateComponent,
  SolSearchInputComponent,
  SolSkeletonComponent,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { readApiError } from '@shared/lib/api-error';
import { AlertService } from '@shared/lib/alerts';
import { PlansService } from '@entities/plan/plans.service';
import { OrganizationsService } from '@entities/organization/organizations.service';
import { OrganizationMembership } from '@entities/organization/organization.model';
import { ActiveOrgStore } from '@features/organizations/active-org.store';
import { AuthService } from '@features/auth/auth.service';
import {
  ActivityConflictCount,
  ActivityTask,
  Plan,
  PlanActivity,
  PlanActivityDetail,
  PlanListResponse,
  ReportPeriod,
} from '@entities/plan/plan.model';
import { PlanReportFormComponent } from './plan-report-form.component';
import { PlanTaskLinksComponent } from './plan-task-links.component';
import {
  PERIODS,
  PlanSummary,
  activitiesByPlan,
  calculatedPercent,
  conflictIndex,
  currentPeriod,
  filterActivities,
  groupActivities,
  presentPlanTypes,
  previousPeriod,
  reportedPercent,
  summarizePlan,
} from './plans-view';

/** Detail of the activity open in the drawer, with its own load state. */
interface ActivityPanel {
  activity: PlanActivity;
  loading: boolean;
  error: string | null;
  detail: PlanActivityDetail | null;
  tasks: ActivityTask[];
}

/**
 * «Planes» (change 45c + task N3): institutional plans (PSPI, PTR, PAI,
 * PTEP) of the active organization. One screen: plan cards with the two
 * progress figures kept apart (calculated from tasks vs. reported for the
 * selected period), the selected plan's activities grouped by group (with a
 * conflict-link badge), and a drawer with an activity's report, links
 * (conflicts flagged) and tasks.
 *
 * Admins and managers of the active organization (same rule as the backend)
 * report the period's progress and link/unlink tasks from any project; every
 * other role sees the read-only drawer. Activity links are never edited here.
 */
@Component({
  selector: 'sol-plans',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    SolBadgeComponent,
    SolButtonComponent,
    SolCardComponent,
    SolDrawerComponent,
    SolEmptyStateComponent,
    SolSearchInputComponent,
    SolSkeletonComponent,
    PlanReportFormComponent,
    PlanTaskLinksComponent,
  ],
  template: `
    <section class="flex flex-col gap-6">
      <header>
        <h1 class="text-2xl font-semibold text-text">{{ text.title() }}</h1>
        <p class="text-sm text-muted">{{ text.subtitle() }}</p>
      </header>

      @if (loading()) {
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-busy="true">
          <span class="sr-only" role="status">{{ text.loading() }}</span>
          <sol-skeleton variant="card" />
          <sol-skeleton variant="card" />
          <sol-skeleton variant="card" />
        </div>
      } @else if (loadError(); as message) {
        <!-- Error de carga: nunca se confunde con «no hay planes». -->
        <div
          role="alert"
          class="flex flex-col gap-3 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger sm:flex-row sm:items-center sm:justify-between"
        >
          <span>{{ message }}</span>
          <sol-button type="button" variant="secondary" size="sm" (clicked)="load()">
            {{ text.retry() }}
          </sol-button>
        </div>
      } @else if (plans().length === 0) {
        <sol-empty-state
          icon="clipboard"
          titleKey="plans.empty.title"
          descriptionKey="plans.empty.description"
        />
      } @else {
        <!-- Filtros -->
        <div class="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4">
          <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div class="flex flex-col gap-1.5">
              <span class="text-xs font-medium text-muted" id="plans-period-label">
                {{ text.periodLabel() }}
              </span>
              <div
                class="flex flex-wrap gap-1.5"
                role="group"
                aria-labelledby="plans-period-label"
              >
                @for (p of periods; track p) {
                  <button
                    type="button"
                    class="min-h-11 rounded-full border px-3 text-sm transition-colors"
                    [class]="segmentClass(period() === p)"
                    [attr.aria-pressed]="period() === p"
                    (click)="setPeriod(p)"
                  >
                    {{ periodLabel(p) }}
                  </button>
                }
              </div>
            </div>

            @if (planTypes().length > 1) {
              <div class="flex flex-col gap-1.5">
                <span class="text-xs font-medium text-muted" id="plans-type-label">
                  {{ text.typeLabel() }}
                </span>
                <div class="flex flex-wrap gap-1.5" role="group" aria-labelledby="plans-type-label">
                  <button
                    type="button"
                    class="min-h-11 rounded-full border px-3 text-sm transition-colors"
                    [class]="segmentClass(typeFilter() === null)"
                    [attr.aria-pressed]="typeFilter() === null"
                    (click)="setType(null)"
                  >
                    {{ text.typeAll() }}
                  </button>
                  @for (type of planTypes(); track type) {
                    <button
                      type="button"
                      class="min-h-11 rounded-full border px-3 text-sm transition-colors"
                      [class]="segmentClass(typeFilter() === type)"
                      [attr.aria-pressed]="typeFilter() === type"
                      (click)="setType(type)"
                    >
                      {{ typeLabel(type) }}
                    </button>
                  }
                </div>
              </div>
            }
          </div>

          <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div class="flex-1">
              <sol-search-input
                #search
                [placeholder]="text.searchPlaceholder()"
                (searchChange)="query.set($event)"
              />
            </div>
            <button
              type="button"
              class="min-h-11 rounded-full border px-4 text-sm transition-colors"
              [class]="segmentClass(onlyMine())"
              [attr.aria-pressed]="onlyMine()"
              [attr.title]="text.onlyMineHint()"
              (click)="onlyMine.set(!onlyMine())"
            >
              {{ text.onlyMine() }}
            </button>
          </div>
        </div>

        @if (activitiesError(); as message) {
          <div
            role="alert"
            class="flex flex-col gap-3 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger sm:flex-row sm:items-center sm:justify-between"
          >
            <span>{{ message }}</span>
            <sol-button type="button" variant="secondary" size="sm" (clicked)="loadActivities()">
              {{ text.retry() }}
            </sol-button>
          </div>
        }

        <!-- Tarjetas de planes -->
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          @for (plan of visiblePlans(); track plan.id) {
            <button
              type="button"
              class="rounded-lg border bg-surface p-4 text-left transition-colors hover:border-brand focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
              [class.border-brand]="selectedPlan()?.id === plan.id"
              [class.ring-1]="selectedPlan()?.id === plan.id"
              [class.ring-brand]="selectedPlan()?.id === plan.id"
              [class.border-border]="selectedPlan()?.id !== plan.id"
              [attr.aria-pressed]="selectedPlan()?.id === plan.id"
              (click)="selectPlan(plan.id)"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <p class="font-mono text-xs text-muted">{{ plan.code }}</p>
                  <h2 class="mt-0.5 line-clamp-2 text-base font-semibold text-text">
                    {{ plan.name }}
                  </h2>
                </div>
                <sol-badge variant="info" size="sm">{{ typeLabel(plan.plan_type) }}</sol-badge>
              </div>
              <p class="mt-1 text-xs text-muted">
                {{ plan.period_year }} · {{ statusLabel(plan.status) }} ·
                {{ activityCountLabel(summaryOf(plan).activityCount) }}
              </p>

              @if (activitiesLoading()) {
                <div class="mt-4"><sol-skeleton variant="text" [count]="2" /></div>
              } @else if (!activitiesError()) {
                <div class="mt-4 grid grid-cols-2 gap-3">
                  <div class="rounded-lg bg-muted/10 px-3 py-2">
                    <p class="text-xs text-muted">{{ text.calculated() }}</p>
                    @if (summaryOf(plan).calculatedAverage !== null) {
                      <p class="mt-0.5 text-xl font-semibold text-text">
                        {{ summaryOf(plan).calculatedAverage }}%
                      </p>
                      <p class="text-[11px] leading-tight text-muted">
                        {{ withTasksLabel(summaryOf(plan)) }}
                      </p>
                    } @else {
                      <p class="mt-0.5 text-sm font-medium text-muted">{{ text.noTasks() }}</p>
                    }
                  </div>
                  <div class="rounded-lg bg-muted/10 px-3 py-2">
                    <p class="text-xs text-muted">{{ reportedTitle() }}</p>
                    @if (summaryOf(plan).reportedAverage !== null) {
                      <p class="mt-0.5 text-xl font-semibold text-text">
                        {{ summaryOf(plan).reportedAverage }}%
                      </p>
                      <p class="text-[11px] leading-tight text-muted">
                        {{ withReportLabel(summaryOf(plan)) }}
                      </p>
                    } @else {
                      <p class="mt-0.5 text-sm font-medium text-muted">{{ text.noReport() }}</p>
                    }
                  </div>
                </div>
              }
            </button>
          }
        </div>

        <!-- Detalle del plan seleccionado -->
        @if (selectedPlan(); as plan) {
          <sol-card>
            <div class="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
              <h2 class="text-lg font-semibold text-text">
                <span class="font-mono text-sm text-muted">{{ plan.code }}</span>
                {{ plan.name }}
              </h2>
              @if (!activitiesLoading() && !activitiesError()) {
                <p class="text-xs text-muted" role="status">
                  {{ shownLabel(selectedActivities().length, selectedPlanActivityCount()) }}
                </p>
              }
            </div>

            @if (activitiesLoading()) {
              <div class="mt-4"><sol-skeleton variant="row" [count]="4" /></div>
            } @else if (activitiesError()) {
              <p class="mt-4 text-sm text-muted">{{ text.activitiesUnavailable() }}</p>
            } @else if (selectedPlanActivityCount() === 0) {
              <p class="mt-4 text-sm text-muted">{{ text.planWithoutActivities() }}</p>
            } @else if (selectedActivities().length === 0) {
              <div class="mt-4 flex flex-col items-start gap-3 rounded-lg bg-muted/10 px-4 py-4">
                <p class="text-sm text-text">{{ text.noResults() }}</p>
                <sol-button type="button" variant="secondary" size="sm" (clicked)="clearFilters()">
                  {{ text.clearFilters() }}
                </sol-button>
              </div>
            } @else {
              <div class="mt-4 flex flex-col gap-5">
                @for (group of selectedGroups(); track group.key) {
                  <section [attr.aria-label]="groupTitle(group.code, group.name)">
                    <h3 class="text-sm font-semibold text-text">
                      {{ groupTitle(group.code, group.name) }}
                      <span class="font-normal text-muted">({{ group.activities.length }})</span>
                    </h3>
                    <ul class="mt-2 flex flex-col divide-y divide-border rounded-lg border border-border">
                      @for (activity of group.activities; track activity.id) {
                        <li>
                          <button
                            type="button"
                            class="flex w-full flex-col gap-2 px-3 py-3 text-left hover:bg-muted/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand md:flex-row md:items-center md:gap-4"
                            [attr.aria-label]="openActivityAria(activity)"
                            (click)="openActivity(activity)"
                          >
                            <div class="min-w-0 flex-1">
                              <p class="font-mono text-xs text-brand">
                                {{ activity.activity_key ?? activity.code }}
                                @if (activity.is_mine) {
                                  <span class="ml-1 rounded bg-brand/10 px-1.5 py-0.5 font-sans text-[11px] text-brand">
                                    {{ text.mine() }}
                                  </span>
                                }
                                @if (conflictsOf(activity.id); as n) {
                                  <span class="ml-1 rounded bg-warning-soft px-1.5 py-0.5 font-sans text-[11px] font-medium text-warning">
                                    {{ conflictLabel(n) }}
                                  </span>
                                }
                              </p>
                              <p class="line-clamp-2 text-sm text-text">{{ activity.name }}</p>
                              <p class="mt-0.5 text-xs text-muted">
                                {{ activity.responsible || text.noResponsible() }}
                                @if (activity.scheduled_periods?.length) {
                                  · {{ text.scheduled() }} {{ periodsList(activity.scheduled_periods) }}
                                }
                              </p>
                            </div>
                            <div class="grid shrink-0 grid-cols-3 gap-3 text-xs md:w-[22rem]">
                              <div>
                                <p class="text-muted">{{ text.calculatedShort() }}</p>
                                <p class="font-medium" [class]="calcClass(activity)">
                                  {{ calcLabel(activity) }}
                                </p>
                              </div>
                              <div>
                                <p class="text-muted">{{ reportedShortTitle() }}</p>
                                <p class="font-medium" [class]="reportedClass(activity)">
                                  {{ reportedLabel(activity) }}
                                </p>
                              </div>
                              <div>
                                <p class="text-muted">{{ text.tasks() }}</p>
                                <p class="font-medium text-text">
                                  {{ taskCountsLabel(activity) }}
                                </p>
                              </div>
                            </div>
                          </button>
                        </li>
                      }
                    </ul>
                  </section>
                }
              </div>
            }
          </sol-card>
        } @else if (visiblePlans().length === 0) {
          <div class="flex flex-col items-start gap-3 rounded-lg bg-muted/10 px-4 py-4">
            <p class="text-sm text-text">{{ text.noPlansForType() }}</p>
            <sol-button type="button" variant="secondary" size="sm" (clicked)="clearFilters()">
              {{ text.clearFilters() }}
            </sol-button>
          </div>
        }

        <p class="text-xs text-muted">{{ canWrite() ? text.writeNote() : text.readOnlyNote() }}</p>
      }
    </section>

    <!-- Detalle de la actividad -->
    <sol-drawer
      [open]="panel() !== null"
      [title]="panelTitle()"
      size="lg"
      (closed)="closeActivity()"
    >
      @if (panel(); as p) {
        <div class="flex flex-col gap-5">
          <div>
            <p class="font-mono text-xs text-brand">{{ p.activity.activity_key ?? p.activity.code }}</p>
            <p class="text-sm text-text">{{ p.activity.name }}</p>
            @if (p.activity.group_name || p.activity.group_code) {
              <p class="mt-0.5 text-xs text-muted">
                {{ groupTitle(p.activity.group_code, p.activity.group_name) }}
              </p>
            }
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div class="rounded-lg bg-muted/10 px-3 py-2">
              <p class="text-xs text-muted">{{ text.calculated() }}</p>
              <p class="mt-0.5 text-lg font-semibold" [class]="calcClass(p.activity)">
                {{ calcLabel(p.activity) }}
              </p>
            </div>
            <div class="rounded-lg bg-muted/10 px-3 py-2">
              <p class="text-xs text-muted">{{ reportedTitle() }}</p>
              <p class="mt-0.5 text-lg font-semibold" [class]="reportedClass(p.activity)">
                {{ reportedLabel(p.activity) }}
              </p>
            </div>
          </div>

          <dl class="grid grid-cols-1 gap-x-4 gap-y-2 text-sm sm:grid-cols-2">
            <div>
              <dt class="text-xs text-muted">{{ text.fields.responsible() }}</dt>
              <dd class="text-text">{{ p.activity.responsible || text.noResponsible() }}</dd>
            </div>
            <div>
              <dt class="text-xs text-muted">{{ text.fields.dueDate() }}</dt>
              <dd class="text-text">{{ formatDate(p.activity.due_date) }}</dd>
            </div>
            <div>
              <dt class="text-xs text-muted">{{ text.fields.periods() }}</dt>
              <dd class="text-text">{{ periodsList(p.activity.scheduled_periods) || '—' }}</dd>
            </div>
            @if (p.activity.iso_controls?.length) {
              <div>
                <dt class="text-xs text-muted">{{ text.fields.iso() }}</dt>
                <dd class="text-text">{{ p.activity.iso_controls!.join(', ') }}</dd>
              </div>
            }
            @if (p.activity.deliverable) {
              <div class="sm:col-span-2">
                <dt class="text-xs text-muted">{{ text.fields.deliverable() }}</dt>
                <dd class="whitespace-pre-line text-text">{{ p.activity.deliverable }}</dd>
              </div>
            }
            @if (p.activity.evidence_expected) {
              <div class="sm:col-span-2">
                <dt class="text-xs text-muted">{{ text.fields.evidence() }}</dt>
                <dd class="whitespace-pre-line text-text">{{ p.activity.evidence_expected }}</dd>
              </div>
            }
          </dl>

          @if (p.loading) {
            <sol-skeleton variant="row" [count]="3" />
          } @else if (p.error) {
            <div
              role="alert"
              class="flex flex-col gap-3 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
            >
              <span>{{ p.error }}</span>
              <sol-button type="button" variant="secondary" size="sm" (clicked)="openActivity(p.activity)">
                {{ text.retry() }}
              </sol-button>
            </div>
          } @else if (p.detail; as detail) {
            <!-- Reporte del periodo -->
            <section class="flex flex-col gap-2">
              <h3 class="text-sm font-semibold text-text">{{ reportSectionTitle() }}</h3>
              @if (canWrite()) {
                <sol-plan-report-form
                  [activityId]="detail.id"
                  [period]="period()"
                  [report]="periodReport(detail)"
                  [previousReport]="previousReport(detail)"
                  [previousPeriod]="previousPeriodOf()"
                  [calculatedPercent]="calcPercent(detail)"
                  (saved)="onReportSaved()"
                />
              } @else if (periodReport(detail); as report) {
                <div class="rounded-lg border border-border px-3 py-2 text-sm">
                  <p class="text-text">
                    {{ text.report.met() }}: {{ yesNo(report.is_met) }} ·
                    {{ text.report.onTime() }}: {{ yesNo(report.met_on_time) }}
                  </p>
                  @if (report.qualitative_summary) {
                    <p class="mt-1 whitespace-pre-line text-muted">{{ report.qualitative_summary }}</p>
                  }
                  @if (report.evidence_refs?.length) {
                    <p class="mt-1 text-xs text-muted">
                      {{ text.report.evidence() }}: {{ report.evidence_refs!.join(', ') }}
                    </p>
                  }
                </div>
              } @else {
                <p class="text-sm text-muted">{{ text.noReport() }}</p>
              }
            </section>

            <!-- Vínculos con otras actividades -->
            @if (detail.links_out.length || detail.links_in.length) {
              <section class="flex flex-col gap-2">
                <h3 class="text-sm font-semibold text-text">{{ text.links.title() }}</h3>
                <ul class="flex flex-col gap-2">
                  @for (link of detail.links_out; track link.id) {
                    <li
                      class="rounded-lg border px-3 py-2 text-sm"
                      [class.border-warning]="!link.is_confirmed"
                      [class.bg-warning-soft]="!link.is_confirmed"
                      [class.border-border]="link.is_confirmed"
                    >
                      <p class="text-text">
                        {{ linkTypeLabel(link.link_type) }}
                        <span class="font-mono text-brand">{{ activityRef(link.to_activity_id) }}</span>
                      </p>
                      @if (!link.is_confirmed) {
                        <p class="mt-1 flex items-center gap-1.5 text-xs font-medium text-warning">
                          <sol-badge variant="warning" size="sm">{{ text.links.conflict() }}</sol-badge>
                        </p>
                      }
                      @if (link.source_reference) {
                        <p class="mt-1 text-xs text-muted">
                          {{ text.links.sourceText() }}: «{{ link.source_reference }}»
                        </p>
                      }
                    </li>
                  }
                  @for (link of detail.links_in; track link.id) {
                    <li
                      class="rounded-lg border px-3 py-2 text-sm"
                      [class.border-warning]="!link.is_confirmed"
                      [class.bg-warning-soft]="!link.is_confirmed"
                      [class.border-border]="link.is_confirmed"
                    >
                      <p class="text-text">
                        {{ text.links.incoming() }}
                        <span class="font-mono text-brand">{{ activityRef(link.from_activity_id) }}</span>
                        <span class="text-muted">({{ linkTypeLabel(link.link_type) }})</span>
                      </p>
                      @if (!link.is_confirmed) {
                        <p class="mt-1">
                          <sol-badge variant="warning" size="sm">{{ text.links.conflict() }}</sol-badge>
                        </p>
                      }
                      @if (link.source_reference) {
                        <p class="mt-1 text-xs text-muted">
                          {{ text.links.sourceText() }}: «{{ link.source_reference }}»
                        </p>
                      }
                    </li>
                  }
                </ul>
              </section>
            }

            <!-- Tareas vinculadas -->
            <sol-plan-task-links
              [activityId]="detail.id"
              [tasks]="p.tasks"
              [canWrite]="canWrite()"
              (changed)="onTasksChanged($event)"
            />
          }
        </div>
      }
    </sol-drawer>
  `,
})
export class PlansComponent implements OnInit {
  private readonly plansService = inject(PlansService);
  private readonly i18n = inject(I18nService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly organizations = inject(OrganizationsService);
  private readonly activeOrg = inject(ActiveOrgStore);
  private readonly auth = inject(AuthService);
  private readonly alert = inject(AlertService);

  /** Textos estáticos de la vista resueltos por i18n (reactivos al idioma). */
  protected readonly text = {
    title: this.i18n.t('plans.title'),
    subtitle: this.i18n.t('plans.subtitle'),
    loading: this.i18n.t('plans.loading'),
    retry: this.i18n.t('plans.retry'),
    periodLabel: this.i18n.t('plans.filters.period'),
    typeLabel: this.i18n.t('plans.filters.type'),
    typeAll: this.i18n.t('plans.filters.typeAll'),
    searchPlaceholder: this.i18n.t('plans.filters.search'),
    onlyMine: this.i18n.t('plans.filters.onlyMine'),
    onlyMineHint: this.i18n.t('plans.filters.onlyMineHint'),
    clearFilters: this.i18n.t('plans.filters.clear'),
    calculated: this.i18n.t('plans.progress.calculated'),
    calculatedShort: this.i18n.t('plans.progress.calculatedShort'),
    noTasks: this.i18n.t('plans.progress.noTasks'),
    noReport: this.i18n.t('plans.progress.noReport'),
    noResults: this.i18n.t('plans.states.noResults'),
    noPlansForType: this.i18n.t('plans.states.noPlansForType'),
    planWithoutActivities: this.i18n.t('plans.states.planWithoutActivities'),
    activitiesUnavailable: this.i18n.t('plans.states.activitiesUnavailable'),
    readOnlyNote: this.i18n.t('plans.readOnlyNote'),
    writeNote: this.i18n.t('plans.writeNote'),
    mine: this.i18n.t('plans.activity.mine'),
    noResponsible: this.i18n.t('plans.activity.noResponsible'),
    scheduled: this.i18n.t('plans.activity.scheduled'),
    tasks: this.i18n.t('plans.activity.tasks'),
    fields: {
      responsible: this.i18n.t('plans.fields.responsible'),
      dueDate: this.i18n.t('plans.fields.dueDate'),
      periods: this.i18n.t('plans.fields.periods'),
      iso: this.i18n.t('plans.fields.iso'),
      deliverable: this.i18n.t('plans.fields.deliverable'),
      evidence: this.i18n.t('plans.fields.evidence'),
    },
    report: {
      met: this.i18n.t('plans.report.met'),
      onTime: this.i18n.t('plans.report.onTime'),
      evidence: this.i18n.t('plans.report.evidence'),
    },
    links: {
      title: this.i18n.t('plans.links.title'),
      incoming: this.i18n.t('plans.links.incoming'),
      conflict: this.i18n.t('plans.links.conflict'),
      sourceText: this.i18n.t('plans.links.sourceText'),
    },
  } as const;

  protected readonly periods = PERIODS;

  protected readonly plans = signal<Plan[]>([]);
  protected readonly activities = signal<PlanActivity[]>([]);
  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);
  protected readonly activitiesLoading = signal(false);
  protected readonly activitiesError = signal<string | null>(null);

  /** Smart default: the current cuatrimestre (I ene–abr, II may–ago, III sep–dic). */
  protected readonly period = signal<ReportPeriod>(currentPeriod(new Date()));
  protected readonly typeFilter = signal<string | null>(null);
  protected readonly onlyMine = signal(false);
  protected readonly query = signal('');
  private readonly selectedPlanId = signal<string | null>(null);
  private readonly searchInput = viewChild<SolSearchInputComponent>('search');

  /** activity id → number of `conflict` links (either end). */
  private readonly conflicts = signal<Map<string, number>>(new Map());
  private readonly memberships = signal<OrganizationMembership[]>([]);

  /**
   * Role in the ACTIVE organization: the `X-Organization-Id` the interceptor
   * sends, or the backend fallback (`/auth/me` organization, then the first
   * membership). Writes are admin/manager, exactly as `require_plans_write_role`.
   */
  protected readonly canWrite = computed(() => {
    const memberships = this.memberships();
    const orgId = this.activeOrg.activeOrgId() ?? this.auth.user()?.organization_id ?? null;
    const membership =
      memberships.find((m) => m.organization.id === orgId) ?? (orgId ? undefined : memberships[0]);
    return membership?.role === 'admin' || membership?.role === 'manager';
  });

  protected readonly previousPeriodOf = computed(() => previousPeriod(this.period()));

  protected readonly panel = signal<ActivityPanel | null>(null);
  private panelSub: Subscription | null = null;
  private activitiesSub: Subscription | null = null;

  protected readonly planTypes = computed(() => presentPlanTypes(this.plans()));

  protected readonly visiblePlans = computed(() => {
    const type = this.typeFilter();
    return type === null ? this.plans() : this.plans().filter((plan) => plan.plan_type === type);
  });

  private readonly byPlan = computed(() => activitiesByPlan(this.activities()));

  private readonly summaries = computed(() => {
    const summaries = new Map<string, PlanSummary>();
    for (const plan of this.plans()) {
      summaries.set(plan.id, summarizePlan(this.byPlan().get(plan.id) ?? []));
    }
    return summaries;
  });

  /** Selected plan; falls back to the first visible one (nothing starts empty). */
  protected readonly selectedPlan = computed<Plan | null>(() => {
    const visible = this.visiblePlans();
    const id = this.selectedPlanId();
    return visible.find((plan) => plan.id === id) ?? visible[0] ?? null;
  });

  protected readonly selectedPlanActivityCount = computed(
    () => this.byPlan().get(this.selectedPlan()?.id ?? '')?.length ?? 0,
  );

  protected readonly selectedActivities = computed(() =>
    filterActivities(this.byPlan().get(this.selectedPlan()?.id ?? '') ?? [], {
      onlyMine: this.onlyMine(),
      query: this.query(),
    }),
  );

  protected readonly selectedGroups = computed(() => groupActivities(this.selectedActivities()));

  /** id → activity, to name the other end of an activity link. */
  private readonly activityIndex = computed(
    () => new Map(this.activities().map((activity) => [activity.id, activity])),
  );

  protected readonly reportedTitle = computed(() =>
    this.translate('plans.progress.reported', { period: this.periodShort(this.period()) }),
  );

  protected readonly reportedShortTitle = computed(() =>
    this.translate('plans.progress.reportedShort', { period: this.periodShort(this.period()) }),
  );

  protected readonly reportSectionTitle = computed(() =>
    this.translate('plans.report.title', { period: this.periodShort(this.period()) }),
  );

  protected readonly panelTitle = computed(() => {
    const activity = this.panel()?.activity;
    return activity ? (activity.activity_key ?? activity.code) : '';
  });

  ngOnInit(): void {
    this.selectedPlanId.set(this.route.snapshot.queryParamMap.get('plan'));
    this.load();
    // Role lookup never blocks the view: on failure it stays read-only.
    this.organizations
      .mine()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => this.memberships.set(res.data ?? []),
        error: () => this.memberships.set([]),
      });
  }

  /** Conflict counts are a hint: a failure must not hide the activities. */
  private conflictCounts$(): Observable<PlanListResponse<ActivityConflictCount>> {
    return this.plansService
      .conflictCounts()
      .pipe(catchError(() => of({ data: [] as ActivityConflictCount[] })));
  }

  /** Initial load: plans and activities of the selected period, together. */
  protected load(): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.activitiesError.set(null);
    this.activitiesSub?.unsubscribe();
    forkJoin({
      plans: this.plansService.list(),
      activities: this.plansService.activities({ period: this.period() }),
      conflicts: this.conflictCounts$(),
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ plans, activities, conflicts }) => {
          this.plans.set(plans.data);
          this.activities.set(activities.data);
          this.conflicts.set(conflictIndex(conflicts.data));
          this.loading.set(false);
        },
        error: (err: unknown) => {
          this.loading.set(false);
          this.loadError.set(this.errorMessage(err, 'plans.errors.loadFailed'));
        },
      });
  }

  /**
   * Reload only the activities (period change or retry). `silent` keeps the
   * current figures on screen (refresh after a write) instead of skeletons.
   */
  protected loadActivities(silent = false): void {
    this.activitiesSub?.unsubscribe();
    if (!silent) {
      this.activitiesLoading.set(true);
    }
    this.activitiesError.set(null);
    this.activitiesSub = forkJoin({
      activities: this.plansService.activities({ period: this.period() }),
      conflicts: this.conflictCounts$(),
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ activities, conflicts }) => {
          this.activities.set(activities.data);
          this.conflicts.set(conflictIndex(conflicts.data));
          this.activitiesLoading.set(false);
        },
        error: (err: unknown) => {
          this.activitiesLoading.set(false);
          this.activitiesError.set(this.errorMessage(err, 'plans.errors.activitiesFailed'));
        },
      });
  }

  protected setPeriod(period: ReportPeriod): void {
    if (period === this.period()) {
      return;
    }
    this.period.set(period);
    this.loadActivities();
    const open = this.panel();
    if (open) {
      this.openActivity(this.activityIndex().get(open.activity.id) ?? open.activity);
    }
  }

  protected setType(type: string | null): void {
    this.typeFilter.set(type);
  }

  protected selectPlan(id: string): void {
    this.selectedPlanId.set(id);
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { plan: id },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  protected clearFilters(): void {
    this.typeFilter.set(null);
    this.onlyMine.set(false);
    this.query.set('');
    // Keep the visible input in sync with the cleared filter.
    this.searchInput()?.value.set('');
  }

  protected openActivity(activity: PlanActivity, keepContent = false): void {
    this.panelSub?.unsubscribe();
    const current = this.panel();
    if (keepContent && current && current.activity.id === activity.id) {
      // Refresh after a write: keep the drawer content, swap it when it arrives.
      this.panel.set({ ...current, error: null });
    } else {
      this.panel.set({ activity, loading: true, error: null, detail: null, tasks: [] });
    }
    this.panelSub = forkJoin({
      detail: this.plansService.activity(activity.id, this.period()),
      tasks: this.plansService.activityTasks(activity.id),
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ detail, tasks }) => {
          this.panel.set({
            activity: detail.data,
            loading: false,
            error: null,
            detail: detail.data,
            tasks: tasks.data,
          });
        },
        error: (err: unknown) => {
          this.panel.set({
            activity,
            loading: false,
            error: this.errorMessage(err, 'plans.errors.activityFailed'),
            detail: null,
            tasks: [],
          });
        },
      });
  }

  /** After a period report was saved: confirm and refresh both figures. */
  protected onReportSaved(): void {
    this.alert.showSuccess(
      this.translate('plans.reportForm.saved', { period: this.periodShort(this.period()) }),
    );
    this.refreshAfterWrite();
  }

  protected onTasksChanged(kind: 'linked' | 'unlinked'): void {
    this.alert.showSuccess(this.translate(`plans.linker.${kind}`));
    this.refreshAfterWrite();
  }

  private refreshAfterWrite(): void {
    const open = this.panel();
    if (open) {
      this.openActivity(open.activity, true);
    }
    this.loadActivities(true);
  }

  protected closeActivity(): void {
    this.panelSub?.unsubscribe();
    this.panel.set(null);
  }

  // --- Presentación -------------------------------------------------------

  protected summaryOf(plan: Plan): PlanSummary {
    return (
      this.summaries().get(plan.id) ?? {
        activityCount: 0,
        withTasks: 0,
        calculatedAverage: null,
        withReport: 0,
        reportedAverage: null,
      }
    );
  }

  protected segmentClass(active: boolean): string {
    return active
      ? 'border-brand bg-brand text-brand-fg'
      : 'border-border bg-surface text-text hover:border-brand';
  }

  protected periodShort(period: string): string {
    return this.translate(`plans.periods.${period}.short`);
  }

  protected periodLabel(period: string): string {
    return this.translate(`plans.periods.${period}.label`);
  }

  protected periodsList(periods: string[] | null | undefined): string {
    return (periods ?? []).join(', ');
  }

  protected typeLabel(type: string): string {
    return this.labelOr(`plans.types.${type}`, type.toUpperCase());
  }

  protected statusLabel(status: string): string {
    return this.labelOr(`plans.status.${status}`, status);
  }

  protected linkTypeLabel(type: string): string {
    return this.labelOr(`plans.links.types.${type}`, type);
  }

  protected groupTitle(code: string | null, name: string | null): string {
    // Prefix only numeric codes the source name does not already carry
    // ("11. Gobierno digital", "Riesgos Altos" for code ALTO).
    if (code && name && /^\d+$/.test(code) && !name.startsWith(`${code}.`) && !name.startsWith(`${code} `)) {
      return `${code}. ${name}`;
    }
    if (name) {
      return name;
    }
    return name || code || this.translate('plans.activity.noGroup');
  }

  protected activityCountLabel(count: number): string {
    return this.translate(count === 1 ? 'plans.card.activityOne' : 'plans.card.activities', {
      n: count,
    });
  }

  protected withTasksLabel(summary: PlanSummary): string {
    return this.translate('plans.card.withTasks', {
      n: summary.withTasks,
      total: summary.activityCount,
    });
  }

  protected withReportLabel(summary: PlanSummary): string {
    return this.translate('plans.card.withReport', {
      n: summary.withReport,
      total: summary.activityCount,
    });
  }

  protected shownLabel(shown: number, total: number): string {
    return this.translate('plans.detail.shown', { n: shown, total });
  }

  protected calcLabel(activity: PlanActivity): string {
    const percent = calculatedPercent(activity);
    return percent === null ? this.translate('plans.progress.noTasks') : `${percent}%`;
  }

  protected reportedLabel(activity: PlanActivity): string {
    const percent = reportedPercent(activity);
    return percent === null ? this.translate('plans.progress.noReport') : `${percent}%`;
  }

  protected calcClass(activity: PlanActivity): string {
    return calculatedPercent(activity) === null ? 'text-muted' : 'text-text';
  }

  protected reportedClass(activity: PlanActivity): string {
    return reportedPercent(activity) === null ? 'text-muted' : 'text-text';
  }

  protected taskCountsLabel(activity: PlanActivity): string {
    return this.translate('plans.activity.taskCounts', {
      primary: activity.primary_task_count,
      contributes: activity.contributing_task_count,
    });
  }

  protected openActivityAria(activity: PlanActivity): string {
    return this.translate('plans.activity.openAria', {
      key: activity.activity_key ?? activity.code,
    });
  }

  protected activityRef(id: string): string {
    const activity = this.activityIndex().get(id);
    if (!activity) {
      return this.translate('plans.links.unknownActivity');
    }
    return `${activity.activity_key ?? activity.code} · ${activity.name}`;
  }

  protected periodReport(detail: PlanActivityDetail) {
    return detail.reports.find((report) => report.period === this.period()) ?? null;
  }

  protected previousReport(detail: PlanActivityDetail) {
    const previous = this.previousPeriodOf();
    return previous ? (detail.reports.find((report) => report.period === previous) ?? null) : null;
  }

  protected calcPercent(activity: PlanActivity): number | null {
    return calculatedPercent(activity);
  }

  protected conflictsOf(activityId: string): number {
    return this.conflicts().get(activityId) ?? 0;
  }

  protected conflictLabel(count: number): string {
    return this.translate(count === 1 ? 'plans.conflicts.one' : 'plans.conflicts.many', {
      n: count,
    });
  }

  protected yesNo(value: boolean | null): string {
    if (value === null || value === undefined) {
      return this.translate('plans.report.noData');
    }
    return this.translate(value ? 'plans.report.yes' : 'plans.report.no');
  }

  protected formatDate(value: string | null): string {
    if (!value) {
      return '—';
    }
    const date = new Date(`${value}T00:00:00`);
    return Number.isNaN(date.getTime())
      ? value
      : date.toLocaleDateString('es-CO', { day: 'numeric', month: 'short', year: 'numeric' });
  }

  private translate(key: string, params?: Record<string, unknown>): string {
    this.i18n.activeLang();
    return this.i18n.translate(key, params);
  }

  /** Translation with fallback when the key is not in the catalog. */
  private labelOr(key: string, fallback: string): string {
    const value = this.translate(key);
    return value === key ? fallback : value;
  }

  private errorMessage(err: unknown, fallbackKey: string): string {
    const api = readApiError(err);
    if (api.status === 0) {
      return this.translate('plans.errors.network');
    }
    return api.detail ?? this.translate(fallbackKey);
  }
}
