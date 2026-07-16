import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
} from '@angular/core';
import { SolChartComponent, type SolChartData } from '@shared/ui';
import { VelocityData } from '@entities/workspace/workspace.model';
import { I18nService } from '@shared/i18n';

function shortSprintLabel(name: string): string {
  const m = /\d+/.exec(name);
  return m ? `S${m[0]}` : name.slice(0, 4);
}

/**
 * Velocity chart, delegando el motor de dibujo a `sol-chart` (11-a-solercia-ui
 * PR9, T69) en vez de SVG a mano. Mantiene el mismo panel de métricas
 * (promedio/backlog/proyección) — es texto puro, no depende del motor de
 * gráficas.
 *
 * Desviación aceptada y documentada: la línea punteada de "promedio" que
 * cruzaba las barras se retira — `sol-chart` (contrato declarativo) no
 * soporta mezclar `bar` + `line` ni una anotación de referencia. El valor
 * promedio SIGUE visible (y con más énfasis) en el panel de métricas de
 * arriba, así que no se pierde información, solo la referencia visual dentro
 * del canvas.
 */
@Component({
  selector: 'sol-velocity-chart',
  standalone: true,
  imports: [SolChartComponent],
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

        <sol-chart
          type="bar"
          [data]="chartData()"
          [options]="{ legend: true }"
          ariaLabelKey="velocityChart.chartAria"
        />
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
    legendCompletedPoints: this.i18n.t('velocityChart.legend.completedPoints'),
  } as const;

  readonly data = input.required<VelocityData>();

  protected readonly series = computed(() => this.data().series);

  protected readonly avgVelocity = computed(() => {
    const v = this.data().average_velocity;
    return Number.isInteger(v) ? v : Math.round(v * 10) / 10;
  });

  protected readonly backlogPoints = computed(() => this.data().backlog_points);
  protected readonly projectedSprints = computed(() => this.data().projected_sprints);

  protected readonly chartData = computed<SolChartData>(() => ({
    labels: this.series().map((entry) => shortSprintLabel(entry.name)),
    series: [
      {
        label: this.text.legendCompletedPoints(),
        data: this.series().map((entry) => entry.completed_points),
      },
    ],
  }));
}
