import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { SolIconComponent } from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { formatOriginalEstimate } from '@shared/lib/estimation';
import {
  Sprint,
  Task,
  formatShortDate,
} from '@entities/workspace/workspace.model';

const DAY_MS = 86_400_000;
/** Pixel width of one day column. */
const DAY_W = 32;
/** Pixel width of the sticky label column. */
const LABEL_W = 240;
/** Pixel height of a task/epic row. */
const ROW_H = 36;
/** Pixel height of one sprint band (lane). */
const BAND_H = 24;
/** Days of padding added on both sides of the computed range. */
const RANGE_PAD_DAYS = 3;
/** Safety cap: never render more than ~2 years of day columns. */
const MAX_DAYS = 731;

/** Positioned bar. `partial` = only one of the two dates is known. */
interface GanttBar {
  left: number;
  width: number;
  partial: boolean;
}

interface GanttRow {
  task: Task;
  bar: GanttBar | null;
}

interface GanttGroup {
  id: string;
  label: string;
  taskKey: string | null;
  epic: Task | null;
  epicBar: GanttBar | null;
  rows: GanttRow[];
}

interface SprintBand {
  sprint: Sprint;
  left: number;
  width: number;
  top: number;
}

interface MonthSegment {
  label: string;
  width: number;
}

/**
 * Cronograma tipo Jira (Gantt por días) construido con CSS puro sobre los
 * tokens `--sol-*` (no depende de `sol-timeline`, que solo maneja eje
 * mensual y nodos planos):
 *
 * - Encabezado sticky con meses y días; fines de semana atenuados y línea
 *   vertical en el día de hoy.
 * - Primera fila del cuerpo: los sprints como bandas horizontales entre su
 *   `start_date` y `end_date` (en carriles apilados si se solapan).
 * - Debajo, las tareas agrupadas por épica (`task_type='epic'` +
 *   `parent_task_id`), colapsables, con un grupo final "Sin épica".
 * - Cada tarea es una barra entre `start_date` y `due_date`, coloreada por
 *   estado, con tooltip (título, fechas, estimación, responsable) y clic
 *   que emite `taskClicked` para abrir el drawer de detalle.
 *
 * Decisiones documentadas:
 * - Tarea con UNA sola fecha → barra mínima de un día anclada a la fecha
 *   disponible, con borde punteado para señalar el dato incompleto.
 * - Tarea SIN fechas → chip clicable en la sección "Tareas sin fechas"
 *   bajo el gráfico (no ocupa fila en el cronograma).
 * - Subtareas (hijas de una tarea no-épica) se excluyen, igual que en el
 *   cronograma de Jira; se gestionan desde el detalle de su tarea padre.
 */
@Component({
  selector: 'sol-sprint-gantt',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgTemplateOutlet, SolIconComponent],
  template: `
    @if (days().length === 0) {
      <div class="rounded-xl border border-border bg-surface">
        <p class="py-10 text-center text-sm text-muted">{{ text.empty() }}</p>
      </div>
    } @else {
      <div class="rounded-xl border border-border bg-surface">
        <div
          class="relative max-h-[70vh] overflow-auto"
          role="region"
          [attr.aria-label]="text.regionAria()"
        >
          <div class="relative" [style.width.px]="totalWidth()">
            <!-- ===== Header: months + days (sticky top) ===== -->
            <div class="sticky top-0 z-30 flex bg-surface">
              <div
                class="sticky left-0 z-10 shrink-0 border-b border-r border-border bg-surface"
                [style.width.px]="labelW"
              ></div>
              <div class="shrink-0 border-b border-border" [style.width.px]="chartWidth()">
                <div class="flex h-6">
                  @for (m of monthSegments(); track $index) {
                    <div
                      class="shrink-0 truncate border-r border-border/60 px-1.5 text-[11px] font-medium leading-6 text-muted"
                      [style.width.px]="m.width"
                    >
                      {{ m.label }}
                    </div>
                  }
                </div>
                <div class="flex h-6">
                  @for (d of days(); track $index) {
                    <div
                      class="shrink-0 text-center text-[10px] leading-6"
                      [class.bg-sunken]="isWeekend(d)"
                      [class.text-brand]="isToday(d)"
                      [class.font-bold]="isToday(d)"
                      [class.text-muted]="!isToday(d)"
                      [style.width.px]="dayW"
                    >
                      {{ d.getDate() }}
                    </div>
                  }
                </div>
              </div>
            </div>

            <!-- ===== Body ===== -->
            <div class="relative">
              <!-- Weekend stripes + today line (content coordinates) -->
              <div
                class="pointer-events-none absolute inset-y-0 z-0"
                [style.left.px]="labelW"
                [style.width.px]="chartWidth()"
              >
                @for (offset of weekendOffsets(); track offset) {
                  <div
                    class="absolute inset-y-0 bg-sunken"
                    [style.left.px]="offset"
                    [style.width.px]="dayW"
                  ></div>
                }
                @if (todayOffset() !== null) {
                  <div
                    class="absolute inset-y-0 w-0.5 bg-brand"
                    [style.left.px]="todayOffset()"
                    [attr.aria-label]="text.today()"
                  ></div>
                }
              </div>

              <!-- Sprints row (first body row, Jira style) -->
              <div class="relative z-10 flex border-b border-border">
                <div
                  class="sticky left-0 z-20 flex shrink-0 items-center border-r border-border bg-surface px-3 text-xs font-semibold uppercase tracking-wide text-muted"
                  [style.width.px]="labelW"
                  [style.height.px]="sprintRowHeight()"
                >
                  {{ text.sprintsRow() }}
                </div>
                <div
                  class="relative shrink-0"
                  [style.width.px]="chartWidth()"
                  [style.height.px]="sprintRowHeight()"
                >
                  @for (band of sprintBands(); track band.sprint.id) {
                    <div
                      class="absolute flex items-center overflow-hidden rounded-full border px-2"
                      [class.border-success]="band.sprint.status === 'active'"
                      [class.bg-success-soft]="band.sprint.status === 'active'"
                      [class.text-success]="band.sprint.status === 'active'"
                      [class.border-border]="band.sprint.status !== 'active'"
                      [class.bg-sunken]="band.sprint.status !== 'active'"
                      [class.text-muted]="band.sprint.status !== 'active'"
                      [style.left.px]="band.left"
                      [style.width.px]="band.width"
                      [style.top.px]="band.top"
                      [style.height.px]="bandH"
                      [attr.aria-label]="sprintBandAria(band.sprint)"
                    >
                      <span class="truncate text-[11px] font-medium">
                        {{ band.sprint.name }}
                      </span>
                    </div>
                  }
                </div>
              </div>

              <!-- Epic groups -->
              @for (group of groups(); track group.id) {
                <div class="relative z-10 flex border-b border-border/60">
                  <div
                    class="sticky left-0 z-20 flex shrink-0 items-center gap-1 border-r border-border bg-surface px-2"
                    [style.width.px]="labelW"
                    [style.height.px]="rowH"
                  >
                    <button
                      type="button"
                      class="shrink-0 rounded p-0.5 text-muted transition-colors hover:text-text focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
                      (click)="toggleGroup(group.id)"
                      [attr.aria-expanded]="!isCollapsed(group.id)"
                      [attr.aria-label]="groupToggleAria(group)"
                    >
                      <sol-icon
                        [name]="isCollapsed(group.id) ? 'chevron-right' : 'chevron-down'"
                        size="sm"
                      />
                    </button>
                    @if (group.epic; as epic) {
                      <button
                        type="button"
                        class="flex min-w-0 items-center gap-1.5 text-left hover:text-brand"
                        (click)="taskClicked.emit(epic)"
                        [attr.aria-label]="openTaskAria(epic)"
                      >
                        @if (group.taskKey) {
                          <span class="shrink-0 font-mono text-[10px] font-semibold text-accent">
                            {{ group.taskKey }}
                          </span>
                        }
                        <span class="truncate text-xs font-semibold text-text">
                          {{ group.label }}
                        </span>
                      </button>
                    } @else {
                      <span class="truncate text-xs font-semibold text-text">
                        {{ group.label }}
                      </span>
                    }
                    <span class="ml-auto shrink-0 text-[10px] text-muted">
                      {{ groupCountLabel(group.rows.length) }}
                    </span>
                  </div>
                  <div
                    class="relative shrink-0"
                    [style.width.px]="chartWidth()"
                    [style.height.px]="rowH"
                  >
                    @if (group.epic && group.epicBar; as bar) {
                      <button
                        type="button"
                        class="group absolute flex items-center overflow-visible rounded-md bg-accent px-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
                        [class.opacity-60]="bar.partial"
                        [style.left.px]="bar.left"
                        [style.width.px]="bar.width"
                        [style.top.px]="barTop"
                        [style.height.px]="barH"
                        (click)="taskClicked.emit(group.epic!)"
                        [attr.aria-label]="openTaskAria(group.epic!)"
                      >
                        <span class="truncate text-[11px] font-medium text-brand-fg">
                          {{ group.label }}
                        </span>
                        <ng-container
                          *ngTemplateOutlet="barTooltip; context: { $implicit: group.epic! }"
                        />
                      </button>
                    }
                  </div>
                </div>

                @if (!isCollapsed(group.id)) {
                  @for (row of group.rows; track row.task.id) {
                    <div class="relative z-10 flex border-b border-border/40">
                      <div
                        class="sticky left-0 z-20 flex shrink-0 items-center border-r border-border bg-surface pl-8 pr-2"
                        [style.width.px]="labelW"
                        [style.height.px]="rowH"
                      >
                        <button
                          type="button"
                          class="flex min-w-0 items-center gap-1.5 text-left hover:text-brand"
                          (click)="taskClicked.emit(row.task)"
                          [attr.aria-label]="openTaskAria(row.task)"
                        >
                          @if (row.task.task_key) {
                            <span class="shrink-0 font-mono text-[10px] text-muted">
                              {{ row.task.task_key }}
                            </span>
                          }
                          <span class="truncate text-xs text-text">
                            {{ row.task.title }}
                          </span>
                        </button>
                      </div>
                      <div
                        class="relative shrink-0"
                        [style.width.px]="chartWidth()"
                        [style.height.px]="rowH"
                      >
                        @if (row.bar; as bar) {
                          <button
                            type="button"
                            class="group absolute flex items-center overflow-visible rounded-md px-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
                            [class]="barClass(row.task, bar)"
                            [style.left.px]="bar.left"
                            [style.width.px]="bar.width"
                            [style.top.px]="barTop"
                            [style.height.px]="barH"
                            (click)="taskClicked.emit(row.task)"
                            [attr.aria-label]="openTaskAria(row.task)"
                          >
                            <span class="truncate text-[11px] font-medium">
                              {{ row.task.title }}
                            </span>
                            <ng-container
                              *ngTemplateOutlet="barTooltip; context: { $implicit: row.task }"
                            />
                          </button>
                        }
                      </div>
                    </div>
                  }
                }
              }
            </div>
          </div>
        </div>

        <!-- Undated tasks: clickable chips below the chart -->
        @if (undatedTasks().length > 0) {
          <div class="border-t border-border p-4">
            <p class="text-xs font-semibold uppercase tracking-wide text-muted">
              {{ text.undatedTitle() }}
            </p>
            <p class="mt-0.5 text-[11px] text-muted">{{ text.undatedHint() }}</p>
            <div class="mt-2 flex flex-wrap gap-2">
              @for (task of undatedTasks(); track task.id) {
                <button
                  type="button"
                  class="inline-flex max-w-xs items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1 text-xs text-text transition-colors hover:border-brand/50 hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
                  (click)="taskClicked.emit(task)"
                  [attr.aria-label]="openTaskAria(task)"
                >
                  @if (task.task_key) {
                    <span class="font-mono text-[10px] text-muted">{{ task.task_key }}</span>
                  }
                  <span class="truncate">{{ task.title }}</span>
                </button>
              }
            </div>
          </div>
        }
      </div>

      <!-- Tooltip proyectado dentro de cada barra (hover/focus) -->
      <ng-template #barTooltip let-task>
        <div
          class="pointer-events-none absolute left-0 top-full z-40 mt-1 hidden w-max max-w-64 flex-col gap-0.5 rounded-lg border border-border bg-surface p-2.5 text-left shadow-lg group-hover:flex group-focus-visible:flex"
          role="tooltip"
        >
          <p class="text-xs font-semibold text-text">
            @if (task.task_key) {
              <span class="font-mono text-[10px] text-muted">{{ task.task_key }}</span>
            }
            {{ task.title }}
          </p>
          <p class="text-[11px] text-muted">{{ barDatesLabel(task) }}</p>
          @if (barEstimateLabel(task); as estimate) {
            <p class="text-[11px] text-muted">
              {{ text.tooltipEstimate() }}: <span class="text-text">{{ estimate }}</span>
            </p>
          }
          <p class="text-[11px] text-muted">
            {{ text.tooltipAssignee() }}:
            <span class="text-text">{{ task.assignee_name || text.unassigned() }}</span>
          </p>
        </div>
      </ng-template>
    }
  `,
})
export class SprintGanttComponent {
  private readonly i18n = inject(I18nService);

  /** Sprints del proyecto (bandas de la primera fila). */
  readonly sprints = input<Sprint[]>([]);
  /** Todas las tareas del proyecto (épicas incluidas). */
  readonly tasks = input<Task[]>([]);
  /** Clic en una barra, en la fila de la izquierda o en un chip sin fechas. */
  readonly taskClicked = output<Task>();

  protected readonly dayW = DAY_W;
  protected readonly labelW = LABEL_W;
  protected readonly rowH = ROW_H;
  protected readonly bandH = BAND_H;
  protected readonly barH = ROW_H - 12;
  protected readonly barTop = 6;

  protected readonly text = {
    empty: this.i18n.t('workspace.gantt.empty'),
    regionAria: this.i18n.t('workspace.timeline.title'),
    sprintsRow: this.i18n.t('workspace.gantt.sprintsRow'),
    today: this.i18n.t('workspace.gantt.today'),
    tooltipAssignee: this.i18n.t('workspace.gantt.tooltipAssignee'),
    tooltipEstimate: this.i18n.t('workspace.gantt.tooltipEstimate'),
    unassigned: this.i18n.t('taskCard.unassigned'),
    undatedHint: this.i18n.t('workspace.gantt.undatedHint'),
    undatedTitle: this.i18n.t('workspace.gantt.undatedTitle'),
  } as const;

  /** Grupos colapsados (id de épica o 'no-epic'). */
  private readonly collapsed = signal<ReadonlySet<string>>(new Set());

  /* ---- Rango de fechas ---------------------------------------------------- */

  /**
   * Rango visible: del mínimo al máximo de las fechas de sprints y tareas,
   * con `RANGE_PAD_DAYS` de margen a cada lado y tope de `MAX_DAYS` días
   * (protección ante datos corruptos, p. ej. un año 9999).
   */
  private readonly range = computed<{ start: Date; end: Date } | null>(() => {
    const dates: number[] = [];
    for (const sprint of this.sprints()) {
      const start = toDay(sprint.start_date);
      const end = toDay(sprint.end_date);
      if (start) dates.push(start.getTime());
      if (end) dates.push(end.getTime());
    }
    for (const task of this.visibleTasks()) {
      const start = toDay(task.start_date);
      const due = toDay(task.due_date);
      if (start) dates.push(start.getTime());
      if (due) dates.push(due.getTime());
    }
    if (dates.length === 0) {
      return null;
    }
    const start = new Date(Math.min(...dates) - RANGE_PAD_DAYS * DAY_MS);
    let end = new Date(Math.max(...dates) + RANGE_PAD_DAYS * DAY_MS);
    const totalDays = diffDays(start, end) + 1;
    if (totalDays > MAX_DAYS) {
      end = new Date(start.getTime() + (MAX_DAYS - 1) * DAY_MS);
    }
    return { start, end };
  });

  protected readonly days = computed<Date[]>(() => {
    const range = this.range();
    if (!range) {
      return [];
    }
    const result: Date[] = [];
    const total = diffDays(range.start, range.end) + 1;
    for (let i = 0; i < total; i++) {
      result.push(new Date(range.start.getTime() + i * DAY_MS));
    }
    return result;
  });

  protected readonly chartWidth = computed(() => this.days().length * DAY_W);
  protected readonly totalWidth = computed(() => LABEL_W + this.chartWidth());

  /** Segmentos de mes consecutivos para la fila superior del encabezado. */
  protected readonly monthSegments = computed<MonthSegment[]>(() => {
    const segments: MonthSegment[] = [];
    for (const day of this.days()) {
      const label = day.toLocaleDateString('es-CO', {
        month: 'short',
        year: 'numeric',
      });
      const last = segments[segments.length - 1];
      if (last && last.label === label) {
        last.width += DAY_W;
      } else {
        segments.push({ label, width: DAY_W });
      }
    }
    return segments;
  });

  /** Offsets (px) de los días de fin de semana para las franjas del fondo. */
  protected readonly weekendOffsets = computed<number[]>(() =>
    this.days()
      .map((day, index) => ({ day, index }))
      .filter(({ day }) => isWeekendDay(day))
      .map(({ index }) => index * DAY_W),
  );

  /** Posición (px) de la línea de hoy, o null si hoy queda fuera del rango. */
  protected readonly todayOffset = computed<number | null>(() => {
    const range = this.range();
    if (!range) {
      return null;
    }
    const today = startOfToday();
    if (today < range.start || today > range.end) {
      return null;
    }
    return diffDays(range.start, today) * DAY_W + DAY_W / 2;
  });

  /* ---- Sprints (primera fila) --------------------------------------------- */

  /**
   * Bandas de sprint en carriles: si dos sprints se solapan en fechas se
   * apilan verticalmente (asignación golosa de carriles por orden de inicio).
   */
  protected readonly sprintBands = computed<SprintBand[]>(() => {
    const range = this.range();
    if (!range) {
      return [];
    }
    const dated = this.sprints()
      .map((sprint) => {
        const start = toDay(sprint.start_date);
        const end = toDay(sprint.end_date);
        const anchor = start ?? end;
        if (!anchor) {
          return null;
        }
        const from = start ?? end!;
        const to = end && start ? (end < start ? start : end) : from;
        return {
          sprint,
          startIdx: diffDays(range.start, from),
          endIdx: diffDays(range.start, to),
        };
      })
      .filter((band): band is NonNullable<typeof band> => band !== null)
      .sort((a, b) => a.startIdx - b.startIdx);

    const laneEnds: number[] = [];
    return dated.map(({ sprint, startIdx, endIdx }) => {
      let lane = laneEnds.findIndex((lastEnd) => lastEnd < startIdx);
      if (lane === -1) {
        lane = laneEnds.length;
        laneEnds.push(endIdx);
      } else {
        laneEnds[lane] = endIdx;
      }
      return {
        sprint,
        left: startIdx * DAY_W,
        width: (endIdx - startIdx + 1) * DAY_W,
        top: 4 + lane * (BAND_H + 4),
      };
    });
  });

  protected readonly sprintRowHeight = computed(() => {
    const lanes = this.sprintBands().reduce(
      (max, band) => Math.max(max, (band.top - 4) / (BAND_H + 4) + 1),
      1,
    );
    return lanes * (BAND_H + 4) + 8;
  });

  /* ---- Agrupación por épicas ----------------------------------------------- */

  /**
   * Tareas que participan del cronograma: épicas, hijas directas de una
   * épica y tareas raíz sin padre. Las subtareas (hijas de una no-épica)
   * se excluyen, como en el cronograma de Jira.
   */
  private readonly visibleTasks = computed<Task[]>(() => {
    const tasks = this.tasks();
    const epicIds = new Set(
      tasks.filter((task) => task.task_type === 'epic').map((task) => task.id),
    );
    return tasks.filter(
      (task) =>
        task.task_type === 'epic' ||
        task.parent_task_id == null ||
        epicIds.has(task.parent_task_id),
    );
  });

  protected readonly groups = computed<GanttGroup[]>(() => {
    // La etiqueta "Sin épica" se traduce aquí: re-computar al cambiar idioma.
    this.i18n.activeLang();
    const range = this.range();
    const tasks = this.visibleTasks();
    const epics = tasks.filter((task) => task.task_type === 'epic');
    const epicIds = new Set(epics.map((epic) => epic.id));

    const rowsFor = (children: Task[]): GanttRow[] =>
      children
        .filter((task) => task.start_date || task.due_date)
        .map((task) => ({ task, bar: range ? taskBar(task, range.start) : null }));

    const result: GanttGroup[] = epics.map((epic) => ({
      id: epic.id,
      label: epic.title,
      taskKey: epic.task_key ?? null,
      epic,
      epicBar:
        range && (epic.start_date || epic.due_date)
          ? taskBar(epic, range.start)
          : null,
      rows: rowsFor(
        tasks.filter(
          (task) => task.parent_task_id === epic.id && task.task_type !== 'epic',
        ),
      ),
    }));

    const orphans = tasks.filter(
      (task) =>
        task.task_type !== 'epic' &&
        (task.parent_task_id == null || !epicIds.has(task.parent_task_id)),
    );
    const orphanRows = rowsFor(orphans);
    if (orphanRows.length > 0) {
      result.push({
        id: 'no-epic',
        label: this.i18n.translate('workspace.gantt.noEpic'),
        taskKey: null,
        epic: null,
        epicBar: null,
        rows: orphanRows,
      });
    }
    return result;
  });

  /** Tareas del cronograma sin ninguna fecha → chips bajo el gráfico. */
  protected readonly undatedTasks = computed<Task[]>(() =>
    this.visibleTasks().filter(
      (task) =>
        task.task_type !== 'epic' && !task.start_date && !task.due_date,
    ),
  );

  /* ---- Interacción ---------------------------------------------------------- */

  protected isCollapsed(id: string): boolean {
    return this.collapsed().has(id);
  }

  protected toggleGroup(id: string): void {
    this.collapsed.update((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  /* ---- Presentación ---------------------------------------------------------- */

  protected isWeekend(day: Date): boolean {
    return isWeekendDay(day);
  }

  protected isToday(day: Date): boolean {
    return day.getTime() === startOfToday().getTime();
  }

  /**
   * Clases de la barra según estado (normalizado: "In Progress" ≡
   * "in_progress"). Barra parcial (una sola fecha) → borde punteado.
   */
  protected barClass(task: Task, bar: GanttBar): string {
    const status = task.status.toLowerCase().replace(/[\s_]+/g, '_');
    let color: string;
    switch (status) {
      case 'done':
        color = 'bg-success text-brand-fg';
        break;
      case 'in_progress':
      case 'doing':
        color = 'bg-info text-brand-fg';
        break;
      case 'in_review':
        color = 'bg-warning text-brand-fg';
        break;
      case 'cancelled':
        color = 'bg-sunken text-muted line-through';
        break;
      default:
        color = 'bg-muted text-brand-fg';
        break;
    }
    return bar.partial
      ? `${color} border-2 border-dashed border-border opacity-80`
      : color;
  }

  protected sprintBandAria(sprint: Sprint): string {
    return this.i18n.translate('workspace.gantt.sprintBarAria', {
      name: sprint.name,
      start: formatShortDate(sprint.start_date) || '—',
      end: formatShortDate(sprint.end_date) || '—',
    });
  }

  protected groupToggleAria(group: GanttGroup): string {
    return this.i18n.translate(
      this.isCollapsed(group.id)
        ? 'workspace.gantt.expandAria'
        : 'workspace.gantt.collapseAria',
      { name: group.label },
    );
  }

  protected groupCountLabel(count: number): string {
    return this.i18n.translate(
      count === 1
        ? 'workspace.gantt.epicTasksCountOne'
        : 'workspace.gantt.epicTasksCount',
      { count },
    );
  }

  protected openTaskAria(task: Task): string {
    return this.i18n.translate('workspace.gantt.openTaskAria', {
      title: task.title,
    });
  }

  /** "12 jul — 20 jul"; con una sola fecha muestra la disponible. */
  protected barDatesLabel(task: Task): string {
    const start = formatShortDate(task.start_date);
    const due = formatShortDate(task.due_date);
    if (start && due) {
      return `${start} — ${due}`;
    }
    if (start || due) {
      return start || due;
    }
    return this.i18n.translate('workspace.gantt.noDates');
  }

  /** "5 pts · 1w 2d" según lo que tenga la tarea; '' si no hay estimación. */
  protected barEstimateLabel(task: Task): string {
    const parts: string[] = [];
    if (task.estimation_points != null) {
      parts.push(`${task.estimation_points} ${this.i18n.translate('taskCard.pts')}`);
    }
    const hours = formatOriginalEstimate(task.estimation_hours);
    if (hours) {
      parts.push(hours);
    }
    return parts.join(' · ');
  }
}

/* ---- Helpers de fecha (día local, sin horas) --------------------------------- */

/** Normaliza un ISO datetime/fecha al inicio del día local; null si no parsea. */
function toDay(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
}

function startOfToday(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

/** Días completos entre dos fechas normalizadas (b - a). */
function diffDays(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / DAY_MS);
}

function isWeekendDay(day: Date): boolean {
  const weekday = day.getDay();
  return weekday === 0 || weekday === 6;
}

/**
 * Barra de una tarea: con ambas fechas ocupa [start, due] inclusive; con una
 * sola, una barra mínima de un día anclada a la fecha disponible (partial).
 */
function taskBar(task: Task, rangeStart: Date): GanttBar | null {
  let start = toDay(task.start_date);
  let due = toDay(task.due_date);
  if (!start && !due) {
    return null;
  }
  if (start && due && due < start) {
    [start, due] = [due, start];
  }
  const partial = !start || !due;
  const anchorStart = start ?? due!;
  const anchorEnd = due ?? start!;
  const startIdx = diffDays(rangeStart, anchorStart);
  const endIdx = diffDays(rangeStart, anchorEnd);
  return {
    left: startIdx * DAY_W,
    width: Math.max((endIdx - startIdx + 1) * DAY_W, DAY_W),
    partial,
  };
}
