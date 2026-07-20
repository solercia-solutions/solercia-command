import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  input,
  output,
  signal,
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
  formatOriginalEstimate,
  parseOriginalEstimate,
} from '@shared/lib/estimation';
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
  start_date: string | null;
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
      [closeOnBackdrop]="!saving()"
      (closed)="onModalClosed()"
      role="dialog"
      aria-modal="true"
      [attr.aria-label]="task() ? text.editAria() : text.createAria()"
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
            <div>
              <label class="block">
                <span class="mb-1.5 block text-sm font-medium text-text"
                  >{{ text.storyPoints() }}</span
                >
                <sol-number-input
                  [min]="0"
                  [step]="1"
                  ariaLabelKey="taskModal.storyPointsAria"
                  formControlName="estimation_points"
                />
              </label>
              @if (pointsError()) {
                <p class="mt-1 text-xs text-danger">
                  {{ text.storyPointsInteger() }}
                </p>
              }
            </div>
          }

          @if (showHours()) {
            <div>
              <sol-input
                [label]="text.originalEstimate()"
                [placeholder]="text.originalEstimatePlaceholder()"
                formControlName="original_estimate"
              />
              @if (estimateError()) {
                <p class="mt-1 text-xs text-danger">
                  {{ text.originalEstimateInvalid() }}
                </p>
              } @else {
                <p class="mt-1 text-xs text-muted">
                  {{ text.originalEstimateHint() }}
                </p>
              }
            </div>
          }

          <label class="block">
            <span class="mb-1.5 block text-sm font-medium text-text"
              >{{ text.startDateLabel() }}</span
            >
            <sol-date-picker formControlName="start_date" />
          </label>

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
            <sol-button
              type="button"
              variant="ghost"
              [disabled]="saving()"
              (click)="closed.emit()"
            >
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
    editAria: this.i18n.t('taskModal.editAria'),
    createAria: this.i18n.t('taskModal.createAria'),
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
    storyPoints: this.i18n.t('taskModal.storyPoints'),
    storyPointsInteger: this.i18n.t('taskModal.storyPointsInteger'),
    originalEstimate: this.i18n.t('taskModal.originalEstimate'),
    originalEstimatePlaceholder: this.i18n.t(
      'taskModal.originalEstimatePlaceholder',
    ),
    originalEstimateHint: this.i18n.t('taskModal.originalEstimateHint'),
    originalEstimateInvalid: this.i18n.t('taskModal.originalEstimateInvalid'),
    startDateLabel: this.i18n.t('taskModal.startDateLabel'),
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
    /** Jira-style text ("4w 2d 3h"); parsed to hours on submit. */
    original_estimate: [''],
    start_date: [''],
    due_date: [''],
    sprint_id: [null as string | null],
    task_type: ['task'],
  });

  /** Story points must be a non-negative integer (Fibonacci-friendly). */
  protected readonly pointsError = signal(false);
  /** Original estimate did not parse ("4w 2d 3h" expected). */
  protected readonly estimateError = signal(false);

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
        original_estimate: formatOriginalEstimate(existing.estimation_hours),
        start_date: existing.start_date ? existing.start_date.slice(0, 10) : '',
        due_date: existing.due_date ? existing.due_date.slice(0, 10) : '',
        sprint_id: existing.sprint_id ?? null,
        task_type: (existing.task_type as string) ?? 'task',
      });
    } else {
      this.form.patchValue({ status: fallbackStatus });
    }
  }

  /**
   * SolModal's `closed` output fires from the backdrop, the Escape key, and
   * its internal X button alike; none of those individually know about the
   * in-flight save, so the guard lives here to block all three while saving.
   */
  protected onModalClosed(): void {
    if (this.saving()) {
      return;
    }
    this.closed.emit();
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

    // Story points: whole number only (0, 1, 2, 3, 5...).
    const points = this.toNumber(raw.estimation_points);
    const pointsInvalid =
      points !== null && (!Number.isInteger(points) || points < 0);
    this.pointsError.set(pointsInvalid);

    // Original estimate: Jira text ("4w 2d 3h") parsed to decimal hours.
    // Empty clears the estimate; a non-empty string that fails to parse is
    // a validation error (the parser returns null in both cases).
    const estimateText = (raw.original_estimate ?? '').trim();
    const hours = parseOriginalEstimate(estimateText);
    const estimateInvalid = estimateText !== '' && hours === null;
    this.estimateError.set(estimateInvalid);

    if (pointsInvalid || estimateInvalid) {
      return;
    }

    const result: TaskFormResult = {
      title: (raw.title ?? '').trim(),
      description: (raw.description ?? '').trim() || null,
      status: raw.status ?? '',
      priority: (raw.priority ?? 'medium') as Priority,
      assignee_id: raw.assignee_id || null,
      estimation_points: points,
      estimation_hours: hours,
      start_date: raw.start_date ? raw.start_date : null,
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
