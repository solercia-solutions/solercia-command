import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  TemplateRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { HttpErrorResponse } from '@angular/common/http';
import {
  FormBuilder,
  FormControl,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import {
  SolButtonComponent,
  SolInputComponent,
  SolBadgeComponent,
  SolIconButtonComponent,
  SolDrawerComponent,
  SolConfirmDialogComponent,
  SolDataTableComponent,
  SolEmptyStateComponent,
  SolSelectComponent,
  SolSelectOption,
  SolSpinnerComponent,
  DataTableColumn,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { AlertService } from '@shared/lib/alerts';
import { DependenciesService } from '@entities/dependency/dependencies.service';
import { Dependency } from '@entities/dependency/dependency.model';

type StatusFilter = 'all' | 'active' | 'inactive';

/**
 * `/admin/dependencies` con el patrón de listado de PANDORA (gestión de usuarios): encabezado
 * `h1.sol-display`, tabla paginada con buscador y acciones al inicio, filtro de estado en la
 * barra de la tabla y formulario de crear/editar en `sol-drawer` lateral.
 */
@Component({
  selector: 'sol-admin-dependencies',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    SolButtonComponent,
    SolInputComponent,
    SolBadgeComponent,
    SolIconButtonComponent,
    SolDrawerComponent,
    SolConfirmDialogComponent,
    SolDataTableComponent,
    SolEmptyStateComponent,
    SolSelectComponent,
    SolSpinnerComponent,
  ],
  styleUrl: '../admin-page.scss',
  template: `
    <section class="adm-page">
      <header class="adm-header">
        <div class="adm-header__text">
          <h1 class="adm-title sol-display">{{ text.title() }}</h1>
          <p class="adm-muted">{{ text.subtitle() }}</p>
        </div>
        <sol-button
          type="button"
          variant="primary"
          [ariaLabel]="text.createAria()"
          (clicked)="openCreate()"
        >
          {{ text.create() }}
        </sol-button>
      </header>

      @if (loading()) {
        <div class="adm-state" role="status" aria-live="polite">
          <sol-spinner size="lg" />
          <p>{{ text.loading() }}</p>
        </div>
      } @else if (loadError(); as message) {
        <div class="adm-alert" role="alert">
          <span>{{ message }}</span>
          <sol-button type="button" variant="secondary" size="sm" (clicked)="load()">
            {{ text.retry() }}
          </sol-button>
        </div>
      } @else if (items().length === 0) {
        <sol-empty-state
          icon="folder"
          titleKey="admin.dependencies.empty.title"
          descriptionKey="admin.dependencies.empty.subtitle"
        />
      } @else {
        @if (deletingId()) {
          <p class="adm-busy" role="status">{{ text.deleting() }}</p>
        }
        <sol-data-table
          [data]="tableData()"
          [columns]="columns()"
          [searchPlaceholder]="text.search()"
          [emptyMessage]="statusFilter() === 'all' ? text.noSearchMatches() : text.noFilterMatches()"
          [paginated]="true"
          [showActions]="true"
          [actionsLabel]="text.thActions()"
          actionsPosition="start"
          [collapseWidth]="760"
          trackByKey="id"
        >
          <div tableActions class="adm-filters">
            <sol-select
              class="adm-filter"
              [label]="text.filterStatus()"
              [options]="statusOptions()"
              [formControl]="statusControl"
            />
            @if (statusFilter() !== 'all') {
              <sol-button type="button" variant="ghost" size="sm" (clicked)="clearFilters()">
                {{ text.clearFilters() }}
              </sol-button>
            }
          </div>
          <ng-template #rowActions let-row>
            <sol-icon-button
              icon="edit"
              variant="outline"
              [ariaLabel]="text.editAria()"
              [disabled]="deletingId() === row['id']"
              (clicked)="openEdit($any(row))"
            />
            <sol-icon-button
              icon="trash"
              variant="danger"
              [ariaLabel]="text.deleteAria()"
              [disabled]="deletingId() === row['id']"
              (clicked)="askDelete($any(row))"
            />
          </ng-template>
        </sol-data-table>
      }
    </section>

    <ng-template #codeCell let-value>
      <span>{{ $any(value) || '—' }}</span>
    </ng-template>
    <ng-template #statusCell let-row="row">
      @if ($any(row).is_active) {
        <sol-badge variant="success">{{ text.statusActive() }}</sol-badge>
      } @else {
        <sol-badge variant="neutral">{{ text.statusInactive() }}</sol-badge>
      }
    </ng-template>

    <sol-drawer
      [open]="showForm()"
      [title]="editing() ? text.formEditTitle() : text.formCreateTitle()"
      side="end"
      size="md"
      (closed)="closeForm()"
    >
      <form [formGroup]="form" (ngSubmit)="onSubmit()" class="adm-form" novalidate>
        <sol-input
          [label]="text.nameLabel()"
          [placeholder]="text.namePlaceholder()"
          [error]="showError('name') ? text.nameRequired() : ''"
          formControlName="name"
        />
        <sol-input
          [label]="text.codeLabel()"
          [placeholder]="text.codePlaceholder()"
          formControlName="code"
        />
        <label class="adm-check">
          <input type="checkbox" formControlName="is_active" />
          {{ text.activeLabel() }}
        </label>

        @if (formError(); as message) {
          <div class="adm-alert" role="alert">{{ message }}</div>
        }
        <button type="submit" class="adm-submit" tabindex="-1" aria-hidden="true"></button>
      </form>

      <div drawerFooter class="adm-footer">
        <sol-button type="button" variant="secondary" (clicked)="closeForm()">
          {{ text.cancel() }}
        </sol-button>
        <sol-button
          type="button"
          variant="primary"
          [disabled]="saving()"
          [loading]="saving()"
          (clicked)="onSubmit()"
        >
          {{ saving() ? text.saving() : text.save() }}
        </sol-button>
      </div>
    </sol-drawer>

    <sol-confirm-dialog
      [open]="deleting() !== null"
      variant="danger"
      [title]="text.deleteTitle()"
      [message]="deleteMessage()"
      [confirmLabel]="text.delete()"
      [cancelLabel]="text.cancel()"
      (confirm)="confirmDelete()"
      (cancel)="cancelDelete()"
    />
  `,
})
export class DependenciesPageComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(DependenciesService);
  private readonly i18n = inject(I18nService);
  private readonly alert = inject(AlertService);

  /** Textos de la vista resueltos por i18n (reactivos al cambio de idioma). */
  protected readonly text = {
    title: this.i18n.t('admin.dependencies.title'),
    subtitle: this.i18n.t('admin.dependencies.subtitle'),
    loading: this.i18n.t('admin.dependencies.loading'),
    thName: this.i18n.t('admin.dependencies.table.name'),
    thCode: this.i18n.t('admin.dependencies.table.code'),
    thStatus: this.i18n.t('admin.dependencies.table.status'),
    thActions: this.i18n.t('admin.dependencies.table.actions'),
    statusActive: this.i18n.t('admin.dependencies.status.active'),
    statusInactive: this.i18n.t('admin.dependencies.status.inactive'),
    create: this.i18n.t('admin.dependencies.actions.create'),
    createAria: this.i18n.t('admin.dependencies.actions.createAria'),
    editAria: this.i18n.t('admin.dependencies.actions.editAria'),
    deleteAria: this.i18n.t('admin.dependencies.actions.deleteAria'),
    cancel: this.i18n.t('admin.dependencies.actions.cancel'),
    save: this.i18n.t('admin.dependencies.actions.save'),
    saving: this.i18n.t('admin.dependencies.actions.saving'),
    delete: this.i18n.t('admin.dependencies.actions.delete'),
    deleting: this.i18n.t('admin.dependencies.actions.deleting'),
    formCreateTitle: this.i18n.t('admin.dependencies.form.createTitle'),
    formEditTitle: this.i18n.t('admin.dependencies.form.editTitle'),
    nameLabel: this.i18n.t('admin.dependencies.form.nameLabel'),
    namePlaceholder: this.i18n.t('admin.dependencies.form.namePlaceholder'),
    nameRequired: this.i18n.t('admin.dependencies.form.nameRequired'),
    codeLabel: this.i18n.t('admin.dependencies.form.codeLabel'),
    codePlaceholder: this.i18n.t('admin.dependencies.form.codePlaceholder'),
    activeLabel: this.i18n.t('admin.dependencies.form.activeLabel'),
    deleteTitle: this.i18n.t('admin.dependencies.delete.title'),
    deleteConfirmPrefix: this.i18n.t('admin.dependencies.delete.confirmPrefix'),
    deleteConfirmSuffix: this.i18n.t('admin.dependencies.delete.confirmSuffix'),
    retry: this.i18n.t('admin.common.retry'),
    search: this.i18n.t('admin.common.searchPlaceholder'),
    noSearchMatches: this.i18n.t('admin.common.noSearchMatches'),
    noFilterMatches: this.i18n.t('admin.common.noFilterMatches'),
    clearFilters: this.i18n.t('admin.common.clearFilters'),
    filterStatus: this.i18n.t('admin.common.filters.status'),
    allStatuses: this.i18n.t('admin.common.filters.allStatuses'),
  } as const;

  protected readonly items = signal<Dependency[]>([]);
  protected readonly loading = signal(false);
  protected readonly loadError = signal<string | null>(null);

  /** Filtro de estado (preseleccionado en «Todos los estados»). */
  protected readonly statusControl = new FormControl<StatusFilter>('all', { nonNullable: true });
  protected readonly statusFilter = toSignal(this.statusControl.valueChanges, {
    initialValue: this.statusControl.value,
  });
  protected readonly statusOptions = computed<SolSelectOption[]>(() => [
    { value: 'all', label: this.text.allStatuses() },
    { value: 'active', label: this.text.statusActive() },
    { value: 'inactive', label: this.text.statusInactive() },
  ]);

  /** Filas para `sol-data-table` (contrato genérico `Record<string, unknown>`), ya filtradas. */
  protected readonly tableData = computed<Record<string, unknown>[]>(() => {
    const status = this.statusFilter();
    const rows =
      status === 'all'
        ? this.items()
        : this.items().filter((item) => item.is_active === (status === 'active'));
    return rows as unknown as Record<string, unknown>[];
  });

  private readonly codeTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('codeCell');
  private readonly statusTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('statusCell');

  /** Columnas de la tabla (reactivas al idioma y a las plantillas de celda). */
  protected readonly columns = computed<DataTableColumn[]>(() => [
    { key: 'name', label: this.text.thName(), sortable: true },
    { key: 'code', label: this.text.thCode(), cellTemplate: this.codeTpl(), sortable: true },
    {
      key: 'is_active',
      label: this.text.thStatus(),
      badge: true,
      cellTemplate: this.statusTpl(),
    },
  ]);

  protected readonly showForm = signal(false);
  protected readonly editing = signal<Dependency | null>(null);
  protected readonly deleting = signal<Dependency | null>(null);
  /** Fila en eliminación: deshabilita sus acciones y muestra «Eliminando…». */
  protected readonly deletingId = signal<string | null>(null);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);

  /** Mensaje del diálogo de confirmación: «¿Confirmas que deseas eliminar {nombre}? …». */
  protected readonly deleteMessage = computed(
    () =>
      `${this.text.deleteConfirmPrefix()} ${this.deleting()?.name ?? ''}${this.text.deleteConfirmSuffix()}`,
  );

  protected readonly form = this.fb.nonNullable.group({
    name: ['', [Validators.required]],
    code: [''],
    is_active: [true],
  });

  ngOnInit(): void {
    this.load();
  }

  protected showError(control: 'name'): boolean {
    const c = this.form.controls[control];
    return c.invalid && (c.touched || c.dirty);
  }

  protected clearFilters(): void {
    this.statusControl.setValue('all');
  }

  protected openCreate(): void {
    this.editing.set(null);
    this.formError.set(null);
    this.form.reset({ name: '', code: '', is_active: true });
    this.showForm.set(true);
  }

  protected openEdit(item: Dependency): void {
    this.editing.set(item);
    this.formError.set(null);
    this.form.reset({
      name: item.name,
      code: item.code ?? '',
      is_active: item.is_active,
    });
    this.showForm.set(true);
  }

  protected closeForm(): void {
    this.showForm.set(false);
    this.editing.set(null);
  }

  protected onSubmit(): void {
    if (this.saving()) {
      return;
    }
    this.formError.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const raw = this.form.getRawValue();
    const payload = {
      name: raw.name.trim(),
      code: raw.code.trim() || null,
      is_active: raw.is_active,
    };
    this.saving.set(true);

    const editing = this.editing();
    const request$ = editing
      ? this.service.update(editing.id, payload)
      : this.service.create(payload);

    request$.subscribe({
      next: () => {
        this.saving.set(false);
        this.closeForm();
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        this.saving.set(false);
        this.formError.set(this.messageFor(err));
      },
    });
  }

  protected askDelete(item: Dependency): void {
    this.deleting.set(item);
  }

  protected cancelDelete(): void {
    this.deleting.set(null);
  }

  /** El diálogo se cierra al confirmar; si la eliminación falla, el motivo llega por alerta. */
  protected confirmDelete(): void {
    const item = this.deleting();
    if (!item || this.deletingId()) {
      return;
    }
    this.deleting.set(null);
    this.deletingId.set(item.id);
    this.service.remove(item.id).subscribe({
      next: () => {
        this.deletingId.set(null);
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        this.deletingId.set(null);
        this.alert.showError(this.messageFor(err));
      },
    });
  }

  protected load(): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.service.list().subscribe({
      next: (res) => {
        this.items.set(res.data ?? []);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.loadError.set(
          err.status === 0
            ? this.i18n.translate('admin.dependencies.errors.network')
            : this.i18n.translate('admin.dependencies.errors.loadFailed'),
        );
      },
    });
  }

  private messageFor(err: HttpErrorResponse): string {
    if (err.status === 0) {
      return this.i18n.translate('admin.dependencies.errors.network');
    }
    const detail = (err.error as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    return this.i18n.translate('admin.dependencies.errors.saveFailed');
  }
}
