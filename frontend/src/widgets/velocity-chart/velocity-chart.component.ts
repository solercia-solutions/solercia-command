import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
} from '@angular/core';
import { VelocityData } from '@entities/workspace/workspace.model';
import { I18nService } from '@shared/i18n';

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
  selector: 'sol-velocity-chart',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (series().length === 0) {
      <p class="py-8 text-center text-sm text-muted">
        {{ text.emptyState() }}
      </p>
    } @else {
      <div class="flex flex-col gap-4">
        <!-- Metrics panel -->
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div class="rounded-lg border border-border bg-surface p-4 text-center">
            <p class="text-2xl font-bold text-brand">{{ avgVelocity() }}</p>
            <p class="mt-1 text-xs text-muted">{{ text.avgPerSprint() }}</p>
          </div>
          <div class="rounded-lg border border-border bg-surface p-4 text-center">
            <p class="text-2xl font-bold text-text">{{ backlogPoints() }}</p>
            <p class="mt-1 text-xs text-muted">{{ text.backlogPoints() }}</p>
          </div>
          <div class="rounded-lg border border-border bg-surface p-4 text-center">
            @if (projectedSprints() !== null) {
              <p class="text-2xl font-bold text-warning">{{ projectedSprints() }}</p>
              <p class="mt-1 text-xs text-muted">{{ text.projectedSprints() }}</p>
            } @else {
              <p class="text-2xl font-bold text-muted">—</p>
              <p class="mt-1 text-xs text-muted">{{ text.insufficientVelocity() }}</p>
            }
          </div>
        </div>

        <!-- Disclaimer -->
        <p class="text-xs italic text-muted">
          {{ text.disclaimer() }}
        </p>

        <!-- SVG bar chart -->
        <svg
          [attr.viewBox]="'0 0 ' + W + ' ' + H"
          class="h-auto w-full"
          role="img"
          [attr.aria-label]="text.chartAria()"
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
            >{{ text.avgAnnotation() }}</text>

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
            {{ text.legendCompleted() }}
          </span>
          <span class="inline-flex items-center gap-2">
            <svg width="22" height="8" viewBox="0 0 22 8" aria-hidden="true">
              <line x1="0" y1="4" x2="22" y2="4"
                stroke="var(--color-warning,#f59e0b)"
                stroke-width="2" stroke-dasharray="6 3"/>
            </svg>
            {{ text.legendAverage() }}
          </span>
        </div>
      </div>
    }
  `,
})
export class VelocityChartComponent {
  private readonly i18n = inject(I18nService);

  /** Textos estáticos de la vista resueltos por i18n (reactivos al idioma). */
  protected readonly text = {
    emptyState: this.i18n.t('velocityChart.emptyState'),
    avgPerSprint: this.i18n.t('velocityChart.metrics.avgPerSprint'),
    backlogPoints: this.i18n.t('velocityChart.metrics.backlogPoints'),
    projectedSprints: this.i18n.t('velocityChart.metrics.projectedSprints'),
    insufficientVelocity: this.i18n.t(
      'velocityChart.metrics.insufficientVelocity',
    ),
    disclaimer: this.i18n.t('velocityChart.disclaimer'),
    chartAria: this.i18n.t('velocityChart.chartAria'),
    avgAnnotation: this.i18n.t('velocityChart.avgAnnotation'),
    legendCompleted: this.i18n.t('velocityChart.legend.completedPoints'),
    legendAverage: this.i18n.t('velocityChart.legend.average'),
  } as const;

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
