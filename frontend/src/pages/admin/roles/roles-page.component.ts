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
  SolFormFieldComponent,
  SolSelectComponent,
  SolSelectOption,
  SolSpinnerComponent,
  DataTableColumn,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { AlertService } from '@shared/lib/alerts';
import { RolesService } from '@entities/role/roles.service';
import { Role } from '@entities/role/role.model';
import { MenusService } from '@entities/menu/menus.service';
import {
  AdminMenu,
  buildMenuTree,
  flattenMenuTree,
} from '@entities/menu/menu-admin.model';

type StatusFilter = 'all' | 'active' | 'inactive';

/**
 * `/admin/roles` con el patrón de listado de PANDORA: encabezado `h1.sol-display`, tabla
 * paginada con buscador, acciones al inicio y filtro de estado; crear/editar y la asociación de
 * actividades en `sol-drawer` lateral.
 */
@Component({
  selector: 'sol-admin-roles',
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
    SolFormFieldComponent,
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
          [ariaLabel]="text.actions.createAria()"
          (clicked)="openCreate()"
        >
          {{ text.actions.create() }}
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
            {{ text.common.retry() }}
          </sol-button>
        </div>
      } @else if (items().length === 0) {
        <sol-empty-state
          icon="shield"
          titleKey="admin.roles.empty.title"
          descriptionKey="admin.roles.empty.subtitle"
        />
      } @else {
        @if (deletingId()) {
          <p class="adm-busy" role="status">{{ text.actions.deleting() }}</p>
        }
        <sol-data-table
          [data]="tableData()"
          [columns]="columns()"
          [searchPlaceholder]="text.common.search()"
          [emptyMessage]="
            statusFilter() === 'all' ? text.common.noSearchMatches() : text.common.noFilterMatches()
          "
          [paginated]="true"
          [showActions]="true"
          [actionsLabel]="text.table.actions()"
          actionsPosition="start"
          [collapseWidth]="760"
          trackByKey="id"
        >
          <div tableActions class="adm-filters">
            <sol-select
              class="adm-filter"
              [label]="text.common.status()"
              [options]="statusOptions()"
              [formControl]="statusControl"
            />
            @if (statusFilter() !== 'all') {
              <sol-button type="button" variant="ghost" size="sm" (clicked)="clearFilters()">
                {{ text.common.clearFilters() }}
              </sol-button>
            }
          </div>
          <ng-template #rowActions let-row>
            <sol-icon-button
              icon="link"
              variant="outline"
              [ariaLabel]="text.actions.menusAria()"
              [disabled]="deletingId() === row['id']"
              (clicked)="openMenus($any(row))"
            />
            <sol-icon-button
              icon="edit"
              variant="outline"
              [ariaLabel]="text.actions.editAria()"
              [disabled]="deletingId() === row['id']"
              (clicked)="openEdit($any(row))"
            />
            <sol-icon-button
              icon="trash"
              variant="danger"
              [ariaLabel]="text.actions.deleteAria()"
              [disabled]="deletingId() === row['id']"
              (clicked)="askDelete($any(row))"
            />
          </ng-template>
        </sol-data-table>
      }
    </section>

    <ng-template #codeCell let-value>
      <sol-badge variant="info">{{ $any(value) }}</sol-badge>
    </ng-template>
    <ng-template #statusCell let-row="row">
      @if ($any(row).is_active) {
        <sol-badge variant="success">{{ text.status.active() }}</sol-badge>
      } @else {
        <sol-badge variant="neutral">{{ text.status.inactive() }}</sol-badge>
      }
    </ng-template>

    <sol-drawer
      [open]="showForm()"
      [title]="editing() ? text.form.editTitle() : text.form.createTitle()"
      side="end"
      size="md"
      (closed)="closeForm()"
    >
      <form [formGroup]="form" (ngSubmit)="onSubmit()" class="adm-form" novalidate>
        <sol-input
          [label]="text.form.code()"
          [placeholder]="text.form.codePlaceholder()"
          [error]="showError('code') ? text.form.errors.codeRequired() : ''"
          formControlName="code"
        />
        <sol-input
          [label]="text.form.name()"
          [placeholder]="text.form.namePlaceholder()"
          [error]="showError('name') ? text.form.errors.nameRequired() : ''"
          formControlName="name"
        />
        <label class="adm-check">
          <input type="checkbox" formControlName="is_active" />
          {{ text.form.active() }}
        </label>

        @if (formError(); as message) {
          <div class="adm-alert" role="alert">{{ message }}</div>
        }
        <button type="submit" class="adm-submit" tabindex="-1" aria-hidden="true"></button>
      </form>

      <div drawerFooter class="adm-footer">
        <sol-button type="button" variant="secondary" (clicked)="closeForm()">
          {{ text.actions.cancel() }}
        </sol-button>
        <sol-button
          type="button"
          variant="primary"
          [disabled]="saving()"
          [loading]="saving()"
          (clicked)="onSubmit()"
        >
          {{ saving() ? text.actions.saving() : text.actions.save() }}
        </sol-button>
      </div>
    </sol-drawer>

    <sol-drawer
      [open]="menusFor() !== null"
      [title]="menusTitle()"
      side="end"
      size="md"
      (closed)="closeMenus()"
    >
      @if (menusLoading()) {
        <div class="adm-state" role="status" aria-live="polite">
          <sol-spinner />
          <p>{{ text.menus.loading() }}</p>
        </div>
      } @else {
        <sol-form-field [label]="text.menus.hint()">
          <div class="flex flex-col gap-1" role="group" [attr.aria-label]="text.menus.hint()">
            @for (row of menuRows(); track row.menu.id) {
              <label class="adm-check" [style.padding-left.px]="row.depth * 20">
                <input
                  type="checkbox"
                  [checked]="selectedMenuIds().has(row.menu.id)"
                  (change)="toggleMenu(row.menu.id)"
                />
                <span>{{ row.menu.name }}</span>
                @if (row.menu.path) {
                  <span class="adm-hint">{{ row.menu.path }}</span>
                }
              </label>
            }
          </div>
        </sol-form-field>
      }

      @if (formError(); as message) {
        <div class="adm-alert" role="alert">{{ message }}</div>
      }

      <div drawerFooter class="adm-footer">
        <sol-button type="button" variant="secondary" (clicked)="closeMenus()">
          {{ text.actions.cancel() }}
        </sol-button>
        <sol-button
          type="button"
          variant="primary"
          [disabled]="saving() || menusLoading()"
          [loading]="saving()"
          (clicked)="saveMenus()"
        >
          {{ saving() ? text.actions.saving() : text.menus.save() }}
        </sol-button>
      </div>
    </sol-drawer>

    <sol-confirm-dialog
      [open]="deleting() !== null"
      variant="danger"
      [title]="text.delete.title()"
      [message]="deleteMessage()"
      [confirmLabel]="text.actions.delete()"
      [cancelLabel]="text.actions.cancel()"
      (confirm)="confirmDelete()"
      (cancel)="cancelDelete()"
    />
  `,
})
export class RolesPageComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(RolesService);
  private readonly menusService = inject(MenusService);
  private readonly i18n = inject(I18nService);
  private readonly alert = inject(AlertService);

  /** Textos de la vista resueltos por i18n (reactivos al cambio de idioma). */
  protected readonly text = {
    title: this.i18n.t('admin.roles.title'),
    subtitle: this.i18n.t('admin.roles.subtitle'),
    loading: this.i18n.t('admin.roles.loading'),
    actions: {
      create: this.i18n.t('admin.roles.actions.create'),
      createAria: this.i18n.t('admin.roles.actions.createAria'),
      menusAria: this.i18n.t('admin.roles.actions.menusAria'),
      editAria: this.i18n.t('admin.roles.actions.editAria'),
      deleteAria: this.i18n.t('admin.roles.actions.deleteAria'),
      cancel: this.i18n.t('admin.roles.actions.cancel'),
      save: this.i18n.t('admin.roles.actions.save'),
      saving: this.i18n.t('admin.roles.actions.saving'),
      delete: this.i18n.t('admin.roles.actions.delete'),
      deleting: this.i18n.t('admin.roles.actions.deleting'),
    },
    status: {
      active: this.i18n.t('admin.roles.status.active'),
      inactive: this.i18n.t('admin.roles.status.inactive'),
    },
    table: {
      code: this.i18n.t('admin.roles.table.code'),
      name: this.i18n.t('admin.roles.table.name'),
      status: this.i18n.t('admin.roles.table.status'),
      actions: this.i18n.t('admin.roles.table.actions'),
    },
    form: {
      createTitle: this.i18n.t('admin.roles.form.createTitle'),
      editTitle: this.i18n.t('admin.roles.form.editTitle'),
      code: this.i18n.t('admin.roles.form.code'),
      codePlaceholder: this.i18n.t('admin.roles.form.codePlaceholder'),
      name: this.i18n.t('admin.roles.form.name'),
      namePlaceholder: this.i18n.t('admin.roles.form.namePlaceholder'),
      active: this.i18n.t('admin.roles.form.active'),
      errors: {
        codeRequired: this.i18n.t('admin.roles.form.errors.codeRequired'),
        nameRequired: this.i18n.t('admin.roles.form.errors.nameRequired'),
      },
    },
    menus: {
      loading: this.i18n.t('admin.roles.menus.loading'),
      hint: this.i18n.t('admin.roles.menus.hint'),
      save: this.i18n.t('admin.roles.menus.save'),
    },
    delete: {
      title: this.i18n.t('admin.roles.delete.title'),
      confirmLead: this.i18n.t('admin.roles.delete.confirmLead'),
      confirmTail: this.i18n.t('admin.roles.delete.confirmTail'),
    },
    common: {
      retry: this.i18n.t('admin.common.retry'),
      search: this.i18n.t('admin.common.searchPlaceholder'),
      noSearchMatches: this.i18n.t('admin.common.noSearchMatches'),
      noFilterMatches: this.i18n.t('admin.common.noFilterMatches'),
      clearFilters: this.i18n.t('admin.common.clearFilters'),
      status: this.i18n.t('admin.common.filters.status'),
      allStatuses: this.i18n.t('admin.common.filters.allStatuses'),
    },
  } as const;

  protected readonly items = signal<Role[]>([]);
  protected readonly loading = signal(false);
  protected readonly loadError = signal<string | null>(null);

  /** Filtro de estado (preseleccionado en «Todos los estados»). */
  protected readonly statusControl = new FormControl<StatusFilter>('all', { nonNullable: true });
  protected readonly statusFilter = toSignal(this.statusControl.valueChanges, {
    initialValue: this.statusControl.value,
  });
  protected readonly statusOptions = computed<SolSelectOption[]>(() => [
    { value: 'all', label: this.text.common.allStatuses() },
    { value: 'active', label: this.text.status.active() },
    { value: 'inactive', label: this.text.status.inactive() },
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
    { key: 'code', label: this.text.table.code(), cellTemplate: this.codeTpl(), sortable: true },
    { key: 'name', label: this.text.table.name(), sortable: true },
    {
      key: 'is_active',
      label: this.text.table.status(),
      badge: true,
      cellTemplate: this.statusTpl(),
    },
  ]);

  protected readonly showForm = signal(false);
  protected readonly editing = signal<Role | null>(null);
  protected readonly deleting = signal<Role | null>(null);
  /** Fila en eliminación: deshabilita sus acciones y muestra «Eliminando…». */
  protected readonly deletingId = signal<string | null>(null);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);

  /** Mensaje del diálogo de confirmación: «¿Confirmas que deseas eliminar {nombre}? …». */
  protected readonly deleteMessage = computed(
    () =>
      `${this.text.delete.confirmLead()} ${this.deleting()?.name ?? ''}${this.text.delete.confirmTail()}`,
  );

  // Menu association modal.
  protected readonly menusFor = signal<Role | null>(null);
  protected readonly menusLoading = signal(false);
  protected readonly menuRows = signal<
    Array<{ menu: AdminMenu; depth: number }>
  >([]);
  protected readonly selectedMenuIds = signal<Set<string>>(new Set());

  /** Título del modal de actividades: depende del rol activo y del idioma. */
  protected readonly menusTitle = computed(() => {
    this.i18n.activeLang();
    return this.i18n.translate('admin.roles.menus.title', {
      name: this.menusFor()?.name ?? '',
    });
  });

  protected readonly form = this.fb.nonNullable.group({
    code: ['', [Validators.required]],
    name: ['', [Validators.required]],
    is_active: [true],
  });

  ngOnInit(): void {
    this.load();
  }

  protected showError(control: 'code' | 'name'): boolean {
    const c = this.form.controls[control];
    return c.invalid && (c.touched || c.dirty);
  }

  protected clearFilters(): void {
    this.statusControl.setValue('all');
  }

  protected openCreate(): void {
    this.editing.set(null);
    this.formError.set(null);
    this.form.reset({ code: '', name: '', is_active: true });
    this.showForm.set(true);
  }

  protected openEdit(item: Role): void {
    this.editing.set(item);
    this.formError.set(null);
    this.form.reset({
      code: item.code,
      name: item.name,
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
      code: raw.code.trim(),
      name: raw.name.trim(),
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

  // --- Menu association -----------------------------------------------------

  protected openMenus(role: Role): void {
    this.menusFor.set(role);
    this.formError.set(null);
    this.menusLoading.set(true);
    this.selectedMenuIds.set(new Set(role.menu_ids ?? []));

    // Load all menus (flat -> tree) and the role's current selection.
    this.menusService.list().subscribe({
      next: (res) => {
        this.menuRows.set(flattenMenuTree(buildMenuTree(res.data ?? [])));
        this.service.get(role.id).subscribe({
          next: (detail) => {
            this.selectedMenuIds.set(new Set(detail.data.menu_ids ?? []));
            this.menusLoading.set(false);
          },
          error: () => {
            // Keep whatever the list row carried; just finish loading.
            this.menusLoading.set(false);
          },
        });
      },
      error: (err: HttpErrorResponse) => {
        this.menusLoading.set(false);
        this.formError.set(this.messageFor(err));
      },
    });
  }

  protected toggleMenu(id: string): void {
    const next = new Set(this.selectedMenuIds());
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    this.selectedMenuIds.set(next);
  }

  protected saveMenus(): void {
    const role = this.menusFor();
    if (!role) {
      return;
    }
    this.saving.set(true);
    this.formError.set(null);
    this.service
      .setMenus(role.id, { menu_ids: Array.from(this.selectedMenuIds()) })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.closeMenus();
          this.load();
        },
        error: (err: HttpErrorResponse) => {
          this.saving.set(false);
          this.formError.set(this.messageFor(err));
        },
      });
  }

  protected closeMenus(): void {
    this.menusFor.set(null);
    this.menuRows.set([]);
    this.selectedMenuIds.set(new Set());
  }

  // --- Delete ---------------------------------------------------------------

  protected askDelete(item: Role): void {
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
            ? this.i18n.translate('admin.roles.errors.network')
            : this.i18n.translate('admin.roles.errors.loadFailed'),
        );
      },
    });
  }

  private messageFor(err: HttpErrorResponse): string {
    if (err.status === 0) {
      return this.i18n.translate('admin.roles.errors.network');
    }
    const detail = (err.error as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    return this.i18n.translate('admin.roles.errors.generic');
  }
}
