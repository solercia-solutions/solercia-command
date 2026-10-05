import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  TemplateRef,
  computed,
  effect,
  inject,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { FormControl } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import {
  Observable,
  Subscription,
  catchError,
  debounceTime,
  distinctUntilChanged,
  forkJoin,
  from,
  map,
  mergeMap,
  of,
  startWith,
} from 'rxjs';
import {
  DataTableColumn,
  SolBadgeComponent,
  SolButtonComponent,
  SolCardComponent,
  SolDataTableComponent,
  SolDataTableRow,
  SolDrawerComponent,
  SolEmptyStateComponent,
  SolIconButtonComponent,
  SolProgressBarComponent,
  SolSelectOption,
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
import { PlansFilterControls, PlansFiltersComponent } from './plans-filters.component';
import {
  LINK_FILTERS,
  LinkFilter,
  PERIODS,
  PlanSummary,
  StatusCount,
  activitiesByPlan,
  calculatedPercent,
  conflictIndex,
  currentPeriod,
  defaultPlanYear,
  externalCode,
  filterActivities,
  linkedTaskCount,
  planYears,
  presentPlanTypes,
  previousPeriod,
  reportedPercent,
  summarizePlan,
  summarizeTaskStatuses,
} from './plans-view';

/** Detail of the activity open in the drawer, with its own load state. */
interface ActivityPanel {
  activity: PlanActivity;
  loading: boolean;
  error: string | null;
  detail: PlanActivityDetail | null;
  tasks: ActivityTask[];
}

/** Linked tasks shown inline per activity row (the rest stay in the drawer). */
const INLINE_TASKS = 4;
/** Parallel `GET .../tasks` while filling the correlation column. */
const TASK_FETCH_CONCURRENCY = 4;

/**
 * «Planes» (change 45c + task N3, PANDORA layout in S07): institutional plans
 * (PSPI, PTR, PAI, PTEP) of the active organization.
 *
 * One screen: filter bar (vigencia, type, report period, correlation with
 * tasks, search, «Solo mías»), plan cards with the two progress figures kept
 * apart (calculated from tasks vs. reported for the period) and how many
 * activities have linked tasks, and the selected plan's activities in a
 * paginated `sol-data-table` whose «Tareas enlazadas» column makes the
 * plan ↔ task correlation visible: role counts, aggregated status, and a
 * direct link to every task (checklist code T-NN + Command key). Activities
 * without tasks and with conflicting source links are flagged.
 *
 * Admins and managers of the active organization (same rule as the backend)
 * report the period's progress and link/unlink tasks from the drawer; every
 * other role sees it read-only. Activity links are never edited here.
 */
@Component({
  selector: 'sol-plans',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    SolBadgeComponent,
    SolButtonComponent,
    SolCardComponent,
    SolDataTableComponent,
    SolDrawerComponent,
    SolEmptyStateComponent,
    SolIconButtonComponent,
    SolProgressBarComponent,
    SolSkeletonComponent,
    PlanReportFormComponent,
    PlanTaskLinksComponent,
    PlansFiltersComponent,
  ],
  styles: [
    `
      .pl-page {
        display: flex;
        flex-direction: column;
        gap: var(--sol-space-lg, 24px);
      }

      .pl-header {
        display: flex;
        flex-direction: column;
        gap: var(--sol-space-xs, 4px);
      }

      .pl-title {
        margin: 0;
        font-size: var(--sol-font-size-xl, 1.25rem);
        color: var(--sol-color-text-primary);
      }

      .pl-muted {
        margin: 0;
        font-size: var(--sol-font-size-sm, 0.875rem);
        color: var(--sol-color-text-secondary);
      }

      .pl-small {
        font-size: var(--sol-font-size-xs, 0.75rem);
        color: var(--sol-color-text-secondary);
      }

      .pl-mono {
        font-family: var(--sol-font-family-mono, ui-monospace, monospace);
        font-size: var(--sol-font-size-xs, 0.75rem);
      }

      .pl-alert {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: var(--sol-space-sm, 8px);
        padding: var(--sol-space-sm, 8px) var(--sol-space-md, 16px);
        border: 1px solid color-mix(in srgb, var(--sol-color-danger) 40%, transparent);
        border-radius: var(--sol-border-radius-md, 8px);
        background: color-mix(in srgb, var(--sol-color-danger) 10%, transparent);
        color: var(--sol-color-danger);
        font-size: var(--sol-font-size-sm, 0.875rem);
      }

      .pl-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: var(--sol-space-sm, 8px);
        padding: var(--sol-space-lg, 24px) var(--sol-space-md, 16px);
        text-align: center;
      }

      .pl-plans {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
        gap: var(--sol-space-md, 16px);
      }

      .pl-plan {
        display: flex;
        flex-direction: column;
        gap: var(--sol-space-sm, 8px);
        width: 100%;
        padding: var(--sol-space-md, 16px);
        border: 1px solid var(--sol-border-color-default);
        border-radius: var(--sol-border-radius-lg, 12px);
        background: var(--sol-bg-surface);
        color: var(--sol-color-text-primary);
        text-align: left;
        cursor: pointer;
        transition: border-color 0.15s ease, box-shadow 0.15s ease;
      }

      .pl-plan:hover {
        border-color: var(--sol-color-primary);
      }

      .pl-plan:focus-visible {
        outline: 2px solid var(--sol-color-primary);
        outline-offset: 2px;
      }

      .pl-plan[aria-pressed='true'] {
        border-color: var(--sol-color-primary);
        box-shadow: 0 0 0 1px var(--sol-color-primary);
      }

      .pl-plan__top {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: var(--sol-space-sm, 8px);
      }

      .pl-plan__name {
        margin: 2px 0 0;
        font-size: var(--sol-font-size-md, 1rem);
        font-weight: 600;
        line-height: 1.3;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
      }

      .pl-figures {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: var(--sol-space-sm, 8px);
      }

      .pl-figure__value {
        margin: 0;
        font-size: var(--sol-font-size-lg, 1.125rem);
        font-weight: 600;
      }

      .pl-figure__value--none {
        font-size: var(--sol-font-size-sm, 0.875rem);
        font-weight: 500;
        color: var(--sol-color-text-secondary);
      }

      .pl-chips {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: var(--sol-space-xs, 4px) var(--sol-space-sm, 8px);
      }

      .pl-detail-head {
        display: flex;
        flex-wrap: wrap;
        align-items: baseline;
        justify-content: space-between;
        gap: var(--sol-space-sm, 8px);
        margin-bottom: var(--sol-space-sm, 8px);
      }

      .pl-detail-title {
        margin: 0;
        font-size: var(--sol-font-size-lg, 1.125rem);
        font-weight: 600;
        color: var(--sol-color-text-primary);
      }

      .pl-summary {
        margin-bottom: var(--sol-space-md, 16px);
      }

      /* El ResizeObserver de la tabla mide el host: inline mediría 0 y colapsaría siempre. */
      .pl-table {
        display: block;
      }

      .pl-cell {
        display: flex;
        flex-direction: column;
        gap: 2px;
        min-width: 0;
      }

      .pl-key {
        padding: 0;
        border: 0;
        background: none;
        color: var(--sol-color-primary);
        cursor: pointer;
        text-align: left;
      }

      .pl-key:hover {
        text-decoration: underline;
      }

      .pl-activity-name {
        color: var(--sol-color-text-primary);
        font-size: var(--sol-font-size-sm, 0.875rem);
        line-height: 1.35;
      }

      .pl-progress {
        min-width: 120px;
      }

      .pl-tasks {
        display: flex;
        flex-direction: column;
        gap: var(--sol-space-xs, 4px);
        min-width: 0;
      }

      /* En la tarjeta colapsada (móvil) los textos largos se parten en vez de recortarse. */
      .pl-cell,
      .pl-tasks {
        white-space: normal;
        overflow-wrap: anywhere;
      }

      @media (min-width: 1024px) {
        .pl-tasks {
          min-width: 220px;
        }
      }

      .pl-task-list {
        display: flex;
        flex-direction: column;
        gap: 2px;
        margin: 0;
        padding: 0;
        list-style: none;
      }

      .pl-task-link {
        color: var(--sol-color-primary);
        text-decoration: none;
        font-size: var(--sol-font-size-xs, 0.75rem);
      }

      .pl-task-link:hover,
      .pl-task-link:focus-visible {
        text-decoration: underline;
      }

      .pl-link-button {
        padding: 0;
        border: 0;
        background: none;
        color: var(--sol-color-primary);
        font-size: var(--sol-font-size-xs, 0.75rem);
        cursor: pointer;
        text-align: left;
      }

      .pl-drawer {
        display: flex;
        flex-direction: column;
        gap: var(--sol-space-lg, 20px);
      }

      .pl-section-title {
        margin: 0 0 var(--sol-space-sm, 8px);
        font-size: var(--sol-font-size-sm, 0.875rem);
        font-weight: 600;
        color: var(--sol-color-text-primary);
      }

      .pl-facts {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: var(--sol-space-sm, 8px) var(--sol-space-md, 16px);
        margin: 0;
        font-size: var(--sol-font-size-sm, 0.875rem);
      }

      .pl-facts dt {
        font-size: var(--sol-font-size-xs, 0.75rem);
        color: var(--sol-color-text-secondary);
      }

      .pl-facts dd {
        margin: 0;
        color: var(--sol-color-text-primary);
        white-space: pre-line;
      }

      .pl-facts .pl-wide {
        grid-column: 1 / -1;
      }

      .pl-box {
        padding: var(--sol-space-sm, 8px) var(--sol-space-md, 12px);
        border: 1px solid var(--sol-border-color-default);
        border-radius: var(--sol-border-radius-md, 8px);
        font-size: var(--sol-font-size-sm, 0.875rem);
      }

      .pl-box--warning {
        border-color: var(--sol-color-warning);
        background: color-mix(in srgb, var(--sol-color-warning) 10%, transparent);
      }

      .pl-links {
        display: flex;
        flex-direction: column;
        gap: var(--sol-space-sm, 8px);
        margin: 0;
        padding: 0;
        list-style: none;
      }
    `,
  ],
  template: `
    <section class="pl-page">
      <header class="pl-header">
        <h1 class="pl-title sol-display">{{ text.title() }}</h1>
        <p class="pl-muted" aria-live="polite">
          @if (!loading() && !loadError() && plans().length > 0) {
            {{ countText() }}
          } @else {
            {{ text.subtitle() }}
          }
        </p>
      </header>

      @if (loading()) {
        <div class="pl-plans" aria-busy="true">
          <span class="sr-only" role="status">{{ text.loading() }}</span>
          <sol-skeleton variant="card" />
          <sol-skeleton variant="card" />
          <sol-skeleton variant="card" />
        </div>
      } @else if (loadError(); as message) {
        <!-- Error de carga: nunca se confunde con «no hay planes». -->
        <div class="pl-alert" role="alert">
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
        <sol-plans-filters
          [controls]="filters"
          [yearOptions]="yearOptions()"
          [typeOptions]="typeOptions()"
          [periodOptions]="periodOptions()"
          [linkOptions]="linkOptions()"
          [activeCount]="activeFilterCount()"
          (cleared)="clearFilters()"
        />

        @if (activitiesError(); as message) {
          <div class="pl-alert" role="alert">
            <span>{{ message }}</span>
            <sol-button type="button" variant="secondary" size="sm" (clicked)="loadActivities()">
              {{ text.retry() }}
            </sol-button>
          </div>
        }

        @if (visiblePlans().length === 0) {
          <sol-card>
            <div class="pl-state" role="status">
              <p class="pl-activity-name">{{ text.noPlansForFilters() }}</p>
              <sol-button type="button" variant="secondary" size="sm" (clicked)="clearFilters()">
                {{ text.clearFilters() }}
              </sol-button>
            </div>
          </sol-card>
        } @else {
          <!-- Tarjetas de planes -->
          <div class="pl-plans">
            @for (plan of visiblePlans(); track plan.id) {
              <button
                type="button"
                class="pl-plan"
                [attr.aria-pressed]="selectedPlan()?.id === plan.id"
                (click)="selectPlan(plan.id)"
              >
                <div class="pl-plan__top">
                  <div>
                    <span class="pl-mono pl-small">{{ plan.code }}</span>
                    <p class="pl-plan__name" [attr.title]="plan.name">{{ plan.name }}</p>
                  </div>
                  <sol-badge variant="info" size="sm">{{ typeLabel(plan.plan_type) }}</sol-badge>
                </div>
                <span class="pl-small">
                  {{ yearLabel(plan.period_year) }} · {{ statusLabel(plan.status) }} ·
                  {{ activityCountLabel(summaryOf(plan).activityCount) }}
                </span>

                @if (activitiesLoading()) {
                  <sol-skeleton variant="text" [count]="2" />
                } @else if (!activitiesError()) {
                  <div class="pl-figures">
                    <div>
                      <span class="pl-small">{{ text.calculated() }}</span>
                      @if (summaryOf(plan).calculatedAverage !== null) {
                        <p class="pl-figure__value">{{ summaryOf(plan).calculatedAverage }} %</p>
                      } @else {
                        <p class="pl-figure__value pl-figure__value--none">{{ text.noTasks() }}</p>
                      }
                    </div>
                    <div>
                      <span class="pl-small">{{ reportedTitle() }}</span>
                      @if (summaryOf(plan).reportedAverage !== null) {
                        <p class="pl-figure__value">{{ summaryOf(plan).reportedAverage }} %</p>
                      } @else {
                        <p class="pl-figure__value pl-figure__value--none">{{ text.noReport() }}</p>
                      }
                    </div>
                  </div>
                  <sol-progress-bar
                    size="sm"
                    [value]="summaryOf(plan).calculatedAverage ?? 0"
                    [variant]="progressVariant(summaryOf(plan).calculatedAverage)"
                    [ariaLabel]="calculatedAria(plan)"
                  />
                  <div class="pl-chips">
                    <span class="pl-small">{{ linkedActivitiesLabel(summaryOf(plan)) }}</span>
                    @if (summaryOf(plan).activityCount - summaryOf(plan).linkedActivities > 0) {
                      <sol-badge variant="warning" size="sm">
                        {{ unlinkedLabel(summaryOf(plan).activityCount - summaryOf(plan).linkedActivities) }}
                      </sol-badge>
                    }
                  </div>
                }
              </button>
            }
          </div>

          <!-- Actividades del plan seleccionado -->
          @if (selectedPlan(); as plan) {
            <sol-card>
              <div class="pl-detail-head">
                <h2 class="pl-detail-title">
                  <span class="pl-mono pl-small">{{ plan.code }}</span>
                  {{ plan.name }}
                </h2>
                @if (!activitiesLoading() && !activitiesError()) {
                  <span class="pl-small" role="status">
                    {{ shownLabel(selectedActivities().length, selectedPlanActivityCount()) }}
                  </span>
                }
              </div>

              @if (!activitiesLoading() && !activitiesError() && selectedPlanActivityCount() > 0) {
                <div class="pl-chips pl-summary">
                  <span class="pl-small">{{ linkedActivitiesLabel(summaryOf(plan)) }}</span>
                  <sol-badge variant="info" size="sm">{{ taskLinksLabel(summaryOf(plan).taskLinks) }}</sol-badge>
                  @if (selectedUnlinked() > 0) {
                    <sol-badge variant="warning" size="sm">{{ unlinkedLabel(selectedUnlinked()) }}</sol-badge>
                  }
                  @if (selectedConflicts() > 0) {
                    <sol-badge variant="warning" size="sm">{{ conflictActivitiesLabel(selectedConflicts()) }}</sol-badge>
                  }
                </div>
              }

              @if (activitiesLoading()) {
                <sol-skeleton variant="row" [count]="4" />
              } @else if (activitiesError()) {
                <p class="pl-muted">{{ text.activitiesUnavailable() }}</p>
              } @else if (selectedPlanActivityCount() === 0) {
                <p class="pl-muted">{{ text.planWithoutActivities() }}</p>
              } @else if (selectedActivities().length === 0) {
                <div class="pl-state" role="status">
                  <p class="pl-activity-name">{{ text.noResults() }}</p>
                  <sol-button type="button" variant="secondary" size="sm" (clicked)="clearFilters()">
                    {{ text.clearFilters() }}
                  </sol-button>
                </div>
              } @else {
                <sol-data-table
                  class="pl-table"
                  [data]="activityRows()"
                  [columns]="activityColumns()"
                  [emptyMessage]="text.noResults()"
                  [paginated]="true"
                  [showToolbar]="false"
                  [showActions]="true"
                  [actionsLabel]="text.actions()"
                  actionsPosition="start"
                  [collapseWidth]="760"
                  trackByKey="id"
                >
                  <ng-template #rowActions let-row>
                    <sol-icon-button
                      icon="eye"
                      variant="outline"
                      [ariaLabel]="openActivityAria($any(row).key)"
                      (clicked)="openActivityById($any(row).id)"
                    />
                  </ng-template>
                </sol-data-table>
              }
            </sol-card>
          }
        }

        <p class="pl-small">{{ canWrite() ? text.writeNote() : text.readOnlyNote() }}</p>
      }
    </section>

    <!-- Celdas de la tabla de actividades -->
    <ng-template #activityCell let-row="row">
      <div class="pl-cell">
        <button
          type="button"
          class="pl-key pl-mono"
          [attr.aria-label]="openActivityAria($any(row).key)"
          (click)="openActivityById($any(row).id)"
        >{{ $any(row).key }}</button>
        <span class="pl-activity-name">{{ $any(row).name }}</span>
        <span class="pl-small">{{ $any(row).group }}</span>
        @if ($any(row).mine || $any(row).conflicts > 0) {
          <span class="pl-chips">
            @if ($any(row).mine) {
              <sol-badge variant="info" size="sm">{{ text.mine() }}</sol-badge>
            }
            @if ($any(row).conflicts > 0) {
              <sol-badge variant="warning" size="sm">{{ conflictLabel($any(row).conflicts) }}</sol-badge>
            }
          </span>
        }
      </div>
    </ng-template>

    <ng-template #calculatedCell let-row="row">
      @if ($any(row).calc === null) {
        <span class="pl-small">{{ text.noTasks() }}</span>
      } @else {
        <div class="pl-progress">
          <sol-progress-bar
            size="sm"
            [value]="$any(row).calc"
            [variant]="progressVariant($any(row).calc)"
            [showLabel]="true"
            [ariaLabel]="text.calculated()"
          />
        </div>
      }
    </ng-template>

    <ng-template #reportedCell let-row="row">
      <span [class.pl-small]="$any(row).reported === null">
        {{ $any(row).reported === null ? text.noReport() : $any(row).reported + ' %' }}
      </span>
    </ng-template>

    <ng-template #tasksCell let-row="row">
      <div class="pl-tasks">
        @if ($any(row).linked === 0) {
          <span><sol-badge variant="warning" size="sm">{{ text.noLinkedTasks() }}</sol-badge></span>
        } @else {
          <span class="pl-small">{{ roleCountsLabel($any(row).primary, $any(row).contributes) }}</span>
          @switch (taskState($any(row).id)) {
            @case ('loading') {
              <span class="pl-small" role="status">{{ text.tasksLoading() }}</span>
            }
            @case ('error') {
              <span class="pl-small">
                {{ text.tasksFailed() }}
                <button type="button" class="pl-link-button" (click)="retryTasks($any(row).id)">
                  {{ text.retry() }}
                </button>
              </span>
            }
            @default {
              <span class="pl-chips">
                @for (status of statusesOf($any(row).id); track status.status) {
                  <sol-badge [variant]="status.tone" size="sm">{{ status.count }} {{ taskStatusLabel(status.status) }}</sol-badge>
                }
              </span>
              <ul class="pl-task-list">
                @for (task of inlineTasks($any(row).id); track task.task_id) {
                  <li>
                    @if (task.task_key) {
                      <a
                        class="pl-task-link"
                        [routerLink]="['/task', task.task_key]"
                        [attr.title]="task.title"
                        [attr.aria-label]="taskLinkAria(task)"
                      ><span class="pl-mono">{{ taskCode(task) }}</span> · {{ task.title }}</a>
                    } @else {
                      <span class="pl-small">{{ task.title }}</span>
                    }
                  </li>
                }
              </ul>
              @if (hiddenTasks($any(row).id) > 0) {
                <button type="button" class="pl-link-button" (click)="openActivityById($any(row).id)">
                  {{ moreTasksLabel(hiddenTasks($any(row).id)) }}
                </button>
              }
            }
          }
        }
      </div>
    </ng-template>

    <!-- Detalle de la actividad -->
    <sol-drawer
      [open]="panel() !== null"
      [title]="panelTitle()"
      size="lg"
      (closed)="closeActivity()"
    >
      @if (panel(); as p) {
        <div class="pl-drawer">
          <div class="pl-cell">
            <span class="pl-mono" style="color: var(--sol-color-primary)">
              {{ p.activity.activity_key ?? p.activity.code }}
            </span>
            <span class="pl-activity-name">{{ p.activity.name }}</span>
            @if (p.activity.group_name || p.activity.group_code) {
              <span class="pl-small">{{ groupTitle(p.activity.group_code, p.activity.group_name) }}</span>
            }
          </div>

          <div class="pl-figures">
            <div>
              <span class="pl-small">{{ text.calculated() }}</span>
              <p class="pl-figure__value" [class.pl-figure__value--none]="calcPercent(p.activity) === null">
                {{ calcLabel(p.activity) }}
              </p>
            </div>
            <div>
              <span class="pl-small">{{ reportedTitle() }}</span>
              <p class="pl-figure__value" [class.pl-figure__value--none]="reportedPercentOf(p.activity) === null">
                {{ reportedLabel(p.activity) }}
              </p>
            </div>
          </div>

          <dl class="pl-facts">
            <div>
              <dt>{{ text.fields.responsible() }}</dt>
              <dd>{{ p.activity.responsible || text.noResponsible() }}</dd>
            </div>
            <div>
              <dt>{{ text.fields.dueDate() }}</dt>
              <dd>{{ formatDate(p.activity.due_date) }}</dd>
            </div>
            <div>
              <dt>{{ text.fields.periods() }}</dt>
              <dd>{{ periodsList(p.activity.scheduled_periods) || '—' }}</dd>
            </div>
            @if (p.activity.iso_controls?.length) {
              <div>
                <dt>{{ text.fields.iso() }}</dt>
                <dd>{{ p.activity.iso_controls!.join(', ') }}</dd>
              </div>
            }
            @if (p.activity.deliverable) {
              <div class="pl-wide">
                <dt>{{ text.fields.deliverable() }}</dt>
                <dd>{{ p.activity.deliverable }}</dd>
              </div>
            }
            @if (p.activity.evidence_expected) {
              <div class="pl-wide">
                <dt>{{ text.fields.evidence() }}</dt>
                <dd>{{ p.activity.evidence_expected }}</dd>
              </div>
            }
          </dl>

          @if (p.loading) {
            <sol-skeleton variant="row" [count]="3" />
          } @else if (p.error) {
            <div class="pl-alert" role="alert">
              <span>{{ p.error }}</span>
              <sol-button type="button" variant="secondary" size="sm" (clicked)="openActivity(p.activity)">
                {{ text.retry() }}
              </sol-button>
            </div>
          } @else if (p.detail; as detail) {
            <!-- Tareas vinculadas: primero, es la correlación que se viene a revisar. -->
            <sol-plan-task-links
              [activityId]="detail.id"
              [tasks]="p.tasks"
              [canWrite]="canWrite()"
              (changed)="onTasksChanged($event)"
            />

            <!-- Reporte del periodo -->
            <section>
              <h3 class="pl-section-title">{{ reportSectionTitle() }}</h3>
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
                <div class="pl-box">
                  <p class="pl-activity-name">
                    {{ text.report.met() }}: {{ yesNo(report.is_met) }} ·
                    {{ text.report.onTime() }}: {{ yesNo(report.met_on_time) }}
                  </p>
                  @if (report.qualitative_summary) {
                    <p class="pl-muted" style="white-space: pre-line">{{ report.qualitative_summary }}</p>
                  }
                  @if (report.evidence_refs?.length) {
                    <p class="pl-small">{{ text.report.evidence() }}: {{ report.evidence_refs!.join(', ') }}</p>
                  }
                </div>
              } @else {
                <p class="pl-muted">{{ text.noReport() }}</p>
              }
            </section>

            <!-- Vínculos con otras actividades -->
            @if (detail.links_out.length || detail.links_in.length) {
              <section>
                <h3 class="pl-section-title">{{ text.links.title() }}</h3>
                <ul class="pl-links">
                  @for (link of detail.links_out; track link.id) {
                    <li class="pl-box" [class.pl-box--warning]="!link.is_confirmed">
                      <p class="pl-activity-name">
                        {{ linkTypeLabel(link.link_type) }}
                        <span class="pl-mono" style="color: var(--sol-color-primary)">{{ activityRef(link.to_activity_id) }}</span>
                      </p>
                      @if (!link.is_confirmed) {
                        <sol-badge variant="warning" size="sm">{{ text.links.conflict() }}</sol-badge>
                      }
                      @if (link.source_reference) {
                        <p class="pl-small">{{ text.links.sourceText() }}: «{{ link.source_reference }}»</p>
                      }
                    </li>
                  }
                  @for (link of detail.links_in; track link.id) {
                    <li class="pl-box" [class.pl-box--warning]="!link.is_confirmed">
                      <p class="pl-activity-name">
                        {{ text.links.incoming() }}
                        <span class="pl-mono" style="color: var(--sol-color-primary)">{{ activityRef(link.from_activity_id) }}</span>
                        <span class="pl-small">({{ linkTypeLabel(link.link_type) }})</span>
                      </p>
                      @if (!link.is_confirmed) {
                        <sol-badge variant="warning" size="sm">{{ text.links.conflict() }}</sol-badge>
                      }
                      @if (link.source_reference) {
                        <p class="pl-small">{{ text.links.sourceText() }}: «{{ link.source_reference }}»</p>
                      }
                    </li>
                  }
                </ul>
              </section>
            }
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
    clearFilters: this.i18n.t('plans.filters.clear'),
    calculated: this.i18n.t('plans.progress.calculated'),
    noTasks: this.i18n.t('plans.progress.noTasks'),
    noReport: this.i18n.t('plans.progress.noReport'),
    noResults: this.i18n.t('plans.states.noResults'),
    noPlansForFilters: this.i18n.t('plans.states.noPlansForFilters'),
    planWithoutActivities: this.i18n.t('plans.states.planWithoutActivities'),
    activitiesUnavailable: this.i18n.t('plans.states.activitiesUnavailable'),
    readOnlyNote: this.i18n.t('plans.readOnlyNote'),
    writeNote: this.i18n.t('plans.writeNote'),
    mine: this.i18n.t('plans.activity.mine'),
    noResponsible: this.i18n.t('plans.activity.noResponsible'),
    actions: this.i18n.t('plans.table.actions'),
    noLinkedTasks: this.i18n.t('plans.correlation.noTasks'),
    tasksLoading: this.i18n.t('plans.correlation.loading'),
    tasksFailed: this.i18n.t('plans.correlation.failed'),
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

  // --- Filtros (los posee la página; la barra es presentacional) ----------

  /** Smart default del periodo: el cuatrimestre actual (I ene–abr, II may–ago, III sep–dic). */
  protected readonly filters: PlansFilterControls = {
    year: new FormControl('', { nonNullable: true }),
    type: new FormControl('', { nonNullable: true }),
    period: new FormControl<string>(currentPeriod(new Date()), { nonNullable: true }),
    link: new FormControl<string>('all', { nonNullable: true }),
    q: new FormControl('', { nonNullable: true }),
    mine: new FormControl(false, { nonNullable: true }),
  };

  private readonly yearValue = toSignal(
    this.filters.year.valueChanges.pipe(startWith(this.filters.year.value)),
    { initialValue: '' },
  );
  private readonly typeValue = toSignal(
    this.filters.type.valueChanges.pipe(startWith(this.filters.type.value)),
    { initialValue: '' },
  );
  private readonly linkValue = toSignal(
    this.filters.link.valueChanges.pipe(startWith(this.filters.link.value)),
    { initialValue: 'all' },
  );
  protected readonly onlyMine = toSignal(
    this.filters.mine.valueChanges.pipe(startWith(this.filters.mine.value)),
    { initialValue: false },
  );
  protected readonly query = toSignal(
    this.filters.q.valueChanges.pipe(debounceTime(250), distinctUntilChanged()),
    { initialValue: '' },
  );

  protected readonly period = signal<ReportPeriod>(this.filters.period.value as ReportPeriod);
  /** Vigencia natural (año actual con planes o el más reciente); «Limpiar» vuelve aquí. */
  private readonly naturalYear = signal<number | null>(null);

  protected readonly plans = signal<Plan[]>([]);
  protected readonly activities = signal<PlanActivity[]>([]);
  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);
  protected readonly activitiesLoading = signal(false);
  protected readonly activitiesError = signal<string | null>(null);

  private readonly selectedPlanId = signal<string | null>(null);

  /** activity id → number of `conflict` links (either end). */
  private readonly conflicts = signal<Map<string, number>>(new Map());
  private readonly memberships = signal<OrganizationMembership[]>([]);

  /** Linked tasks per activity (correlation column), cached by activity id. */
  private readonly taskMap = signal<Map<string, ActivityTask[]>>(new Map());
  private readonly taskLoading = signal<Set<string>>(new Set());
  private readonly taskErrors = signal<Set<string>>(new Set());
  private tasksSub: Subscription | null = null;

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

  // --- Opciones de la barra ----------------------------------------------

  protected readonly yearOptions = computed<SolSelectOption[]>(() =>
    planYears(this.plans()).map((year) => ({ value: String(year), label: String(year) })),
  );

  protected readonly typeOptions = computed<SolSelectOption[]>(() => {
    this.i18n.activeLang();
    return presentPlanTypes(this.plans()).map((type) => ({ value: type, label: this.typeLabel(type) }));
  });

  protected readonly periodOptions = computed<SolSelectOption[]>(() => {
    this.i18n.activeLang();
    return PERIODS.map((period) => ({ value: period, label: this.periodLabel(period) }));
  });

  protected readonly linkOptions = computed<SolSelectOption[]>(() => {
    this.i18n.activeLang();
    return LINK_FILTERS.map((value) => ({
      value,
      label: this.translate(`plans.correlation.filter.${value}`),
    }));
  });

  protected readonly activeFilterCount = computed(() => {
    const natural = this.naturalYear();
    const year = this.yearValue();
    let count = 0;
    if (natural !== null && year !== String(natural)) {
      count++;
    }
    if (this.typeValue()) {
      count++;
    }
    if (this.linkValue() !== 'all') {
      count++;
    }
    if (this.query().trim()) {
      count++;
    }
    if (this.onlyMine()) {
      count++;
    }
    return count;
  });

  // --- Datos derivados ----------------------------------------------------

  protected readonly visiblePlans = computed(() => {
    const year = this.yearValue();
    const type = this.typeValue();
    return this.plans().filter(
      (plan) => (!year || String(plan.period_year) === year) && (!type || plan.plan_type === type),
    );
  });

  protected readonly countText = computed(() => {
    const visible = this.visiblePlans().length;
    const year = this.yearValue();
    if (year) {
      return this.translate(visible === 1 ? 'plans.count.yearOne' : 'plans.count.yearOther', {
        n: visible,
        year,
      });
    }
    return this.translate(visible === 1 ? 'plans.count.one' : 'plans.count.other', { n: visible });
  });

  private readonly byPlan = computed(() => activitiesByPlan(this.activities()));

  private readonly summaries = computed(() => {
    const summaries = new Map<string, PlanSummary>();
    for (const plan of this.plans()) {
      summaries.set(plan.id, summarizePlan(this.byPlan().get(plan.id) ?? []));
    }
    return summaries;
  });

  /**
   * Selected plan. Smart default (nothing starts empty): the visible plan with
   * the most task links, so the correlation is the first thing on screen.
   */
  protected readonly selectedPlan = computed<Plan | null>(() => {
    const visible = this.visiblePlans();
    const id = this.selectedPlanId();
    const chosen = visible.find((plan) => plan.id === id);
    if (chosen) {
      return chosen;
    }
    return visible.reduce<Plan | null>(
      (best, plan) =>
        best === null || this.summaryOf(plan).taskLinks > this.summaryOf(best).taskLinks ? plan : best,
      null,
    );
  });

  private readonly selectedPlanActivities = computed(
    () => this.byPlan().get(this.selectedPlan()?.id ?? '') ?? [],
  );

  protected readonly selectedPlanActivityCount = computed(() => this.selectedPlanActivities().length);

  protected readonly selectedUnlinked = computed(
    () => this.selectedPlanActivities().filter((activity) => linkedTaskCount(activity) === 0).length,
  );

  protected readonly selectedConflicts = computed(
    () => this.selectedPlanActivities().filter((activity) => this.conflictsOf(activity.id) > 0).length,
  );

  /** Searchable codes of the linked tasks (Command key and T-NN). */
  private readonly taskCodes = computed(() => {
    const codes = new Map<string, string[]>();
    for (const [id, tasks] of this.taskMap()) {
      codes.set(
        id,
        tasks.flatMap((task) => [task.task_key, externalCode(task)]).filter((v): v is string => !!v),
      );
    }
    return codes;
  });

  protected readonly selectedActivities = computed(() =>
    filterActivities(this.selectedPlanActivities(), {
      onlyMine: this.onlyMine(),
      query: this.query(),
      link: this.linkValue() as LinkFilter,
      conflicts: this.conflicts(),
      taskCodes: this.taskCodes(),
    }),
  );

  /** id → activity, to name the other end of an activity link. */
  private readonly activityIndex = computed(
    () => new Map(this.activities().map((activity) => [activity.id, activity])),
  );

  // --- Tabla de actividades ----------------------------------------------

  private readonly activityCell = viewChild<TemplateRef<unknown>>('activityCell');
  private readonly calculatedCell = viewChild<TemplateRef<unknown>>('calculatedCell');
  private readonly reportedCell = viewChild<TemplateRef<unknown>>('reportedCell');
  private readonly tasksCell = viewChild<TemplateRef<unknown>>('tasksCell');

  protected readonly activityColumns = computed<DataTableColumn[]>(() => {
    this.i18n.activeLang();
    return [
      { key: 'key', label: this.translate('plans.table.activity'), sortable: true, cellTemplate: this.activityCell() as DataTableColumn['cellTemplate'] },
      { key: 'responsible', label: this.translate('plans.fields.responsible'), sortable: true },
      { key: 'calc_sort', label: this.translate('plans.progress.calculatedShort'), sortable: true, cellTemplate: this.calculatedCell() as DataTableColumn['cellTemplate'] },
      { key: 'reported_sort', label: this.reportedShortTitle(), sortable: true, cellTemplate: this.reportedCell() as DataTableColumn['cellTemplate'] },
      { key: 'linked', label: this.translate('plans.table.tasks'), sortable: true, cellTemplate: this.tasksCell() as DataTableColumn['cellTemplate'] },
    ];
  });

  /** Flat rows: labels resolved and numeric sort keys (null sorts last). */
  protected readonly activityRows = computed<SolDataTableRow[]>(() => {
    this.i18n.activeLang();
    return this.selectedActivities().map((activity) => {
      const calc = calculatedPercent(activity);
      const reported = reportedPercent(activity);
      return {
        id: activity.id,
        key: activity.activity_key ?? activity.code,
        name: activity.name,
        group: this.groupTitle(activity.group_code, activity.group_name),
        responsible: activity.responsible || this.translate('plans.activity.noResponsible'),
        mine: activity.is_mine,
        conflicts: this.conflictsOf(activity.id),
        calc,
        calc_sort: calc ?? -1,
        reported,
        reported_sort: reported ?? -1,
        primary: activity.primary_task_count,
        contributes: activity.contributing_task_count,
        linked: linkedTaskCount(activity),
      };
    });
  });

  // --- Títulos dependientes del periodo ----------------------------------

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

  constructor() {
    this.filters.period.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => this.setPeriod(value as ReportPeriod));

    // Correlation column: fetch the linked tasks of the selected plan's
    // activities that have any (cached; a write refreshes its activity).
    effect(() => {
      const activities = this.selectedPlanActivities();
      if (this.loading() || this.activitiesLoading()) {
        return;
      }
      untracked(() => this.loadTasks(activities));
    });
  }

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
          this.applyNaturalYear(plans.data);
          this.loading.set(false);
        },
        error: (err: unknown) => {
          this.loading.set(false);
          this.loadError.set(this.errorMessage(err, 'plans.errors.loadFailed'));
        },
      });
  }

  /** Preselects the vigencia once (current year with plans, else the newest). */
  private applyNaturalYear(plans: Plan[]): void {
    const natural = defaultPlanYear(planYears(plans), new Date());
    const first = this.naturalYear() === null;
    this.naturalYear.set(natural);
    // A selected plan from the URL keeps its own year visible.
    const fromUrl = plans.find((plan) => plan.id === this.selectedPlanId());
    if (first && natural !== null) {
      this.filters.year.setValue(String(fromUrl?.period_year ?? natural));
    }
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

  /** Linked tasks of the activities with links that are not cached yet. */
  private loadTasks(activities: PlanActivity[]): void {
    const cached = this.taskMap();
    const busy = this.taskLoading();
    const errors = this.taskErrors();
    const ids = activities
      .filter((a) => linkedTaskCount(a) > 0 && !cached.has(a.id) && !busy.has(a.id) && !errors.has(a.id))
      .map((a) => a.id);
    if (ids.length === 0) {
      return;
    }
    this.taskLoading.update((set) => new Set([...set, ...ids]));
    from(ids)
      .pipe(
        mergeMap(
          (id) =>
            this.plansService.activityTasks(id).pipe(
              map((res) => ({ id, tasks: res.data as ActivityTask[] | null })),
              catchError(() => of({ id, tasks: null as ActivityTask[] | null })),
            ),
          TASK_FETCH_CONCURRENCY,
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(({ id, tasks }) => {
        this.taskLoading.update((set) => {
          const next = new Set(set);
          next.delete(id);
          return next;
        });
        if (tasks === null) {
          this.taskErrors.update((set) => new Set([...set, id]));
        } else {
          this.setTasks(id, tasks);
        }
      });
  }

  private setTasks(activityId: string, tasks: ActivityTask[]): void {
    this.taskMap.update((current) => new Map(current).set(activityId, tasks));
  }

  protected retryTasks(activityId: string): void {
    this.taskErrors.update((set) => {
      const next = new Set(set);
      next.delete(activityId);
      return next;
    });
    const activity = this.activityIndex().get(activityId);
    if (activity) {
      this.loadTasks([activity]);
    }
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
    const natural = this.naturalYear();
    this.filters.year.setValue(natural === null ? '' : String(natural));
    this.filters.type.setValue('');
    this.filters.link.setValue('all');
    this.filters.q.setValue('');
    this.filters.mine.setValue(false);
  }

  protected openActivityById(id: string): void {
    const activity = this.activityIndex().get(id);
    if (activity) {
      this.openActivity(activity);
    }
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
          // The drawer's list is the freshest: the table row follows it.
          this.setTasks(activity.id, tasks.data);
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
        linkedActivities: 0,
        taskLinks: 0,
      }
    );
  }

  /** Row's correlation state: tasks loading, failed, or ready (cached). */
  protected taskState(activityId: string): 'loading' | 'error' | 'ready' {
    if (this.taskErrors().has(activityId)) {
      return 'error';
    }
    return this.taskMap().has(activityId) ? 'ready' : 'loading';
  }

  protected statusesOf(activityId: string): StatusCount[] {
    return summarizeTaskStatuses(this.taskMap().get(activityId) ?? []);
  }

  protected inlineTasks(activityId: string): ActivityTask[] {
    return (this.taskMap().get(activityId) ?? []).slice(0, INLINE_TASKS);
  }

  protected hiddenTasks(activityId: string): number {
    return Math.max(0, (this.taskMap().get(activityId)?.length ?? 0) - INLINE_TASKS);
  }

  /** «T-07 · SGSI-12»: the checklist code first when the task has one. */
  protected taskCode(task: ActivityTask): string {
    const code = externalCode(task);
    return code && task.task_key ? `${code} · ${task.task_key}` : (task.task_key ?? code ?? '');
  }

  protected taskLinkAria(task: ActivityTask): string {
    return this.translate('plans.correlation.openTaskAria', {
      code: this.taskCode(task),
      title: task.title ?? '',
      role: this.labelOr(`plans.tasksSection.roles.${task.role}`, task.role),
    });
  }

  /** Only enum codes (`in_progress`) have a label; board names («En curso») show as they are. */
  protected taskStatusLabel(status: string): string {
    return /^[a-z_]+$/.test(status) ? this.labelOr(`plans.taskStatus.${status}`, status) : status;
  }

  protected progressVariant(percent: number | null): 'primary' | 'success' | 'warning' {
    if (percent === null) {
      return 'primary';
    }
    return percent >= 100 ? 'success' : percent < 25 ? 'warning' : 'primary';
  }

  protected calculatedAria(plan: Plan): string {
    const value = this.summaryOf(plan).calculatedAverage;
    return `${this.translate('plans.progress.calculated')}: ${
      value === null ? this.translate('plans.progress.noTasks') : `${value} %`
    }`;
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

  protected yearLabel(year: number): string {
    return this.translate('plans.card.year', { year });
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
    return name || code || this.translate('plans.activity.noGroup');
  }

  protected activityCountLabel(count: number): string {
    return this.translate(count === 1 ? 'plans.card.activityOne' : 'plans.card.activities', {
      n: count,
    });
  }

  protected linkedActivitiesLabel(summary: PlanSummary): string {
    return this.translate('plans.correlation.linkedActivities', {
      n: summary.linkedActivities,
      total: summary.activityCount,
    });
  }

  protected taskLinksLabel(count: number): string {
    return this.translate(count === 1 ? 'plans.correlation.linksOne' : 'plans.correlation.linksOther', {
      n: count,
    });
  }

  protected unlinkedLabel(count: number): string {
    return this.translate(count === 1 ? 'plans.correlation.unlinkedOne' : 'plans.correlation.unlinkedOther', {
      n: count,
    });
  }

  protected conflictActivitiesLabel(count: number): string {
    return this.translate(
      count === 1 ? 'plans.correlation.conflictActivitiesOne' : 'plans.correlation.conflictActivitiesOther',
      { n: count },
    );
  }

  protected roleCountsLabel(primary: number, contributes: number): string {
    return this.translate('plans.correlation.roleCounts', { primary, contributes });
  }

  protected moreTasksLabel(count: number): string {
    return this.translate('plans.correlation.more', { n: count });
  }

  protected shownLabel(shown: number, total: number): string {
    return this.translate('plans.detail.shown', { n: shown, total });
  }

  protected calcLabel(activity: PlanActivity): string {
    const percent = calculatedPercent(activity);
    return percent === null ? this.translate('plans.progress.noTasks') : `${percent} %`;
  }

  protected reportedLabel(activity: PlanActivity): string {
    const percent = reportedPercent(activity);
    return percent === null ? this.translate('plans.progress.noReport') : `${percent} %`;
  }

  protected reportedPercentOf(activity: PlanActivity): number | null {
    return reportedPercent(activity);
  }

  protected openActivityAria(key: string): string {
    return this.translate('plans.activity.openAria', { key });
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
