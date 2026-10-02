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
import { HttpErrorResponse } from '@angular/common/http';
import {
  FormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import {
  SolButtonComponent,
  SolInputComponent,
  SolPageHeaderComponent,
  SolBadgeComponent,
  SolIconButtonComponent,
  SolModalComponent,
  SolConfirmDialogComponent,
  SolDataTableComponent,
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

@Component({
  selector: 'sol-admin-roles',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    SolButtonComponent,
    SolInputComponent,
    SolPageHeaderComponent,
    SolBadgeComponent,
    SolIconButtonComponent,
    SolModalComponent,
    SolConfirmDialogComponent,
    SolDataTableComponent,
  ],
  template: `
    <section class="flex flex-col gap-6">
      <sol-page-header
        [title]="text.title()"
        [subtitle]="text.subtitle()"
      >
        <sol-button
          type="button"
          variant="primary"
          (click)="openCreate()"
          [ariaLabel]="text.actions.createAria()"
        >
          {{ text.actions.create() }}
        </sol-button>
      </sol-page-header>

      @if (loading()) {
        <p class="text-sm text-muted">{{ text.loading() }}</p>
      } @else if (loadError()) {
        <div
          role="alert"
          class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {{ loadError() }}
        </div>
      } @else if (items().length === 0) {
        <div class="rounded-xl border border-border bg-surface p-8 text-center">
          <p class="text-base font-medium text-text">{{ text.empty.title() }}</p>
          <p class="mt-1 text-sm text-muted">
            {{ text.empty.subtitle() }}
          </p>
        </div>
      } @else {
        <sol-data-table
          [data]="tableData()"
          [columns]="columns()"
          [showToolbar]="false"
          [paginated]="false"
          [actionsLabel]="text.table.actions()"
        >
          <ng-template #rowActions let-row>
            <div class="flex items-center justify-end gap-2">
              <sol-icon-button
                icon="link"
                [ariaLabel]="text.actions.menusAria()"
                (clicked)="openMenus($any(row))"
              />
              <sol-icon-button
                icon="edit"
                [ariaLabel]="text.actions.editAria()"
                (clicked)="openEdit($any(row))"
              />
              <sol-icon-button
                icon="trash"
                variant="danger"
                [ariaLabel]="text.actions.deleteAria()"
                (clicked)="askDelete($any(row))"
              />
            </div>
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

    @if (showForm()) {
      <sol-modal [open]="true"
        [title]="editing() ? text.form.editTitle() : text.form.createTitle()"
        (closed)="closeForm()"
      >
        <form
          [formGroup]="form"
          (ngSubmit)="onSubmit()"
          class="flex flex-col gap-4"
          novalidate
        >
          <div>
            <sol-input
              [label]="text.form.code()"
              [placeholder]="text.form.codePlaceholder()"
              formControlName="code"
            ></sol-input>
            @if (showError('code')) {
              <p class="mt-1 text-xs text-danger">{{ text.form.errors.codeRequired() }}</p>
            }
          </div>

          <div>
            <sol-input
              [label]="text.form.name()"
              [placeholder]="text.form.namePlaceholder()"
              formControlName="name"
            ></sol-input>
            @if (showError('name')) {
              <p class="mt-1 text-xs text-danger">{{ text.form.errors.nameRequired() }}</p>
            }
          </div>

          <label class="flex items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              formControlName="is_active"
              class="h-4 w-4 rounded border-border text-brand focus:ring-brand/40"
            />
            {{ text.form.active() }}
          </label>

          @if (formError()) {
            <div
              role="alert"
              class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
            >
              {{ formError() }}
            </div>
          }

          <div class="flex items-center justify-end gap-2">
            <sol-button type="button" variant="ghost" (click)="closeForm()">
              {{ text.actions.cancel() }}
            </sol-button>
            <sol-button type="submit" variant="primary" [disabled]="saving()">
              {{ saving() ? text.actions.saving() : text.actions.save() }}
            </sol-button>
          </div>
        </form>
      </sol-modal>
    }

    @if (menusFor()) {
      <sol-modal [open]="true"
        size="lg"
        [title]="menusTitle()"
        (closed)="closeMenus()"
      >
        @if (menusLoading()) {
          <p class="text-sm text-muted">{{ text.menus.loading() }}</p>
        } @else {
          <p class="mb-3 text-sm text-muted">
            {{ text.menus.hint() }}
          </p>
          <div class="flex flex-col gap-1">
            @for (row of menuRows(); track row.menu.id) {
              <label
                class="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-text hover:bg-muted/10"
                [style.padding-left.px]="8 + row.depth * 20"
              >
                <input
                  type="checkbox"
                  [checked]="selectedMenuIds().has(row.menu.id)"
                  (change)="toggleMenu(row.menu.id)"
                  class="h-4 w-4 rounded border-border text-brand focus:ring-brand/40"
                />
                <span>{{ row.menu.name }}</span>
                @if (row.menu.path) {
                  <span class="text-xs text-muted">{{ row.menu.path }}</span>
                }
              </label>
            }
          </div>
        }

        @if (formError()) {
          <div
            role="alert"
            class="mt-3 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {{ formError() }}
          </div>
        }

        <div class="mt-5 flex items-center justify-end gap-2">
          <sol-button type="button" variant="ghost" (click)="closeMenus()">
            {{ text.actions.cancel() }}
          </sol-button>
          <sol-button
            type="button"
            variant="primary"
            [disabled]="saving() || menusLoading()"
            (click)="saveMenus()"
          >
            {{ saving() ? text.actions.saving() : text.menus.save() }}
          </sol-button>
        </div>
      </sol-modal>
    }

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
    },
    status: {
      active: this.i18n.t('admin.roles.status.active'),
      inactive: this.i18n.t('admin.roles.status.inactive'),
    },
    empty: {
      title: this.i18n.t('admin.roles.empty.title'),
      subtitle: this.i18n.t('admin.roles.empty.subtitle'),
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
  } as const;

  protected readonly items = signal<Role[]>([]);
  protected readonly loading = signal(false);
  protected readonly loadError = signal<string | null>(null);

  /** Filas para `sol-data-table` (contrato genérico `Record<string, unknown>`). */
  protected readonly tableData = computed<Record<string, unknown>[]>(
    () => this.items() as unknown as Record<string, unknown>[],
  );

  private readonly codeTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('codeCell');
  private readonly statusTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('statusCell');

  /** Columnas de la tabla (reactivas al idioma y a las plantillas de celda). */
  protected readonly columns = computed<DataTableColumn[]>(() => [
    { key: 'code', label: this.text.table.code(), cellTemplate: this.codeTpl() },
    { key: 'name', label: this.text.table.name() },
    { key: 'is_active', label: this.text.table.status(), cellTemplate: this.statusTpl() },
  ]);

  protected readonly showForm = signal(false);
  protected readonly editing = signal<Role | null>(null);
  protected readonly deleting = signal<Role | null>(null);
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
    if (!item || this.saving()) {
      return;
    }
    this.deleting.set(null);
    this.saving.set(true);
    this.service.remove(item.id).subscribe({
      next: () => {
        this.saving.set(false);
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        this.saving.set(false);
        this.alert.showError(this.messageFor(err));
      },
    });
  }

  private load(): void {
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
