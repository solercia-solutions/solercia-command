import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import {
  FormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { ButtonComponent } from '../../../shared/ui/button.component';
import { TextInputComponent } from '../../../shared/ui/text-input.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';
import { BadgeComponent } from '../../../shared/ui/badge.component';
import { IconButtonComponent } from '../../../shared/ui/icon-button.component';
import { ModalComponent } from '../../../shared/ui/modal.component';
import { TableComponent } from '../../../shared/ui/table.component';
import { RolesService } from './roles.service';
import { Role } from './role.model';
import { MenusService } from '../menus/menus.service';
import {
  AdminMenu,
  buildMenuTree,
  flattenMenuTree,
} from '../menus/menu-admin.model';

@Component({
  selector: 'sp-admin-roles',
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
    TableComponent,
  ],
  template: `
    <section class="flex flex-col gap-6">
      <sp-page-header
        title="Roles"
        subtitle="Define los roles y las actividades que cada uno puede ver."
      >
        <sp-button
          type="button"
          variant="primary"
          (click)="openCreate()"
          ariaLabel="Crea un rol"
        >
          Crear rol
        </sp-button>
      </sp-page-header>

      @if (loading()) {
        <p class="text-sm text-muted">Cargando roles…</p>
      } @else if (loadError()) {
        <div
          role="alert"
          class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {{ loadError() }}
        </div>
      } @else if (items().length === 0) {
        <div class="rounded-xl border border-border bg-surface p-8 text-center">
          <p class="text-base font-medium text-text">Todavía no hay roles.</p>
          <p class="mt-1 text-sm text-muted">
            Crea el primer rol para empezar a controlar los accesos.
          </p>
        </div>
      } @else {
        <sp-table>
          <thead>
            <tr class="border-b border-border text-xs uppercase text-muted">
              <th class="px-4 py-3 font-medium">Código</th>
              <th class="px-4 py-3 font-medium">Nombre</th>
              <th class="px-4 py-3 font-medium">Estado</th>
              <th class="px-4 py-3 text-right font-medium">Acciones</th>
            </tr>
          </thead>
          <tbody>
            @for (item of items(); track item.id) {
              <tr class="border-b border-border last:border-0">
                <td class="px-4 py-3">
                  <sp-badge tone="brand">{{ item.code }}</sp-badge>
                </td>
                <td class="px-4 py-3 font-medium text-text">{{ item.name }}</td>
                <td class="px-4 py-3">
                  @if (item.is_active) {
                    <sp-badge tone="success">Activo</sp-badge>
                  } @else {
                    <sp-badge tone="muted">Inactivo</sp-badge>
                  }
                </td>
                <td class="px-4 py-3">
                  <div class="flex items-center justify-end gap-2">
                    <sp-icon-button
                      icon="link"
                      ariaLabel="Asocia actividades al rol"
                      (click)="openMenus(item)"
                    ></sp-icon-button>
                    <sp-icon-button
                      icon="edit"
                      ariaLabel="Edita el rol"
                      (click)="openEdit(item)"
                    ></sp-icon-button>
                    <sp-icon-button
                      icon="delete"
                      tone="danger"
                      ariaLabel="Elimina el rol"
                      (click)="askDelete(item)"
                    ></sp-icon-button>
                  </div>
                </td>
              </tr>
            }
          </tbody>
        </sp-table>
      }
    </section>

    @if (showForm()) {
      <sp-modal
        [title]="editing() ? 'Editar rol' : 'Nuevo rol'"
        (close)="closeForm()"
      >
        <form
          [formGroup]="form"
          (ngSubmit)="onSubmit()"
          class="flex flex-col gap-4"
          novalidate
        >
          <div>
            <sp-text-input
              label="Código"
              placeholder="Ej. MANAGER"
              formControlName="code"
            ></sp-text-input>
            @if (showError('code')) {
              <p class="mt-1 text-xs text-danger">El código es obligatorio.</p>
            }
          </div>

          <div>
            <sp-text-input
              label="Nombre"
              placeholder="Ej. Líder"
              formControlName="name"
            ></sp-text-input>
            @if (showError('name')) {
              <p class="mt-1 text-xs text-danger">El nombre es obligatorio.</p>
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
            <sp-button type="button" variant="ghost" (click)="closeForm()">
              Cancelar
            </sp-button>
            <sp-button type="submit" variant="primary" [disabled]="saving()">
              {{ saving() ? 'Guardando…' : 'Guardar' }}
            </sp-button>
          </div>
        </form>
      </sp-modal>
    }

    @if (menusFor()) {
      <sp-modal
        size="lg"
        [title]="'Actividades de ' + (menusFor()?.name ?? '')"
        (close)="closeMenus()"
      >
        @if (menusLoading()) {
          <p class="text-sm text-muted">Cargando actividades…</p>
        } @else {
          <p class="mb-3 text-sm text-muted">
            Selecciona las actividades que este rol puede ver.
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
          <sp-button type="button" variant="ghost" (click)="closeMenus()">
            Cancelar
          </sp-button>
          <sp-button
            type="button"
            variant="primary"
            [disabled]="saving() || menusLoading()"
            (click)="saveMenus()"
          >
            {{ saving() ? 'Guardando…' : 'Guardar actividades' }}
          </sp-button>
        </div>
      </sp-modal>
    }

    @if (deleting()) {
      <sp-modal size="sm" title="Eliminar rol" (close)="cancelDelete()">
        <p class="text-sm text-muted">
          ¿Confirmas que deseas eliminar
          <span class="font-medium text-text">{{ deleting()?.name }}</span>? Esta
          acción no se puede deshacer.
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
          <sp-button type="button" variant="ghost" (click)="cancelDelete()">
            Cancelar
          </sp-button>
          <sp-button
            type="button"
            variant="danger"
            [disabled]="saving()"
            (click)="confirmDelete()"
          >
            {{ saving() ? 'Eliminando…' : 'Eliminar' }}
          </sp-button>
        </div>
      </sp-modal>
    }
  `,
})
export class RolesPageComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(RolesService);
  private readonly menusService = inject(MenusService);

  protected readonly items = signal<Role[]>([]);
  protected readonly loading = signal(false);
  protected readonly loadError = signal<string | null>(null);

  protected readonly showForm = signal(false);
  protected readonly editing = signal<Role | null>(null);
  protected readonly deleting = signal<Role | null>(null);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);

  // Menu association modal.
  protected readonly menusFor = signal<Role | null>(null);
  protected readonly menusLoading = signal(false);
  protected readonly menuRows = signal<
    Array<{ menu: AdminMenu; depth: number }>
  >([]);
  protected readonly selectedMenuIds = signal<Set<string>>(new Set());

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
            : 'No se pudieron cargar los roles. Inténtalo más tarde.',
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
