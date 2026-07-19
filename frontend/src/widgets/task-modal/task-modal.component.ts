import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
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
import {
  SolButtonComponent,
  SolDatePickerComponent,
  SolInputComponent,
  SolModalComponent,
  SolNumberInputComponent,
  SolSelectComponent,
  SolTextareaComponent,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
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
 * when sprints are enabled. Purely presentational — emits `save`/`closed`.
 */
@Component({
  selector: 'sol-task-modal',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    SolButtonComponent,
    SolDatePickerComponent,
    SolInputComponent,
    SolModalComponent,
    SolNumberInputComponent,
    SolSelectComponent,
    SolTextareaComponent,
  ],
  template: `
    <sol-modal
      [open]="true"
      [title]="task() ? text.editTitle() : text.createTitle()"
      size="md"
      [closeOnBackdrop]="true"
      (closed)="closed.emit()"
    >
      <form
        [formGroup]="form"
        (ngSubmit)="onSubmit()"
        class="flex flex-col gap-4"
        novalidate
      >
        <div>
          <sol-input
            [label]="text.titleLabel()"
            [placeholder]="text.titlePlaceholder()"
            formControlName="title"
          />
          @if (showError('title')) {
            <p class="mt-1 text-xs text-danger">{{ text.titleRequired() }}</p>
          }
        </div>

        <sol-textarea
          [label]="text.descriptionLabel()"
          [placeholder]="text.descriptionPlaceholder()"
          [rows]="3"
          formControlName="description"
        />

        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <sol-select
            [label]="text.statusLabel()"
            [options]="statusOptions()"
            formControlName="status"
          />

          <sol-select
            [label]="text.priorityLabel()"
            [options]="priorityOptions"
            formControlName="priority"
          />

          <sol-select
            [label]="text.assigneeLabel()"
            [options]="assigneeOptions()"
            [showAllOption]="true"
            [allOptionLabel]="text.assigneeNone()"
            formControlName="assignee_id"
          />

          <sol-select
            [label]="text.typeLabel()"
            [options]="taskTypeOptions"
            formControlName="task_type"
          />

          @if (showPoints()) {
            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-text"
                >{{ text.estimationPoints() }}</span
              >
              <sol-number-input
                [min]="0"
                [step]="1"
                ariaLabelKey="taskModal.estimationPointsAria"
                formControlName="estimation_points"
              />
            </label>
          }

          @if (showHours()) {
            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-text"
                >{{ text.estimationHours() }}</span
              >
              <sol-number-input
                [min]="0"
                [step]="0.5"
                ariaLabelKey="taskModal.estimationHoursAria"
                formControlName="estimation_hours"
              />
            </label>
          }

          <label class="block">
            <span class="mb-1.5 block text-sm font-medium text-text"
              >{{ text.dueDateLabel() }}</span
            >
            <sol-date-picker formControlName="due_date" />
          </label>

          @if (sprintsEnabled()) {
            <sol-select
              [label]="text.sprintLabel()"
              [options]="sprintOptions()"
              [showAllOption]="true"
              [allOptionLabel]="text.backlogOption()"
              formControlName="sprint_id"
            />
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
            <sol-button
              type="button"
              variant="danger"
              (click)="remove.emit(task()!.id)"
            >
              {{ text.remove() }}
            </sol-button>
          } @else {
            <span></span>
          }
          <div class="flex items-center gap-2">
            <sol-button type="button" variant="ghost" (click)="closed.emit()">
              {{ text.cancel() }}
            </sol-button>
            <sol-button type="submit" variant="primary" [disabled]="saving()">
              {{ saving() ? text.saving() : text.save() }}
            </sol-button>
          </div>
        </div>
      </form>
    </sol-modal>
  `,
})
export class TaskModalComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly i18n = inject(I18nService);

  /** Static UI chrome resolved by i18n (reactive to language changes). */
  protected readonly text = {
    editTitle: this.i18n.t('taskModal.editTitle'),
    createTitle: this.i18n.t('taskModal.createTitle'),
    titleLabel: this.i18n.t('taskModal.titleLabel'),
    titlePlaceholder: this.i18n.t('taskModal.titlePlaceholder'),
    titleRequired: this.i18n.t('taskModal.titleRequired'),
    descriptionLabel: this.i18n.t('taskModal.descriptionLabel'),
    descriptionPlaceholder: this.i18n.t('taskModal.descriptionPlaceholder'),
    statusLabel: this.i18n.t('taskModal.statusLabel'),
    priorityLabel: this.i18n.t('taskModal.priorityLabel'),
    assigneeLabel: this.i18n.t('taskModal.assigneeLabel'),
    assigneeNone: this.i18n.t('taskModal.assigneeNone'),
    typeLabel: this.i18n.t('taskModal.typeLabel'),
    estimationPoints: this.i18n.t('taskModal.estimationPoints'),
    estimationHours: this.i18n.t('taskModal.estimationHours'),
    dueDateLabel: this.i18n.t('taskModal.dueDateLabel'),
    sprintLabel: this.i18n.t('taskModal.sprintLabel'),
    backlogOption: this.i18n.t('taskModal.backlogOption'),
    remove: this.i18n.t('taskModal.remove'),
    cancel: this.i18n.t('taskModal.cancel'),
    saving: this.i18n.t('taskModal.saving'),
    save: this.i18n.t('taskModal.save'),
  } as const;

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
  readonly closed = output<void>();
  readonly remove = output<string>();

  protected readonly priorityOptions = PRIORITY_OPTIONS.map((option) => ({
    value: option.value,
    label: option.label,
  }));
  protected readonly taskTypeOptions = TASK_TYPE_OPTIONS.map((option) => ({
    value: option.value,
    label: option.label,
  }));

  protected readonly statusOptions = computed(() =>
    this.allowedStatuses().map((status) => ({
      value: status,
      label: this.statusLabel(status),
    })),
  );

  protected readonly assigneeOptions = computed(() =>
    this.members().map((member) => ({
      value: member.user_id,
      label: member.full_name,
    })),
  );

  protected readonly sprintOptions = computed(() =>
    this.sprints().map((sprint) => ({
      value: sprint.id,
      label: sprint.name,
    })),
  );

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
