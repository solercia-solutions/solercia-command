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
import { NgTemplateOutlet } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { forkJoin } from 'rxjs';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import {
  KanbanColumn,
  KanbanItemMoved,
  SolButtonComponent,
  SolCardComponent,
  SolDrawerComponent,
  SolIconComponent,
  SolModalComponent,
  SolKanbanBoardComponent,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { ProjectsService } from '@entities/project/projects.service';
import { EstimationMode, ProjectDetail } from '@entities/project/project.model';
import { WorkspaceService } from '@entities/workspace/workspace.service';
import { BurndownChartComponent } from '@widgets/burndown-chart/burndown-chart.component';
import { VelocityChartComponent } from '@widgets/velocity-chart/velocity-chart.component';
import {
  TaskFormResult,
  TaskModalComponent,
} from '@widgets/task-modal/task-modal.component';
import { TaskDetailPanelComponent } from '@widgets/task-detail-panel/task-detail-panel.component';
import { SprintGanttComponent } from '@widgets/sprint-gantt/sprint-gantt.component';
import { TaskDetail } from '@entities/task/task-detail.model';
import {
  BacklogAggregate,
  BurndownData,
  METHODOLOGY_BADGE,
  Member,
  PRIORITY_CHIP_CLASS,
  PRIORITY_LABELS,
  Sprint,
  SprintCloseResult,
  SprintListItem,
  Task,
  VelocityData,
  formatShortDate,
  isOverdue,
  statusDisplay,
} from '@entities/workspace/workspace.model';

type TabId = 'board' | 'backlog' | 'sprints' | 'timeline';
type ViewMode = 'board' | 'grid';

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
    NgTemplateOutlet,
    SolButtonComponent,
    SolCardComponent,
    SolDrawerComponent,
    SolIconComponent,
    SolModalComponent,
    SolKanbanBoardComponent,
    SprintGanttComponent,
    TaskModalComponent,
    TaskDetailPanelComponent,
    BurndownChartComponent,
    VelocityChartComponent,
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
              <sol-icon name="view-columns" size="sm" />
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
              <sol-icon name="squares-2x2" size="sm" />
              {{ text.viewGrid() }}
            </button>
          </div>

          @if (viewMode() === 'board') {
            <!-- Kanban board (sol-kanban-board: la lib no conoce Task, el
                 contenido de tarjeta se proyecta vía taskCardTpl más abajo). -->
            @if (kanbanColumns().length === 0) {
              <sol-card>
                <p class="py-6 text-center text-sm text-muted">
                  {{ text.boardNoColumns() }}
                </p>
              </sol-card>
            } @else {
              <sol-kanban-board
                [columns]="kanbanColumns()"
                [cardTemplate]="taskCardTpl"
                (itemMoved)="onKanbanItemMoved($event)"
                (addRequested)="openCreate($event)"
              />
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
              <div class="overflow-x-auto rounded-xl border border-border bg-surface">
                <table class="w-full border-collapse text-left text-sm text-text">
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
                      (click)="openTaskDrawer(task)"
                    >
                      <td class="px-4 py-3 text-xs font-mono text-muted">
                        @if (task.task_key) {
                          <button
                            type="button"
                            (click)="$event.stopPropagation(); openTaskDrawer(task)"
                            class="font-semibold text-brand hover:underline"
                            [attr.aria-label]="openDetailAria(task.task_key)"
                          >{{ task.task_key }}</button>
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
                </table>
              </div>
            }
          }
        }

        <!-- BACKLOG (change 30-backlog-sprints-agrupados: secciones
             colapsables estilo Jira — active → draft → Backlog al final;
             closed detrás de un enlace. Cabecera = agregados del servidor;
             cuerpo = allTasks() ya cargadas, agrupadas por sprint_id, sin
             fetch extra — D3/D7.) -->
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

            @for (sprint of openSprintSections(); track sprint.id) {
              <ng-container
                *ngTemplateOutlet="sprintSectionTpl; context: { sprint: sprint, readOnly: false }"
              ></ng-container>
            }

            @if (closedSprints().length > 0) {
              <button
                type="button"
                (click)="showClosedSprints.set(!showClosedSprints())"
                class="self-start text-xs text-muted transition-colors hover:text-text"
              >
                {{
                  showClosedSprints()
                    ? text.hideClosedSprints()
                    : viewClosedSprintsLabel(closedSprints().length)
                }}
              </button>
            }

            @if (showClosedSprints()) {
              @for (sprint of closedSprints(); track sprint.id) {
                <ng-container
                  *ngTemplateOutlet="sprintSectionTpl; context: { sprint: sprint, readOnly: true }"
                ></ng-container>
              }
            }

            <!-- Sección Backlog fija al final (D4/D7: id estable 'backlog'). -->
            <div class="rounded-xl border border-border bg-surface shadow-sm">
              <div [id]="sectionId(null)" class="flex items-center justify-between gap-3 p-4">
                <div class="flex items-center gap-3">
                  <button
                    type="button"
                    (click)="toggleSection(sectionId(null))"
                    class="text-muted transition-colors hover:text-text"
                    [attr.aria-expanded]="!collapsedSections().has(sectionId(null))"
                    [attr.aria-label]="sectionToggleAria(text.backlogTitle(), sectionId(null))"
                  >
                    <sol-icon
                      [name]="collapsedSections().has(sectionId(null)) ? 'chevron-right' : 'chevron-down'"
                      size="sm"
                    />
                  </button>
                  <div>
                    <h3 class="text-base font-semibold text-text">{{ text.backlogTitle() }}</h3>
                    <p class="mt-1 text-xs text-muted">
                      {{ storyCountLabel(backlogAggregate().story_count) }} ·
                      {{ hoursSumLabel(backlogAggregate().estimation_hours_sum) }}
                    </p>
                  </div>
                </div>
              </div>
              @if (!collapsedSections().has(sectionId(null))) {
                <div class="flex flex-col gap-3 border-t border-border p-4">
                  @if (backlogTasks().length === 0) {
                    <p class="py-6 text-center text-sm text-muted">
                      {{ text.backlogEmpty() }}
                    </p>
                  } @else {
                    <!-- La reasignación de sprint vive ahora en el drawer de
                         detalle de la tarea (enlace "Abrir detalle" de cada
                         tarjeta). -->
                    @for (task of backlogTasks(); track task.id) {
                      <ng-container
                        *ngTemplateOutlet="taskCardTpl; context: { $implicit: task }"
                      ></ng-container>
                    }
                  }
                </div>
              }
            </div>
          </div>

          <!-- Cabecera + cuerpo de una sección de sprint, reutilizada para
               las abiertas (active/draft, con acción) y las cerradas
               (readOnly, sin acción — D5). -->
          <ng-template #sprintSectionTpl let-sprint="sprint" let-readOnly="readOnly">
            <div
              class="rounded-xl border border-border bg-surface shadow-sm"
              [class.opacity-80]="readOnly"
            >
              <div [id]="sectionId(sprint)" class="flex flex-wrap items-center justify-between gap-3 p-4">
                <div class="flex items-center gap-3">
                  <button
                    type="button"
                    (click)="toggleSection(sectionId(sprint))"
                    class="text-muted transition-colors hover:text-text"
                    [attr.aria-expanded]="!collapsedSections().has(sectionId(sprint))"
                    [attr.aria-label]="sectionToggleAria(sprint.name, sectionId(sprint))"
                  >
                    <sol-icon
                      [name]="collapsedSections().has(sectionId(sprint)) ? 'chevron-right' : 'chevron-down'"
                      size="sm"
                    />
                  </button>
                  <div>
                    <div class="flex items-center gap-2">
                      <h3 class="text-base font-semibold text-text">{{ sprint.name }}</h3>
                      <span
                        class="rounded-full px-2.5 py-0.5 text-xs font-medium"
                        [class]="sprintBadgeClass(sprint)"
                      >
                        {{ sprintStatusLabel(sprint) }}
                      </span>
                    </div>
                    <p class="mt-1 text-xs text-muted">
                      @if (sprint.start_date || sprint.end_date) {
                        {{ dateLabel(sprint.start_date) }} — {{ dateLabel(sprint.end_date) }}
                      } @else {
                        {{ text.backlogNoDates() }}
                      }
                      · {{ storyCountLabel(sprint.story_count) }} ·
                      {{ hoursSumLabel(sprint.estimation_hours_sum) }}
                    </p>
                  </div>
                </div>
                @if (!readOnly) {
                  <div class="shrink-0">
                    @if (sprint.status === 'active') {
                      <sol-button
                        type="button"
                        variant="secondary"
                        (click)="openCloseSprint(sprint)"
                        [ariaLabel]="closeSprintAria(sprint.name)"
                      >
                        {{ text.closeSprint() }}
                      </sol-button>
                    } @else if (canStartSprint(sprint)) {
                      <sol-button
                        type="button"
                        variant="primary"
                        [disabled]="startingSprintId() === sprint.id"
                        (click)="startSprint(sprint)"
                        [ariaLabel]="startSprintAria(sprint.name)"
                      >
                        {{ text.startSprint() }}
                      </sol-button>
                    } @else {
                      <sol-button
                        type="button"
                        variant="secondary"
                        (click)="openAddDates(sprint)"
                        [ariaLabel]="addDatesAria(sprint.name)"
                      >
                        {{ text.addDates() }}
                      </sol-button>
                    }
                  </div>
                }
              </div>
              @if (!collapsedSections().has(sectionId(sprint))) {
                <div class="flex flex-col gap-3 border-t border-border p-4">
                  @for (task of tasksBySprint().get(sprint.id) ?? []; track task.id) {
                    <ng-container
                      *ngTemplateOutlet="taskCardTpl; context: { $implicit: task }"
                    ></ng-container>
                  }
                </div>
              }
            </div>
          </ng-template>
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
                  <!-- Sin fechas aquí a propósito: el sprint nace en
                       "Borrador" y las fechas se agregan luego con
                       "Añadir fechas" (modal dedicado). -->
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
              @if (startSprintError()) {
                <!-- El servidor sigue siendo la fuente de verdad (D3/D4):
                     el botón "Iniciar sprint" se deshabilita en el cliente
                     sin fechas, pero una carrera entre pestañas puede llegar
                     igual a un 422/409 desde el backend. -->
                <div
                  role="alert"
                  class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
                >
                  {{ startSprintError() }}
                </div>
              }
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
                            {{ sprintStatusLabel(sprint) }}
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
                        @if (sprint.status === 'draft') {
                          <sol-button
                            type="button"
                            variant="secondary"
                            (click)="openAddDates(sprint)"
                            [ariaLabel]="addDatesAria(sprint.name)"
                          >
                            {{ text.addDates() }}
                          </sol-button>
                          <sol-button
                            type="button"
                            variant="primary"
                            [disabled]="!canStartSprint(sprint) || startingSprintId() === sprint.id"
                            [title]="canStartSprint(sprint) ? '' : text.startDisabledTooltip()"
                            (click)="startSprint(sprint)"
                            [ariaLabel]="startSprintAria(sprint.name)"
                          >
                            {{ text.startSprint() }}
                          </sol-button>
                        } @else if (sprint.status === 'active') {
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

        <!-- TIMELINE (Gantt estilo Jira: días arriba, banda de sprints,
             épicas agrupando sus tareas; clic en barra → drawer sin blur) -->
        @if (activeTab() === 'timeline') {
          <div class="flex flex-col gap-4">
            <div class="flex items-center justify-between gap-3">
              <h2 class="text-lg font-semibold text-text">{{ text.timelineTitle() }}</h2>
              <p class="text-xs text-muted">{{ text.timelineDescription() }}</p>
            </div>
            <sol-sprint-gantt
              [sprints]="sprints()"
              [tasks]="ganttTasks()"
              (taskClicked)="openTaskDrawer($event, { blur: false })"
            ></sol-sprint-gantt>
          </div>
        }

        <!-- Task card content: proyectado dentro de sol-kanban-board (tablero)
             y reutilizado tal cual en la lista de backlog. La librería
             sol-kanban-* NUNCA conoce Task (D2): este template es 100 %
             propiedad del consumidor. -->
        <ng-template #taskCardTpl let-task>
          <button
            type="button"
            (click)="openEdit(task)"
            class="group flex w-full flex-col gap-2 rounded-lg border border-border bg-surface p-3 text-left
                   shadow-sm transition-colors hover:border-brand/50 focus:outline-none
                   focus-visible:ring-2 focus-visible:ring-brand/50"
            [attr.aria-label]="taskCardEditAria(task)"
          >
            <div class="flex items-start justify-between gap-2">
              <p class="text-sm font-medium leading-snug text-text">
                {{ task.title }}
              </p>
              @if (task.risk_flag) {
                <span
                  class="shrink-0 text-danger"
                  [attr.aria-label]="task.risk_reason || text.taskCardRiskDefault()"
                  [attr.title]="task.risk_reason || text.taskCardRiskDefault()"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M4 22V4a1 1 0 0 1 1-1h13l-2.5 4L18 11H5" />
                  </svg>
                </span>
              }
            </div>

            <div class="flex flex-wrap items-center gap-1.5">
              <span
                class="rounded-full px-2 py-0.5 text-[11px] font-medium"
                [class]="priorityChipClass(task.priority)"
              >
                {{ priorityLabel(task.priority) }}
              </span>

              @if (taskCardShowPoints(task)) {
                <span
                  class="rounded-full bg-muted/10 px-2 py-0.5 text-[11px] font-medium text-muted"
                >
                  {{ task.estimation_points }} {{ text.taskCardPts() }}
                </span>
              }
              @if (taskCardShowHours(task)) {
                <span
                  class="rounded-full bg-muted/10 px-2 py-0.5 text-[11px] font-medium text-muted"
                >
                  {{ task.estimation_hours }} {{ text.taskCardHours() }}
                </span>
              }

              @if (taskCardDueLabel(task); as due) {
                <span
                  class="ml-auto inline-flex items-center gap-1 text-[11px] font-medium"
                  [class.text-danger]="isOverdue(task, doneStatus())"
                  [class.text-muted]="!isOverdue(task, doneStatus())"
                >
                  <sol-icon name="calendar" size="sm" />
                  {{ due }}
                </span>
              }
            </div>

            <div class="flex items-center gap-2 pt-1">
              <span
                class="grid h-6 w-6 place-items-center rounded-full bg-brand/10 text-[11px] font-semibold text-brand"
                [attr.aria-label]="taskCardAssigneeAria(task)"
                [attr.title]="task.assignee_name || text.taskCardUnassigned()"
              >
                {{ taskCardInitial(task) }}
              </span>
              <span class="truncate text-xs text-muted">
                {{ task.assignee_name || text.taskCardUnassigned() }}
              </span>
            </div>

            @if (task.task_key) {
              <button
                type="button"
                (click)="$event.stopPropagation(); openTaskDrawer(task)"
                class="mt-1 text-[11px] text-brand hover:underline self-end"
                [attr.aria-label]="text.taskCardOpenDetailAria()">
                {{ text.taskCardOpenDetail() }}
              </button>
            }
          </button>
        </ng-template>

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

      <!-- Add dates modal (sprint "Borrador" -> fechas antes de iniciar) -->
      @if (addDatesOpen()) {
        <sol-modal [open]="true"
          [title]="text.addDatesModalTitle()"
          size="sm"
          (closed)="cancelAddDates()"
        >
          <form
            [formGroup]="addDatesForm"
            (ngSubmit)="confirmAddDates()"
            class="flex flex-col gap-4"
            novalidate
          >
            <p class="text-sm text-muted">
              {{ text.addDatesModalDescription() }}
            </p>
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

            @if (addDatesError()) {
              <div
                role="alert"
                class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
              >
                {{ addDatesError() }}
              </div>
            }

            <div class="flex gap-3">
              <sol-button
                type="button"
                variant="secondary"
                class="w-full"
                [disabled]="addingDatesBusy()"
                (click)="cancelAddDates()"
              >
                {{ text.addDatesModalCancel() }}
              </sol-button>
              <sol-button
                type="submit"
                variant="primary"
                class="w-full"
                [disabled]="addingDatesBusy()"
              >
                {{ addingDatesBusy() ? text.addDatesModalSaving() : text.addDatesModalSave() }}
              </sol-button>
            </div>
          </form>
        </sol-modal>
      }

      <!-- Task detail drawer (estilo Jira): hospeda el panel de detalle sin
           salir del workspace. En el cronograma abre SIN blur (blur=false)
           para no difuminar la vista densa de barras. -->
      @if (openedTask(); as opened) {
        <sol-drawer
          [open]="true"
          [title]="drawerTitle()"
          size="lg"
          [blur]="drawerBlur()"
          (closed)="closeTaskDrawer()"
        >
          <sol-task-detail-panel
            [taskKey]="opened.task_key!"
            [compact]="true"
            [sprints]="sprints()"
            [sprintsEnabled]="sprintsEnabled()"
            [estimationMode]="estimationMode()"
            (taskChanged)="onDrawerTaskChanged($event)"
          />
        </sol-drawer>
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
    backlogNoDates: this.i18n.t('workspace.backlog.noDates'),
    hideClosedSprints: this.i18n.t('workspace.backlog.hideClosedSprints'),
    newSprintTitle: this.i18n.t('workspace.sprints.newTitle'),
    sprintNameLabel: this.i18n.t('workspace.sprints.nameLabel'),
    sprintNamePlaceholder: this.i18n.t('workspace.sprints.namePlaceholder'),
    sprintGoalLabel: this.i18n.t('workspace.sprints.goalLabel'),
    sprintGoalPlaceholder: this.i18n.t('workspace.sprints.goalPlaceholder'),
    sprintStartLabel: this.i18n.t('workspace.sprints.startLabel'),
    sprintEndLabel: this.i18n.t('workspace.sprints.endLabel'),
    saving: this.i18n.t('workspace.sprints.saving'),
    createSprint: this.i18n.t('workspace.sprints.create'),
    sprintsEmpty: this.i18n.t('workspace.sprints.empty'),
    sprintActive: this.i18n.t('workspace.sprints.statusActive'),
    sprintClosed: this.i18n.t('workspace.sprints.statusClosed'),
    sprintDraft: this.i18n.t('workspace.sprints.statusDraft'),
    hideBurndown: this.i18n.t('workspace.sprints.hideBurndown'),
    showBurndown: this.i18n.t('workspace.sprints.showBurndown'),
    closeSprint: this.i18n.t('workspace.sprints.close'),
    reactivate: this.i18n.t('workspace.sprints.reactivate'),
    addDates: this.i18n.t('workspace.sprints.addDates'),
    startSprint: this.i18n.t('workspace.sprints.start'),
    startDisabledTooltip: this.i18n.t('workspace.sprints.startDisabledTooltip'),
    addDatesModalTitle: this.i18n.t('workspace.addDates.title'),
    addDatesModalDescription: this.i18n.t('workspace.addDates.description'),
    addDatesModalCancel: this.i18n.t('workspace.addDates.cancel'),
    addDatesModalSave: this.i18n.t('workspace.addDates.save'),
    addDatesModalSaving: this.i18n.t('workspace.addDates.saving'),
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
    /* Contenido de la tarjeta de tarea (antes en el widget task-card, ya
       retirado — T70): proyectado en sol-kanban-board y reutilizado en el
       backlog vía taskCardTpl. */
    taskCardRiskDefault: this.i18n.t('taskCard.riskDefault'),
    taskCardUnassigned: this.i18n.t('taskCard.unassigned'),
    taskCardPts: this.i18n.t('taskCard.pts'),
    taskCardHours: this.i18n.t('taskCard.hours'),
    taskCardOpenDetail: this.i18n.t('taskCard.openDetail'),
    taskCardOpenDetailAria: this.i18n.t('taskCard.openDetailAria'),
  } as const;

  protected readonly fieldClass =
    'h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text ' +
    'transition-colors focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40';

  private readonly projectId = signal<string>('');

  protected readonly project = signal<ProjectDetail | null>(null);
  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);

  protected readonly allTasks = signal<Task[]>([]);
  protected readonly tasksError = signal<string | null>(null);

  /**
   * Hijas directas de cada épica. El listado del proyecto solo devuelve
   * tareas raíz (`parent_task_id` nulo), así que el árbol épica→historias
   * del Gantt se completa con una consulta `?parent_task_id={epicId}` por
   * épica (B1) tras cada carga de tareas.
   */
  protected readonly epicChildren = signal<Task[]>([]);

  /** Tareas del cronograma: raíces + hijas de épicas, sin duplicados. */
  protected readonly ganttTasks = computed<Task[]>(() => {
    const roots = this.allTasks();
    const seen = new Set(roots.map((task) => task.id));
    const children = this.epicChildren().filter((task) => !seen.has(task.id));
    return [...roots, ...children];
  });

  protected readonly members = signal<Member[]>([]);
  protected readonly sprints = signal<SprintListItem[]>([]);

  /** Aggregate of the project's tasks with no sprint (change
   * 30-backlog-sprints-agrupados) — populated from `meta.backlog` on every
   * `loadSprints()`, never left `null`. */
  protected readonly backlogAggregate = signal<BacklogAggregate>({
    story_count: 0,
    estimation_hours_sum: 0,
  });

  /** Backlog section collapse state, hydrated per-project from localStorage
   * (design.md D6). */
  protected readonly collapsedSections = signal<Set<string>>(new Set());

  /** "Ver sprints cerrados" toggle — in-memory only (not persisted, see
   * tasks.md Risks). */
  protected readonly showClosedSprints = signal(false);

  protected readonly activeTab = signal<TabId>('board');
  protected readonly viewMode = signal<ViewMode>('board');

  protected readonly modalOpen = signal(false);
  protected readonly editingTask = signal<Task | null>(null);
  protected readonly presetStatus = signal<string | null>(null);
  protected readonly savingTask = signal(false);
  protected readonly modalError = signal<string | null>(null);

  protected readonly savingSprint = signal(false);

  /* ---- Task detail drawer state ------------------------------------------ */

  /** Tarea abierta en el drawer de detalle (null = drawer cerrado). */
  protected readonly openedTask = signal<Task | null>(null);
  /** El cronograma abre el drawer sin blur (velo suave); el resto con blur. */
  protected readonly drawerBlur = signal(true);
  /** Hubo cambios guardados desde el drawer → recargar listas al cerrarlo. */
  private drawerChanged = false;

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

  /* ---- Draft sprint flow (change 29-sprint-borrador) --------------------- */
  /** "Iniciar sprint" en curso para este id (deshabilita ese botón puntual). */
  protected readonly startingSprintId = signal<string | null>(null);
  /** Mensaje visible cuando el servidor rechaza "Iniciar sprint" (422/409). */
  protected readonly startSprintError = signal<string | null>(null);

  protected readonly addDatesOpen = signal(false);
  protected readonly addingDatesSprintId = signal<string | null>(null);
  protected readonly addingDatesBusy = signal(false);
  protected readonly addDatesError = signal<string | null>(null);

  protected readonly addDatesForm = this.fb.group({
    start_date: [''],
    end_date: [''],
  });

  /** Sin fechas a propósito: el sprint nace "Borrador" (nombre opcional —
   * el backend autonombra cuando queda vacío). */
  protected readonly sprintForm = this.fb.group({
    name: [''],
    goal: [''],
  });

  constructor() {
    // Lazy-load velocity when the sprints tab becomes active.
    effect(() => {
      if (this.activeTab() === 'sprints' && !this.velocityLoaded()) {
        this.loadVelocity();
      }
    });

    // Prefill the sprint name with the backend's auto-name suggestion the
    // first time the sprints tab is opened (same lazy pattern as loadVelocity
    // above), only while the user hasn't typed anything yet.
    effect(() => {
      if (this.activeTab() === 'sprints' && this.sprintForm.controls.name.pristine) {
        this.workspace.suggestedSprintName(this.projectId()).subscribe({
          next: (res) => {
            if (this.sprintForm.controls.name.pristine) {
              this.sprintForm.patchValue({ name: res.data.name });
            }
          },
          error: () => undefined,
        });
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

  /**
   * Sections of the grouped Backlog tab, in display order (design.md D4):
   * `active` sprints first, then `draft` ordered ascending by `created_at`.
   * `closed` sprints are excluded here — they only render behind the "Ver
   * sprints cerrados" toggle (`closedSprints` below).
   */
  protected readonly openSprintSections = computed<SprintListItem[]>(() => {
    const all = this.sprints();
    const active = all.filter((sprint) => sprint.status === 'active');
    const draft = all
      .filter((sprint) => sprint.status === 'draft')
      .sort((a, b) => a.created_at.localeCompare(b.created_at));
    return [...active, ...draft];
  });

  protected readonly closedSprints = computed<SprintListItem[]>(() =>
    this.sprints().filter((sprint) => sprint.status === 'closed'),
  );

  /**
   * Groups the ALREADY-LOADED `allTasks()` by `sprint_id` (design.md D3/D7)
   * — no extra fetch. The section HEADER never reads from this map: it
   * always shows the server-authoritative `story_count`/
   * `estimation_hours_sum` (avoids the divergence risk #1 from proposal.md).
   */
  protected readonly tasksBySprint = computed<Map<string, Task[]>>(() => {
    const map = new Map<string, Task[]>();
    for (const task of this.allTasks()) {
      if (!task.sprint_id) {
        continue;
      }
      const bucket = map.get(task.sprint_id);
      if (bucket) {
        bucket.push(task);
      } else {
        map.set(task.sprint_id, [task]);
      }
    }
    return map;
  });

  /**
   * Columnas genéricas para `sol-kanban-board` (D2: la lib nunca conoce
   * `Task`). Cada `KanbanColumn.id` es el propio valor de `status` — así
   * `KanbanItemMoved.toColumnId` ya es el nuevo status listo para el PATCH.
   * `Task` satisface `KanbanItem` (`id: string`) sin adaptador.
   */
  protected readonly kanbanColumns = computed<KanbanColumn<Task>[]>(() => {
    const tasks = this.allTasks();
    return this.allowedStatuses().map((status) => ({
      id: status,
      title: statusDisplay(status),
      items: tasks.filter((task) => task.status === status),
    }));
  });

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

  protected addDatesAria(name: string): string {
    return this.i18n.translate('workspace.sprints.addDatesAria', { name });
  }

  protected startSprintAria(name: string): string {
    return this.i18n.translate('workspace.sprints.startAria', { name });
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

  /* ---- Task card content (taskCardTpl) ----------------------------------- */

  /** Solo `null | undefined | ''` para vía `isOverdue`; el helper del modelo ya cubre esto. */
  protected isOverdue(task: Task, doneStatus: string | null): boolean {
    return isOverdue(task, doneStatus);
  }

  protected taskCardEditAria(task: Task): string {
    return this.i18n.translate('taskCard.editAria', { title: task.title });
  }

  protected taskCardAssigneeAria(task: Task): string {
    return task.assignee_name
      ? this.i18n.translate('taskCard.assignedTo', { name: task.assignee_name })
      : this.i18n.translate('taskCard.unassigned');
  }

  protected taskCardInitial(task: Task): string {
    const name = task.assignee_name?.trim();
    return name ? name.charAt(0).toUpperCase() : '?';
  }

  protected taskCardShowPoints(task: Task): boolean {
    const mode = this.estimationMode();
    return (mode === 'points' || mode === 'both') && task.estimation_points != null;
  }

  protected taskCardShowHours(task: Task): boolean {
    const mode = this.estimationMode();
    return (mode === 'hours' || mode === 'both') && task.estimation_hours != null;
  }

  /** Vacío cuando no hay fecha (a diferencia de `dateLabel`, que cae a "sin fecha") — oculta el badge por completo. */
  protected taskCardDueLabel(task: Task): string {
    return formatShortDate(task.due_date);
  }

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id') ?? '';
    this.projectId.set(id);
    this.collapsedSections.set(readPersistedSections(id));
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
      next: (res) => {
        this.sprints.set(res.data ?? []);
        this.backlogAggregate.set(
          res.meta?.backlog ?? { story_count: 0, estimation_hours_sum: 0 },
        );
      },
      error: () => {
        this.sprints.set([]);
        this.backlogAggregate.set({ story_count: 0, estimation_hours_sum: 0 });
      },
    });
  }

  private loadTasks(): void {
    this.tasksError.set(null);
    this.workspace.tasks(this.projectId()).subscribe({
      next: (res) => {
        this.allTasks.set(res.data ?? []);
        this.loadEpicChildren(res.data ?? []);
      },
      error: () =>
        this.tasksError.set(
          this.i18n.translate('workspace.errors.tasksLoad'),
        ),
    });
  }

  /** Carga las hijas de cada épica (una consulta por épica, en paralelo). */
  private loadEpicChildren(tasks: Task[]): void {
    const epics = tasks.filter((task) => task.task_type === 'epic');
    if (epics.length === 0) {
      this.epicChildren.set([]);
      return;
    }
    forkJoin(
      epics.map((epic) =>
        this.workspace.tasks(this.projectId(), { parent_task_id: epic.id }),
      ),
    ).subscribe({
      next: (responses) =>
        this.epicChildren.set(responses.flatMap((res) => res.data ?? [])),
      error: () => this.epicChildren.set([]),
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

  /* ---- Drag and drop ------------------------------------------------------
   * `sol-kanban-board` mantiene su propio espejo interno (D4): un reorden
   * DENTRO de la misma columna ya queda reflejado ahí sin que este consumidor
   * haga nada (no se persiste orden, igual que el board manual anterior). Un
   * movimiento ENTRE columnas sí requiere el PATCH optimista — actualizar
   * `allTasks` reasigna una referencia NUEVA a `kanbanColumns()`, lo que hace
   * que el board re-siembre su espejo (rollback natural si el PATCH falla).
   */

  protected onKanbanItemMoved(moved: KanbanItemMoved<Task>): void {
    if (moved.fromColumnId === moved.toColumnId) {
      return;
    }

    const taskId = moved.item.id;
    const previousStatus = moved.item.status;
    const nextStatus = moved.toColumnId;

    this.allTasks.update((tasks) =>
      tasks.map((task) => (task.id === taskId ? { ...task, status: nextStatus } : task)),
    );

    this.workspace.updateTask(taskId, { status: nextStatus }).subscribe({
      error: () => {
        this.allTasks.update((tasks) =>
          tasks.map((task) => (task.id === taskId ? { ...task, status: previousStatus } : task)),
        );
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
          start_date: result.start_date,
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
          start_date: result.start_date,
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

  /* ---- Task detail drawer -------------------------------------------------
   * Grid y cronograma abren el detalle in-place (estilo Jira) en vez de
   * navegar a /task/:key. La ruta sigue existiendo para enlaces directos.
   * Los cambios guardados en el drawer se reflejan de inmediato en la copia
   * local (`allTasks`) y las listas se recargan del backend al cerrarlo.
   */

  protected openTaskDrawer(task: Task, opts?: { blur?: boolean }): void {
    if (!task.task_key) {
      // Sin clave no hay detalle por key: cae al modal de edición.
      this.openEdit(task);
      return;
    }
    this.drawerBlur.set(opts?.blur ?? true);
    this.openedTask.set(task);
  }

  protected closeTaskDrawer(): void {
    this.openedTask.set(null);
    this.drawerBlur.set(true);
    if (this.drawerChanged) {
      this.drawerChanged = false;
      this.loadTasks();
      const selected = this.selectedSprintId();
      if (selected) {
        this.loadBurndown(selected);
      }
    }
  }

  /** Espeja cada guardado del drawer sobre las copias locales sin ir al backend. */
  protected onDrawerTaskChanged(updated: TaskDetail): void {
    this.drawerChanged = true;
    this.allTasks.update((tasks) =>
      tasks.map((task) =>
        task.id === updated.id ? { ...task, ...updated } : task,
      ),
    );
    this.epicChildren.update((tasks) =>
      tasks.map((task) =>
        task.id === updated.id ? { ...task, ...updated } : task,
      ),
    );
  }

  protected readonly drawerTitle = computed<string>(() => {
    const task = this.openedTask();
    return task?.task_key ?? task?.title ?? '';
  });

  /* ---- Sprints ----------------------------------------------------------- */

  protected onCreateSprint(): void {
    const raw = this.sprintForm.getRawValue();
    this.savingSprint.set(true);
    this.workspace
      .createSprint(this.projectId(), {
        // Blank -> omitted entirely: the backend auto-names the sprint.
        name: (raw.name ?? '').trim() || undefined,
        goal: (raw.goal ?? '').trim() || null,
      })
      .subscribe({
        next: () => {
          this.savingSprint.set(false);
          this.sprintForm.reset({ name: '', goal: '' });
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

  /* ---- Draft sprint: add dates + start (change 29-sprint-borrador) ------- */

  protected canStartSprint(sprint: Sprint): boolean {
    return !!sprint.start_date && !!sprint.end_date;
  }

  protected openAddDates(sprint: Sprint): void {
    this.addingDatesSprintId.set(sprint.id);
    this.addDatesError.set(null);
    this.addDatesForm.reset({
      start_date: sprint.start_date ? sprint.start_date.slice(0, 10) : '',
      end_date: sprint.end_date ? sprint.end_date.slice(0, 10) : '',
    });
    this.addDatesOpen.set(true);
  }

  protected cancelAddDates(): void {
    this.addDatesOpen.set(false);
    this.addingDatesSprintId.set(null);
    this.addDatesError.set(null);
  }

  protected confirmAddDates(): void {
    const sprintId = this.addingDatesSprintId();
    if (!sprintId) return;

    const raw = this.addDatesForm.getRawValue();
    this.addingDatesBusy.set(true);
    this.addDatesError.set(null);

    this.workspace
      .updateSprint(sprintId, {
        start_date: raw.start_date || null,
        end_date: raw.end_date || null,
      })
      .subscribe({
        next: () => {
          this.addingDatesBusy.set(false);
          this.addDatesOpen.set(false);
          this.addingDatesSprintId.set(null);
          this.loadSprints();
        },
        error: () => {
          this.addingDatesBusy.set(false);
          this.addDatesError.set(this.i18n.translate('workspace.addDates.error'));
        },
      });
  }

  protected startSprint(sprint: Sprint): void {
    this.startingSprintId.set(sprint.id);
    this.startSprintError.set(null);
    this.workspace.startSprint(sprint.id).subscribe({
      next: () => {
        this.startingSprintId.set(null);
        this.loadSprints();
      },
      error: (err: HttpErrorResponse) => {
        this.startingSprintId.set(null);
        if (err.status === 422) {
          this.startSprintError.set(
            this.i18n.translate('workspace.errors.sprintMissingDates'),
          );
        } else if (err.status === 409) {
          this.startSprintError.set(
            this.i18n.translate('workspace.errors.sprintAlreadyStarted'),
          );
        } else {
          this.startSprintError.set(
            this.i18n.translate('workspace.errors.sprintStart'),
          );
        }
        this.loadSprints();
      },
    });
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
    if (sprint.status === 'active') {
      return 'bg-success/10 text-success';
    }
    if (sprint.status === 'draft') {
      return 'bg-warning/10 text-warning';
    }
    return 'bg-muted/15 text-muted';
  }

  protected sprintStatusLabel(sprint: Sprint): string {
    if (sprint.status === 'active') {
      return this.text.sprintActive();
    }
    if (sprint.status === 'draft') {
      return this.text.sprintDraft();
    }
    return this.text.sprintClosed();
  }

  /* ---- Grouped backlog sections (change 30-backlog-sprints-agrupados) --- */

  /** Stable id per section (design.md D7 — seam for drag & drop in 31):
   * `sprint-<uuid>` for a sprint, the literal `'backlog'` for the Backlog
   * section (`sprint === null`). */
  protected sectionId(sprint: Sprint | null): string {
    return sprint ? `sprint-${sprint.id}` : 'backlog';
  }

  protected toggleSection(id: string): void {
    const next = new Set(this.collapsedSections());
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    this.collapsedSections.set(next);
    persistSections(this.projectId(), next);
  }

  protected storyCountLabel(count: number): string {
    return this.i18n.translate('workspace.backlog.storyCount', { count });
  }

  protected hoursSumLabel(hours: number): string {
    return this.i18n.translate('workspace.backlog.hoursSum', { hours });
  }

  protected viewClosedSprintsLabel(count: number): string {
    return this.i18n.translate('workspace.backlog.viewClosedSprints', { count });
  }

  protected sectionToggleAria(name: string, sectionId: string): string {
    return this.collapsedSections().has(sectionId)
      ? this.i18n.translate('workspace.backlog.expandAria', { name })
      : this.i18n.translate('workspace.backlog.collapseAria', { name });
  }
}

/** localStorage key for the collapsed-section ids of one project (design.md
 * D6) — one key per project, so collapse state never leaks across projects. */
function backlogSectionsKey(projectId: string): string {
  return `sp-backlog-sections-${projectId}`;
}

/** Reads the collapsed section ids for a project. Missing key, invalid JSON
 * or storage failures all fall back to the design's explicit default:
 * expanded (empty set). */
function readPersistedSections(projectId: string): Set<string> {
  try {
    const raw = localStorage.getItem(backlogSectionsKey(projectId));
    if (!raw) {
      return new Set();
    }
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? new Set(parsed) : new Set();
  } catch {
    return new Set();
  }
}

/** Persists the collapsed section ids for a project; storage failures are
 * silently ignored (state degrades to in-memory only, mirrors
 * `persistCollapsed` in `layout-shell.component.ts`). */
function persistSections(projectId: string, ids: Set<string>): void {
  try {
    localStorage.setItem(backlogSectionsKey(projectId), JSON.stringify([...ids]));
  } catch {
    // Storage no disponible (modo privado/quota): el estado queda en memoria.
  }
}
