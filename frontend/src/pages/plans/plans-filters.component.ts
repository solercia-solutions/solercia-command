import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import {
  SolButtonComponent,
  SolCardComponent,
  SolInputComponent,
  SolSelectComponent,
  SolSelectOption,
  SolToggleComponent,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';

/** Controles de la barra de filtros de `/plans` (los posee la página). */
export interface PlansFilterControls {
  /** Vigencia (`period_year`); '' = todas. */
  year: FormControl<string>;
  /** Tipo de plan; '' = todos. */
  type: FormControl<string>;
  /** Periodo del avance reportado (I, II, III, ANUAL); nunca vacío. */
  period: FormControl<string>;
  /** Correlación con tareas (`LinkFilter`). */
  link: FormControl<string>;
  q: FormControl<string>;
  mine: FormControl<boolean>;
}

/**
 * Barra de filtros de `/plans` (patrón de listado de PANDORA, igual que `/projects` y el
 * espacio de trabajo): `sol-card` con Vigencia, Tipo, Periodo, Enlace con tareas y Buscar
 * en una fila que se apila en móvil, más «Solo mías». Presentacional: controles, opciones y
 * conteo de filtros activos vienen de la página.
 */
@Component({
  selector: 'sol-plans-filters',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    SolButtonComponent,
    SolCardComponent,
    SolInputComponent,
    SolSelectComponent,
    SolToggleComponent,
  ],
  styles: [
    `
      :host {
        display: block;
      }

      .plf-card {
        display: block;
        width: 100%;
      }

      .plf-form {
        display: flex;
        flex-wrap: wrap;
        align-items: flex-end;
        gap: var(--sol-space-md, 16px);
      }

      .plf-field {
        flex: 1 1 180px;
        min-width: 150px;
      }

      .plf-field--year {
        flex: 0 1 150px;
        min-width: 130px;
      }

      .plf-field--search {
        flex: 2 1 260px;
      }

      /* Misma etiqueta que sol-select (sol-input la pinta en versalitas). */
      .plf-field--search ::ng-deep .sol-input-label {
        text-transform: none;
        letter-spacing: normal;
        font-weight: 600;
        line-height: 1.4;
        margin-bottom: 2px;
      }

      .plf-footer {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: var(--sol-space-sm, 8px);
        margin-top: var(--sol-space-md, 16px);
        min-height: 2.25rem;
        font-size: var(--sol-font-size-sm, 0.875rem);
        color: var(--sol-color-text-secondary);
      }

      .plf-footer__start {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: var(--sol-space-md, 16px);
      }

      @media (max-width: 767px) {
        .plf-form {
          flex-direction: column;
          align-items: stretch;
        }

        .plf-field,
        .plf-field--year,
        .plf-field--search {
          flex: none;
          min-width: 0;
          max-width: 100%;
        }

        .plf-clear {
          width: 100%;
        }

        .plf-clear ::ng-deep button {
          width: 100%;
          min-height: var(--sol-size-control-touch, 44px);
        }
      }
    `,
  ],
  template: `
    <sol-card class="plf-card">
      <div class="plf-form" role="search" [attr.aria-label]="text.regionAria()">
        @if (yearOptions().length > 0) {
          <sol-select
            class="plf-field plf-field--year"
            [label]="text.year()"
            [options]="yearOptions()"
            [showAllOption]="true"
            [allOptionLabel]="text.yearAll()"
            [placeholder]="text.yearAll()"
            [formControl]="controls().year"
          />
        }
        @if (typeOptions().length > 1) {
          <sol-select
            class="plf-field"
            [label]="text.type()"
            [options]="typeOptions()"
            [showAllOption]="true"
            [allOptionLabel]="text.typeAll()"
            [placeholder]="text.typeAll()"
            [formControl]="controls().type"
          />
        }
        <sol-select
          class="plf-field"
          [label]="text.period()"
          [options]="periodOptions()"
          [formControl]="controls().period"
        />
        <sol-select
          class="plf-field"
          [label]="text.link()"
          [options]="linkOptions()"
          [formControl]="controls().link"
        />
        <sol-input
          class="plf-field plf-field--search"
          type="search"
          [label]="text.search()"
          [placeholder]="text.searchPlaceholder()"
          [formControl]="controls().q"
        />
      </div>

      <div class="plf-footer">
        <div class="plf-footer__start">
          <sol-toggle [label]="text.onlyMine()" [formControl]="controls().mine" />
          <span aria-live="polite">
            @if (activeCount() > 0) {
              {{ activeLabel() }}
            }
          </span>
        </div>
        @if (activeCount() > 0) {
          <sol-button class="plf-clear" type="button" variant="ghost" size="sm" (click)="cleared.emit()">
            {{ text.clear() }}
          </sol-button>
        }
      </div>
    </sol-card>
  `,
})
export class PlansFiltersComponent {
  private readonly i18n = inject(I18nService);

  readonly controls = input.required<PlansFilterControls>();
  readonly yearOptions = input<SolSelectOption[]>([]);
  readonly typeOptions = input<SolSelectOption[]>([]);
  readonly periodOptions = input<SolSelectOption[]>([]);
  readonly linkOptions = input<SolSelectOption[]>([]);
  /** Filtros distintos del estado por defecto (vigencia natural y periodo no cuentan). */
  readonly activeCount = input(0);

  readonly cleared = output<void>();

  protected readonly text = {
    regionAria: this.i18n.t('plans.filters.regionAria'),
    year: this.i18n.t('plans.filters.year'),
    yearAll: this.i18n.t('plans.filters.yearAll'),
    type: this.i18n.t('plans.filters.type'),
    typeAll: this.i18n.t('plans.filters.typeAllPlans'),
    period: this.i18n.t('plans.filters.period'),
    link: this.i18n.t('plans.filters.link'),
    search: this.i18n.t('plans.filters.searchLabel'),
    searchPlaceholder: this.i18n.t('plans.filters.searchPlaceholder'),
    onlyMine: this.i18n.t('plans.filters.onlyMine'),
    clear: this.i18n.t('plans.filters.clear'),
  } as const;

  protected readonly activeLabel = computed(() => {
    this.i18n.activeLang();
    const count = this.activeCount();
    return count === 1
      ? this.i18n.translate('plans.filters.activeOne')
      : this.i18n.translate('plans.filters.activeOther', { count });
  });
}
