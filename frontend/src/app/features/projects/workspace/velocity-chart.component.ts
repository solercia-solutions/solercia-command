import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
} from '@angular/core';
import { VelocityData } from './workspace.model';

interface Bar {
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  shortLabel: string;
  points: number;
}

interface YTick {
  y: number;
  label: string;
}

function shortSprintLabel(name: string): string {
  const m = /\d+/.exec(name);
  return m ? `S${m[0]}` : name.slice(0, 4);
}

/**
 * Dependency-free SVG velocity chart. Renders one bar per closed sprint
 * (completed story points) with a dashed average line and a metrics panel.
 * Follows the same visual pattern as BurndownChartComponent.
 */
@Component({
  selector: 'sp-velocity-chart',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (series().length === 0) {
      <p class="py-8 text-center text-sm text-muted">
        Aún no hay sprints cerrados para calcular la velocidad.
      </p>
    } @else {
      <div class="flex flex-col gap-4">
        <!-- Metrics panel -->
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div class="rounded-lg border border-border bg-surface p-4 text-center">
            <p class="text-2xl font-bold text-brand">{{ avgVelocity() }}</p>
            <p class="mt-1 text-xs text-muted">pts / sprint (promedio)</p>
          </div>
          <div class="rounded-lg border border-border bg-surface p-4 text-center">
            <p class="text-2xl font-bold text-text">{{ backlogPoints() }}</p>
            <p class="mt-1 text-xs text-muted">puntos en el backlog</p>
          </div>
          <div class="rounded-lg border border-border bg-surface p-4 text-center">
            @if (projectedSprints() !== null) {
              <p class="text-2xl font-bold text-warning">{{ projectedSprints() }}</p>
              <p class="mt-1 text-xs text-muted">sprints estimados para vaciar el backlog</p>
            } @else {
              <p class="text-2xl font-bold text-muted">—</p>
              <p class="mt-1 text-xs text-muted">velocidad insuficiente para proyectar</p>
            }
          </div>
        </div>

        <!-- Disclaimer -->
        <p class="text-xs italic text-muted">
          La velocidad refleja el rendimiento histórico del equipo y sirve para estimar, no para exigir.
        </p>

        <!-- SVG bar chart -->
        <svg
          [attr.viewBox]="'0 0 ' + W + ' ' + H"
          class="h-auto w-full"
          role="img"
          aria-label="Gráfico de velocidad por sprint: puntos completados por sprint cerrado"
          preserveAspectRatio="xMidYMid meet"
        >
          <g [attr.transform]="'translate(' + padLeft + ',' + padTop + ')'">

            <!-- Horizontal grid + y-axis labels -->
            @for (tick of yTicks(); track tick.label) {
              <line
                [attr.x1]="0"
                [attr.y1]="tick.y"
                [attr.x2]="innerW"
                [attr.y2]="tick.y"
                stroke="var(--color-border, #e2e8f0)"
                stroke-width="1"
              />
              <text
                [attr.x]="-6"
                [attr.y]="tick.y"
                text-anchor="end"
                dominant-baseline="middle"
                style="font-size:10px;fill:var(--color-muted,#94a3b8)"
              >{{ tick.label }}</text>
            }

            <!-- Bars -->
            @for (bar of bars(); track bar.label) {
              <rect
                [attr.x]="bar.x"
                [attr.y]="bar.y"
                [attr.width]="bar.width"
                [attr.height]="bar.height"
                rx="3"
                fill="var(--color-brand, #6366f1)"
                opacity="0.75"
              />
              @if (bar.height > 16) {
                <text
                  [attr.x]="bar.x + bar.width / 2"
                  [attr.y]="bar.y - 5"
                  text-anchor="middle"
                  style="font-size:10px;fill:var(--color-text,#1e293b);font-weight:600"
                >{{ bar.points }}</text>
              }
              <!-- X-axis label -->
              <text
                [attr.x]="bar.x + bar.width / 2"
                [attr.y]="innerH + 16"
                text-anchor="middle"
                style="font-size:9px;fill:var(--color-muted,#94a3b8)"
              >{{ bar.shortLabel }}</text>
            }

            <!-- Average line (dashed, warning color) -->
            <line
              [attr.x1]="0"
              [attr.y1]="avgY()"
              [attr.x2]="innerW"
              [attr.y2]="avgY()"
              stroke="var(--color-warning, #f59e0b)"
              stroke-width="2"
              stroke-dasharray="6 3"
            />
            <text
              [attr.x]="innerW + 4"
              [attr.y]="avgY()"
              dominant-baseline="middle"
              style="font-size:10px;fill:var(--color-warning,#f59e0b);font-weight:600"
            >avg</text>

            <!-- X axis baseline -->
            <line
              [attr.x1]="0"
              [attr.y1]="innerH"
              [attr.x2]="innerW"
              [attr.y2]="innerH"
              stroke="var(--color-border, #e2e8f0)"
              stroke-width="1"
            />
          </g>
        </svg>

        <!-- Legend -->
        <div class="flex flex-wrap items-center gap-4 text-xs text-muted">
          <span class="inline-flex items-center gap-2">
            <svg width="22" height="8" viewBox="0 0 22 8" aria-hidden="true">
              <rect x="0" y="1" width="22" height="6" rx="2"
                fill="var(--color-brand,#6366f1)" opacity="0.75"/>
            </svg>
            Puntos completados
          </span>
          <span class="inline-flex items-center gap-2">
            <svg width="22" height="8" viewBox="0 0 22 8" aria-hidden="true">
              <line x1="0" y1="4" x2="22" y2="4"
                stroke="var(--color-warning,#f59e0b)"
                stroke-width="2" stroke-dasharray="6 3"/>
            </svg>
            Promedio
          </span>
        </div>
      </div>
    }
  `,
})
export class VelocityChartComponent {
  readonly data = input.required<VelocityData>();

  // SVG layout constants
  protected readonly W = 600;
  protected readonly H = 260;
  protected readonly padTop = 24;
  protected readonly padRight = 44;
  protected readonly padBottom = 44;
  protected readonly padLeft = 44;
  protected readonly innerW = 600 - 44 - 44; // W - padLeft - padRight = 512
  protected readonly innerH = 260 - 24 - 44; // H - padTop - padBottom = 192

  protected readonly series = computed(() => this.data().series);

  protected readonly avgVelocity = computed(() => {
    const v = this.data().average_velocity;
    return Number.isInteger(v) ? v : Math.round(v * 10) / 10;
  });

  protected readonly backlogPoints = computed(() => this.data().backlog_points);
  protected readonly projectedSprints = computed(() => this.data().projected_sprints);

  private readonly maxPoints = computed(() => {
    const pts = this.series().map((e) => e.completed_points);
    return Math.max(...pts, Math.ceil(this.data().average_velocity), 1);
  });

  protected readonly yTicks = computed<YTick[]>(() => {
    const maxP = this.maxPoints();
    const h = this.innerH;
    const count = 4;
    return Array.from({ length: count + 1 }, (_, i) => {
      const value = Math.round((maxP * i) / count);
      const y = h - (value / maxP) * h;
      return { y, label: String(value) };
    });
  });

  private readonly barSpacing = computed(() => {
    const n = this.series().length;
    return n > 0 ? this.innerW / n : 0;
  });

  private readonly barWidth = computed(() =>
    Math.min(52, Math.max(8, this.barSpacing() * 0.6)),
  );

  protected readonly bars = computed<Bar[]>(() => {
    const series = this.series();
    const h = this.innerH;
    const maxP = this.maxPoints();
    const spacing = this.barSpacing();
    const bw = this.barWidth();
    return series.map((entry, i) => {
      const cx = i * spacing + spacing / 2;
      const barH = maxP > 0 ? (entry.completed_points / maxP) * h : 0;
      return {
        x: cx - bw / 2,
        y: h - barH,
        width: bw,
        height: barH,
        label: entry.name,
        shortLabel: shortSprintLabel(entry.name),
        points: entry.completed_points,
      };
    });
  });

  protected readonly avgY = computed(() => {
    const maxP = this.maxPoints();
    return maxP > 0
      ? this.innerH - (this.data().average_velocity / maxP) * this.innerH
      : this.innerH;
  });
}
