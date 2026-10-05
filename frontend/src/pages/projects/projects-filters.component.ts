import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import {
  SolButtonComponent,
  SolCardComponent,
  SolInputComponent,
  SolSelectComponent,
  SolSelectOption,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';

/** Controles de la barra de filtros de `/projects` (los posee la página). */
export interface ProjectsFilterControls {
  year: FormControl<string>;
  methodology: FormControl<string>;
  q: FormControl<string>;
}

/**
 * Barra de filtros de `/projects` (patrón de listado de PANDORA, igual que la del espacio de
 * trabajo): `sol-card` con Año, Metodología y Buscar en una fila que se apila en móvil.
 * Presentacional: controles, opciones y conteo de filtros activos vienen de la página.
 */
@Component({
  selector: 'sol-projects-filters',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    SolButtonComponent,
    SolCardComponent,
    SolInputComponent,
    SolSelectComponent,
  ],
  styles: [
    `
      :host {
        display: block;
      }

      .pf-card {
        display: block;
        width: 100%;
      }

      .pf-form {
        display: flex;
        flex-wrap: wrap;
        align-items: flex-end;
        gap: var(--sol-space-md, 16px);
      }

      .pf-field {
        flex: 1 1 200px;
        min-width: 160px;
      }

      .pf-field--year {
        flex: 0 1 160px;
        min-width: 130px;
      }

      .pf-field--search {
        flex: 2 1 260px;
      }

      /* Misma etiqueta que sol-select (sol-input la pinta en versalitas). */
      .pf-field--search ::ng-deep .sol-input-label {
        text-transform: none;
        letter-spacing: normal;
        font-weight: 600;
        line-height: 1.4;
        margin-bottom: 2px;
      }

      .pf-footer {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: var(--sol-space-sm, 8px);
        margin-top: var(--sol-space-sm, 8px);
        min-height: 2.25rem;
        font-size: var(--sol-font-size-sm, 0.875rem);
        color: var(--sol-color-text-secondary);
      }

      @media (max-width: 767px) {
        .pf-form {
          flex-direction: column;
          align-items: stretch;
        }

        .pf-field,
        .pf-field--year,
        .pf-field--search {
          flex: none;
          min-width: 0;
          max-width: 100%;
        }

        .pf-clear {
          width: 100%;
        }

        .pf-clear ::ng-deep button {
          width: 100%;
          min-height: var(--sol-size-control-touch, 44px);
        }
      }
    `,
  ],
  template: `
    <sol-card class="pf-card">
      <div class="pf-form" role="search" [attr.aria-label]="text.regionAria()">
        <sol-select
          class="pf-field pf-field--year"
          [label]="text.year()"
          [options]="yearOptions()"
          [showAllOption]="true"
          [allOptionLabel]="text.yearAll()"
          [placeholder]="text.yearAll()"
          [formControl]="controls().year"
        />
        <sol-select
          class="pf-field"
          [label]="text.methodology()"
          [options]="methodologyOptions()"
          [showAllOption]="true"
          [allOptionLabel]="text.methodologyAll()"
          [placeholder]="text.methodologyAll()"
          [formControl]="controls().methodology"
        />
        <sol-input
          class="pf-field pf-field--search"
          type="search"
          [label]="text.search()"
          [placeholder]="text.searchPlaceholder()"
          [formControl]="controls().q"
        />
      </div>

      @if (yearsUnavailable() || activeCount() > 0) {
        <div class="pf-footer">
          <span aria-live="polite">
            @if (activeCount() > 0) {
              {{ activeLabel() }}
            }
            @if (yearsUnavailable()) {
              {{ text.yearsUnavailable() }}
            }
          </span>
          @if (activeCount() > 0) {
            <sol-button class="pf-clear" type="button" variant="ghost" size="sm" (click)="cleared.emit()">
              {{ text.clear() }}
            </sol-button>
          }
        </div>
      }
    </sol-card>
  `,
})
export class ProjectsFiltersComponent {
  private readonly i18n = inject(I18nService);

  readonly controls = input.required<ProjectsFilterControls>();
  readonly yearOptions = input<SolSelectOption[]>([]);
  readonly methodologyOptions = input<SolSelectOption[]>([]);
  readonly yearsUnavailable = input(false);
  /** Filtros distintos del estado por defecto (el año preseleccionado no cuenta). */
  readonly activeCount = input(0);

  readonly cleared = output<void>();

  protected readonly text = {
    regionAria: this.i18n.t('projects.filters.regionAria'),
    year: this.i18n.t('projects.filters.year'),
    yearAll: this.i18n.t('projects.filters.yearAll'),
    yearsUnavailable: this.i18n.t('projects.filters.yearsUnavailable'),
    methodology: this.i18n.t('projects.filters.methodology'),
    methodologyAll: this.i18n.t('projects.filters.methodologyAll'),
    search: this.i18n.t('projects.filters.search'),
    searchPlaceholder: this.i18n.t('projects.filters.searchPlaceholder'),
    clear: this.i18n.t('projects.filters.clear'),
  } as const;

  protected readonly activeLabel = computed(() => {
    this.i18n.activeLang();
    const count = this.activeCount();
    return count === 1
      ? this.i18n.translate('projects.filters.activeOne')
      : this.i18n.translate('projects.filters.activeOther', { count });
  });
}
