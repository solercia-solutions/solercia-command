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
import { switchMap } from 'rxjs';
import {
  SolButtonComponent,
  SolInputComponent,
  SolPageHeaderComponent,
  SolBadgeComponent,
  SolIconButtonComponent,
  SolModalComponent,
  SolSelectComponent,
  SolDataTableComponent,
  DataTableColumn,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { UsersService } from '@entities/user/users.service';
import { AdminUser } from '@entities/user/user-admin.model';
import { DependenciesService } from '@entities/dependency/dependencies.service';
import { Dependency } from '@entities/dependency/dependency.model';
import { RolesService } from '@entities/role/roles.service';
import { Role } from '@entities/role/role.model';

@Component({
  selector: 'sol-admin-users',
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
    SolSelectComponent,
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

    <ng-template #dependencyCell let-row="row">
      <span class="text-muted">{{ dependencyName($any(row).dependency_id) }}</span>
    </ng-template>
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

    @if (showForm()) {
      <sol-modal [open]="true"
        size="xl"
        [title]="editing() ? text.form.editTitle() : text.form.createTitle()"
        (closed)="closeForm()"
      >
        <form
          [formGroup]="form"
          (ngSubmit)="onSubmit()"
          class="flex flex-col gap-4"
          novalidate
        >
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <sol-input
                [label]="text.form.firstName()"
                [placeholder]="text.form.firstNamePlaceholder()"
                formControlName="primer_nombre"
              ></sol-input>
              @if (showError('primer_nombre')) {
                <p class="mt-1 text-xs text-danger">
                  {{ text.form.errors.firstNameRequired() }}
                </p>
              }
            </div>
            <sol-input
              [label]="text.form.secondName()"
              [placeholder]="text.form.secondNamePlaceholder()"
              formControlName="segundo_nombre"
            ></sol-input>
            <div>
              <sol-input
                [label]="text.form.firstLastName()"
                [placeholder]="text.form.firstLastNamePlaceholder()"
                formControlName="primer_apellido"
              ></sol-input>
              @if (showError('primer_apellido')) {
                <p class="mt-1 text-xs text-danger">
                  {{ text.form.errors.firstLastNameRequired() }}
                </p>
              }
            </div>
            <sol-input
              [label]="text.form.secondLastName()"
              [placeholder]="text.form.secondLastNamePlaceholder()"
              formControlName="segundo_apellido"
            ></sol-input>
          </div>

          <div>
            <sol-input
              [label]="text.form.email()"
              type="email"
              [placeholder]="text.form.emailPlaceholder()"
              autocomplete="email"
              formControlName="email"
            ></sol-input>
            @if (showError('email')) {
              <p class="mt-1 text-xs text-danger">{{ emailError() }}</p>
            }
          </div>

          @if (!editing()) {
            <div>
              <sol-input
                [label]="text.form.password()"
                type="password"
                [placeholder]="text.form.passwordPlaceholder()"
                autocomplete="new-password"
                formControlName="password"
              ></sol-input>
              @if (showError('password')) {
                <p class="mt-1 text-xs text-danger">
                  {{ text.form.errors.passwordMinLength() }}
                </p>
              }
            </div>
          }

          <label class="block">
            <span class="mb-1.5 block text-sm font-medium text-text"
              >{{ text.form.dependency() }}</span
            >
            <select
              formControlName="dependency_id"
              class="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text
                     transition-colors focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40"
            >
              <option value="">{{ text.form.noDependency() }}</option>
              @for (dependency of dependencies(); track dependency.id) {
                <option [value]="dependency.id">{{ dependency.name }}</option>
              }
            </select>
          </label>

          <div>
            @if (roles().length === 0) {
              <span class="mb-1.5 block text-sm font-medium text-text">{{ text.form.roles() }}</span>
              <p class="text-xs text-muted">
                {{ text.form.noRolesHint() }}
              </p>
            } @else {
              <sol-select
                [label]="text.form.roles()"
                [multiple]="true"
                [options]="roleOptions()"
                [placeholder]="text.form.rolesPlaceholder()"
                formControlName="role_ids"
              ></sol-select>
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

    @if (deleting()) {
      <sol-modal [open]="true" size="sm" [title]="text.delete.title()" (closed)="cancelDelete()">
        <p class="text-sm text-muted">
          {{ text.delete.confirmLead() }}
          <span class="font-medium text-text">{{ deleting()?.full_name }}</span
          >{{ text.delete.confirmTail() }}
        </p>
        @if (formError()) {
          <div
            role="alert"
            class="mt-3 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {{ formError() }}
          </div>
        }
        <div class="mt-5 flex items-center justify-end gap-2">
          <sol-button type="button" variant="ghost" (click)="cancelDelete()">
            {{ text.actions.cancel() }}
          </sol-button>
          <sol-button
            type="button"
            variant="danger"
            [disabled]="saving()"
            (click)="confirmDelete()"
          >
            {{ saving() ? text.actions.deleting() : text.actions.delete() }}
          </sol-button>
        </div>
      </sol-modal>
    }
  `,
})
export class UsersPageComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(UsersService);
  private readonly dependenciesService = inject(DependenciesService);
  private readonly rolesService = inject(RolesService);
  private readonly i18n = inject(I18nService);

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
    empty: {
      title: this.i18n.t('admin.users.empty.title'),
      subtitle: this.i18n.t('admin.users.empty.subtitle'),
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

  /** Filas para `sol-data-table` (contrato genérico `Record<string, unknown>`). */
  protected readonly tableData = computed<Record<string, unknown>[]>(
    () => this.items() as unknown as Record<string, unknown>[],
  );

  private readonly dependencyTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('dependencyCell');
  private readonly rolesTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('rolesCell');
  private readonly statusTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>('statusCell');

  /** Columnas de la tabla (reactivas al idioma y a las plantillas de celda). */
  protected readonly columns = computed<DataTableColumn[]>(() => [
    { key: 'full_name', label: this.text.table.name() },
    { key: 'email', label: this.text.table.email() },
    { key: 'dependency_id', label: this.text.table.dependency(), cellTemplate: this.dependencyTpl() },
    { key: 'roles', label: this.text.table.roles(), cellTemplate: this.rolesTpl() },
    { key: 'is_active', label: this.text.table.status(), cellTemplate: this.statusTpl() },
  ]);

  protected readonly showForm = signal(false);
  protected readonly editing = signal<AdminUser | null>(null);
  protected readonly deleting = signal<AdminUser | null>(null);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);

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

  protected dependencyName(id?: string | null): string {
    if (!id) {
      return '—';
    }
    return this.dependencies().find((d) => d.id === id)?.name ?? '—';
  }

  protected showError(
    control:
      | 'primer_nombre'
      | 'primer_apellido'
      | 'email'
      | 'password',
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
        .pipe(
          switchMap(() =>
            this.service.setRoles(editing.id, { role_ids: roleIds }),
          ),
        )
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
    this.formError.set(null);
    this.deleting.set(item);
  }

  protected cancelDelete(): void {
    this.deleting.set(null);
  }

  protected confirmDelete(): void {
    const item = this.deleting();
    if (!item) {
      return;
    }
    this.saving.set(true);
    this.formError.set(null);
    this.service.remove(item.id).subscribe({
      next: () => {
        this.saving.set(false);
        this.deleting.set(null);
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        this.saving.set(false);
        this.formError.set(this.messageFor(err));
      },
    });
  }

  private setPasswordRequired(required: boolean): void {
    const control = this.form.controls.password;
    control.setValidators(
      required ? [Validators.required, Validators.minLength(8)] : [],
    );
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
