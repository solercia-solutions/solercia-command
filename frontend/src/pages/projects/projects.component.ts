import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { RouterLink } from '@angular/router';
import {
  FormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { SolButtonComponent } from '@shared/ui';
import { SolCardComponent } from '@shared/ui';
import { SolDrawerComponent } from '@shared/ui';
import { SolIconComponent } from '@shared/ui';
import { SolInputComponent } from '@shared/ui';
import { SolSelectComponent } from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { ProjectsService } from '@entities/project/projects.service';
import {
  METHODOLOGY_LABELS,
  METHODOLOGY_OPTIONS,
  Methodology,
  Project,
  UpdateProjectPayload,
  statusLabel,
} from '@entities/project/project.model';

@Component({
  selector: 'sol-projects',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    ReactiveFormsModule,
    SolButtonComponent,
    SolCardComponent,
    SolDrawerComponent,
    SolIconComponent,
    SolInputComponent,
    SolSelectComponent,
  ],
  template: `
    <section class="flex flex-col gap-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 class="text-2xl font-semibold text-text">{{ text.title() }}</h1>
          <p class="text-sm text-muted">
            {{ text.subtitle() }}
          </p>
        </div>
        <sol-button
          type="button"
          variant="primary"
          (click)="toggleForm()"
          [ariaLabel]="showForm() ? text.toggleClose() : text.toggleOpen()"
        >
          {{ showForm() ? text.close() : text.create() }}
        </sol-button>
      </div>

      @if (showForm()) {
        <sol-card>
          <h2 class="mb-4 text-lg font-semibold text-text">{{ text.formTitle() }}</h2>
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
                <p class="mt-1 text-xs text-danger">
                  {{ text.nameRequired() }}
                </p>
              }
            </div>

            <div>
              <sol-input
                [label]="text.descriptionLabel()"
                [placeholder]="text.descriptionPlaceholder()"
                formControlName="description"
              ></sol-input>
            </div>

            <div>
              <label class="block">
                <span class="mb-1.5 block text-sm font-medium text-text"
                  >{{ text.methodologyLabel() }}</span
                >
                <select
                  formControlName="methodology"
                  class="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text
                         transition-colors focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40"
                >
                  @for (option of methodologyOptions; track option.value) {
                    <option [value]="option.value">{{ option.label }}</option>
                  }
                </select>
              </label>
            </div>

            <div>
              <sol-select
                [label]="text.parentLabel()"
                [placeholder]="text.parentPlaceholder()"
                [options]="createParentOptions()"
                formControlName="parent"
              ></sol-select>
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
              <sol-button
                type="button"
                variant="ghost"
                (click)="toggleForm()"
              >
                {{ text.cancel() }}
              </sol-button>
              <sol-button
                type="submit"
                variant="primary"
                [disabled]="saving()"
              >
                {{ saving() ? text.saving() : text.save() }}
              </sol-button>
            </div>
          </form>
        </sol-card>
      }

      @if (loading()) {
        <p class="text-sm text-muted">{{ text.loading() }}</p>
      } @else if (loadError()) {
        <div
          role="alert"
          class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {{ loadError() }}
        </div>
      } @else if (projects().length === 0) {
        <sol-card>
          <div class="py-8 text-center">
            <p class="text-base font-medium text-text">
              {{ text.emptyTitle() }}
            </p>
            <p class="mt-1 text-sm text-muted">
              {{ text.emptySubtitle() }}
            </p>
          </div>
        </sol-card>
      } @else {
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          @for (project of projects(); track project.id) {
            <div class="relative">
              <a
                [routerLink]="['/projects', project.id]"
                class="block rounded-xl transition-transform hover:-translate-y-0.5
                       focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
                [attr.aria-label]="cardAria(project.name)"
              >
              <sol-card>
                <div class="flex h-full flex-col gap-3">
                  <div class="flex items-start justify-between gap-2">
                    <h3 class="text-base font-semibold text-text">
                      {{ project.name }}
                    </h3>
                    <span
                      class="shrink-0 rounded-full bg-brand/10 px-2.5 py-0.5 text-xs font-medium text-brand"
                    >
                      {{ methodologyLabel(project.methodology) }}
                    </span>
                  </div>
                  <p class="flex-1 text-sm text-muted">
                    {{ project.description || text.noDescription() }}
                  </p>
                  <div class="flex items-center gap-2 pt-1 pr-9">
                    <span
                      class="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-2.5 py-0.5 text-xs font-medium text-success"
                    >
                      <span
                        class="h-1.5 w-1.5 rounded-full bg-success"
                        aria-hidden="true"
                      ></span>
                      {{ statusText(project.status) }}
                    </span>
                  </div>
                </div>
              </sol-card>
              </a>
              <!-- Fuera del <a> (hermano posicionado) para no anidar controles
                   interactivos dentro del enlace de la tarjeta. -->
              <button
                type="button"
                class="absolute bottom-3 right-3 inline-flex h-8 w-8 items-center justify-center
                       rounded-lg text-muted transition-colors hover:bg-brand/10 hover:text-brand
                       focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
                [attr.aria-label]="editAria(project.name)"
                (click)="openEdit(project)"
              >
                <sol-icon name="pencil" size="sm" />
              </button>
            </div>
          }
        </div>
      }
    </section>

    <sol-drawer
      [open]="editOpen()"
      [title]="text.editTitle()"
      size="md"
      (closed)="closeEdit()"
    >
      <form
        [formGroup]="editForm"
        (ngSubmit)="onEditSubmit()"
        class="flex flex-col gap-4"
        novalidate
      >
        <div>
          <sol-input
            [label]="text.nameLabel()"
            [placeholder]="text.namePlaceholder()"
            formControlName="name"
          ></sol-input>
          @if (showEditError('name')) {
            <p class="mt-1 text-xs text-danger">
              {{ text.nameRequired() }}
            </p>
          }
        </div>

        <div>
          <sol-input
            [label]="text.descriptionLabel()"
            [placeholder]="text.descriptionPlaceholder()"
            formControlName="description"
          ></sol-input>
        </div>

        <div>
          <sol-input
            [label]="text.codeLabel()"
            [placeholder]="text.codePlaceholder()"
            formControlName="code"
          ></sol-input>
        </div>

        <div>
          <sol-select
            [label]="text.parentLabel()"
            [placeholder]="text.parentPlaceholder()"
            [options]="editParentOptions()"
            formControlName="parent"
          ></sol-select>
        </div>

        @if (editError()) {
          <div
            role="alert"
            class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {{ editError() }}
          </div>
        }

        <div class="flex items-center justify-end gap-2 pt-2">
          <sol-button type="button" variant="ghost" (click)="closeEdit()">
            {{ text.cancel() }}
          </sol-button>
          <sol-button
            type="submit"
            variant="primary"
            [disabled]="editSaving()"
          >
            {{ editSaving() ? text.saving() : text.editSave() }}
          </sol-button>
        </div>
      </form>
    </sol-drawer>
  `,
})
export class ProjectsComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly projectsService = inject(ProjectsService);
  private readonly i18n = inject(I18nService);

  /** Textos estáticos de la vista resueltos por i18n (reactivos al idioma). */
  protected readonly text = {
    title: this.i18n.t('projects.title'),
    subtitle: this.i18n.t('projects.subtitle'),
    toggleClose: this.i18n.t('projects.toggle.closeAria'),
    toggleOpen: this.i18n.t('projects.toggle.openAria'),
    close: this.i18n.t('projects.toggle.close'),
    create: this.i18n.t('projects.toggle.create'),
    formTitle: this.i18n.t('projects.form.title'),
    nameLabel: this.i18n.t('projects.form.nameLabel'),
    namePlaceholder: this.i18n.t('projects.form.namePlaceholder'),
    nameRequired: this.i18n.t('projects.form.nameRequired'),
    descriptionLabel: this.i18n.t('projects.form.descriptionLabel'),
    descriptionPlaceholder: this.i18n.t('projects.form.descriptionPlaceholder'),
    methodologyLabel: this.i18n.t('projects.form.methodologyLabel'),
    codeLabel: this.i18n.t('projects.form.codeLabel'),
    codePlaceholder: this.i18n.t('projects.form.codePlaceholder'),
    parentLabel: this.i18n.t('projects.form.parentLabel'),
    parentNone: this.i18n.t('projects.form.parentNone'),
    parentPlaceholder: this.i18n.t('projects.form.parentPlaceholder'),
    cancel: this.i18n.t('projects.actions.cancel'),
    save: this.i18n.t('projects.actions.save'),
    saving: this.i18n.t('projects.actions.saving'),
    editTitle: this.i18n.t('projects.edit.title'),
    editSave: this.i18n.t('projects.edit.save'),
    loading: this.i18n.t('projects.loading'),
    emptyTitle: this.i18n.t('projects.empty.title'),
    emptySubtitle: this.i18n.t('projects.empty.subtitle'),
    noDescription: this.i18n.t('projects.noDescription'),
  } as const;

  protected readonly methodologyOptions = METHODOLOGY_OPTIONS;

  protected readonly projects = signal<Project[]>([]);
  protected readonly loading = signal(false);
  protected readonly loadError = signal<string | null>(null);

  protected readonly showForm = signal(false);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);

  /** Proyecto actualmente en edición (dueño del drawer F1/F2). */
  protected readonly editing = signal<Project | null>(null);
  protected readonly editOpen = computed(() => this.editing() !== null);
  protected readonly editSaving = signal(false);
  protected readonly editError = signal<string | null>(null);

  protected readonly form = this.fb.nonNullable.group({
    name: ['', [Validators.required]],
    description: [''],
    methodology: ['planner' as Methodology, [Validators.required]],
    // '' = sin padre (proyecto raíz).
    parent: [''],
  });

  protected readonly editForm = this.fb.nonNullable.group({
    name: ['', [Validators.required]],
    description: [''],
    code: [''],
    parent: [''],
  });

  /** Opciones del select de padre al CREAR: raíz + todos los proyectos. */
  protected readonly createParentOptions = computed(() => [
    { value: '', label: this.text.parentNone() },
    ...this.projects().map((p) => ({ value: p.id, label: p.name })),
  ]);

  /** Opciones del select de padre al EDITAR: excluye el propio proyecto. */
  protected readonly editParentOptions = computed(() => {
    const editingId = this.editing()?.id;
    return [
      { value: '', label: this.text.parentNone() },
      ...this.projects()
        .filter((p) => p.id !== editingId)
        .map((p) => ({ value: p.id, label: p.name })),
    ];
  });

  ngOnInit(): void {
    this.loadProjects();
  }

  protected methodologyLabel(methodology: Methodology): string {
    return METHODOLOGY_LABELS[methodology] ?? methodology;
  }

  protected statusText(status: string): string {
    return statusLabel(status);
  }

  protected cardAria(name: string): string {
    return this.i18n.translate('projects.cardAria', { name });
  }

  protected editAria(name: string): string {
    return this.i18n.translate('projects.edit.openAria', { name });
  }

  protected toggleForm(): void {
    this.formError.set(null);
    this.showForm.update((open) => !open);
    if (!this.showForm()) {
      this.form.reset({
        name: '',
        description: '',
        methodology: 'planner',
        parent: '',
      });
    }
  }

  protected showError(control: 'name'): boolean {
    const c = this.form.controls[control];
    return c.invalid && (c.touched || c.dirty);
  }

  protected showEditError(control: 'name'): boolean {
    const c = this.editForm.controls[control];
    return c.invalid && (c.touched || c.dirty);
  }

  protected onSubmit(): void {
    this.formError.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const { name, description, methodology, parent } = this.form.getRawValue();
    this.saving.set(true);

    this.projectsService
      .create({
        name: name.trim(),
        description: description.trim() || null,
        methodology,
        parent_project_id: parent || null,
      })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.showForm.set(false);
          this.form.reset({
            name: '',
            description: '',
            methodology: 'planner',
            parent: '',
          });
          this.loadProjects();
        },
        error: (err: HttpErrorResponse) => {
          this.saving.set(false);
          this.formError.set(
            this.domainErrorMessage(err, 'projects.errors.create'),
          );
        },
      });
  }

  protected openEdit(project: Project): void {
    this.editError.set(null);
    this.editForm.reset({
      name: project.name,
      description: project.description ?? '',
      code: project.code ?? '',
      parent: project.parent_project_id ?? '',
    });
    this.editing.set(project);
  }

  protected closeEdit(): void {
    if (this.editSaving()) {
      return;
    }
    this.editing.set(null);
    this.editError.set(null);
  }

  /**
   * Guarda la edición en dos pasos: PATCH /projects/:id con los campos que
   * cambiaron y luego PATCH /projects/:id/parent solo si el padre cambió.
   * Los errores de dominio (código duplicado, ciclo, profundidad…) se
   * muestran dentro del formulario, nunca como toast genérico.
   */
  protected async onEditSubmit(): Promise<void> {
    const project = this.editing();
    if (!project) {
      return;
    }
    this.editError.set(null);
    if (this.editForm.invalid) {
      this.editForm.markAllAsTouched();
      return;
    }

    const { name, description, code, parent } = this.editForm.getRawValue();
    const payload: UpdateProjectPayload = {};

    const trimmedName = name.trim();
    if (trimmedName && trimmedName !== project.name) {
      payload.name = trimmedName;
    }
    const trimmedDescription = description.trim();
    if ((trimmedDescription || null) !== (project.description ?? null)) {
      payload.description = trimmedDescription || null;
    }
    const trimmedCode = code.trim().toUpperCase();
    if (trimmedCode && trimmedCode !== (project.code ?? '')) {
      payload.code = trimmedCode;
    }

    const newParent = parent || null;
    const parentChanged = newParent !== (project.parent_project_id ?? null);

    if (Object.keys(payload).length === 0 && !parentChanged) {
      this.closeEdit();
      return;
    }

    this.editSaving.set(true);
    // true cuando el PATCH de campos ya aplicó: distingue el fallo parcial
    // (campos guardados, reparent fallido) del fallo total.
    let fieldsSaved = false;
    try {
      if (Object.keys(payload).length > 0) {
        await firstValueFrom(this.projectsService.update(project.id, payload));
        fieldsSaved = true;
        // Resincroniza el proyecto en edición con lo ya guardado: si el
        // reparent falla, reintentar recalcula el diff contra este estado y
        // solo repite el movimiento de padre (no re-envía los campos).
        this.editing.set({
          ...project,
          ...(payload.name !== undefined ? { name: payload.name } : {}),
          ...(payload.description !== undefined
            ? { description: payload.description }
            : {}),
          ...(payload.code !== undefined ? { code: payload.code } : {}),
        });
      }
      if (parentChanged) {
        await firstValueFrom(
          this.projectsService.reparent(project.id, newParent),
        );
      }
      this.editSaving.set(false);
      this.editing.set(null);
      this.loadProjects();
    } catch (err) {
      this.editSaving.set(false);
      const reason = this.domainErrorMessage(
        err as HttpErrorResponse,
        'projects.errors.update',
      );
      // Fallo parcial: los campos ya quedaron guardados y solo falló el
      // cambio de padre — el mensaje debe decirlo, no leer como fallo total.
      this.editError.set(
        fieldsSaved && parentChanged
          ? this.i18n.translate('projects.errors.reparentAfterSave', {
              reason,
            })
          : reason,
      );
      // Si el PATCH de campos alcanzó a aplicarse antes del error del
      // reparent, la lista debe reflejarlo aunque el drawer siga abierto.
      this.loadProjects();
    }
  }

  /** Traduce el `code` de dominio del backend a un mensaje claro del form. */
  private domainErrorMessage(
    err: HttpErrorResponse,
    fallbackKey: string,
  ): string {
    if (err.status === 0) {
      return this.i18n.translate('projects.errors.network');
    }
    if (err.status === 403) {
      return this.i18n.translate('projects.errors.forbidden');
    }
    const code: string | undefined = err.error?.code;
    const byCode: Record<string, string> = {
      project_code_taken: 'projects.errors.codeTaken',
      methodology_not_editable: 'projects.errors.methodologyNotEditable',
      self_parent: 'projects.errors.selfParent',
      parent_not_found: 'projects.errors.parentNotFound',
      project_cycle: 'projects.errors.projectCycle',
      max_depth_exceeded: 'projects.errors.maxDepth',
    };
    return this.i18n.translate(code && byCode[code] ? byCode[code] : fallbackKey);
  }

  private loadProjects(): void {
    this.loading.set(true);
    this.loadError.set(null);

    this.projectsService.list().subscribe({
      next: (res) => {
        this.projects.set(res.data ?? []);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.loadError.set(
          err.status === 0
            ? this.i18n.translate('projects.errors.network')
            : this.i18n.translate('projects.errors.load'),
        );
      },
    });
  }
}
