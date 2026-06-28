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
import { MenusService } from './menus.service';
import {
  AdminMenu,
  AdminMenuNode,
  buildMenuTree,
  flattenMenuTree,
} from './menu-admin.model';

@Component({
  selector: 'bk-admin-menus',
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
      <bk-page-header
        title="Actividades"
        subtitle="Organiza las actividades del menú y su jerarquía."
      >
        <bk-button
          type="button"
          variant="primary"
          (click)="openCreate()"
          ariaLabel="Crea una actividad"
        >
          Crear actividad
        </bk-button>
      </bk-page-header>

      @if (loading()) {
        <p class="text-sm text-muted">Cargando actividades…</p>
      } @else if (loadError()) {
        <div
          role="alert"
          class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {{ loadError() }}
        </div>
      } @else if (rows().length === 0) {
        <div class="rounded-xl border border-border bg-surface p-8 text-center">
          <p class="text-base font-medium text-text">
            Todavía no hay actividades.
          </p>
          <p class="mt-1 text-sm text-muted">
            Crea la primera para construir el menú de la aplicación.
          </p>
        </div>
      } @else {
        <bk-table>
          <thead>
            <tr class="border-b border-border text-xs uppercase text-muted">
              <th class="px-4 py-3 font-medium">Actividad</th>
              <th class="px-4 py-3 font-medium">Ruta</th>
              <th class="px-4 py-3 font-medium">Orden</th>
              <th class="px-4 py-3 font-medium">Estado</th>
              <th class="px-4 py-3 text-right font-medium">Acciones</th>
            </tr>
          </thead>
          <tbody>
            @for (row of rows(); track row.menu.id) {
              <tr class="border-b border-border last:border-0">
                <td class="px-4 py-3">
                  <span
                    class="font-medium text-text"
                    [style.padding-left.px]="row.depth * 20"
                  >
                    {{ row.menu.name }}
                  </span>
                </td>
                <td class="px-4 py-3 text-muted">{{ row.menu.path || '—' }}</td>
                <td class="px-4 py-3 text-muted">{{ row.menu.order }}</td>
                <td class="px-4 py-3">
                  @if (row.menu.is_active) {
                    <bk-badge tone="success">Activa</bk-badge>
                  } @else {
                    <bk-badge tone="muted">Inactiva</bk-badge>
                  }
                </td>
                <td class="px-4 py-3">
                  <div class="flex items-center justify-end gap-2">
                    <bk-icon-button
                      icon="edit"
                      ariaLabel="Edita la actividad"
                      (click)="openEdit(row.menu)"
                    ></bk-icon-button>
                    <bk-icon-button
                      icon="delete"
                      tone="danger"
                      ariaLabel="Elimina la actividad"
                      (click)="askDelete(row.menu)"
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
        [title]="editing() ? 'Editar actividad' : 'Nueva actividad'"
        (close)="closeForm()"
      >
        <form
          [formGroup]="form"
          (ngSubmit)="onSubmit()"
          class="flex flex-col gap-4"
          novalidate
        >
          <div>
            <bk-text-input
              label="Nombre"
              placeholder="Ej. Proyectos"
              formControlName="name"
            ></bk-text-input>
            @if (showError('name')) {
              <p class="mt-1 text-xs text-danger">El nombre es obligatorio.</p>
            }
          </div>

          <bk-text-input
            label="Ícono (opcional)"
            placeholder="Ej. folder"
            formControlName="icon"
          ></bk-text-input>

          <bk-text-input
            label="Ruta (opcional)"
            placeholder="Ej. /projects"
            formControlName="path"
          ></bk-text-input>

          <label class="block">
            <span class="mb-1.5 block text-sm font-medium text-text"
              >Actividad padre (opcional)</span
            >
            <select
              formControlName="parent_id"
              class="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text
                     transition-colors focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40"
            >
              <option value="">Sin padre (nivel superior)</option>
              @for (option of parentOptions(); track option.id) {
                <option [value]="option.id">{{ option.name }}</option>
              }
            </select>
          </label>

          <bk-text-input
            label="Orden"
            type="number"
            placeholder="0"
            formControlName="order"
          ></bk-text-input>

          <label class="flex items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              formControlName="is_active"
              class="h-4 w-4 rounded border-border text-brand focus:ring-brand/40"
            />
            Activa
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
      <bk-modal size="sm" title="Eliminar actividad" (close)="cancelDelete()">
        <p class="text-sm text-muted">
          ¿Confirmas que deseas eliminar
          <span class="font-medium text-text">{{ deleting()?.name }}</span>? Si
          tiene actividades hijas, revisa que no queden huérfanas.
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
export class MenusPageComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(MenusService);

  private readonly flat = signal<AdminMenu[]>([]);
  protected readonly rows = signal<
    Array<{ menu: AdminMenuNode; depth: number }>
  >([]);
  protected readonly loading = signal(false);
  protected readonly loadError = signal<string | null>(null);

  protected readonly showForm = signal(false);
  protected readonly editing = signal<AdminMenu | null>(null);
  protected readonly deleting = signal<AdminMenu | null>(null);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);

  protected readonly form = this.fb.nonNullable.group({
    name: ['', [Validators.required]],
    icon: [''],
    path: [''],
    parent_id: [''],
    order: ['0'],
    is_active: [true],
  });

  ngOnInit(): void {
    this.load();
  }

  /** Parent candidates: all menus except the one being edited. */
  protected parentOptions(): AdminMenu[] {
    const editingId = this.editing()?.id;
    return this.flat().filter((menu) => menu.id !== editingId);
  }

  protected showError(control: 'name'): boolean {
    const c = this.form.controls[control];
    return c.invalid && (c.touched || c.dirty);
  }

  protected openCreate(): void {
    this.editing.set(null);
    this.formError.set(null);
    this.form.reset({
      name: '',
      icon: '',
      path: '',
      parent_id: '',
      order: '0',
      is_active: true,
    });
    this.showForm.set(true);
  }

  protected openEdit(item: AdminMenu): void {
    this.editing.set(item);
    this.formError.set(null);
    this.form.reset({
      name: item.name,
      icon: item.icon ?? '',
      path: item.path ?? '',
      parent_id: item.parent_id ?? '',
      order: String(item.order ?? 0),
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
    const parsedOrder = Number.parseInt(raw.order, 10);
    const payload = {
      name: raw.name.trim(),
      icon: raw.icon.trim() || null,
      path: raw.path.trim() || null,
      parent_id: raw.parent_id || null,
      order: Number.isNaN(parsedOrder) ? 0 : parsedOrder,
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

  protected askDelete(item: AdminMenu): void {
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
        const data = res.data ?? [];
        this.flat.set(data);
        this.rows.set(flattenMenuTree(buildMenuTree(data)));
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.loadError.set(
          err.status === 0
            ? 'No fue posible conectar con el servidor. Inténtalo de nuevo.'
            : 'No se pudieron cargar las actividades. Inténtalo más tarde.',
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
