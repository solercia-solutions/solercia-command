import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  output,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { EstimationMode } from '../project.model';
import {
  PRIORITY_CHIP_CLASS,
  PRIORITY_LABELS,
  Priority,
  Task,
  formatShortDate,
  isOverdue,
} from './workspace.model';

/**
 * Presentational task card: title, assignee avatar, priority chip, due date
 * (danger when overdue and not done), estimation (per estimation_mode) and a
 * small risk flag. Emits `edit` when activated.
 */
@Component({
  selector: 'bk-task-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <button
      type="button"
      (click)="edit.emit(task())"
      class="group flex w-full flex-col gap-2 rounded-lg border border-border bg-surface p-3 text-left
             shadow-sm transition-colors hover:border-brand/50 focus:outline-none
             focus-visible:ring-2 focus-visible:ring-brand/50"
      [attr.aria-label]="'Edita la tarea ' + task().title"
    >
      <div class="flex items-start justify-between gap-2">
        <p class="text-sm font-medium leading-snug text-text">
          {{ task().title }}
        </p>
        @if (task().risk_flag) {
          <span
            class="shrink-0 text-danger"
            [attr.aria-label]="task().risk_reason || 'Tarea en riesgo'"
            [attr.title]="task().risk_reason || 'Tarea en riesgo'"
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
          [class]="priorityChip()"
        >
          {{ priorityText() }}
        </span>

        @if (showPoints()) {
          <span
            class="rounded-full bg-muted/10 px-2 py-0.5 text-[11px] font-medium text-muted"
          >
            {{ task().estimation_points }} pts
          </span>
        }
        @if (showHours()) {
          <span
            class="rounded-full bg-muted/10 px-2 py-0.5 text-[11px] font-medium text-muted"
          >
            {{ task().estimation_hours }} h
          </span>
        }

        @if (dueLabel()) {
          <span
            class="ml-auto inline-flex items-center gap-1 text-[11px] font-medium"
            [class.text-danger]="overdue()"
            [class.text-muted]="!overdue()"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
            {{ dueLabel() }}
          </span>
        }
      </div>

      <div class="flex items-center gap-2 pt-1">
        <span
          class="grid h-6 w-6 place-items-center rounded-full bg-brand/10 text-[11px] font-semibold text-brand"
          [attr.aria-label]="
            task().assignee_name
              ? 'Asignada a ' + task().assignee_name
              : 'Sin responsable'
          "
          [attr.title]="task().assignee_name || 'Sin responsable'"
        >
          {{ initial() }}
        </span>
        <span class="truncate text-xs text-muted">
          {{ task().assignee_name || 'Sin responsable' }}
        </span>
      </div>

      @if (task().task_key) {
        <a [routerLink]="['/task', task().task_key]"
           (click)="$event.stopPropagation()"
           class="mt-1 text-[11px] text-brand hover:underline self-end"
           aria-label="Abrir detalle de la tarea">
          Abrir detalle
        </a>
      }
    </button>
  `,
})
export class TaskCardComponent {
  readonly task = input.required<Task>();
  readonly estimationMode = input<EstimationMode>('none');
  /** Last allowed status (the "done" column); drives overdue styling. */
  readonly doneStatus = input<string | null>(null);

  readonly edit = output<Task>();

  protected readonly initial = computed<string>(() => {
    const name = this.task().assignee_name?.trim();
    return name ? name.charAt(0).toUpperCase() : '?';
  });

  protected readonly priorityChip = computed<string>(
    () => PRIORITY_CHIP_CLASS[this.priority()] ?? PRIORITY_CHIP_CLASS.medium,
  );

  protected readonly priorityText = computed<string>(
    () => PRIORITY_LABELS[this.priority()] ?? this.task().priority,
  );

  protected readonly showPoints = computed<boolean>(() => {
    const mode = this.estimationMode();
    return (
      (mode === 'points' || mode === 'both') &&
      this.task().estimation_points != null
    );
  });

  protected readonly showHours = computed<boolean>(() => {
    const mode = this.estimationMode();
    return (
      (mode === 'hours' || mode === 'both') &&
      this.task().estimation_hours != null
    );
  });

  protected readonly overdue = computed<boolean>(() =>
    isOverdue(this.task(), this.doneStatus()),
  );

  protected readonly dueLabel = computed<string>(() =>
    formatShortDate(this.task().due_date),
  );

  private priority(): Priority {
    return this.task().priority;
  }
}
