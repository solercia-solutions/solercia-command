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
  SolSelectComponent,
  SolSelectOption,
  SolDataTableComponent,
  DataTableColumn,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { AlertService } from '@shared/lib/alerts';
import { OrganizationsService } from '@entities/organization/organizations.service';
import {
  MemberRole,
  Organization,
  OrganizationMember,
  OrganizationMembership,
} from '@entities/organization/organization.model';

const MEMBER_ROLES: MemberRole[] = ['admin', 'manager', 'member', 'viewer'];

/**
 * Página admin de empresas (organizations-admin): listado + CRUD de la
 * propia empresa y gestión de sus miembros (Fases 11-12, Lote 3).
 *
 * La UI oculta las acciones de escritura (editar/eliminar/gestionar
 * miembros) cuando el rol del usuario en ESA fila no es `admin`, pero el
 * backend SIEMPRE re-valida con `require_org_admin` — la UI es cosmética,
 * nunca el control de acceso real (design.md, Fase 11.2).
 */
@Component({
  selector: 'sol-admin-organizations',
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
      } @else if (memberships().length === 0) {
        <div class="rounded-xl border border-border bg-surface p-8 text-center">
          <p class="text-base font-medium text-text">{{ text.empty.title() }}</p>
          <p class="mt-1 text-sm text-muted">{{ text.empty.subtitle() }}</p>
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
                icon="users"
                [ariaLabel]="text.actions.membersAria()"
                (clicked)="openMembers($any(row))"
              />
              @if ($any(row).role === 'admin') {
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
              }
            </div>
          </ng-template>
        </sol-data-table>
      }
    </section>

    <ng-template #roleCell let-row="row">
      <sol-badge [variant]="roleVariant($any(row).role)">{{ roleLabel($any(row).role) }}</sol-badge>
    </ng-template>
    <ng-template #statusCell let-row="row">
      @if ($any(row).organization.is_active) {
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
              [label]="text.form.name()"
              [placeholder]="text.form.namePlaceholder()"
              formControlName="name"
            ></sol-input>
            @if (showError('name')) {
              <p class="mt-1 text-xs text-danger">{{ text.form.errors.nameRequired() }}</p>
            }
          </div>

          <div>
            <sol-input
              [label]="text.form.slug()"
              [placeholder]="text.form.slugPlaceholder()"
              formControlName="slug"
            ></sol-input>
            @if (showError('slug')) {
              <p class="mt-1 text-xs text-danger">{{ text.form.errors.slugRequired() }}</p>
            }
          </div>

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

    @if (membersFor()) {
      <sol-modal [open]="true" size="lg" [title]="membersTitle()" (closed)="closeMembers()">
        @if (membersFor()!.role === 'admin') {
          <form
            [formGroup]="addMemberForm"
            (ngSubmit)="onAddMember()"
            class="mb-4 flex flex-col gap-3 rounded-lg border border-border bg-sunken/40 p-3 sm:flex-row sm:items-end"
          >
            <div class="flex-1">
              <sol-input
                [label]="text.members.add.email()"
                type="email"
                [placeholder]="text.members.add.emailPlaceholder()"
                formControlName="email"
              ></sol-input>
              @if (addMemberEmailError()) {
                <p class="mt-1 text-xs text-danger">{{ addMemberEmailError() }}</p>
              }
            </div>
            <div class="sm:w-40">
              <sol-select
                [label]="text.members.add.role()"
                [options]="roleOptions()"
                formControlName="role"
              ></sol-select>
            </div>
            <sol-button type="submit" variant="primary" [disabled]="addingMember()">
              {{ addingMember() ? text.members.add.submitting() : text.members.add.submit() }}
            </sol-button>
          </form>
        }

        @if (membersLoading()) {
          <p class="text-sm text-muted">{{ text.members.loading() }}</p>
        } @else if (members().length === 0) {
          <p class="text-sm text-muted">{{ text.members.empty() }}</p>
        } @else {
          <div class="flex flex-col gap-1">
            @for (member of members(); track member.id) {
              <div class="flex flex-col gap-2 rounded-lg border border-border p-3 sm:flex-row sm:items-center sm:justify-between">
                <div class="min-w-0">
                  <p class="truncate text-sm font-medium text-text">{{ member.full_name }}</p>
                  <p class="truncate text-xs text-muted">{{ member.email }}</p>
                </div>
                <div class="flex items-center gap-2">
                  @if (membersFor()!.role === 'admin') {
                    <select
                      [value]="member.role"
                      (change)="onRoleChange(member, $any($event.target).value)"
                      class="h-9 rounded-lg border border-border bg-surface px-2 text-sm text-text
                             focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40"
                    >
                      @for (role of memberRoles; track role) {
                        <option [value]="role">{{ roleLabel(role) }}</option>
                      }
                    </select>
                    <sol-icon-button
                      icon="trash"
                      variant="danger"
                      [ariaLabel]="text.members.remove.ariaLabel({ name: member.full_name })"
                      (clicked)="askRemoveMember(member)"
                    />
                  } @else {
                    <sol-badge [variant]="roleVariant(member.role)">{{ roleLabel(member.role) }}</sol-badge>
                  }
                </div>
              </div>

              @if (removing()?.id === member.id) {
                <div class="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-text">
                  <p>
                    {{ text.members.remove.confirmLead() }}
                    <span class="font-medium">{{ member.full_name }}</span>
                    {{ text.members.remove.confirmTail() }}
                  </p>
                  <div class="mt-2 flex justify-end gap-2">
                    <sol-button type="button" variant="ghost" (click)="cancelRemoveMember()">
                      {{ text.members.remove.cancel() }}
                    </sol-button>
                    <sol-button
                      type="button"
                      variant="danger"
                      [disabled]="removingBusy()"
                      (click)="confirmRemoveMember()"
                    >
                      {{ text.members.remove.confirm() }}
                    </sol-button>
                  </div>
                </div>
              }
            }
          </div>
        }

        @if (membersError()) {
          <div
            role="alert"
            class="mt-3 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {{ membersError() }}
          </div>
        }

        <div class="mt-5 flex items-center justify-end">
          <sol-button type="button" variant="ghost" (click)="closeMembers()">
            {{ text.members.close() }}
          </sol-button>
        </div>
      </sol-modal>
    }
  `,
})
export class OrganizationsPageComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(OrganizationsService);
  private readonly i18n = inject(I18nService);
  private readonly alert = inject(AlertService);

  protected readonly memberRoles = MEMBER_ROLES;

  protected readonly text = {
    title: this.i18n.t('admin.organizations.title'),
    subtitle: this.i18n.t('admin.organizations.subtitle'),
    loading: this.i18n.t('admin.organizations.loading'),
    actions: {
      create: this.i18n.t('admin.organizations.actions.create'),
      createAria: this.i18n.t('admin.organizations.actions.createAria'),
      membersAria: this.i18n.t('admin.organizations.actions.membersAria'),
      editAria: this.i18n.t('admin.organizations.actions.editAria'),
      deleteAria: this.i18n.t('admin.organizations.actions.deleteAria'),
      cancel: this.i18n.t('admin.organizations.actions.cancel'),
      save: this.i18n.t('admin.organizations.actions.save'),
      saving: this.i18n.t('admin.organizations.actions.saving'),
      delete: this.i18n.t('admin.organizations.actions.delete'),
    },
    status: {
      active: this.i18n.t('admin.organizations.status.active'),
      inactive: this.i18n.t('admin.organizations.status.inactive'),
    },
    empty: {
      title: this.i18n.t('admin.organizations.empty.title'),
      subtitle: this.i18n.t('admin.organizations.empty.subtitle'),
    },
    table: {
      name: this.i18n.t('admin.organizations.table.name'),
      slug: this.i18n.t('admin.organizations.table.slug'),
      role: this.i18n.t('admin.organizations.table.role'),
      status: this.i18n.t('admin.organizations.table.status'),
      actions: this.i18n.t('admin.organizations.table.actions'),
    },
    form: {
      createTitle: this.i18n.t('admin.organizations.form.createTitle'),
      editTitle: this.i18n.t('admin.organizations.form.editTitle'),
      name: this.i18n.t('admin.organizations.form.name'),
      namePlaceholder: this.i18n.t('admin.organizations.form.namePlaceholder'),
      slug: this.i18n.t('admin.organizations.form.slug'),
      slugPlaceholder: this.i18n.t('admin.organizations.form.slugPlaceholder'),
      errors: {
        nameRequired: this.i18n.t('admin.organizations.form.errors.nameRequired'),
        slugRequired: this.i18n.t('admin.organizations.form.errors.slugRequired'),
      },
    },
    delete: {
      title: this.i18n.t('admin.organizations.delete.title'),
      confirmLead: this.i18n.t('admin.organizations.delete.confirmLead'),
      confirmTail: this.i18n.t('admin.organizations.delete.confirmTail'),
    },
    members: {
      loading: this.i18n.t('admin.organizations.members.loading'),
      empty: this.i18n.t('admin.organizations.members.empty'),
      close: this.i18n.t('admin.organizations.members.close'),
      add: {
        email: this.i18n.t('admin.organizations.members.add.email'),
        emailPlaceholder: this.i18n.t(
          'admin.organizations.members.add.emailPlaceholder',
        ),
        role: this.i18n.t('admin.organizations.members.add.role'),
        submit: this.i18n.t('admin.organizations.members.add.submit'),
        submitting: this.i18n.t('admin.organizations.members.add.submitting'),
        errors: {
          emailRequired: this.i18n.t(
            'admin.organizations.members.add.errors.emailRequired',
          ),
          emailInvalid: this.i18n.t(
            'admin.organizations.members.add.errors.emailInvalid',
          ),
        },
      },
      remove: {
        confirmLead: this.i18n.t('admin.organizations.members.remove.confirmLead'),
        confirmTail: this.i18n.t('admin.organizations.members.remove.confirmTail'),
        confirm: this.i18n.t('admin.organizations.members.remove.confirm'),
        cancel: this.i18n.t('admin.organizations.members.remove.cancel'),
        ariaLabel: (params: { name: string }) =>
          this.i18n.translate('admin.organizations.members.remove.ariaLabel', params),
      },
    },
  } as const;

  protected readonly memberships = signal<OrganizationMembership[]>([]);
  protected readonly loading = signal(false);
  protected readonly loadError = signal<string | null>(null);

  protected readonly tableData = computed<Record<string, unknown>[]>(
    () => this.memberships() as unknown as Record<string, unknown>[],
  );

  private readonly roleTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>(
      'roleCell',
    );
  private readonly statusTpl =
    viewChild<TemplateRef<{ $implicit: unknown; row: Record<string, unknown> }>>(
      'statusCell',
    );

  protected readonly columns = computed<DataTableColumn[]>(() => [
    { key: 'organization.name', label: this.text.table.name() },
    { key: 'organization.slug', label: this.text.table.slug() },
    { key: 'role', label: this.text.table.role(), cellTemplate: this.roleTpl() },
    {
      key: 'organization.is_active',
      label: this.text.table.status(),
      cellTemplate: this.statusTpl(),
    },
  ]);

  protected readonly roleOptions = computed<SolSelectOption[]>(() =>
    this.memberRoles.map((role) => ({ value: role, label: this.roleLabel(role) })),
  );

  // --- CRUD de la empresa ------------------------------------------------

  protected readonly showForm = signal(false);
  protected readonly editing = signal<OrganizationMembership | null>(null);
  protected readonly deleting = signal<OrganizationMembership | null>(null);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);

  /** Mensaje del diálogo de confirmación: «¿Confirmas que deseas eliminar {nombre}? …». */
  protected readonly deleteMessage = computed(
    () =>
      `${this.text.delete.confirmLead()} ${this.deleting()?.organization?.name ?? ''}${this.text.delete.confirmTail()}`,
  );

  protected readonly form = this.fb.nonNullable.group({
    name: ['', [Validators.required]],
    slug: ['', [Validators.required]],
  });

  // --- Gestión de miembros ------------------------------------------------

  protected readonly membersFor = signal<OrganizationMembership | null>(null);
  protected readonly members = signal<OrganizationMember[]>([]);
  protected readonly membersLoading = signal(false);
  protected readonly membersError = signal<string | null>(null);
  protected readonly addingMember = signal(false);
  protected readonly removing = signal<OrganizationMember | null>(null);
  protected readonly removingBusy = signal(false);

  protected readonly addMemberForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    role: ['member' as MemberRole, [Validators.required]],
  });

  protected readonly membersTitle = computed(() => {
    this.i18n.activeLang();
    return this.i18n.translate('admin.organizations.members.title', {
      name: this.membersFor()?.organization.name ?? '',
    });
  });

  protected readonly addMemberEmailError = computed<string | null>(() => {
    const control = this.addMemberForm.controls.email;
    if (!control.invalid || (!control.touched && !control.dirty)) {
      return null;
    }
    return control.hasError('required')
      ? this.text.members.add.errors.emailRequired()
      : this.text.members.add.errors.emailInvalid();
  });

  ngOnInit(): void {
    this.load();
  }

  // --- Helpers de presentación --------------------------------------------

  protected roleLabel(role: MemberRole): string {
    return this.i18n.translate(`orgSwitcher.roles.${role}`);
  }

  protected roleVariant(role: MemberRole): 'info' | 'success' | 'neutral' {
    if (role === 'admin') {
      return 'info';
    }
    if (role === 'manager') {
      return 'success';
    }
    return 'neutral';
  }

  protected showError(control: 'name' | 'slug'): boolean {
    const c = this.form.controls[control];
    return c.invalid && (c.touched || c.dirty);
  }

  // --- CRUD ---------------------------------------------------------------

  protected openCreate(): void {
    this.editing.set(null);
    this.formError.set(null);
    this.form.reset({ name: '', slug: '' });
    this.showForm.set(true);
  }

  protected openEdit(item: OrganizationMembership): void {
    this.editing.set(item);
    this.formError.set(null);
    this.form.reset({ name: item.organization.name, slug: item.organization.slug });
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
    const payload = { name: raw.name.trim(), slug: raw.slug.trim() };
    this.saving.set(true);

    const editing = this.editing();
    const request$ = editing
      ? this.service.update(editing.organization.id, payload)
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

  protected askDelete(item: OrganizationMembership): void {
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
    this.service.remove(item.organization.id).subscribe({
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
    this.service.mine().subscribe({
      next: (res) => {
        this.memberships.set(res.data ?? []);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.loadError.set(
          err.status === 0
            ? this.i18n.translate('admin.organizations.errors.network')
            : this.i18n.translate('admin.organizations.errors.loadFailed'),
        );
      },
    });
  }

  // --- Miembros -------------------------------------------------------------

  protected openMembers(item: OrganizationMembership): void {
    this.membersFor.set(item);
    this.membersError.set(null);
    this.addMemberForm.reset({ email: '', role: 'member' });
    this.loadMembers(item.organization.id);
  }

  protected closeMembers(): void {
    this.membersFor.set(null);
    this.members.set([]);
    this.removing.set(null);
  }

  private loadMembers(organizationId: string): void {
    this.membersLoading.set(true);
    this.service.listMembers(organizationId).subscribe({
      next: (res) => {
        this.members.set(res.data ?? []);
        this.membersLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.membersLoading.set(false);
        this.membersError.set(this.messageFor(err));
      },
    });
  }

  protected onAddMember(): void {
    const org = this.membersFor();
    this.membersError.set(null);
    if (!org || this.addMemberForm.invalid) {
      this.addMemberForm.markAllAsTouched();
      return;
    }

    const raw = this.addMemberForm.getRawValue();
    this.addingMember.set(true);
    this.service
      .addMember(org.organization.id, { email: raw.email.trim(), role: raw.role })
      .subscribe({
        next: () => {
          this.addingMember.set(false);
          this.addMemberForm.reset({ email: '', role: 'member' });
          this.loadMembers(org.organization.id);
        },
        error: (err: HttpErrorResponse) => {
          this.addingMember.set(false);
          this.membersError.set(this.messageFor(err));
        },
      });
  }

  protected onRoleChange(member: OrganizationMember, role: string): void {
    const org = this.membersFor();
    if (!org) {
      return;
    }
    this.membersError.set(null);
    this.service
      .updateMemberRole(org.organization.id, member.id, role as MemberRole)
      .subscribe({
        next: () => this.loadMembers(org.organization.id),
        error: (err: HttpErrorResponse) => {
          this.membersError.set(this.messageFor(err));
          // Revierte el <select> a la lista tal como está en el servidor.
          this.loadMembers(org.organization.id);
        },
      });
  }

  protected askRemoveMember(member: OrganizationMember): void {
    this.membersError.set(null);
    this.removing.set(member);
  }

  protected cancelRemoveMember(): void {
    this.removing.set(null);
  }

  protected confirmRemoveMember(): void {
    const org = this.membersFor();
    const member = this.removing();
    if (!org || !member) {
      return;
    }
    this.removingBusy.set(true);
    this.service.removeMember(org.organization.id, member.id).subscribe({
      next: () => {
        this.removingBusy.set(false);
        this.removing.set(null);
        this.loadMembers(org.organization.id);
      },
      error: (err: HttpErrorResponse) => {
        this.removingBusy.set(false);
        this.membersError.set(this.messageFor(err));
      },
    });
  }

  // --- Errores ---------------------------------------------------------------

  private messageFor(err: HttpErrorResponse): string {
    if (err.status === 0) {
      return this.i18n.translate('admin.organizations.errors.network');
    }
    const detail = (err.error as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    return this.i18n.translate('admin.organizations.errors.generic');
  }
}
