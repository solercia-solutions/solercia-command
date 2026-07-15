import {
  ChangeDetectionStrategy,
  Component,
  input,
  output,
} from '@angular/core';
import {
  CdkDragDrop,
  DragDropModule,
} from '@angular/cdk/drag-drop';
import { EstimationMode } from '@entities/project/project.model';
import { TaskCardComponent } from '@widgets/task-card/task-card.component';
import { Task, statusDisplay } from '@entities/workspace/workspace.model';

/** Event emitted when a card is dropped, carrying the destination column. */
export interface ColumnDrop {
  event: CdkDragDrop<Task[]>;
  status: string;
}

/**
 * Presentational board column. Renders a CDK drop list of task cards for a
 * single status. Connection across columns is provided by a `cdkDropListGroup`
 * ancestor in the workspace container.
 */
@Component({
  selector: 'bk-board-column',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DragDropModule, TaskCardComponent],
  template: `
    <section
      class="flex w-72 shrink-0 flex-col rounded-xl border border-border bg-page/60"
      [attr.aria-label]="'Columna ' + label()"
    >
      <header
        class="flex items-center justify-between gap-2 border-b border-border px-3 py-2"
      >
        <h3 class="text-sm font-semibold text-text">{{ label() }}</h3>
        <span
          class="grid h-5 min-w-5 place-items-center rounded-full bg-muted/15 px-1.5 text-[11px] font-medium text-muted"
        >
          {{ tasks().length }}
        </span>
      </header>

      <div
        cdkDropList
        [cdkDropListData]="tasks()"
        (cdkDropListDropped)="dropped.emit({ event: $event, status: status() })"
        class="flex min-h-[120px] flex-1 flex-col gap-2 p-2"
      >
        @for (task of tasks(); track task.id) {
          <div cdkDrag class="cursor-grab active:cursor-grabbing">
            <bk-task-card
              [task]="task"
              [estimationMode]="estimationMode()"
              [doneStatus]="doneStatus()"
              (edit)="editTask.emit($event)"
            ></bk-task-card>
          </div>
        }
        @if (tasks().length === 0) {
          <p class="px-2 py-6 text-center text-xs text-muted">
            Suelta tareas aquí.
          </p>
        }
      </div>

      <button
        type="button"
        (click)="addTask.emit(status())"
        class="m-2 inline-flex items-center justify-center gap-1 rounded-lg border border-dashed border-border
               px-3 py-2 text-xs font-medium text-muted transition-colors hover:border-brand/50 hover:text-brand
               focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
        [attr.aria-label]="'Agrega una tarea en ' + label()"
      >
        + Agregar
      </button>
    </section>
  `,
})
export class BoardColumnComponent {
  /** Raw status value used for PATCH and as the CDK list identity. */
  readonly status = input.required<string>();
  readonly tasks = input.required<Task[]>();
  readonly estimationMode = input<EstimationMode>('none');
  readonly doneStatus = input<string | null>(null);

  readonly addTask = output<string>();
  readonly editTask = output<Task>();
  readonly dropped = output<ColumnDrop>();

  /** Spanish display label for the column header. */
  protected label(): string {
    return statusDisplay(this.status());
  }
}
