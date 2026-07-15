import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  inject,
  input,
  output,
} from '@angular/core';
import {
  FormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { EstimationMode } from '@entities/project/project.model';
import { ButtonComponent } from '@shared/ui/button.component';
import {
  Member,
  PRIORITY_OPTIONS,
  Priority,
  Sprint,
  TASK_TYPE_OPTIONS,
  Task,
  statusDisplay,
} from '@entities/workspace/workspace.model';

/** Normalized result emitted on save; the container maps it to POST/PATCH. */
export interface TaskFormResult {
  title: string;
  description: string | null;
  status: string;
  priority: Priority;
  assignee_id: string | null;
  estimation_points: number | null;
  estimation_hours: number | null;
  due_date: string | null;
  sprint_id: string | null;
  task_type: string;
}

/**
 * Modal form to create or edit a task. Fields shown adapt to the methodology:
 * estimation inputs follow `estimationMode`; the sprint selector appears only
 * when sprints are enabled. Purely presentational — emits `save`/`close`.
 */
@Component({
  selector: 'bk-task-modal',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, ButtonComponent],
  template: `
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
      (click)="close.emit()"
    >
      <div
        role="dialog"
        aria-modal="true"
        [attr.aria-label]="task() ? 'Edita la tarea' : 'Crea una tarea'"
        (click)="$event.stopPropagation()"
        class="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-border bg-surface p-5 shadow-lg"
      >
        <div class="mb-4 flex items-center justify-between gap-2">
          <h2 class="text-lg font-semibold text-text">
            {{ task() ? 'Editar tarea' : 'Nueva tarea' }}
          </h2>
          <button
            type="button"
            (click)="close.emit()"
            class="grid h-8 w-8 place-items-center rounded-lg text-muted transition-colors hover:bg-muted/10 hover:text-text
                   focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
            aria-label="Cierra el formulario"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <form
          [formGroup]="form"
          (ngSubmit)="onSubmit()"
          class="flex flex-col gap-4"
          novalidate
        >
          <label class="block">
            <span class="mb-1.5 block text-sm font-medium text-text">Título</span>
            <input
              formControlName="title"
              placeholder="Ej. Diseñar el formulario de registro"
              [class]="fieldClass"
            />
            @if (showError('title')) {
              <p class="mt-1 text-xs text-danger">El título es obligatorio.</p>
            }
          </label>

          <label class="block">
            <span class="mb-1.5 block text-sm font-medium text-text"
              >Descripción</span
            >
            <textarea
              formControlName="description"
              rows="3"
              placeholder="Detalla el alcance (opcional)"
              class="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text
                     placeholder:text-muted transition-colors focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40"
            ></textarea>
          </label>

          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-text"
                >Estado</span
              >
              <select formControlName="status" [class]="fieldClass">
                @for (status of allowedStatuses(); track status) {
                  <option [value]="status">{{ statusLabel(status) }}</option>
                }
              </select>
            </label>

            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-text"
                >Prioridad</span
              >
              <select formControlName="priority" [class]="fieldClass">
                @for (option of priorityOptions; track option.value) {
                  <option [value]="option.value">{{ option.label }}</option>
                }
              </select>
            </label>

            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-text"
                >Responsable</span
              >
              <select formControlName="assignee_id" [class]="fieldClass">
                <option [ngValue]="null">Sin responsable</option>
                @for (member of members(); track member.user_id) {
                  <option [ngValue]="member.user_id">
                    {{ member.full_name }}
                  </option>
                }
              </select>
            </label>

            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-text"
                >Tipo</span
              >
              <select formControlName="task_type" [class]="fieldClass">
                @for (option of taskTypeOptions; track option.value) {
                  <option [value]="option.value">{{ option.label }}</option>
                }
              </select>
            </label>

            @if (showPoints()) {
              <label class="block">
                <span class="mb-1.5 block text-sm font-medium text-text"
                  >Estimación (puntos)</span
                >
                <input
                  type="number"
                  min="0"
                  step="1"
                  formControlName="estimation_points"
                  placeholder="0"
                  [class]="fieldClass"
                />
              </label>
            }

            @if (showHours()) {
              <label class="block">
                <span class="mb-1.5 block text-sm font-medium text-text"
                  >Estimación (horas)</span
                >
                <input
                  type="number"
                  min="0"
                  step="0.5"
                  formControlName="estimation_hours"
                  placeholder="0"
                  [class]="fieldClass"
                />
              </label>
            }

            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-text"
                >Fecha límite</span
              >
              <input type="date" formControlName="due_date" [class]="fieldClass" />
            </label>

            @if (sprintsEnabled()) {
              <label class="block">
                <span class="mb-1.5 block text-sm font-medium text-text"
                  >Sprint</span
                >
                <select formControlName="sprint_id" [class]="fieldClass">
                  <option [ngValue]="null">Backlog</option>
                  @for (sprint of sprints(); track sprint.id) {
                    <option [ngValue]="sprint.id">{{ sprint.name }}</option>
                  }
                </select>
              </label>
            }
          </div>

          @if (error()) {
            <div
              role="alert"
              class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
            >
              {{ error() }}
            </div>
          }

          <div class="flex items-center justify-between gap-2 pt-1">
            @if (task()) {
              <bk-button
                type="button"
                variant="danger"
                (click)="remove.emit(task()!.id)"
              >
                Eliminar
              </bk-button>
            } @else {
              <span></span>
            }
            <div class="flex items-center gap-2">
              <bk-button type="button" variant="ghost" (click)="close.emit()">
                Cancelar
              </bk-button>
              <bk-button type="submit" variant="primary" [disabled]="saving()">
                {{ saving() ? 'Guardando…' : 'Guardar' }}
              </bk-button>
            </div>
          </div>
        </form>
      </div>
    </div>
  `,
})
export class TaskModalComponent implements OnInit {
  private readonly fb = inject(FormBuilder);

  readonly allowedStatuses = input.required<string[]>();
  readonly estimationMode = input<EstimationMode>('none');
  readonly members = input<Member[]>([]);
  readonly sprints = input<Sprint[]>([]);
  readonly sprintsEnabled = input<boolean>(false);
  /** Preset status for "+ Agregar" from a specific column. */
  readonly presetStatus = input<string | null>(null);
  /** When set, the modal is in edit mode and prefills the form. */
  readonly task = input<Task | null>(null);
  readonly saving = input<boolean>(false);
  readonly error = input<string | null>(null);

  readonly save = output<TaskFormResult>();
  readonly close = output<void>();
  readonly remove = output<string>();

  protected readonly priorityOptions = PRIORITY_OPTIONS;
  protected readonly taskTypeOptions = TASK_TYPE_OPTIONS;

  protected readonly fieldClass =
    'h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text ' +
    'transition-colors focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40';

  protected readonly form = this.fb.group({
    title: ['', [Validators.required]],
    description: [''],
    status: [''],
    priority: ['medium' as Priority],
    assignee_id: [null as string | null],
    estimation_points: [null as number | null],
    estimation_hours: [null as number | null],
    due_date: [''],
    sprint_id: [null as string | null],
    task_type: ['task'],
  });

  ngOnInit(): void {
    const existing = this.task();
    const statuses = this.allowedStatuses();
    const fallbackStatus =
      this.presetStatus() ?? (statuses.length > 0 ? statuses[0] : '');

    if (existing) {
      this.form.patchValue({
        title: existing.title,
        description: existing.description ?? '',
        status: existing.status,
        priority: existing.priority,
        assignee_id: existing.assignee_id ?? null,
        estimation_points: existing.estimation_points ?? null,
        estimation_hours: existing.estimation_hours ?? null,
        due_date: existing.due_date ? existing.due_date.slice(0, 10) : '',
        sprint_id: existing.sprint_id ?? null,
        task_type: (existing.task_type as string) ?? 'task',
      });
    } else {
      this.form.patchValue({ status: fallbackStatus });
    }
  }

  protected statusLabel(status: string): string {
    return statusDisplay(status);
  }

  protected showPoints(): boolean {
    const mode = this.estimationMode();
    return mode === 'points' || mode === 'both';
  }

  protected showHours(): boolean {
    const mode = this.estimationMode();
    return mode === 'hours' || mode === 'both';
  }

  protected showError(control: 'title'): boolean {
    const c = this.form.controls[control];
    return c.invalid && (c.touched || c.dirty);
  }

  protected onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const raw = this.form.getRawValue();
    const result: TaskFormResult = {
      title: (raw.title ?? '').trim(),
      description: (raw.description ?? '').trim() || null,
      status: raw.status ?? '',
      priority: (raw.priority ?? 'medium') as Priority,
      assignee_id: raw.assignee_id || null,
      estimation_points: this.toNumber(raw.estimation_points),
      estimation_hours: this.toNumber(raw.estimation_hours),
      due_date: raw.due_date ? raw.due_date : null,
      sprint_id: raw.sprint_id || null,
      task_type: raw.task_type ?? 'task',
    };
    this.save.emit(result);
  }

  private toNumber(value: number | string | null): number | null {
    if (value === null || value === '') {
      return null;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
}
