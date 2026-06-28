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
import { DependenciesService } from './dependencies.service';
import { Dependency } from './dependency.model';

@Component({
  selector: 'bk-admin-dependencies',
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
        title="Dependencias"
        subtitle="Administra las áreas o dependencias de tu organización."
      >
        <bk-button
          type="button"
          variant="primary"
          (click)="openCreate()"
          ariaLabel="Crea una dependencia"
        >
          Crear dependencia
        </bk-button>
      </bk-page-header>

      @if (loading()) {
        <p class="text-sm text-muted">Cargando dependencias…</p>
      } @else if (loadError()) {
        <div
          role="alert"
          class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {{ loadError() }}
        </div>
      } @else if (items().length === 0) {
        <div class="rounded-xl border border-border bg-surface p-8 text-center">
          <p class="text-base font-medium text-text">
            Todavía no hay dependencias.
          </p>
          <p class="mt-1 text-sm text-muted">
            Crea la primera para clasificar a las personas de tu organización.
          </p>
        </div>
      } @else {
        <bk-table>
          <thead>
            <tr class="border-b border-border text-xs uppercase text-muted">
              <th class="px-4 py-3 font-medium">Nombre</th>
              <th class="px-4 py-3 font-medium">Código</th>
              <th class="px-4 py-3 font-medium">Estado</th>
              <th class="px-4 py-3 text-right font-medium">Acciones</th>
            </tr>
          </thead>
          <tbody>
            @for (item of items(); track item.id) {
              <tr class="border-b border-border last:border-0">
                <td class="px-4 py-3 font-medium text-text">{{ item.name }}</td>
                <td class="px-4 py-3 text-muted">{{ item.code || '—' }}</td>
                <td class="px-4 py-3">
                  @if (item.is_active) {
                    <bk-badge tone="success">Activa</bk-badge>
                  } @else {
                    <bk-badge tone="muted">Inactiva</bk-badge>
                  }
                </td>
                <td class="px-4 py-3">
                  <div class="flex items-center justify-end gap-2">
                    <bk-icon-button
                      icon="edit"
                      ariaLabel="Edita la dependencia"
                      (click)="openEdit(item)"
                    ></bk-icon-button>
                    <bk-icon-button
                      icon="delete"
                      tone="danger"
                      ariaLabel="Elimina la dependencia"
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
        [title]="editing() ? 'Editar dependencia' : 'Nueva dependencia'"
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
              placeholder="Ej. Tecnología"
              formControlName="name"
            ></bk-text-input>
            @if (showError('name')) {
              <p class="mt-1 text-xs text-danger">El nombre es obligatorio.</p>
            }
          </div>

          <bk-text-input
            label="Código (opcional)"
            placeholder="Ej. TEC"
            formControlName="code"
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
      <bk-modal
        size="sm"
        title="Eliminar dependencia"
        (close)="cancelDelete()"
      >
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
export class DependenciesPageComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(DependenciesService);

  protected readonly items = signal<Dependency[]>([]);
  protected readonly loading = signal(false);
  protected readonly loadError = signal<string | null>(null);

  protected readonly showForm = signal(false);
  protected readonly editing = signal<Dependency | null>(null);
  protected readonly deleting = signal<Dependency | null>(null);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);

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
            : 'No se pudieron cargar las dependencias. Inténtalo más tarde.',
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
