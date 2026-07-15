import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import {
  FormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import {
  DragDropModule,
  moveItemInArray,
  transferArrayItem,
} from '@angular/cdk/drag-drop';
import { SolButtonComponent } from '@shared/ui';
import { SolCardComponent } from '@shared/ui';
import { SolModalComponent } from '@shared/ui';
import { SolTableComponent } from '@shared/ui/table.component';
import { I18nService } from '@shared/i18n';
import { ProjectsService } from '@entities/project/projects.service';
import { EstimationMode, ProjectDetail } from '@entities/project/project.model';
import { WorkspaceService } from '@entities/workspace/workspace.service';
import {
  BoardColumnComponent,
  ColumnDrop,
} from '@widgets/board-column/board-column.component';
import { TaskCardComponent } from '@widgets/task-card/task-card.component';
import { BurndownChartComponent } from '@widgets/burndown-chart/burndown-chart.component';
import { VelocityChartComponent } from '@widgets/velocity-chart/velocity-chart.component';
import { SprintTimelineComponent } from '@widgets/sprint-timeline/sprint-timeline.component';
import {
  TaskFormResult,
  TaskModalComponent,
} from '@widgets/task-modal/task-modal.component';
import {
  BurndownData,
  METHODOLOGY_BADGE,
  Member,
  PRIORITY_CHIP_CLASS,
  PRIORITY_LABELS,
  Sprint,
  SprintCloseResult,
  Task,
  VelocityData,
  formatShortDate,
  statusDisplay,
} from '@entities/workspace/workspace.model';

type TabId = 'board' | 'backlog' | 'sprints' | 'timeline';
type ViewMode = 'board' | 'grid';

/** Board column working state; `tasks` are live arrays for CDK drag-drop. */
interface BoardColumn {
  status: string;
  tasks: Task[];
}

/**
 * Methodology-driven project workspace. Renders a board (one column per
 * allowed status), plus backlog, sprint and timeline tabs when the methodology
 * enables them. All behaviour derives from `methodology_info`.
 */
@Component({
  selector: 'sol-project-workspace',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    ReactiveFormsModule,
    DragDropModule,
    SolButtonComponent,
    SolCardComponent,
    SolModalComponent,
    SolTableComponent,
    BoardColumnComponent,
    TaskCardComponent,
    TaskModalComponent,
    BurndownChartComponent,
    VelocityChartComponent,
    SprintTimelineComponent,
  ],
  template: `
    @if (loading()) {
      <p class="text-sm text-muted">{{ text.loading() }}</p>
    } @else if (loadError()) {
      <div
        role="alert"
        class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
      >
        {{ loadError() }}
      </div>
    } @else if (project(); as proj) {
      <section class="flex flex-col gap-6">
        <!-- Header -->
        <div class="flex flex-col gap-3">
          <a
            routerLink="/projects"
            class="inline-flex w-fit items-center gap-1 text-sm text-muted transition-colors hover:text-text"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </svg>
            {{ text.backToProjects() }}
          </a>
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-3">
              <h1 class="text-2xl font-semibold text-text">{{ proj.name }}</h1>
              <span
                class="rounded-full bg-brand/10 px-2.5 py-0.5 text-xs font-medium text-brand"
              >
                {{ methodologyBadge() }}
              </span>
            </div>
            <sol-button
              type="button"
              variant="primary"
              (click)="openCreate()"
              [ariaLabel]="text.newTaskAria()"
            >
              + {{ text.newTask() }}
            </sol-button>
          </div>
        </div>

        <!-- Tabs -->
        <div class="flex gap-1 border-b border-border" role="tablist">
          @for (tab of tabs(); track tab.id) {
            <button
              type="button"
              role="tab"
              [attr.aria-selected]="activeTab() === tab.id"
              (click)="activeTab.set(tab.id)"
              class="-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors focus:outline-none"
              [class.border-brand]="activeTab() === tab.id"
              [class.text-brand]="activeTab() === tab.id"
              [class.border-transparent]="activeTab() !== tab.id"
              [class.text-muted]="activeTab() !== tab.id"
            >
              {{ tab.label }}
            </button>
          }
        </div>

        @if (tasksError()) {
          <div
            role="alert"
            class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
          >
            {{ tasksError() }}
          </div>
        }

        <!-- BOARD / GRID -->
        @if (activeTab() === 'board') {
          <!-- View mode toggle -->
          <div class="flex items-center gap-2" role="group" [attr.aria-label]="text.viewModeGroupAria()">
            <button
              type="button"
              (click)="viewMode.set('board')"
              class="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium
                     transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
              [class.border-brand]="viewMode() === 'board'"
              [class.bg-brand/10]="viewMode() === 'board'"
              [class.text-brand]="viewMode() === 'board'"
              [class.border-border]="viewMode() !== 'board'"
              [class.text-muted]="viewMode() !== 'board'"
              [attr.aria-pressed]="viewMode() === 'board'"
              [attr.aria-label]="text.viewBoardAria()"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15"
                viewBox="0 0 24 24" fill="none" stroke="currentColor"
                stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                aria-hidden="true">
                <rect x="3" y="3" width="7" height="18"/><rect x="14" y="3" width="7" height="18"/>
              </svg>
              {{ text.viewBoard() }}
            </button>
            <button
              type="button"
              (click)="viewMode.set('grid')"
              class="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium
                     transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
              [class.border-brand]="viewMode() === 'grid'"
              [class.bg-brand/10]="viewMode() === 'grid'"
              [class.text-brand]="viewMode() === 'grid'"
              [class.border-border]="viewMode() !== 'grid'"
              [class.text-muted]="viewMode() !== 'grid'"
              [attr.aria-pressed]="viewMode() === 'grid'"
              [attr.aria-label]="text.viewGridAria()"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15"
                viewBox="0 0 24 24" fill="none" stroke="currentColor"
                stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                aria-hidden="true">
                <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
                <rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
              </svg>
              {{ text.viewGrid() }}
            </button>
          </div>

          @if (viewMode() === 'board') {
            <!-- Kanban board -->
            @if (boardColumns().length === 0) {
              <sol-card>
                <p class="py-6 text-center text-sm text-muted">
                  {{ text.boardNoColumns() }}
                </p>
              </sol-card>
            } @else {
              <div
                cdkDropListGroup
                class="flex gap-4 overflow-x-auto pb-2"
              >
                @for (column of boardColumns(); track column.status) {
                  <sol-board-column
                    class="shrink-0"
                    [status]="column.status"
                    [tasks]="column.tasks"
                    [estimationMode]="estimationMode()"
                    [doneStatus]="doneStatus()"
                    (addTask)="openCreate($event)"
                    (editTask)="openEdit($event)"
                    (dropped)="onDrop($event)"
                  ></sol-board-column>
                }
              </div>
            }
          } @else {
            <!-- Grid view -->
            @if (allTasks().length === 0) {
              <sol-card>
                <p class="py-6 text-center text-sm text-muted">
                  {{ text.boardEmpty() }}
                </p>
              </sol-card>
            } @else {
              <sol-table>
                <thead>
                  <tr class="border-b border-border bg-surface/60">
                    <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted">{{ text.colCode() }}</th>
                    <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted">{{ text.colTitle() }}</th>
                    <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted">{{ text.colStatus() }}</th>
                    <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted">{{ text.colAssignee() }}</th>
                    <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted">{{ text.colPriority() }}</th>
                    <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted">{{ text.colDueDate() }}</th>
                    @if (estimationMode() !== 'none') {
                      <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted">{{ text.colEstimation() }}</th>
                    }
                  </tr>
                </thead>
                <tbody>
                  @for (task of allTasks(); track task.id) {
                    <tr
                      class="border-b border-border/50 transition-colors hover:bg-brand/5 cursor-pointer"
                      (click)="openEdit(task)"
                    >
                      <td class="px-4 py-3 text-xs font-mono text-muted">
                        @if (task.task_key) {
                          <a
                            [routerLink]="['/task', task.task_key]"
                            (click)="$event.stopPropagation()"
                            class="font-semibold text-brand hover:underline"
                            [attr.aria-label]="openDetailAria(task.task_key)"
                          >{{ task.task_key }}</a>
                        } @else {
                          <span class="text-muted">—</span>
                        }
                      </td>
                      <td class="px-4 py-3 text-sm text-text max-w-xs truncate">
                        {{ task.title }}
                      </td>
                      <td class="px-4 py-3">
                        <span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-muted/10 text-muted">
                          {{ statusDisplay(task.status) }}
                        </span>
                      </td>
                      <td class="px-4 py-3 text-sm text-text">
                        {{ task.assignee_name || '—' }}
                      </td>
                      <td class="px-4 py-3">
                        <span
                          class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                          [class]="priorityChipClass(task.priority)"
                        >{{ priorityLabel(task.priority) }}</span>
                      </td>
                      <td class="px-4 py-3 text-sm text-muted">
                        {{ dateLabel(task.due_date) }}
                      </td>
                      @if (estimationMode() !== 'none') {
                        <td class="px-4 py-3 text-sm text-muted text-right tabular-nums">
                          @if (estimationMode() === 'points' || estimationMode() === 'both') {
                            @if (task.estimation_points != null) {
                              <span>{{ task.estimation_points }} {{ text.pointsSuffix() }}</span>
                            }
                          }
                          @if (estimationMode() === 'hours' || estimationMode() === 'both') {
                            @if (task.estimation_hours != null) {
                              <span class="ml-1">{{ task.estimation_hours }} {{ text.hoursSuffix() }}</span>
                            }
                          }
                          @if (task.estimation_points == null && task.estimation_hours == null) {
                            <span>—</span>
                          }
                        </td>
                      }
                    </tr>
                  }
                </tbody>
              </sol-table>
            }
          }
        }

        <!-- BACKLOG -->
        @if (activeTab() === 'backlog') {
          <div class="flex flex-col gap-4">
            <div class="flex items-center justify-between gap-3">
              <h2 class="text-lg font-semibold text-text">{{ text.backlogTitle() }}</h2>
              <sol-button
                type="button"
                variant="secondary"
                (click)="openCreate()"
                [ariaLabel]="text.backlogAddAria()"
              >
                + {{ text.backlogAdd() }}
              </sol-button>
            </div>
            @if (backlogTasks().length === 0) {
              <sol-card>
                <p class="py-6 text-center text-sm text-muted">
                  {{ text.backlogEmpty() }}
                </p>
              </sol-card>
            } @else {
              <div class="flex flex-col gap-3">
                @for (task of backlogTasks(); track task.id) {
                  <div class="flex flex-col gap-2 sm:flex-row sm:items-start">
                    <div class="flex-1">
                      <sol-task-card
                        [task]="task"
                        [estimationMode]="estimationMode()"
                        [doneStatus]="doneStatus()"
                        (edit)="openEdit($event)"
                      ></sol-task-card>
                    </div>
                    @if (sprintsEnabled()) {
                      <label class="block sm:w-56">
                        <span class="mb-1 block text-xs font-medium text-muted"
                          >{{ text.moveToSprint() }}</span
                        >
                        <select
                          [value]="task.sprint_id ?? ''"
                          (change)="onAssignSprint(task, $event)"
                          class="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text
                                 transition-colors focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40"
                          [attr.aria-label]="assignSprintAria(task.title)"
                        >
                          <option value="">{{ text.backlogOption() }}</option>
                          @for (sprint of sprints(); track sprint.id) {
                            <option [value]="sprint.id">{{ sprint.name }}</option>
                          }
                        </select>
                      </label>
                    }
                  </div>
                }
              </div>
            }
          </div>
        }

        <!-- SPRINTS -->
        @if (activeTab() === 'sprints') {
          <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <div class="lg:col-span-1">
              <sol-card>
                <h2 class="mb-4 text-lg font-semibold text-text">{{ text.newSprintTitle() }}</h2>
                <form
                  [formGroup]="sprintForm"
                  (ngSubmit)="onCreateSprint()"
                  class="flex flex-col gap-4"
                  novalidate
                >
                  <label class="block">
                    <span class="mb-1.5 block text-sm font-medium text-text"
                      >{{ text.sprintNameLabel() }}</span
                    >
                    <input
                      formControlName="name"
                      [placeholder]="text.sprintNamePlaceholder()"
                      [class]="fieldClass"
                    />
                    @if (sprintNameError()) {
                      <p class="mt-1 text-xs text-danger">
                        {{ text.sprintNameRequired() }}
                      </p>
                    }
                  </label>
                  <label class="block">
                    <span class="mb-1.5 block text-sm font-medium text-text"
                      >{{ text.sprintGoalLabel() }}</span
                    >
                    <input
                      formControlName="goal"
                      [placeholder]="text.sprintGoalPlaceholder()"
                      [class]="fieldClass"
                    />
                  </label>
                  <div class="grid grid-cols-2 gap-3">
                    <label class="block">
                      <span class="mb-1.5 block text-sm font-medium text-text"
                        >{{ text.sprintStartLabel() }}</span
                      >
                      <input
                        type="date"
                        formControlName="start_date"
                        [class]="fieldClass"
                      />
                    </label>
                    <label class="block">
                      <span class="mb-1.5 block text-sm font-medium text-text"
                        >{{ text.sprintEndLabel() }}</span
                      >
                      <input
                        type="date"
                        formControlName="end_date"
                        [class]="fieldClass"
                      />
                    </label>
                  </div>
                  <sol-button
                    type="submit"
                    variant="primary"
                    class="w-full"
                    [disabled]="savingSprint()"
                  >
                    {{ savingSprint() ? text.saving() : text.createSprint() }}
                  </sol-button>
                </form>
              </sol-card>
            </div>

            <div class="flex flex-col gap-3 lg:col-span-2">
              @if (sprints().length === 0) {
                <sol-card>
                  <p class="py-6 text-center text-sm text-muted">
                    {{ text.sprintsEmpty() }}
                  </p>
                </sol-card>
              } @else {
                @for (sprint of sprints(); track sprint.id) {
                  <div
                    class="rounded-xl border bg-surface p-5 shadow-sm transition-colors"
                    [class.border-brand]="selectedSprintId() === sprint.id"
                    [class.border-border]="selectedSprintId() !== sprint.id"
                  >
                    <div class="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div class="flex items-center gap-2">
                          <h3 class="text-base font-semibold text-text">
                            {{ sprint.name }}
                          </h3>
                          <span
                            class="rounded-full px-2.5 py-0.5 text-xs font-medium"
                            [class]="sprintBadgeClass(sprint)"
                          >
                            {{ sprint.status === 'active' ? text.sprintActive() : text.sprintClosed() }}
                          </span>
                          @if (sprint.status === 'closed' && sprint.completed_points != null) {
                            <span class="text-xs text-muted">
                              {{ pointsCompletedLabel(sprint.completed_points) }}
                            </span>
                          }
                        </div>
                        @if (sprint.goal) {
                          <p class="mt-1 text-sm text-muted">{{ sprint.goal }}</p>
                        }
                        @if (sprint.start_date || sprint.end_date) {
                          <p class="mt-1 text-xs text-muted">
                            {{ dateLabel(sprint.start_date) }} —
                            {{ dateLabel(sprint.end_date) }}
                          </p>
                        }
                      </div>
                      <div class="flex shrink-0 flex-wrap items-center gap-2">
                        <sol-button
                          type="button"
                          variant="primary"
                          (click)="selectSprint(sprint)"
                          [ariaLabel]="showBurndownAria(sprint.name)"
                        >
                          {{
                            selectedSprintId() === sprint.id
                              ? text.hideBurndown()
                              : text.showBurndown()
                          }}
                        </sol-button>
                        @if (sprint.status === 'active') {
                          <sol-button
                            type="button"
                            variant="secondary"
                            (click)="openCloseSprint(sprint)"
                            [ariaLabel]="closeSprintAria(sprint.name)"
                          >
                            {{ text.closeSprint() }}
                          </sol-button>
                        } @else {
                          <sol-button
                            type="button"
                            variant="secondary"
                            (click)="toggleSprintStatus(sprint)"
                            [ariaLabel]="reactivateSprintAria(sprint.name)"
                          >
                            {{ text.reactivate() }}
                          </sol-button>
                        }
                      </div>
                    </div>

                    @if (selectedSprintId() === sprint.id) {
                      <div class="mt-4 border-t border-border pt-4">
                        @if (burndownLoading()) {
                          <p class="py-6 text-center text-sm text-muted">
                            {{ text.burndownLoading() }}
                          </p>
                        } @else if (burndownError()) {
                          <div
                            role="alert"
                            class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
                          >
                            {{ burndownError() }}
                          </div>
                        } @else if (burndown(); as bd) {
                          <div
                            class="mb-3 flex flex-wrap items-center gap-x-6 gap-y-1 text-sm"
                          >
                            <span class="text-muted">
                              {{ text.burndownTotal() }}
                              <span class="font-semibold text-text">
                                {{ burndownTotal(bd) }} {{ burndownUnitLabel(bd) }}
                              </span>
                            </span>
                            <span class="text-muted">
                              {{ text.burndownCompleted() }}
                              <span class="font-semibold text-text">
                                {{ completedOfTotalLabel(bd.completed_tasks, bd.total_tasks) }}
                              </span>
                            </span>
                          </div>
                          <sol-burndown-chart
                            [days]="bd.days"
                            [unit]="bd.unit"
                          ></sol-burndown-chart>
                        }
                      </div>
                    }
                  </div>
                }
              }

              <!-- Velocity section -->
              <div class="mt-2">
                <div class="mb-3 flex items-center justify-between gap-2">
                  <h3 class="text-base font-semibold text-text">{{ text.velocityTitle() }}</h3>
                  @if (velocityLoaded()) {
                    <button
                      type="button"
                      (click)="loadVelocity()"
                      class="text-xs text-muted hover:text-text transition-colors"
                      [attr.aria-label]="text.velocityRefreshAria()"
                    >{{ text.velocityRefresh() }}</button>
                  }
                </div>
                @if (velocityLoading()) {
                  <p class="py-4 text-center text-sm text-muted">{{ text.velocityLoading() }}</p>
                } @else if (velocityError()) {
                  <div
                    role="alert"
                    class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
                  >
                    {{ velocityError() }}
                  </div>
                } @else if (velocityData(); as vd) {
                  <sol-velocity-chart [data]="vd"></sol-velocity-chart>
                }
              </div>
            </div>
          </div>
        }

        <!-- TIMELINE -->
        @if (activeTab() === 'timeline') {
          <div class="flex flex-col gap-4">
            <div class="flex items-center justify-between gap-3">
              <h2 class="text-lg font-semibold text-text">{{ text.timelineTitle() }}</h2>
              <p class="text-xs text-muted">{{ text.timelineDescription() }}</p>
            </div>
            <sol-sprint-timeline [sprints]="sprints()"></sol-sprint-timeline>
          </div>
        }

      </section>

      <!-- Task modal -->
      @if (modalOpen()) {
        <sol-task-modal
          [allowedStatuses]="allowedStatuses()"
          [estimationMode]="estimationMode()"
          [members]="members()"
          [sprints]="sprints()"
          [sprintsEnabled]="sprintsEnabled()"
          [presetStatus]="presetStatus()"
          [task]="editingTask()"
          [saving]="savingTask()"
          [error]="modalError()"
          (save)="onSaveTask($event)"
          (remove)="onDeleteTask($event)"
          (closed)="closeModal()"
        ></sol-task-modal>
      }

      <!-- Close sprint modal -->
      @if (closeSprintOpen()) {
        <sol-modal [open]="true"
          [title]="text.closeSprintTitle()"
          size="sm"
          (closed)="cancelCloseSprint()"
        >
          @if (closeSprintResult(); as result) {
            <!-- Success state -->
            <div class="flex flex-col gap-4">
              <div class="rounded-lg bg-success/10 px-4 py-3 text-sm text-success">
                {{ text.closeSprintSuccess() }}
              </div>
              <div class="flex flex-col gap-1 text-sm text-text">
                <p>
                  <span class="font-semibold">{{ result.sprint.completed_points ?? 0 }}</span>
                  {{ text.closeSprintPointsCompleted() }}
                </p>
                <p>
                  <span class="font-semibold">{{ result.tasks_moved }}</span>
                  {{ tasksMovedLabel(result.tasks_moved) }}
                </p>
              </div>
              <sol-button
                type="button"
                variant="primary"
                class="w-full"
                (click)="cancelCloseSprint()"
              >
                {{ text.closeSprintUnderstood() }}
              </sol-button>
            </div>
          } @else {
            <!-- Confirmation state -->
            <div class="flex flex-col gap-4">
              <p class="text-sm text-muted">
                {{ text.closeSprintDescription() }}
              </p>

              @if (activeSprintsForClose().length > 0) {
                <label class="block">
                  <span class="mb-1.5 block text-sm font-medium text-text">
                    {{ text.closeSprintMoveIncompleteTo() }}
                  </span>
                  <select
                    [value]="closingTargetSprintId()"
                    (change)="closingTargetSprintId.set(toSelectValue($event))"
                    class="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text
                           transition-colors focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40"
                    [attr.aria-label]="text.closeSprintTargetAria()"
                  >
                    <option value="">{{ text.closeSprintBacklogDefault() }}</option>
                    @for (s of activeSprintsForClose(); track s.id) {
                      <option [value]="s.id">{{ s.name }}</option>
                    }
                  </select>
                </label>
              } @else {
                <p class="rounded-lg bg-muted/10 px-3 py-2 text-xs text-muted">
                  {{ text.closeSprintNoOtherSprints() }}
                </p>
              }

              @if (closeSprintError()) {
                <div
                  role="alert"
                  class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
                >
                  {{ closeSprintError() }}
                </div>
              }

              <div class="flex gap-3">
                <sol-button
                  type="button"
                  variant="secondary"
                  class="w-full"
                  [disabled]="closingSprintBusy()"
                  (click)="cancelCloseSprint()"
                >
                  {{ text.cancel() }}
                </sol-button>
                <sol-button
                  type="button"
                  variant="primary"
                  class="w-full"
                  [disabled]="closingSprintBusy()"
                  (click)="confirmCloseSprint()"
                >
                  {{ closingSprintBusy() ? text.closing() : text.closeSprintTitle() }}
                </sol-button>
              </div>
            </div>
          }
        </sol-modal>
      }
    }
  `,
})
export class ProjectWorkspaceComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly fb = inject(FormBuilder);
  private readonly projectsService = inject(ProjectsService);
  private readonly workspace = inject(WorkspaceService);
  private readonly i18n = inject(I18nService);

  /** Static UI chrome resolved by i18n (reactive to language changes). */
  protected readonly text = {
    loading: this.i18n.t('workspace.loading'),
    backToProjects: this.i18n.t('workspace.backToProjects'),
    newTask: this.i18n.t('workspace.newTask'),
    newTaskAria: this.i18n.t('workspace.newTaskAria'),
    viewModeGroupAria: this.i18n.t('workspace.viewMode.groupAria'),
    viewBoard: this.i18n.t('workspace.viewMode.board'),
    viewBoardAria: this.i18n.t('workspace.viewMode.boardAria'),
    viewGrid: this.i18n.t('workspace.viewMode.grid'),
    viewGridAria: this.i18n.t('workspace.viewMode.gridAria'),
    boardNoColumns: this.i18n.t('workspace.board.noColumns'),
    boardEmpty: this.i18n.t('workspace.board.empty'),
    colCode: this.i18n.t('workspace.grid.columns.code'),
    colTitle: this.i18n.t('workspace.grid.columns.title'),
    colStatus: this.i18n.t('workspace.grid.columns.status'),
    colAssignee: this.i18n.t('workspace.grid.columns.assignee'),
    colPriority: this.i18n.t('workspace.grid.columns.priority'),
    colDueDate: this.i18n.t('workspace.grid.columns.dueDate'),
    colEstimation: this.i18n.t('workspace.grid.columns.estimation'),
    pointsSuffix: this.i18n.t('workspace.grid.pointsSuffix'),
    hoursSuffix: this.i18n.t('workspace.grid.hoursSuffix'),
    backlogTitle: this.i18n.t('workspace.backlog.title'),
    backlogAdd: this.i18n.t('workspace.backlog.add'),
    backlogAddAria: this.i18n.t('workspace.backlog.addAria'),
    backlogEmpty: this.i18n.t('workspace.backlog.empty'),
    moveToSprint: this.i18n.t('workspace.backlog.moveToSprint'),
    backlogOption: this.i18n.t('workspace.backlog.backlogOption'),
    newSprintTitle: this.i18n.t('workspace.sprints.newTitle'),
    sprintNameLabel: this.i18n.t('workspace.sprints.nameLabel'),
    sprintNamePlaceholder: this.i18n.t('workspace.sprints.namePlaceholder'),
    sprintNameRequired: this.i18n.t('workspace.sprints.nameRequired'),
    sprintGoalLabel: this.i18n.t('workspace.sprints.goalLabel'),
    sprintGoalPlaceholder: this.i18n.t('workspace.sprints.goalPlaceholder'),
    sprintStartLabel: this.i18n.t('workspace.sprints.startLabel'),
    sprintEndLabel: this.i18n.t('workspace.sprints.endLabel'),
    saving: this.i18n.t('workspace.sprints.saving'),
    createSprint: this.i18n.t('workspace.sprints.create'),
    sprintsEmpty: this.i18n.t('workspace.sprints.empty'),
    sprintActive: this.i18n.t('workspace.sprints.statusActive'),
    sprintClosed: this.i18n.t('workspace.sprints.statusClosed'),
    hideBurndown: this.i18n.t('workspace.sprints.hideBurndown'),
    showBurndown: this.i18n.t('workspace.sprints.showBurndown'),
    closeSprint: this.i18n.t('workspace.sprints.close'),
    reactivate: this.i18n.t('workspace.sprints.reactivate'),
    burndownLoading: this.i18n.t('workspace.sprints.burndownLoading'),
    burndownTotal: this.i18n.t('workspace.sprints.totalLabel'),
    burndownCompleted: this.i18n.t('workspace.sprints.completedLabel'),
    velocityTitle: this.i18n.t('workspace.sprints.velocityTitle'),
    velocityRefresh: this.i18n.t('workspace.sprints.velocityRefresh'),
    velocityRefreshAria: this.i18n.t('workspace.sprints.velocityRefreshAria'),
    velocityLoading: this.i18n.t('workspace.sprints.velocityLoading'),
    timelineTitle: this.i18n.t('workspace.timeline.title'),
    timelineDescription: this.i18n.t('workspace.timeline.description'),
    closeSprintTitle: this.i18n.t('workspace.closeSprint.title'),
    closeSprintSuccess: this.i18n.t('workspace.closeSprint.success'),
    closeSprintPointsCompleted: this.i18n.t('workspace.closeSprint.pointsCompleted'),
    closeSprintUnderstood: this.i18n.t('workspace.closeSprint.understood'),
    closeSprintDescription: this.i18n.t('workspace.closeSprint.description'),
    closeSprintMoveIncompleteTo: this.i18n.t('workspace.closeSprint.moveIncompleteTo'),
    closeSprintTargetAria: this.i18n.t('workspace.closeSprint.targetAria'),
    closeSprintBacklogDefault: this.i18n.t('workspace.closeSprint.backlogDefault'),
    closeSprintNoOtherSprints: this.i18n.t('workspace.closeSprint.noOtherSprints'),
    cancel: this.i18n.t('workspace.closeSprint.cancel'),
    closing: this.i18n.t('workspace.closeSprint.closing'),
  } as const;

  protected readonly fieldClass =
    'h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text ' +
    'transition-colors focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40';

  private readonly projectId = signal<string>('');

  protected readonly project = signal<ProjectDetail | null>(null);
  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);

  protected readonly allTasks = signal<Task[]>([]);
  protected readonly boardColumns = signal<BoardColumn[]>([]);
  protected readonly tasksError = signal<string | null>(null);

  protected readonly members = signal<Member[]>([]);
  protected readonly sprints = signal<Sprint[]>([]);

  protected readonly activeTab = signal<TabId>('board');
  protected readonly viewMode = signal<ViewMode>('board');

  protected readonly modalOpen = signal(false);
  protected readonly editingTask = signal<Task | null>(null);
  protected readonly presetStatus = signal<string | null>(null);
  protected readonly savingTask = signal(false);
  protected readonly modalError = signal<string | null>(null);

  protected readonly savingSprint = signal(false);

  protected readonly selectedSprintId = signal<string | null>(null);
  protected readonly burndown = signal<BurndownData | null>(null);
  protected readonly burndownLoading = signal(false);
  protected readonly burndownError = signal<string | null>(null);

  /* ---- Close sprint state ----------------------------------------------- */
  protected readonly closeSprintOpen = signal(false);
  protected readonly closingSprintId = signal<string | null>(null);
  protected readonly closingTargetSprintId = signal<string>('');
  protected readonly closingSprintBusy = signal(false);
  protected readonly closeSprintError = signal<string | null>(null);
  protected readonly closeSprintResult = signal<SprintCloseResult | null>(null);

  /* ---- Velocity state --------------------------------------------------- */
  protected readonly velocityData = signal<VelocityData | null>(null);
  protected readonly velocityLoading = signal(false);
  protected readonly velocityError = signal<string | null>(null);
  protected readonly velocityLoaded = signal(false);

  protected readonly sprintForm = this.fb.group({
    name: ['', [Validators.required]],
    goal: [''],
    start_date: [''],
    end_date: [''],
  });

  constructor() {
    // Lazy-load velocity when the sprints tab becomes active.
    effect(() => {
      if (this.activeTab() === 'sprints' && !this.velocityLoaded()) {
        this.loadVelocity();
      }
    });
  }

  protected readonly tabs = computed(() => {
    this.i18n.activeLang();
    const info = this.project()?.methodology_info;
    const list: { id: TabId; label: string }[] = [
      { id: 'board', label: this.i18n.translate('workspace.tabs.board') },
    ];
    if (info?.has_backlog) {
      list.push({ id: 'backlog', label: this.i18n.translate('workspace.tabs.backlog') });
    }
    if (info?.sprints_enabled) {
      list.push({ id: 'sprints', label: this.i18n.translate('workspace.tabs.sprints') });
      list.push({ id: 'timeline', label: this.i18n.translate('workspace.tabs.timeline') });
    }
    return list;
  });

  protected readonly allowedStatuses = computed<string[]>(
    () => this.project()?.methodology_info.allowed_statuses ?? [],
  );

  protected readonly estimationMode = computed<EstimationMode>(
    () => this.project()?.methodology_info.estimation_mode ?? 'none',
  );

  protected readonly sprintsEnabled = computed<boolean>(
    () => this.project()?.methodology_info.sprints_enabled ?? false,
  );

  protected readonly doneStatus = computed<string | null>(() => {
    const statuses = this.allowedStatuses();
    return statuses.length > 0 ? statuses[statuses.length - 1] : null;
  });

  protected readonly backlogTasks = computed<Task[]>(() =>
    this.allTasks().filter((task) => task.sprint_id == null),
  );

  /** Active sprints other than the one being closed (for the target selector). */
  protected readonly activeSprintsForClose = computed<Sprint[]>(() =>
    this.sprints().filter(
      (s) => s.status === 'active' && s.id !== this.closingSprintId(),
    ),
  );

  protected methodologyBadge(): string {
    const methodology = this.project()?.methodology;
    return methodology ? METHODOLOGY_BADGE[methodology] : '';
  }

  protected statusDisplay(status: string): string {
    return statusDisplay(status);
  }

  protected priorityChipClass(priority: string): string {
    return (
      PRIORITY_CHIP_CLASS[priority as keyof typeof PRIORITY_CHIP_CLASS] ??
      'bg-muted/10 text-muted'
    );
  }

  protected priorityLabel(priority: string): string {
    return (
      PRIORITY_LABELS[priority as keyof typeof PRIORITY_LABELS] ?? priority
    );
  }

  /** Extracts the value from a native select change event. */
  protected toSelectValue(event: Event): string {
    return (event.target as HTMLSelectElement).value;
  }

  /* ---- i18n dynamic labels (loop/param dependent) ------------------------ */

  protected openDetailAria(key: string): string {
    return this.i18n.translate('workspace.grid.openDetailAria', { key });
  }

  protected assignSprintAria(title: string): string {
    return this.i18n.translate('workspace.backlog.assignSprintAria', { title });
  }

  protected pointsCompletedLabel(points: number): string {
    return this.i18n.translate('workspace.sprints.pointsCompleted', {
      n: points,
    });
  }

  protected showBurndownAria(name: string): string {
    return this.i18n.translate('workspace.sprints.showBurndownAria', { name });
  }

  protected closeSprintAria(name: string): string {
    return this.i18n.translate('workspace.sprints.closeAria', { name });
  }

  protected reactivateSprintAria(name: string): string {
    return this.i18n.translate('workspace.sprints.reactivateAria', { name });
  }

  protected completedOfTotalLabel(done: number, total: number): string {
    return this.i18n.translate('workspace.sprints.completedOfTotal', {
      done,
      total,
    });
  }

  protected tasksMovedLabel(count: number): string {
    return this.i18n.translate(
      count === 1
        ? 'workspace.closeSprint.tasksMovedOne'
        : 'workspace.closeSprint.tasksMovedOther',
    );
  }

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id') ?? '';
    this.projectId.set(id);
    this.loadProject();
  }

  private loadProject(): void {
    const id = this.projectId();
    if (!id) {
      this.loading.set(false);
      this.loadError.set(this.i18n.translate('workspace.errors.projectNotFound'));
      return;
    }
    this.loading.set(true);
    this.loadError.set(null);

    this.projectsService.get(id).subscribe({
      next: (res) => {
        this.project.set(res.data);
        this.loading.set(false);
        this.loadMembers();
        this.loadTasks();
        if (res.data.methodology_info.sprints_enabled) {
          this.loadSprints();
        }
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.loadError.set(
          this.i18n.translate(
            err.status === 0
              ? 'workspace.errors.projectNetwork'
              : 'workspace.errors.projectLoad',
          ),
        );
      },
    });
  }

  private loadMembers(): void {
    this.workspace.members(this.projectId()).subscribe({
      next: (res) => this.members.set(res.data ?? []),
      error: () => this.members.set([]),
    });
  }

  private loadSprints(): void {
    this.workspace.sprints(this.projectId()).subscribe({
      next: (res) => this.sprints.set(res.data ?? []),
      error: () => this.sprints.set([]),
    });
  }

  private loadTasks(): void {
    this.tasksError.set(null);
    this.workspace.tasks(this.projectId()).subscribe({
      next: (res) => {
        this.allTasks.set(res.data ?? []);
        this.buildBoard();
      },
      error: () =>
        this.tasksError.set(
          this.i18n.translate('workspace.errors.tasksLoad'),
        ),
    });
  }

  protected loadVelocity(): void {
    this.velocityLoading.set(true);
    this.velocityError.set(null);
    this.workspace.velocity(this.projectId()).subscribe({
      next: (res) => {
        this.velocityData.set(res.data);
        this.velocityLoading.set(false);
        this.velocityLoaded.set(true);
      },
      error: () => {
        this.velocityLoading.set(false);
        this.velocityError.set(
          this.i18n.translate('workspace.errors.velocityLoad'),
        );
      },
    });
  }

  /** Rebuild the board columns from the current statuses + tasks. */
  private buildBoard(): void {
    const statuses = this.allowedStatuses();
    const tasks = this.allTasks();
    this.boardColumns.set(
      statuses.map((status) => ({
        status,
        tasks: tasks.filter((task) => task.status === status),
      })),
    );
  }

  /* ---- Drag and drop ----------------------------------------------------- */

  protected onDrop({ event, status }: ColumnDrop): void {
    if (event.previousContainer === event.container) {
      moveItemInArray(
        event.container.data,
        event.previousIndex,
        event.currentIndex,
      );
      this.boardColumns.update((cols) => [...cols]);
      return;
    }

    const moved = event.previousContainer.data[event.previousIndex];
    const previousStatus = moved.status;
    transferArrayItem(
      event.previousContainer.data,
      event.container.data,
      event.previousIndex,
      event.currentIndex,
    );
    moved.status = status;
    this.boardColumns.update((cols) => [...cols]);

    this.workspace.updateTask(moved.id, { status }).subscribe({
      error: () => {
        moved.status = previousStatus;
        this.loadTasks();
      },
    });
  }

  /* ---- Task modal -------------------------------------------------------- */

  protected openCreate(status?: string): void {
    this.editingTask.set(null);
    this.presetStatus.set(status ?? null);
    this.modalError.set(null);
    this.modalOpen.set(true);
  }

  protected openEdit(task: Task): void {
    this.editingTask.set(task);
    this.presetStatus.set(null);
    this.modalError.set(null);
    this.modalOpen.set(true);
  }

  protected closeModal(): void {
    this.modalOpen.set(false);
    this.editingTask.set(null);
    this.presetStatus.set(null);
    this.modalError.set(null);
  }

  protected onSaveTask(result: TaskFormResult): void {
    this.savingTask.set(true);
    this.modalError.set(null);
    const editing = this.editingTask();

    const done = (): void => {
      this.savingTask.set(false);
      this.closeModal();
      this.loadTasks();
    };
    const fail = (): void => {
      this.savingTask.set(false);
      this.modalError.set(
        this.i18n.translate('workspace.errors.taskSave'),
      );
    };

    if (editing) {
      this.workspace
        .updateTask(editing.id, {
          title: result.title,
          description: result.description,
          status: result.status,
          priority: result.priority,
          assignee_id: result.assignee_id,
          estimation_points: result.estimation_points,
          estimation_hours: result.estimation_hours,
          due_date: result.due_date,
          sprint_id: result.sprint_id,
        })
        .subscribe({ next: done, error: fail });
    } else {
      this.workspace
        .createTask(this.projectId(), {
          title: result.title,
          description: result.description,
          status: result.status,
          priority: result.priority,
          assignee_id: result.assignee_id,
          estimation_points: result.estimation_points,
          estimation_hours: result.estimation_hours,
          due_date: result.due_date,
          sprint_id: result.sprint_id,
          task_type: result.task_type,
        })
        .subscribe({ next: done, error: fail });
    }
  }

  protected onDeleteTask(taskId: string): void {
    this.savingTask.set(true);
    this.workspace.deleteTask(taskId).subscribe({
      next: () => {
        this.savingTask.set(false);
        this.closeModal();
        this.loadTasks();
      },
      error: () => {
        this.savingTask.set(false);
        this.modalError.set(this.i18n.translate('workspace.errors.taskDelete'));
      },
    });
  }

  /* ---- Backlog ----------------------------------------------------------- */

  protected onAssignSprint(task: Task, event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    this.workspace
      .updateTask(task.id, { sprint_id: value || null })
      .subscribe({
        next: () => {
          this.loadTasks();
          const selected = this.selectedSprintId();
          if (selected && (selected === value || selected === task.sprint_id)) {
            this.loadBurndown(selected);
          }
        },
      });
  }

  /* ---- Sprints ----------------------------------------------------------- */

  protected sprintNameError(): boolean {
    const c = this.sprintForm.controls.name;
    return c.invalid && (c.touched || c.dirty);
  }

  protected onCreateSprint(): void {
    if (this.sprintForm.invalid) {
      this.sprintForm.markAllAsTouched();
      return;
    }
    const raw = this.sprintForm.getRawValue();
    this.savingSprint.set(true);
    this.workspace
      .createSprint(this.projectId(), {
        name: (raw.name ?? '').trim(),
        goal: (raw.goal ?? '').trim() || null,
        start_date: raw.start_date || null,
        end_date: raw.end_date || null,
      })
      .subscribe({
        next: () => {
          this.savingSprint.set(false);
          this.sprintForm.reset({
            name: '',
            goal: '',
            start_date: '',
            end_date: '',
          });
          this.loadSprints();
        },
        error: () => this.savingSprint.set(false),
      });
  }

  protected toggleSprintStatus(sprint: Sprint): void {
    const next = sprint.status === 'active' ? 'closed' : 'active';
    this.workspace
      .updateSprint(sprint.id, { status: next })
      .subscribe({ next: () => this.loadSprints() });
  }

  /* ---- Close sprint ------------------------------------------------------ */

  protected openCloseSprint(sprint: Sprint): void {
    this.closingSprintId.set(sprint.id);
    this.closingTargetSprintId.set('');
    this.closeSprintError.set(null);
    this.closeSprintResult.set(null);
    this.closeSprintOpen.set(true);
  }

  protected cancelCloseSprint(): void {
    this.closeSprintOpen.set(false);
    this.closingSprintId.set(null);
  }

  protected confirmCloseSprint(): void {
    const sprintId = this.closingSprintId();
    if (!sprintId) return;

    this.closingSprintBusy.set(true);
    this.closeSprintError.set(null);

    const target = this.closingTargetSprintId();
    this.workspace
      .closeSprint(sprintId, target ? { target_sprint_id: target } : {})
      .subscribe({
        next: (res) => {
          this.closingSprintBusy.set(false);
          this.closeSprintResult.set(res.data);
          this.loadSprints();
          this.loadTasks();
          // Invalidate velocity so it reloads fresh.
          this.velocityLoaded.set(false);
          this.velocityData.set(null);
        },
        error: (err: HttpErrorResponse) => {
          this.closingSprintBusy.set(false);
          if (err.status === 409) {
            this.closeSprintError.set(
              this.i18n.translate('workspace.errors.sprintAlreadyClosed'),
            );
          } else {
            this.closeSprintError.set(
              this.i18n.translate('workspace.errors.sprintClose'),
            );
          }
        },
      });
  }

  /* ---- Burndown ---------------------------------------------------------- */

  protected selectSprint(sprint: Sprint): void {
    if (this.selectedSprintId() === sprint.id) {
      this.selectedSprintId.set(null);
      this.burndown.set(null);
      this.burndownError.set(null);
      return;
    }
    this.selectedSprintId.set(sprint.id);
    this.loadBurndown(sprint.id);
  }

  private loadBurndown(sprintId: string): void {
    this.burndownLoading.set(true);
    this.burndownError.set(null);
    this.workspace.burndown(this.projectId(), sprintId).subscribe({
      next: (res) => {
        this.burndown.set(res.data);
        this.burndownLoading.set(false);
      },
      error: () => {
        this.burndownLoading.set(false);
        this.burndown.set(null);
        this.burndownError.set(
          this.i18n.translate('workspace.errors.burndownLoad'),
        );
      },
    });
  }

  protected burndownTotal(data: BurndownData): number {
    return data.unit === 'points' ? data.total_points : data.total_tasks;
  }

  protected burndownUnitLabel(data: BurndownData): string {
    return this.i18n.translate(
      data.unit === 'points'
        ? 'workspace.sprints.unitPoints'
        : 'workspace.sprints.unitTasks',
    );
  }

  protected dateLabel(value: string | null | undefined): string {
    return formatShortDate(value) || this.i18n.translate('workspace.dates.noDate');
  }

  protected sprintBadgeClass(sprint: Sprint): string {
    return sprint.status === 'active'
      ? 'bg-success/10 text-success'
      : 'bg-muted/15 text-muted';
  }
}
