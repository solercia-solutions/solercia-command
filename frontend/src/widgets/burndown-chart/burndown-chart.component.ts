import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
} from '@angular/core';
import { SolChartComponent, type SolChartData } from '@shared/ui';
import { BurndownDay, BurndownUnit } from '@entities/workspace/workspace.model';
import { I18nService } from '@shared/i18n';

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
 * Burndown chart, delegando el motor de dibujo a `sol-chart` (11-a-solercia-ui
 * PR9, T69) en vez de SVG a mano. Mantiene la misma API pública (`days`,
 * `unit`) para que `project-workspace` no requiera cambios de consumo.
 *
 * Fidelidad visual — desviaciones aceptadas y documentadas (contrato
 * declarativo de `sol-chart`, sin acceso a opciones por-serie de Chart.js):
 * - La línea "Ideal" ya no se distingue por trazo punteado (solo por color +
 *   leyenda) — `SolChartSeries` no expone `borderDash`.
 * - Se pierde el anillo destacado del punto "hoy"; el resto de puntos siguen
 *   visibles (tooltip al pasar el mouse).
 * - El eje Y se autoescala con Chart.js en vez del cálculo manual anterior.
 */
@Component({
  selector: 'sol-burndown-chart',
  standalone: true,
  imports: [SolChartComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (days().length === 0) {
      <p class="py-8 text-center text-sm text-muted">
        {{ text.emptyState() }}
      </p>
    } @else {
      <div class="flex flex-col gap-2">
        <p class="text-right text-xs text-muted">{{ yAxisCaption() }}</p>
        <sol-chart type="line" [data]="chartData()" [ariaLabelKey]="ariaLabelKey()" />
      </div>
    }
  `,
})
export class BurndownChartComponent {
  private readonly i18n = inject(I18nService);

  /** Textos estáticos de la vista resueltos por i18n (reactivos al idioma). */
  protected readonly text = {
    emptyState: this.i18n.t('burndownChart.emptyState'),
    legendIdeal: this.i18n.t('burndownChart.legend.ideal'),
    legendActual: this.i18n.t('burndownChart.legend.actual'),
  } as const;

  /** The full day-by-day series (ideal + actual). */
  readonly days = input.required<BurndownDay[]>();
  /** Estimation unit the y-axis is measured in. */
  readonly unit = input<BurndownUnit>('points');

  protected readonly unitLabel = computed<string>(() => {
    this.i18n.activeLang();
    return this.unit() === 'points'
      ? this.i18n.translate('burndownChart.unit.points')
      : this.i18n.translate('burndownChart.unit.tasks');
  });

  /** Leyenda del eje vertical, dependiente de la unidad. */
  protected readonly yAxisCaption = computed<string>(() =>
    this.i18n.translate('burndownChart.yAxisCaption', {
      unit: this.unitLabel(),
    }),
  );

  /**
   * `sol-chart` solo acepta una CLAVE i18n estática (sin parámetros) para el
   * `aria-label` — a diferencia del `chartAria` original (con `{{ unit }}`
   * interpolado), se resuelve con 2 claves fijas según la unidad.
   */
  protected readonly ariaLabelKey = computed<string>(() =>
    this.unit() === 'points' ? 'burndownChart.chartAriaPoints' : 'burndownChart.chartAriaTasks',
  );

  /**
   * Serie "Real" recortada a los días con dato (sin `null`): `SolChartSeries.data`
   * exige `number[]`. Un arreglo más corto que `labels` no dibuja línea más
   * allá del último punto real — mismo efecto visual que "se detiene en hoy".
   */
  protected readonly chartData = computed<SolChartData>(() => {
    const days = this.days();
    return {
      labels: days.map((day) => formatDayLabel(day.date)),
      series: [
        { label: this.text.legendIdeal(), data: days.map((day) => day.ideal) },
        {
          label: this.text.legendActual(),
          data: days.filter((day) => day.actual != null).map((day) => day.actual as number),
        },
      ],
    };
  });
}
