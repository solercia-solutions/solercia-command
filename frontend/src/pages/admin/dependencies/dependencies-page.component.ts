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
import { SolButtonComponent } from '@shared/ui';
import { SolInputComponent } from '@shared/ui';
import { SolPageHeaderComponent } from '@shared/ui/page-header.component';
import { SolBadgeComponent } from '@shared/ui';
import { SolIconButtonComponent } from '@shared/ui/icon-button.component';
import { SolModalComponent } from '@shared/ui';
import { SolTableComponent } from '@shared/ui/table.component';
import { I18nService } from '@shared/i18n';
import { DependenciesService } from '@entities/dependency/dependencies.service';
import { Dependency } from '@entities/dependency/dependency.model';

@Component({
  selector: 'sol-admin-dependencies',
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
    SolTableComponent,
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
          [ariaLabel]="text.createAria()"
        >
          {{ text.create() }}
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
          <p class="text-base font-medium text-text">
            {{ text.emptyTitle() }}
          </p>
          <p class="mt-1 text-sm text-muted">
            {{ text.emptySubtitle() }}
          </p>
        </div>
      } @else {
        <sol-table>
          <thead>
            <tr class="border-b border-border text-xs uppercase text-muted">
              <th class="px-4 py-3 font-medium">{{ text.thName() }}</th>
              <th class="px-4 py-3 font-medium">{{ text.thCode() }}</th>
              <th class="px-4 py-3 font-medium">{{ text.thStatus() }}</th>
              <th class="px-4 py-3 text-right font-medium">{{ text.thActions() }}</th>
            </tr>
          </thead>
          <tbody>
            @for (item of items(); track item.id) {
              <tr class="border-b border-border last:border-0">
                <td class="px-4 py-3 font-medium text-text">{{ item.name }}</td>
                <td class="px-4 py-3 text-muted">{{ item.code || '—' }}</td>
                <td class="px-4 py-3">
                  @if (item.is_active) {
                    <sol-badge variant="success">{{ text.statusActive() }}</sol-badge>
                  } @else {
                    <sol-badge variant="neutral">{{ text.statusInactive() }}</sol-badge>
                  }
                </td>
                <td class="px-4 py-3">
                  <div class="flex items-center justify-end gap-2">
                    <sol-icon-button
                      icon="edit"
                      [ariaLabel]="text.editAria()"
                      (click)="openEdit(item)"
                    ></sol-icon-button>
                    <sol-icon-button
                      icon="delete"
                      variant="danger"
                      [ariaLabel]="text.deleteAria()"
                      (click)="askDelete(item)"
                    ></sol-icon-button>
                  </div>
                </td>
              </tr>
            }
          </tbody>
        </sol-table>
      }
    </section>

    @if (showForm()) {
      <sol-modal [open]="true"
        [title]="editing() ? text.formEditTitle() : text.formCreateTitle()"
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
              [label]="text.nameLabel()"
              [placeholder]="text.namePlaceholder()"
              formControlName="name"
            ></sol-input>
            @if (showError('name')) {
              <p class="mt-1 text-xs text-danger">{{ text.nameRequired() }}</p>
            }
          </div>

          <sol-input
            [label]="text.codeLabel()"
            [placeholder]="text.codePlaceholder()"
            formControlName="code"
          ></sol-input>

          <label class="flex items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              formControlName="is_active"
              class="h-4 w-4 rounded border-border text-brand focus:ring-brand/40"
            />
            {{ text.activeLabel() }}
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
              {{ text.cancel() }}
            </sol-button>
            <sol-button type="submit" variant="primary" [disabled]="saving()">
              {{ saving() ? text.saving() : text.save() }}
            </sol-button>
          </div>
        </form>
      </sol-modal>
    }

    @if (deleting()) {
      <sol-modal [open]="true"
        size="sm"
        [title]="text.deleteTitle()"
        (closed)="cancelDelete()"
      >
        <p class="text-sm text-muted">
          {{ text.deleteConfirmPrefix() }}
          <span class="font-medium text-text">{{ deleting()?.name }}</span
          >{{ text.deleteConfirmSuffix() }}
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
            {{ text.cancel() }}
          </sol-button>
          <sol-button
            type="button"
            variant="danger"
            [disabled]="saving()"
            (click)="confirmDelete()"
          >
            {{ saving() ? text.deleting() : text.delete() }}
          </sol-button>
        </div>
      </sol-modal>
    }
  `,
})
export class DependenciesPageComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(DependenciesService);
  private readonly i18n = inject(I18nService);

  /** Textos de la vista resueltos por i18n (reactivos al cambio de idioma). */
  protected readonly text = {
    title: this.i18n.t('admin.dependencies.title'),
    subtitle: this.i18n.t('admin.dependencies.subtitle'),
    loading: this.i18n.t('admin.dependencies.loading'),
    emptyTitle: this.i18n.t('admin.dependencies.empty.title'),
    emptySubtitle: this.i18n.t('admin.dependencies.empty.subtitle'),
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
  } as const;

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
