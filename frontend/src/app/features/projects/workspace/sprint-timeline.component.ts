import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
} from '@angular/core';
import { Sprint } from './workspace.model';

interface TimelineSprint {
  sprint: Sprint;
  /** Offset from the left edge of the chart area, 0–100. */
  leftPct: number;
  /** Width as percentage of the total chart area, 0–100. */
  widthPct: number;
  label: string;
  dateRange: string;
}

interface AxisLabel {
  leftPct: number;
  label: string;
}

const MONTHS_ES = [
  'ene', 'feb', 'mar', 'abr', 'may', 'jun',
  'jul', 'ago', 'sep', 'oct', 'nov', 'dic',
];

function monthLabel(date: Date): string {
  return `${MONTHS_ES[date.getMonth()]} ${date.getFullYear()}`;
}

function shortDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getDate()} ${MONTHS_ES[d.getMonth()]}`;
}

/**
 * Dependency-free horizontal timeline of project sprints.
 * Each sprint is a bar positioned by start_date / end_date.
 * Sprints without both dates are shown in a "sin fechas" section below.
 */
@Component({
  selector: 'sp-sprint-timeline',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (sprints().length === 0) {
      <p class="py-8 text-center text-sm text-muted">
        No hay sprints en este proyecto todavía.
      </p>
    } @else {
      <div class="flex flex-col gap-6">

        @if (timedSprints().length > 0) {
          <!-- Timeline chart -->
          <div class="overflow-x-auto">
            <div class="relative min-w-[480px]">

              <!-- Month axis labels -->
              <div class="relative mb-2 h-5 text-xs text-muted">
                @for (lbl of axisLabels(); track lbl.label) {
                  <span
                    class="absolute whitespace-nowrap"
                    [style.left]="lbl.leftPct + '%'"
                    style="transform: translateX(-50%)"
                  >{{ lbl.label }}</span>
                }
              </div>

              <!-- Top axis rule -->
              <div class="mb-3 h-px bg-border"></div>

              <!-- Sprint rows -->
              <div class="flex flex-col gap-2">
                @for (item of timedSprints(); track item.sprint.id) {
                  <div class="relative h-9">
                    <!-- Full-width backdrop -->
                    <div class="absolute inset-y-0 left-0 right-0 rounded bg-surface/50"></div>

                    <!-- Sprint bar -->
                    <div
                      class="absolute inset-y-0 flex items-center overflow-hidden
                             rounded px-2 text-xs font-medium text-white shadow-sm"
                      [class.bg-success]="item.sprint.status === 'active'"
                      [class.bg-muted]="item.sprint.status !== 'active'"
                      [style.left]="item.leftPct + '%'"
                      [style.width]="item.widthPct + '%'"
                      [attr.title]="item.sprint.name + ' · ' + item.dateRange"
                      [attr.aria-label]="item.sprint.name + ', ' + item.dateRange"
                    >
                      <span class="truncate">{{ item.label }}</span>
                    </div>
                  </div>
                }
              </div>

              <!-- Legend -->
              <div class="mt-4 flex flex-wrap gap-4 text-xs text-muted">
                <span class="inline-flex items-center gap-1.5">
                  <span class="h-3 w-3 rounded bg-success"></span> Activo
                </span>
                <span class="inline-flex items-center gap-1.5">
                  <span class="h-3 w-3 rounded bg-muted"></span> Cerrado
                </span>
              </div>
            </div>
          </div>
        }

        <!-- Sprints without dates -->
        @if (undatedSprints().length > 0) {
          <div>
            <p class="mb-2 text-xs font-medium text-muted">
              Sprints sin fechas definidas
            </p>
            <div class="flex flex-wrap gap-2">
              @for (s of undatedSprints(); track s.id) {
                <span
                  class="inline-flex items-center gap-1.5 rounded-full border border-border
                         px-3 py-1 text-xs font-medium"
                  [class.text-success]="s.status === 'active'"
                  [class.text-muted]="s.status !== 'active'"
                >
                  {{ s.name }}
                  <span class="opacity-60">
                    {{ s.status === 'active' ? '· Activo' : '· Cerrado' }}
                  </span>
                </span>
              }
            </div>
          </div>
        }

      </div>
    }
  `,
})
export class SprintTimelineComponent {
  readonly sprints = input.required<Sprint[]>();

  /** Sprints that have at least a start_date and an end_date. */
  protected readonly timedSprints = computed<TimelineSprint[]>(() => {
    const timed = this.sprints().filter(
      (s) => s.start_date && s.end_date,
    );
    if (timed.length === 0) return [];

    const starts = timed.map((s) => new Date(s.start_date!).getTime());
    const ends = timed.map((s) => new Date(s.end_date!).getTime());
    const rangeStart = Math.min(...starts);
    const rangeEnd = Math.max(...ends);
    const totalMs = rangeEnd - rangeStart;
    if (totalMs <= 0) return [];

    return timed.map((s) => {
      const start = new Date(s.start_date!).getTime();
      const end = new Date(s.end_date!).getTime();
      const leftPct = ((start - rangeStart) / totalMs) * 100;
      const widthPct = Math.max(((end - start) / totalMs) * 100, 2);
      return {
        sprint: s,
        leftPct,
        widthPct,
        label: s.name,
        dateRange: `${shortDate(s.start_date)} — ${shortDate(s.end_date)}`,
      };
    });
  });

  protected readonly undatedSprints = computed<Sprint[]>(() =>
    this.sprints().filter((s) => !s.start_date || !s.end_date),
  );

  /** Month labels evenly distributed along the axis. */
  protected readonly axisLabels = computed<AxisLabel[]>(() => {
    const timed = this.sprints().filter(
      (s) => s.start_date && s.end_date,
    );
    if (timed.length === 0) return [];

    const starts = timed.map((s) => new Date(s.start_date!).getTime());
    const ends = timed.map((s) => new Date(s.end_date!).getTime());
    const rangeStart = Math.min(...starts);
    const rangeEnd = Math.max(...ends);
    const totalMs = rangeEnd - rangeStart;
    if (totalMs <= 0) return [];

    const labels: AxisLabel[] = [];
    const startDate = new Date(rangeStart);
    // Walk month by month
    const cursor = new Date(startDate.getFullYear(), startDate.getMonth(), 1);
    while (cursor.getTime() <= rangeEnd) {
      const leftPct = ((cursor.getTime() - rangeStart) / totalMs) * 100;
      if (leftPct >= 0 && leftPct <= 100) {
        labels.push({ leftPct, label: monthLabel(cursor) });
      }
      cursor.setMonth(cursor.getMonth() + 1);
    }
    // Always show last boundary
    labels.push({ leftPct: 100, label: monthLabel(new Date(rangeEnd)) });
    return labels;
  });
}
