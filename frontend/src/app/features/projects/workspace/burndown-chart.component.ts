import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
} from '@angular/core';
import { BurndownDay, BurndownUnit } from './workspace.model';

/** A plotted point in the SVG coordinate system. */
interface ChartPoint {
  x: number;
  y: number;
}

/** A labelled horizontal gridline / y-axis tick. */
interface YTick {
  y: number;
  label: string;
}

/** A labelled x-axis tick at a given day index. */
interface XTick {
  x: number;
  label: string;
}

const MONTHS_ES = [
  'ene',
  'feb',
  'mar',
  'abr',
  'may',
  'jun',
  'jul',
  'ago',
  'sep',
  'oct',
  'nov',
  'dic',
];

/** Format a "YYYY-MM-DD" string as "d mmm" without timezone drift. */
function formatDayLabel(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) {
    return iso;
  }
  const day = Number(match[3]);
  const month = MONTHS_ES[Number(match[2]) - 1] ?? '';
  return `${day} ${month}`.trim();
}

/**
 * Dependency-free SVG burndown chart. Renders the ideal remaining-work line
 * (dashed) against the actual line (solid), with a y-axis in the sprint's
 * estimation unit and an x-axis of dates. The actual line stops at "today":
 * future days arrive with `actual = null` and are not plotted.
 *
 * Purely presentational — it only needs the `days[]` series and the `unit`.
 */
@Component({
  selector: 'bk-burndown-chart',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (days().length === 0) {
      <p class="py-8 text-center text-sm text-muted">
        No hay datos suficientes para dibujar el burndown.
      </p>
    } @else {
      <div class="flex flex-col gap-3">
        <!-- Legend -->
        <div
          class="flex flex-wrap items-center gap-4 text-xs font-medium text-muted"
        >
          <span class="inline-flex items-center gap-2">
            <svg width="22" height="8" viewBox="0 0 22 8" aria-hidden="true">
              <line
                x1="0"
                y1="4"
                x2="22"
                y2="4"
                stroke="currentColor"
                class="text-muted"
                stroke-width="2"
                stroke-dasharray="4 3"
              />
            </svg>
            Ideal
          </span>
          <span class="inline-flex items-center gap-2 text-brand">
            <svg width="22" height="8" viewBox="0 0 22 8" aria-hidden="true">
              <line
                x1="0"
                y1="4"
                x2="22"
                y2="4"
                stroke="currentColor"
                stroke-width="2.5"
              />
            </svg>
            Real
          </span>
          <span class="ml-auto text-muted">
            Eje vertical: {{ unitLabel() }} restantes
          </span>
        </div>

        <svg
          [attr.viewBox]="'0 0 ' + width + ' ' + height"
          class="h-auto w-full"
          role="img"
          [attr.aria-label]="
            'Gráfico de burndown del sprint, eje vertical en ' + unitLabel()
          "
          preserveAspectRatio="xMidYMid meet"
        >
          <!-- Horizontal grid + y-axis labels -->
          @for (tick of yTicks(); track tick.label) {
            <line
              [attr.x1]="padLeft"
              [attr.y1]="tick.y"
              [attr.x2]="width - padRight"
              [attr.y2]="tick.y"
              stroke="currentColor"
              class="text-border"
              stroke-width="1"
            />
            <text
              [attr.x]="padLeft - 8"
              [attr.y]="tick.y + 4"
              text-anchor="end"
              class="fill-muted text-[10px]"
            >
              {{ tick.label }}
            </text>
          }

          <!-- x-axis baseline -->
          <line
            [attr.x1]="padLeft"
            [attr.y1]="baselineY()"
            [attr.x2]="width - padRight"
            [attr.y2]="baselineY()"
            stroke="currentColor"
            class="text-border"
            stroke-width="1.5"
          />

          <!-- x-axis date labels -->
          @for (tick of xTicks(); track tick.x) {
            <text
              [attr.x]="tick.x"
              [attr.y]="height - 12"
              text-anchor="middle"
              class="fill-muted text-[10px]"
            >
              {{ tick.label }}
            </text>
          }

          <!-- Ideal line (dashed) -->
          <polyline
            [attr.points]="idealPath()"
            fill="none"
            stroke="currentColor"
            class="text-muted"
            stroke-width="2"
            stroke-dasharray="5 4"
            stroke-linecap="round"
            stroke-linejoin="round"
          />

          <!-- Actual line (solid, stops at today) -->
          <polyline
            [attr.points]="actualPath()"
            fill="none"
            stroke="currentColor"
            class="text-brand"
            stroke-width="2.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />

          <!-- Actual data points -->
          @for (point of actualPoints(); track point.x) {
            <circle
              [attr.cx]="point.x"
              [attr.cy]="point.y"
              r="2.5"
              fill="currentColor"
              class="text-brand"
            />
          }

          <!-- "Hoy" marker on the last actual point -->
          @if (todayPoint(); as today) {
            <circle
              [attr.cx]="today.x"
              [attr.cy]="today.y"
              r="4.5"
              fill="none"
              stroke="currentColor"
              class="text-brand"
              stroke-width="2"
            />
          }
        </svg>
      </div>
    }
  `,
})
export class BurndownChartComponent {
  /** The full day-by-day series (ideal + actual). */
  readonly days = input.required<BurndownDay[]>();
  /** Estimation unit the y-axis is measured in. */
  readonly unit = input<BurndownUnit>('points');

  /* ---- SVG geometry (internal coordinate system) ------------------------- */
  protected readonly width = 640;
  protected readonly height = 280;
  protected readonly padLeft = 44;
  protected readonly padRight = 16;
  protected readonly padTop = 16;
  protected readonly padBottom = 44;

  protected readonly unitLabel = computed<string>(() =>
    this.unit() === 'points' ? 'puntos' : 'tareas',
  );

  /** Upper bound of the y-axis (max remaining work, rounded up). */
  private readonly maxY = computed<number>(() => {
    const max = this.days().reduce((acc, day) => {
      const actual = day.actual ?? 0;
      return Math.max(acc, day.ideal, actual);
    }, 0);
    return Math.max(1, Math.ceil(max));
  });

  protected readonly baselineY = computed<number>(() => this.scaleY(0));

  private readonly innerWidth = computed<number>(
    () => this.width - this.padLeft - this.padRight,
  );

  private scaleX(index: number): number {
    const count = this.days().length;
    if (count <= 1) {
      return this.padLeft + this.innerWidth() / 2;
    }
    return this.padLeft + (this.innerWidth() * index) / (count - 1);
  }

  private scaleY(value: number): number {
    const innerHeight = this.height - this.padTop - this.padBottom;
    const ratio = value / this.maxY();
    return this.padTop + innerHeight * (1 - ratio);
  }

  /** Ideal points (always the full span). */
  protected readonly idealPath = computed<string>(() =>
    this.days()
      .map((day, i) => `${this.scaleX(i)},${this.scaleY(day.ideal)}`)
      .join(' '),
  );

  /** Actual points where data exists (null = future, not plotted). */
  protected readonly actualPoints = computed<ChartPoint[]>(() =>
    this.days()
      .map((day, i) =>
        day.actual == null
          ? null
          : { x: this.scaleX(i), y: this.scaleY(day.actual) },
      )
      .filter((p): p is ChartPoint => p !== null),
  );

  protected readonly actualPath = computed<string>(() =>
    this.actualPoints()
      .map((point) => `${point.x},${point.y}`)
      .join(' '),
  );

  /** Last plotted actual point — i.e. "today". */
  protected readonly todayPoint = computed<ChartPoint | null>(() => {
    const points = this.actualPoints();
    return points.length > 0 ? points[points.length - 1] : null;
  });

  protected readonly yTicks = computed<YTick[]>(() => {
    const max = this.maxY();
    const steps = 4;
    const ticks: YTick[] = [];
    for (let i = 0; i <= steps; i++) {
      const value = (max * i) / steps;
      ticks.push({ y: this.scaleY(value), label: String(Math.round(value)) });
    }
    return ticks;
  });

  protected readonly xTicks = computed<XTick[]>(() => {
    const days = this.days();
    const count = days.length;
    if (count === 0) {
      return [];
    }
    // Aim for ~6 labels; always include first and last.
    const target = 6;
    const step = Math.max(1, Math.ceil(count / target));
    const ticks: XTick[] = [];
    for (let i = 0; i < count; i += step) {
      ticks.push({ x: this.scaleX(i), label: formatDayLabel(days[i].date) });
    }
    const lastIndex = count - 1;
    if ((ticks.length === 0 || ticks[ticks.length - 1].x !== this.scaleX(lastIndex))) {
      ticks.push({
        x: this.scaleX(lastIndex),
        label: formatDayLabel(days[lastIndex].date),
      });
    }
    return ticks;
  });
}
