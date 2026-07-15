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
import { MenusService } from '@entities/menu/menus.service';
import {
  AdminMenu,
  AdminMenuNode,
  buildMenuTree,
  flattenMenuTree,
} from '@entities/menu/menu-admin.model';

@Component({
  selector: 'sol-admin-menus',
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
      } @else if (rows().length === 0) {
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
              <th class="px-4 py-3 font-medium">{{ text.thActivity() }}</th>
              <th class="px-4 py-3 font-medium">{{ text.thPath() }}</th>
              <th class="px-4 py-3 font-medium">{{ text.thOrder() }}</th>
              <th class="px-4 py-3 font-medium">{{ text.thStatus() }}</th>
              <th class="px-4 py-3 text-right font-medium">{{ text.thActions() }}</th>
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
                      (click)="openEdit(row.menu)"
                    ></sol-icon-button>
                    <sol-icon-button
                      icon="delete"
                      variant="danger"
                      [ariaLabel]="text.deleteAria()"
                      (click)="askDelete(row.menu)"
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
            [label]="text.iconLabel()"
            [placeholder]="text.iconPlaceholder()"
            formControlName="icon"
          ></sol-input>

          <sol-input
            [label]="text.pathLabel()"
            [placeholder]="text.pathPlaceholder()"
            formControlName="path"
          ></sol-input>

          <label class="block">
            <span class="mb-1.5 block text-sm font-medium text-text"
              >{{ text.parentLabel() }}</span
            >
            <select
              formControlName="parent_id"
              class="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text
                     transition-colors focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40"
            >
              <option value="">{{ text.noParent() }}</option>
              @for (option of parentOptions(); track option.id) {
                <option [value]="option.id">{{ option.name }}</option>
              }
            </select>
          </label>

          <sol-input
            [label]="text.orderLabel()"
            type="number"
            placeholder="0"
            formControlName="order"
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
      <sol-modal [open]="true" size="sm" [title]="text.deleteTitle()" (closed)="cancelDelete()">
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
export class MenusPageComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(MenusService);
  private readonly i18n = inject(I18nService);

  /** Textos de la vista resueltos por i18n (reactivos al cambio de idioma). */
  protected readonly text = {
    title: this.i18n.t('admin.menus.title'),
    subtitle: this.i18n.t('admin.menus.subtitle'),
    loading: this.i18n.t('admin.menus.loading'),
    emptyTitle: this.i18n.t('admin.menus.empty.title'),
    emptySubtitle: this.i18n.t('admin.menus.empty.subtitle'),
    thActivity: this.i18n.t('admin.menus.table.activity'),
    thPath: this.i18n.t('admin.menus.table.path'),
    thOrder: this.i18n.t('admin.menus.table.order'),
    thStatus: this.i18n.t('admin.menus.table.status'),
    thActions: this.i18n.t('admin.menus.table.actions'),
    statusActive: this.i18n.t('admin.menus.status.active'),
    statusInactive: this.i18n.t('admin.menus.status.inactive'),
    create: this.i18n.t('admin.menus.actions.create'),
    createAria: this.i18n.t('admin.menus.actions.createAria'),
    editAria: this.i18n.t('admin.menus.actions.editAria'),
    deleteAria: this.i18n.t('admin.menus.actions.deleteAria'),
    cancel: this.i18n.t('admin.menus.actions.cancel'),
    save: this.i18n.t('admin.menus.actions.save'),
    saving: this.i18n.t('admin.menus.actions.saving'),
    delete: this.i18n.t('admin.menus.actions.delete'),
    deleting: this.i18n.t('admin.menus.actions.deleting'),
    formCreateTitle: this.i18n.t('admin.menus.form.createTitle'),
    formEditTitle: this.i18n.t('admin.menus.form.editTitle'),
    nameLabel: this.i18n.t('admin.menus.form.nameLabel'),
    namePlaceholder: this.i18n.t('admin.menus.form.namePlaceholder'),
    nameRequired: this.i18n.t('admin.menus.form.nameRequired'),
    iconLabel: this.i18n.t('admin.menus.form.iconLabel'),
    iconPlaceholder: this.i18n.t('admin.menus.form.iconPlaceholder'),
    pathLabel: this.i18n.t('admin.menus.form.pathLabel'),
    pathPlaceholder: this.i18n.t('admin.menus.form.pathPlaceholder'),
    parentLabel: this.i18n.t('admin.menus.form.parentLabel'),
    noParent: this.i18n.t('admin.menus.form.noParent'),
    orderLabel: this.i18n.t('admin.menus.form.orderLabel'),
    activeLabel: this.i18n.t('admin.menus.form.activeLabel'),
    deleteTitle: this.i18n.t('admin.menus.delete.title'),
    deleteConfirmPrefix: this.i18n.t('admin.menus.delete.confirmPrefix'),
    deleteConfirmSuffix: this.i18n.t('admin.menus.delete.confirmSuffix'),
  } as const;

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
            ? this.i18n.translate('admin.menus.errors.network')
            : this.i18n.translate('admin.menus.errors.loadFailed'),
        );
      },
    });
  }

  private messageFor(err: HttpErrorResponse): string {
    if (err.status === 0) {
      return this.i18n.translate('admin.menus.errors.network');
    }
    const detail = (err.error as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    return this.i18n.translate('admin.menus.errors.saveFailed');
  }
}
