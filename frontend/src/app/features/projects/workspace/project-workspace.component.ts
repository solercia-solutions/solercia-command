import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
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
import { ButtonComponent } from '../../../shared/ui/button.component';
import { CardComponent } from '../../../shared/ui/card.component';
import { ProjectsService } from '../projects.service';
import { EstimationMode, ProjectDetail } from '../project.model';
import { WorkspaceService } from './workspace.service';
import {
  BoardColumnComponent,
  ColumnDrop,
} from './board-column.component';
import { TaskCardComponent } from './task-card.component';
import { BurndownChartComponent } from './burndown-chart.component';
import {
  TaskFormResult,
  TaskModalComponent,
} from './task-modal.component';
import {
  BurndownData,
  METHODOLOGY_BADGE,
  Member,
  Sprint,
  Task,
  formatShortDate,
} from './workspace.model';

type TabId = 'board' | 'backlog' | 'sprints';

/** Board column working state; `tasks` are live arrays for CDK drag-drop. */
interface BoardColumn {
  status: string;
  tasks: Task[];
}

/**
 * Methodology-driven project workspace. Renders a board (one column per
 * allowed status), plus backlog and sprint tabs when the methodology enables
 * them. All behaviour derives from `methodology_info` — no per-methodology ifs.
 */
@Component({
  selector: 'sp-project-workspace',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    ReactiveFormsModule,
    DragDropModule,
    ButtonComponent,
    CardComponent,
    BoardColumnComponent,
    TaskCardComponent,
    TaskModalComponent,
    BurndownChartComponent,
  ],
  template: `
    @if (loading()) {
      <p class="text-sm text-muted">Cargando proyecto…</p>
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
            Volver a proyectos
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
            <sp-button
              type="button"
              variant="primary"
              (click)="openCreate()"
              ariaLabel="Crea una nueva tarea"
            >
              + Nueva tarea
            </sp-button>
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

        <!-- BOARD -->
        @if (activeTab() === 'board') {
          @if (boardColumns().length === 0) {
            <sp-card>
              <p class="py-6 text-center text-sm text-muted">
                Esta metodología no define columnas de tablero.
              </p>
            </sp-card>
          } @else {
            <div
              cdkDropListGroup
              class="flex gap-4 overflow-x-auto pb-2"
            >
              @for (column of boardColumns(); track column.status) {
                <sp-board-column
                  [status]="column.status"
                  [tasks]="column.tasks"
                  [estimationMode]="estimationMode()"
                  [doneStatus]="doneStatus()"
                  (addTask)="openCreate($event)"
                  (editTask)="openEdit($event)"
                  (dropped)="onDrop($event)"
                ></sp-board-column>
              }
            </div>
          }
        }

        <!-- BACKLOG -->
        @if (activeTab() === 'backlog') {
          <div class="flex flex-col gap-4">
            <div class="flex items-center justify-between gap-3">
              <h2 class="text-lg font-semibold text-text">Backlog</h2>
              <sp-button
                type="button"
                variant="secondary"
                (click)="openCreate()"
                ariaLabel="Agrega una tarea al backlog"
              >
                + Agregar al backlog
              </sp-button>
            </div>
            @if (backlogTasks().length === 0) {
              <sp-card>
                <p class="py-6 text-center text-sm text-muted">
                  No hay tareas en el backlog.
                </p>
              </sp-card>
            } @else {
              <div class="flex flex-col gap-3">
                @for (task of backlogTasks(); track task.id) {
                  <div class="flex flex-col gap-2 sm:flex-row sm:items-start">
                    <div class="flex-1">
                      <sp-task-card
                        [task]="task"
                        [estimationMode]="estimationMode()"
                        [doneStatus]="doneStatus()"
                        (edit)="openEdit($event)"
                      ></sp-task-card>
                    </div>
                    @if (sprintsEnabled()) {
                      <label class="block sm:w-56">
                        <span class="mb-1 block text-xs font-medium text-muted"
                          >Mover a sprint</span
                        >
                        <select
                          [value]="task.sprint_id ?? ''"
                          (change)="onAssignSprint(task, $event)"
                          class="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text
                                 transition-colors focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40"
                          [attr.aria-label]="'Asigna ' + task.title + ' a un sprint'"
                        >
                          <option value="">Backlog</option>
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
              <sp-card>
                <h2 class="mb-4 text-lg font-semibold text-text">Nuevo sprint</h2>
                <form
                  [formGroup]="sprintForm"
                  (ngSubmit)="onCreateSprint()"
                  class="flex flex-col gap-4"
                  novalidate
                >
                  <label class="block">
                    <span class="mb-1.5 block text-sm font-medium text-text"
                      >Nombre</span
                    >
                    <input
                      formControlName="name"
                      placeholder="Ej. Sprint 1"
                      [class]="fieldClass"
                    />
                    @if (sprintNameError()) {
                      <p class="mt-1 text-xs text-danger">
                        El nombre es obligatorio.
                      </p>
                    }
                  </label>
                  <label class="block">
                    <span class="mb-1.5 block text-sm font-medium text-text"
                      >Objetivo</span
                    >
                    <input
                      formControlName="goal"
                      placeholder="Meta del sprint (opcional)"
                      [class]="fieldClass"
                    />
                  </label>
                  <div class="grid grid-cols-2 gap-3">
                    <label class="block">
                      <span class="mb-1.5 block text-sm font-medium text-text"
                        >Inicio</span
                      >
                      <input
                        type="date"
                        formControlName="start_date"
                        [class]="fieldClass"
                      />
                    </label>
                    <label class="block">
                      <span class="mb-1.5 block text-sm font-medium text-text"
                        >Fin</span
                      >
                      <input
                        type="date"
                        formControlName="end_date"
                        [class]="fieldClass"
                      />
                    </label>
                  </div>
                  <sp-button
                    type="submit"
                    variant="primary"
                    [block]="true"
                    [disabled]="savingSprint()"
                  >
                    {{ savingSprint() ? 'Guardando…' : 'Crear sprint' }}
                  </sp-button>
                </form>
              </sp-card>
            </div>

            <div class="flex flex-col gap-3 lg:col-span-2">
              @if (sprints().length === 0) {
                <sp-card>
                  <p class="py-6 text-center text-sm text-muted">
                    Todavía no hay sprints en este proyecto.
                  </p>
                </sp-card>
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
                            {{ sprint.status === 'active' ? 'Activo' : 'Cerrado' }}
                          </span>
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
                      <div class="flex shrink-0 items-center gap-2">
                        <sp-button
                          type="button"
                          variant="primary"
                          (click)="selectSprint(sprint)"
                          [ariaLabel]="'Muestra el burndown del sprint ' + sprint.name"
                        >
                          {{
                            selectedSprintId() === sprint.id
                              ? 'Ocultar burndown'
                              : 'Ver burndown'
                          }}
                        </sp-button>
                        <sp-button
                          type="button"
                          variant="secondary"
                          (click)="toggleSprintStatus(sprint)"
                          [ariaLabel]="
                            sprint.status === 'active'
                              ? 'Cierra el sprint ' + sprint.name
                              : 'Reactiva el sprint ' + sprint.name
                          "
                        >
                          {{ sprint.status === 'active' ? 'Cerrar' : 'Reactivar' }}
                        </sp-button>
                      </div>
                    </div>

                    @if (selectedSprintId() === sprint.id) {
                      <div class="mt-4 border-t border-border pt-4">
                        @if (burndownLoading()) {
                          <p class="py-6 text-center text-sm text-muted">
                            Cargando burndown…
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
                              Total:
                              <span class="font-semibold text-text">
                                {{ burndownTotal(bd) }} {{ burndownUnitLabel(bd) }}
                              </span>
                            </span>
                            <span class="text-muted">
                              Completadas:
                              <span class="font-semibold text-text">
                                {{ bd.completed_tasks }} de {{ bd.total_tasks }}
                                tareas
                              </span>
                            </span>
                          </div>
                          <sp-burndown-chart
                            [days]="bd.days"
                            [unit]="bd.unit"
                          ></sp-burndown-chart>
                        }
                      </div>
                    }
                  </div>
                }
              }
            </div>
          </div>
        }
      </section>

      <!-- Task modal -->
      @if (modalOpen()) {
        <sp-task-modal
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
          (close)="closeModal()"
        ></sp-task-modal>
      }
    }
  `,
})
export class ProjectWorkspaceComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly fb = inject(FormBuilder);
  private readonly projectsService = inject(ProjectsService);
  private readonly workspace = inject(WorkspaceService);

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

  protected readonly sprintForm = this.fb.group({
    name: ['', [Validators.required]],
    goal: [''],
    start_date: [''],
    end_date: [''],
  });

  protected readonly tabs = computed(() => {
    const info = this.project()?.methodology_info;
    const list: { id: TabId; label: string }[] = [
      { id: 'board', label: 'Tablero' },
    ];
    if (info?.has_backlog) {
      list.push({ id: 'backlog', label: 'Backlog' });
    }
    if (info?.sprints_enabled) {
      list.push({ id: 'sprints', label: 'Sprints' });
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

  protected methodologyBadge(): string {
    const methodology = this.project()?.methodology;
    return methodology ? METHODOLOGY_BADGE[methodology] : '';
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
      this.loadError.set('No se encontró el proyecto solicitado.');
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
          err.status === 0
            ? 'No fue posible conectar con el servidor. Inténtalo de nuevo.'
            : 'No se pudo cargar el proyecto. Inténtalo más tarde.',
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
          'No se pudieron cargar las tareas. Inténtalo más tarde.',
        ),
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
    // Optimistic: the status IS the column.
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
        'No se pudo guardar la tarea. Revisa los datos e inténtalo de nuevo.',
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
        this.modalError.set('No se pudo eliminar la tarea. Inténtalo de nuevo.');
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
          // Keep the open burndown in sync with the new sprint contents.
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

  /* ---- Burndown ---------------------------------------------------------- */

  protected selectSprint(sprint: Sprint): void {
    // Toggle: clicking the open sprint again hides its burndown.
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
          'No se pudo cargar el burndown del sprint. Inténtalo más tarde.',
        );
      },
    });
  }

  protected burndownTotal(data: BurndownData): number {
    return data.unit === 'points' ? data.total_points : data.total_tasks;
  }

  protected burndownUnitLabel(data: BurndownData): string {
    return data.unit === 'points' ? 'puntos' : 'tareas';
  }

  protected dateLabel(value: string | null | undefined): string {
    return formatShortDate(value) || 'sin fecha';
  }

  protected sprintBadgeClass(sprint: Sprint): string {
    return sprint.status === 'active'
      ? 'bg-success/10 text-success'
      : 'bg-muted/15 text-muted';
  }
}
