import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import {
  FormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { switchMap } from 'rxjs';
import { ButtonComponent } from '@shared/ui/button.component';
import { TextInputComponent } from '@shared/ui/text-input.component';
import { PageHeaderComponent } from '@shared/ui/page-header.component';
import { BadgeComponent } from '@shared/ui/badge.component';
import { IconButtonComponent } from '@shared/ui/icon-button.component';
import { ModalComponent } from '@shared/ui/modal.component';
import { SelectComponent } from '@shared/ui/select.component';
import { TableComponent } from '@shared/ui/table.component';
import { UsersService } from '@entities/user/users.service';
import { AdminUser } from '@entities/user/user-admin.model';
import { DependenciesService } from '@entities/dependency/dependencies.service';
import { Dependency } from '@entities/dependency/dependency.model';
import { RolesService } from '@entities/role/roles.service';
import { Role } from '@entities/role/role.model';

@Component({
  selector: 'bk-admin-users',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    ButtonComponent,
    TextInputComponent,
    PageHeaderComponent,
    BadgeComponent,
    IconButtonComponent,
    ModalComponent,
    SelectComponent,
    TableComponent,
  ],
  template: `
    <section class="flex flex-col gap-6">
      <bk-page-header
        title="Usuarios"
        subtitle="Administra las personas, sus dependencias y sus roles."
      >
        <bk-button
          type="button"
          variant="primary"
          (click)="openCreate()"
          ariaLabel="Crea un usuario"
        >
          Crear usuario
        </bk-button>
      </bk-page-header>

      @if (loading()) {
        <p class="text-sm text-muted">Cargando usuarios…</p>
      } @else if (loadError()) {
        <div
          role="alert"
          class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {{ loadError() }}
        </div>
      } @else if (items().length === 0) {
        <div class="rounded-xl border border-border bg-surface p-8 text-center">
          <p class="text-base font-medium text-text">Todavía no hay usuarios.</p>
          <p class="mt-1 text-sm text-muted">
            Crea el primer usuario para dar acceso a tu organización.
          </p>
        </div>
      } @else {
        <bk-table>
          <thead>
            <tr class="border-b border-border text-xs uppercase text-muted">
              <th class="px-4 py-3 font-medium">Nombre</th>
              <th class="px-4 py-3 font-medium">Correo</th>
              <th class="px-4 py-3 font-medium">Dependencia</th>
              <th class="px-4 py-3 font-medium">Roles</th>
              <th class="px-4 py-3 font-medium">Estado</th>
              <th class="px-4 py-3 text-right font-medium">Acciones</th>
            </tr>
          </thead>
          <tbody>
            @for (item of items(); track item.id) {
              <tr class="border-b border-border last:border-0">
                <td class="px-4 py-3 font-medium text-text">
                  {{ item.full_name }}
                </td>
                <td class="px-4 py-3 text-muted">{{ item.email }}</td>
                <td class="px-4 py-3 text-muted">
                  {{ dependencyName(item.dependency_id) }}
                </td>
                <td class="px-4 py-3">
                  <div class="flex flex-wrap gap-1">
                    @for (role of item.roles ?? []; track role.id) {
                      <bk-badge tone="brand">{{ role.name }}</bk-badge>
                    } @empty {
                      <span class="text-xs text-muted">Sin roles</span>
                    }
                  </div>
                </td>
                <td class="px-4 py-3">
                  @if (item.is_active) {
                    <bk-badge tone="success">Activo</bk-badge>
                  } @else {
                    <bk-badge tone="muted">Inactivo</bk-badge>
                  }
                </td>
                <td class="px-4 py-3">
                  <div class="flex items-center justify-end gap-2">
                    <bk-icon-button
                      icon="edit"
                      ariaLabel="Edita el usuario"
                      (click)="openEdit(item)"
                    ></bk-icon-button>
                    <bk-icon-button
                      icon="delete"
                      tone="danger"
                      ariaLabel="Elimina el usuario"
                      (click)="askDelete(item)"
                    ></bk-icon-button>
                  </div>
                </td>
              </tr>
            }
          </tbody>
        </bk-table>
      }
    </section>

    @if (showForm()) {
      <bk-modal
        size="xl"
        [title]="editing() ? 'Editar usuario' : 'Nuevo usuario'"
        (close)="closeForm()"
      >
        <form
          [formGroup]="form"
          (ngSubmit)="onSubmit()"
          class="flex flex-col gap-4"
          novalidate
        >
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <bk-text-input
                label="Primer nombre"
                placeholder="Ej. Ana"
                formControlName="primer_nombre"
              ></bk-text-input>
              @if (showError('primer_nombre')) {
                <p class="mt-1 text-xs text-danger">
                  El primer nombre es obligatorio.
                </p>
              }
            </div>
            <bk-text-input
              label="Segundo nombre (opcional)"
              placeholder="Ej. María"
              formControlName="segundo_nombre"
            ></bk-text-input>
            <div>
              <bk-text-input
                label="Primer apellido"
                placeholder="Ej. Torres"
                formControlName="primer_apellido"
              ></bk-text-input>
              @if (showError('primer_apellido')) {
                <p class="mt-1 text-xs text-danger">
                  El primer apellido es obligatorio.
                </p>
              }
            </div>
            <bk-text-input
              label="Segundo apellido (opcional)"
              placeholder="Ej. Páez"
              formControlName="segundo_apellido"
            ></bk-text-input>
          </div>

          <div>
            <bk-text-input
              label="Correo electrónico"
              type="email"
              placeholder="persona@solercia.com"
              autocomplete="email"
              formControlName="email"
            ></bk-text-input>
            @if (showError('email')) {
              <p class="mt-1 text-xs text-danger">{{ emailError() }}</p>
            }
          </div>

          @if (!editing()) {
            <div>
              <bk-text-input
                label="Contraseña"
                type="password"
                placeholder="••••••••"
                autocomplete="new-password"
                formControlName="password"
              ></bk-text-input>
              @if (showError('password')) {
                <p class="mt-1 text-xs text-danger">
                  La contraseña debe tener al menos 8 caracteres.
                </p>
              }
            </div>
          }

          <label class="block">
            <span class="mb-1.5 block text-sm font-medium text-text"
              >Dependencia (opcional)</span
            >
            <select
              formControlName="dependency_id"
              class="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text
                     transition-colors focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40"
            >
              <option value="">Sin dependencia</option>
              @for (dependency of dependencies(); track dependency.id) {
                <option [value]="dependency.id">{{ dependency.name }}</option>
              }
            </select>
          </label>

          <div>
            @if (roles().length === 0) {
              <span class="mb-1.5 block text-sm font-medium text-text">Roles</span>
              <p class="text-xs text-muted">
                No hay roles creados todavía. Crea roles para poder asignarlos.
              </p>
            } @else {
              <bk-select
                label="Roles"
                [multiple]="true"
                [options]="roleOptions()"
                placeholder="Asigna uno o más roles"
                formControlName="role_ids"
              ></bk-select>
            }
          </div>

          <label class="flex items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              formControlName="is_active"
              class="h-4 w-4 rounded border-border text-brand focus:ring-brand/40"
            />
            Activo
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
            <bk-button type="button" variant="ghost" (click)="closeForm()">
              Cancelar
            </bk-button>
            <bk-button type="submit" variant="primary" [disabled]="saving()">
              {{ saving() ? 'Guardando…' : 'Guardar' }}
            </bk-button>
          </div>
        </form>
      </bk-modal>
    }

    @if (deleting()) {
      <bk-modal size="sm" title="Eliminar usuario" (close)="cancelDelete()">
        <p class="text-sm text-muted">
          ¿Confirmas que deseas eliminar a
          <span class="font-medium text-text">{{ deleting()?.full_name }}</span
          >? Esta acción no se puede deshacer.
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
          <bk-button type="button" variant="ghost" (click)="cancelDelete()">
            Cancelar
          </bk-button>
          <bk-button
            type="button"
            variant="danger"
            [disabled]="saving()"
            (click)="confirmDelete()"
          >
            {{ saving() ? 'Eliminando…' : 'Eliminar' }}
          </bk-button>
        </div>
      </bk-modal>
    }
  `,
})
export class UsersPageComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(UsersService);
  private readonly dependenciesService = inject(DependenciesService);
  private readonly rolesService = inject(RolesService);

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
      return 'El correo es obligatorio.';
    }
    if (c.hasError('email')) {
      return 'El correo no es válido.';
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
            ? 'No fue posible conectar con el servidor. Inténtalo de nuevo.'
            : 'No se pudieron cargar los usuarios. Inténtalo más tarde.',
        );
      },
    });
  }

  private messageFor(err: HttpErrorResponse): string {
    if (err.status === 0) {
      return 'No fue posible conectar con el servidor. Inténtalo de nuevo.';
    }
    const detail = (err.error as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    return 'No se pudo completar la operación. Revisa los datos e inténtalo de nuevo.';
  }
}
