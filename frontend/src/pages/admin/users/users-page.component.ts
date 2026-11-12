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
import { switchMap } from 'rxjs';
import {
  SolButtonComponent,
  SolInputComponent,
  SolBadgeComponent,
  SolIconButtonComponent,
  SolDrawerComponent,
  SolConfirmDialogComponent,
  SolSelectComponent,
  SolSelectOption,
  SolDataTableComponent,
  SolEmptyStateComponent,
  SolFormFieldComponent,
  SolSpinnerComponent,
  DataTableColumn,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { AlertService } from '@shared/lib/alerts';
import { UsersService } from '@entities/user/users.service';
import { AdminUser } from '@entities/user/user-admin.model';
import { DependenciesService } from '@entities/dependency/dependencies.service';
import { Dependency } from '@entities/dependency/dependency.model';
import { RolesService } from '@entities/role/roles.service';
import { Role } from '@entities/role/role.model';

/** Valor centinela de los filtros: «todos». `none` = sin dependencia. */
const ALL = 'all';
const NONE = 'none';

/**
 * `/admin/users` con el patrón de PANDORA (`gestion-usuarios-page` + `usuario-form-modal`):
 * encabezado `h1.sol-display`, tabla paginada con buscador, acciones al inicio y filtros de
 * estado, rol y dependencia con valores reales; crear/editar en `sol-drawer` lateral.
 */
@Component({
  selector: 'sol-admin-users',
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
    SolSelectComponent,
    SolDataTableComponent,
    SolEmptyStateComponent,
    SolFormFieldComponent,
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
          icon="users"
          titleKey="admin.users.empty.title"
          descriptionKey="admin.users.empty.subtitle"
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
            activeFilterCount() > 0 ? text.common.noFilterMatches() : text.common.noSearchMatches()
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
            @if (roles().length > 0) {
              <sol-select
                class="adm-filter"
                [label]="text.common.role()"
                [options]="roleFilterOptions()"
                [searchable]="roles().length > 7"
                [formControl]="roleControl"
              />
            }
            @if (dependencies().length > 0) {
              <sol-select
                class="adm-filter"
                [label]="text.common.dependency()"
                [options]="dependencyFilterOptions()"
                [searchable]="dependencies().length > 7"
                [formControl]="dependencyControl"
              />
            }
            @if (activeFilterCount() > 0) {
              <sol-button type="button" variant="ghost" size="sm" (clicked)="clearFilters()">
                {{ text.common.clearFilters() }}
              </sol-button>
            }
          </div>
          <ng-template #rowActions let-row>
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

    <ng-template #rolesCell let-row="row">
      <div class="flex flex-wrap gap-1">
        @for (role of $any(row).roles ?? []; track role.id) {
          <sol-badge variant="info">{{ role.name }}</sol-badge>
        } @empty {
          <span class="text-xs text-muted">{{ text.noRoles() }}</span>
        }
      </div>
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
      size="lg"
      (closed)="closeForm()"
    >
      <form [formGroup]="form" (ngSubmit)="onSubmit()" class="adm-form adm-form--two" novalidate>
        <sol-input
          [label]="text.form.firstName()"
          [placeholder]="text.form.firstNamePlaceholder()"
          [error]="showError('primer_nombre') ? text.form.errors.firstNameRequired() : ''"
          formControlName="primer_nombre"
        />
        <sol-input
          [label]="text.form.secondName()"
          [placeholder]="text.form.secondNamePlaceholder()"
          formControlName="segundo_nombre"
        />
        <sol-input
          [label]="text.form.firstLastName()"
          [placeholder]="text.form.firstLastNamePlaceholder()"
          [error]="showError('primer_apellido') ? text.form.errors.firstLastNameRequired() : ''"
          formControlName="primer_apellido"
        />
        <sol-input
          [label]="text.form.secondLastName()"
          [placeholder]="text.form.secondLastNamePlaceholder()"
          formControlName="segundo_apellido"
        />
        <sol-input
          class="adm-form__full"
          [label]="text.form.email()"
          type="email"
          [placeholder]="text.form.emailPlaceholder()"
          autocomplete="email"
          [error]="showError('email') ? emailError() : ''"
          formControlName="email"
        />
        @if (!editing()) {
          <sol-input
            class="adm-form__full"
            [label]="text.form.password()"
            type="password"
            [placeholder]="text.form.passwordPlaceholder()"
            autocomplete="new-password"
            [error]="showError('password') ? text.form.errors.passwordMinLength() : ''"
            formControlName="password"
          />
        }
        <sol-select
          class="adm-form__full"
          [label]="text.form.dependency()"
          [placeholder]="text.form.noDependency()"
          [options]="dependencyFormOptions()"
          [searchable]="dependencies().length > 7"
          formControlName="dependency_id"
        />
        <div class="adm-form__full">
          @if (roles().length === 0) {
            <sol-form-field [label]="text.form.roles()" [hint]="text.form.noRolesHint()" />
          } @else {
            <sol-select
              [label]="text.form.roles()"
              [multiple]="true"
              [options]="roleOptions()"
              [placeholder]="text.form.rolesPlaceholder()"
              formControlName="role_ids"
            />
          }
        </div>
        <label class="adm-check adm-form__full">
          <input type="checkbox" formControlName="is_active" />
          {{ text.form.active() }}
        </label>

        @if (formError(); as message) {
          <div class="adm-alert adm-form__full" role="alert">{{ message }}</div>
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
export class UsersPageComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(UsersService);
  private readonly dependenciesService = inject(DependenciesService);
  private readonly rolesService = inject(RolesService);
  private readonly i18n = inject(I18nService);
  private readonly alert = inject(AlertService);

  /** Textos de la vista resueltos por i18n (reactivos al cambio de idioma). */
  protected readonly text = {
    title: this.i18n.t('admin.users.title'),
    subtitle: this.i18n.t('admin.users.subtitle'),
    loading: this.i18n.t('admin.users.loading'),
    noRoles: this.i18n.t('admin.users.noRoles'),
    actions: {
      create: this.i18n.t('admin.users.actions.create'),
      createAria: this.i18n.t('admin.users.actions.createAria'),
      editAria: this.i18n.t('admin.users.actions.editAria'),
      deleteAria: this.i18n.t('admin.users.actions.deleteAria'),
      cancel: this.i18n.t('admin.users.actions.cancel'),
      save: this.i18n.t('admin.users.actions.save'),
      saving: this.i18n.t('admin.users.actions.saving'),
      delete: this.i18n.t('admin.users.actions.delete'),
      deleting: this.i18n.t('admin.users.actions.deleting'),
    },
    status: {
      active: this.i18n.t('admin.users.status.active'),
      inactive: this.i18n.t('admin.users.status.inactive'),
    },
    table: {
      name: this.i18n.t('admin.users.table.name'),
      email: this.i18n.t('admin.users.table.email'),
      dependency: this.i18n.t('admin.users.table.dependency'),
      roles: this.i18n.t('admin.users.table.roles'),
      status: this.i18n.t('admin.users.table.status'),
      actions: this.i18n.t('admin.users.table.actions'),
    },
    form: {
      createTitle: this.i18n.t('admin.users.form.createTitle'),
      editTitle: this.i18n.t('admin.users.form.editTitle'),
      firstName: this.i18n.t('admin.users.form.firstName'),
      firstNamePlaceholder: this.i18n.t('admin.users.form.firstNamePlaceholder'),
      secondName: this.i18n.t('admin.users.form.secondName'),
      secondNamePlaceholder: this.i18n.t('admin.users.form.secondNamePlaceholder'),
      firstLastName: this.i18n.t('admin.users.form.firstLastName'),
      firstLastNamePlaceholder: this.i18n.t('admin.users.form.firstLastNamePlaceholder'),
      secondLastName: this.i18n.t('admin.users.form.secondLastName'),
      secondLastNamePlaceholder: this.i18n.t('admin.users.form.secondLastNamePlaceholder'),
      email: this.i18n.t('admin.users.form.email'),
      emailPlaceholder: this.i18n.t('admin.users.form.emailPlaceholder'),
      password: this.i18n.t('admin.users.form.password'),
      passwordPlaceholder: this.i18n.t('admin.users.form.passwordPlaceholder'),
      dependency: this.i18n.t('admin.users.form.dependency'),
      noDependency: this.i18n.t('admin.users.form.noDependency'),
      roles: this.i18n.t('admin.users.form.roles'),
      noRolesHint: this.i18n.t('admin.users.form.noRolesHint'),
      rolesPlaceholder: this.i18n.t('admin.users.form.rolesPlaceholder'),
      active: this.i18n.t('admin.users.form.active'),
      errors: {
        firstNameRequired: this.i18n.t('admin.users.form.errors.firstNameRequired'),
        firstLastNameRequired: this.i18n.t('admin.users.form.errors.firstLastNameRequired'),
        passwordMinLength: this.i18n.t('admin.users.form.errors.passwordMinLength'),
      },
    },
    delete: {
      title: this.i18n.t('admin.users.delete.title'),
      confirmLead: this.i18n.t('admin.users.delete.confirmLead'),
      confirmTail: this.i18n.t('admin.users.delete.confirmTail'),
    },
    common: {
      retry: this.i18n.t('admin.common.retry'),
      search: this.i18n.t('admin.common.searchPlaceholder'),
      noSearchMatches: this.i18n.t('admin.common.noSearchMatches'),
      noFilterMatches: this.i18n.t('admin.common.noFilterMatches'),
      clearFilters: this.i18n.t('admin.common.clearFilters'),
      status: this.i18n.t('admin.common.filters.status'),
      allStatuses: this.i18n.t('admin.common.filters.allStatuses'),
      role: this.i18n.t('admin.common.filters.role'),
      allRoles: this.i18n.t('admin.common.filters.allRoles'),
      dependency: this.i18n.t('admin.common.filters.dependency'),
      allDependencies: this.i18n.t('admin.common.filters.allDependencies'),
    },
  } as const;

  protected readonly items = signal<AdminUser[]>([]);
  protected readonly dependencies = signal<Dependency[]>([]);
  protected readonly roles = signal<Role[]>([]);
  protected readonly roleOptions = computed(() =>
    this.roles().map((r) => ({
      value: r.id,
      label: r.code ? `${r.name} · ${r.code}` : r.name,
    })),
  );
  protected readonly loading = signal(false);
  protected readonly loadError = signal<string | null>(null);

  // --- Filtros (valores reales: roles y dependencias de la organización) ---
  protected readonly statusControl = new FormControl(ALL, { nonNullable: true });
  protected readonly roleControl = new FormControl(ALL, { nonNullable: true });
  protected readonly dependencyControl = new FormControl(ALL, { nonNullable: true });
  private readonly statusFilter = toSignal(this.statusControl.valueChanges, {
    initialValue: ALL,
  });
  private readonly roleFilter = toSignal(this.roleControl.valueChanges, { initialValue: ALL });
  private readonly dependencyFilter = toSignal(this.dependencyControl.valueChanges, {
    initialValue: ALL,
  });

  protected readonly activeFilterCount = computed(
    () =>
      [this.statusFilter(), this.roleFilter(), this.dependencyFilter()].filter((v) => v !== ALL)
        .length,
  );

  protected readonly statusOptions = computed<SolSelectOption[]>(() => [
    { value: ALL, label: this.text.common.allStatuses() },
    { value: 'active', label: this.text.status.active() },
    { value: 'inactive', label: this.text.status.inactive() },
  ]);
  protected readonly roleFilterOptions = computed<SolSelectOption[]>(() => [
    { value: ALL, label: this.text.common.allRoles() },
    ...this.roles().map((r) => ({ value: r.id, label: r.name })),
  ]);
  protected readonly dependencyFilterOptions = computed<SolSelectOption[]>(() => [
    { value: ALL, label: this.text.common.allDependencies() },
    { value: NONE, label: this.text.form.noDependency() },
    ...this.dependencies().map((d) => ({ value: d.id, label: d.name })),
  ]);
  /** Opciones del formulario: «Sin dependencia» envía `null`, como antes. */
  protected readonly dependencyFormOptions = computed<SolSelectOption[]>(() => [
    { value: '', label: this.text.form.noDependency() },
    ...this.dependencies().map((d) => ({ value: d.id, label: d.name })),
  ]);

  /**
   * Filas para `sol-data-table`, filtradas y con `dependency_name`/`role_names` derivados para
   * que el buscador y el orden de la tabla trabajen sobre el texto visible (no sobre ids).
   */
  protected readonly tableData = computed<Record<string, unknown>[]>(() => {
    const status = this.statusFilter();
    const role = this.roleFilter();
    const dependency = this.dependencyFilter();
    const names = new Map(this.dependencies().map((d) => [d.id, d.name]));
    return this.items()
      .filter((u) => status === ALL || u.is_active === (status === 'active'))
      .filter((u) => role === ALL || (u.roles ?? []).some((r) => r.id === role))
      .filter(
        (u) =>
          dependency === ALL ||
          (dependency === NONE ? !u.dependency_id : u.dependency_id === dependency),
      )
      .map((u) => ({
        ...u,
        dependency_name: (u.dependency_id && names.get(u.dependency_id)) || '—',
        role_names: (u.roles ?? []).map((r) => r.name).join(', '),
      }));
  });

  private readonly rolesTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('rolesCell');
  private readonly statusTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('statusCell');

  /** Columnas de la tabla (reactivas al idioma y a las plantillas de celda). */
  protected readonly columns = computed<DataTableColumn[]>(() => [
    { key: 'full_name', label: this.text.table.name(), sortable: true },
    { key: 'email', label: this.text.table.email(), sortable: true },
    { key: 'dependency_name', label: this.text.table.dependency(), sortable: true },
    { key: 'role_names', label: this.text.table.roles(), cellTemplate: this.rolesTpl() },
    {
      key: 'is_active',
      label: this.text.table.status(),
      badge: true,
      cellTemplate: this.statusTpl(),
    },
  ]);

  protected readonly showForm = signal(false);
  protected readonly editing = signal<AdminUser | null>(null);
  protected readonly deleting = signal<AdminUser | null>(null);
  /** Fila en eliminación: deshabilita sus acciones y muestra «Eliminando…». */
  protected readonly deletingId = signal<string | null>(null);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);

  /** Mensaje del diálogo de confirmación: «¿Confirmas que deseas eliminar a {nombre}? …». */
  protected readonly deleteMessage = computed(
    () =>
      `${this.text.delete.confirmLead()} ${this.deleting()?.full_name ?? ''}${this.text.delete.confirmTail()}`,
  );

  protected readonly form = this.fb.nonNullable.group({
    primer_nombre: ['', [Validators.required]],
    segundo_nombre: [''],
    primer_apellido: ['', [Validators.required]],
    segundo_apellido: [''],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(8)]],
    dependency_id: [''],
    is_active: [true],
    role_ids: [[] as string[]],
  });

  ngOnInit(): void {
    this.loadReferenceData();
    this.load();
  }

  protected showError(
    control: 'primer_nombre' | 'primer_apellido' | 'email' | 'password',
  ): boolean {
    const c = this.form.controls[control];
    return c.invalid && (c.touched || c.dirty);
  }

  protected emailError(): string {
    const c = this.form.controls.email;
    if (c.hasError('required')) {
      return this.i18n.translate('admin.users.form.errors.emailRequired');
    }
    if (c.hasError('email')) {
      return this.i18n.translate('admin.users.form.errors.emailInvalid');
    }
    return '';
  }

  protected clearFilters(): void {
    this.statusControl.setValue(ALL);
    this.roleControl.setValue(ALL);
    this.dependencyControl.setValue(ALL);
  }

  protected openCreate(): void {
    this.editing.set(null);
    this.formError.set(null);
    this.setPasswordRequired(true);
    this.form.reset({
      primer_nombre: '',
      segundo_nombre: '',
      primer_apellido: '',
      segundo_apellido: '',
      email: '',
      password: '',
      dependency_id: '',
      is_active: true,
      role_ids: [],
    });
    this.showForm.set(true);
  }

  protected openEdit(item: AdminUser): void {
    this.editing.set(item);
    this.formError.set(null);
    this.setPasswordRequired(false);
    this.form.reset({
      primer_nombre: item.primer_nombre,
      segundo_nombre: item.segundo_nombre ?? '',
      primer_apellido: item.primer_apellido,
      segundo_apellido: item.segundo_apellido ?? '',
      email: item.email,
      password: '',
      dependency_id: item.dependency_id ?? '',
      is_active: item.is_active,
      role_ids: (item.roles ?? []).map((r) => r.id),
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
    const roleIds = raw.role_ids;
    this.saving.set(true);

    const editing = this.editing();
    if (editing) {
      // Update the profile, then replace the role set.
      this.service
        .update(editing.id, {
          primer_nombre: raw.primer_nombre.trim(),
          segundo_nombre: raw.segundo_nombre.trim() || null,
          primer_apellido: raw.primer_apellido.trim(),
          segundo_apellido: raw.segundo_apellido.trim() || null,
          email: raw.email.trim(),
          dependency_id: raw.dependency_id || null,
          is_active: raw.is_active,
        })
        .pipe(switchMap(() => this.service.setRoles(editing.id, { role_ids: roleIds })))
        .subscribe({
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
      return;
    }

    this.service
      .create({
        primer_nombre: raw.primer_nombre.trim(),
        segundo_nombre: raw.segundo_nombre.trim() || null,
        primer_apellido: raw.primer_apellido.trim(),
        segundo_apellido: raw.segundo_apellido.trim() || null,
        email: raw.email.trim(),
        password: raw.password,
        dependency_id: raw.dependency_id || null,
        is_active: raw.is_active,
        role_ids: roleIds,
      })
      .subscribe({
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

  protected askDelete(item: AdminUser): void {
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

  private setPasswordRequired(required: boolean): void {
    const control = this.form.controls.password;
    control.setValidators(required ? [Validators.required, Validators.minLength(8)] : []);
    control.updateValueAndValidity();
  }

  private loadReferenceData(): void {
    this.dependenciesService.list().subscribe({
      next: (res) => this.dependencies.set(res.data ?? []),
      error: () => this.dependencies.set([]),
    });
    this.rolesService.list().subscribe({
      next: (res) => this.roles.set(res.data ?? []),
      error: () => this.roles.set([]),
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
            ? this.i18n.translate('admin.users.errors.network')
            : this.i18n.translate('admin.users.errors.loadFailed'),
        );
      },
    });
  }

  private messageFor(err: HttpErrorResponse): string {
    if (err.status === 0) {
      return this.i18n.translate('admin.users.errors.network');
    }
    const detail = (err.error as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    return this.i18n.translate('admin.users.errors.generic');
  }
}
