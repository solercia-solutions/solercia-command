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

/** Controles de la barra de filtros del espacio de trabajo (los posee el padre). */
export interface WorkspaceFilterControls {
  year: FormControl<string>;
  status: FormControl<string>;
  assignee_id: FormControl<string>;
  priority: FormControl<string>;
  q: FormControl<string>;
}

/**
 * Barra de filtros de `/projects/:id` (patrón de listado de PANDORA: `sol-card` con los
 * controles en una fila que se apila en móvil). Presentacional: los controles, las opciones y
 * el conteo de filtros activos vienen del padre, que es quien consulta al backend.
 */
@Component({
  selector: 'sol-workspace-filters',
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

      .wf-card {
        display: block;
        width: 100%;
      }

      .wf-form {
        display: flex;
        flex-wrap: wrap;
        align-items: flex-end;
        gap: var(--sol-space-md, 16px);
      }

      .wf-field {
        flex: 1 1 180px;
        min-width: 160px;
      }

      .wf-field--year {
        flex: 0 1 160px;
        min-width: 130px;
      }

      .wf-field--search {
        flex: 2 1 240px;
      }

      /* sol-input pinta su etiqueta en versalitas; aquí se iguala a la de
         sol-select para que la fila de filtros se lea como un solo bloque. */
      .wf-field--search ::ng-deep .sol-input-label {
        text-transform: none;
        letter-spacing: normal;
        font-weight: 600;
        line-height: 1.4;
        margin-bottom: 2px;
      }

      .wf-footer {
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
        .wf-form {
          flex-direction: column;
          align-items: stretch;
        }

        .wf-field,
        .wf-field--year,
        .wf-field--search {
          flex: none;
          min-width: 0;
          max-width: 100%;
        }

        .wf-clear {
          width: 100%;
        }

        .wf-clear ::ng-deep button {
          width: 100%;
          min-height: var(--sol-size-control-touch, 44px);
        }
      }
    `,
  ],
  template: `
    <sol-card class="wf-card">
      <div class="wf-form" role="search" [attr.aria-label]="text.regionAria()">
        <sol-select
          class="wf-field wf-field--year"
          [label]="text.year()"
          [options]="yearOptions()"
          [showAllOption]="true"
          [allOptionLabel]="text.yearAll()"
          [placeholder]="text.yearAll()"
          [formControl]="controls().year"
        />
        <sol-select
          class="wf-field"
          [label]="text.status()"
          [options]="statusOptions()"
          [showAllOption]="true"
          [allOptionLabel]="text.statusAll()"
          [placeholder]="text.statusAll()"
          [formControl]="controls().status"
        />
        <sol-select
          class="wf-field"
          [label]="text.assignee()"
          [options]="assigneeOptions()"
          [showAllOption]="true"
          [allOptionLabel]="text.assigneeAll()"
          [placeholder]="text.assigneeAll()"
          [searchable]="assigneeOptions().length > 7"
          [formControl]="controls().assignee_id"
        />
        <sol-select
          class="wf-field"
          [label]="text.priority()"
          [options]="priorityOptions()"
          [showAllOption]="true"
          [allOptionLabel]="text.priorityAll()"
          [placeholder]="text.priorityAll()"
          [formControl]="controls().priority"
        />
        <sol-input
          class="wf-field wf-field--search"
          type="search"
          [label]="text.search()"
          [placeholder]="text.searchPlaceholder()"
          [formControl]="controls().q"
        />
      </div>

      @if (yearsUnavailable() || activeCount() > 0) {
        <div class="wf-footer">
          <span aria-live="polite">
            @if (activeCount() > 0) {
              {{ activeLabel() }}
            }
            @if (yearsUnavailable()) {
              {{ text.yearsUnavailable() }}
            }
          </span>
          @if (activeCount() > 0) {
            <sol-button class="wf-clear" type="button" variant="ghost" size="sm" (click)="cleared.emit()">
              {{ text.clear() }}
            </sol-button>
          }
        </div>
      }
    </sol-card>
  `,
})
export class WorkspaceFiltersComponent {
  private readonly i18n = inject(I18nService);

  readonly controls = input.required<WorkspaceFilterControls>();
  readonly yearOptions = input<SolSelectOption[]>([]);
  readonly statusOptions = input<SolSelectOption[]>([]);
  readonly assigneeOptions = input<SolSelectOption[]>([]);
  readonly priorityOptions = input<SolSelectOption[]>([]);
  readonly yearsUnavailable = input(false);
  /** Filtros distintos del estado por defecto (el año preseleccionado no cuenta). */
  readonly activeCount = input(0);

  readonly cleared = output<void>();

  protected readonly text = {
    regionAria: this.i18n.t('workspace.filters.regionAria'),
    year: this.i18n.t('workspace.year.label'),
    yearAll: this.i18n.t('workspace.year.all'),
    yearsUnavailable: this.i18n.t('workspace.year.yearsUnavailable'),
    status: this.i18n.t('workspace.filters.status'),
    statusAll: this.i18n.t('workspace.filters.statusAll'),
    assignee: this.i18n.t('workspace.filters.assignee'),
    assigneeAll: this.i18n.t('workspace.filters.assigneeAll'),
    priority: this.i18n.t('workspace.filters.priority'),
    priorityAll: this.i18n.t('workspace.filters.priorityAll'),
    search: this.i18n.t('workspace.filters.search'),
    searchPlaceholder: this.i18n.t('workspace.filters.searchPlaceholder'),
    clear: this.i18n.t('workspace.filters.clear'),
  } as const;

  protected readonly activeLabel = computed(() => {
    this.i18n.activeLang();
    const count = this.activeCount();
    return count === 1
      ? this.i18n.translate('workspace.filters.activeOne')
      : this.i18n.translate('workspace.filters.activeOther', { count });
  });
}
