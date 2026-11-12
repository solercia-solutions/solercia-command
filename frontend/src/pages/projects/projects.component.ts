import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  FormBuilder,
  FormControl,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { Subscription, firstValueFrom } from 'rxjs';
import { SolButtonComponent } from '@shared/ui';
import { SolCardComponent } from '@shared/ui';
import { SolDrawerComponent } from '@shared/ui';
import { SolIconComponent } from '@shared/ui';
import { SolInputComponent } from '@shared/ui';
import { SolSelectComponent, SolSelectOption, SolSpinnerComponent } from '@shared/ui';
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
import {
  ProjectsFilterControls,
  ProjectsFiltersComponent,
} from './projects-filters.component';

/** Valor de `?year=` que significa «Todos los años» (lo comparte el espacio de trabajo). */
const ALL_YEARS_PARAM = 'all';

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
    SolSpinnerComponent,
    ProjectsFiltersComponent,
  ],
  styles: [
    `
      /* Encabezado al estilo PANDORA (igual que el espacio de trabajo):
         título + conteo a la izquierda, acción principal en la misma fila. */
      .pj-header {
        display: flex;
        flex-wrap: wrap;
        align-items: flex-start;
        justify-content: space-between;
        gap: var(--sol-space-md, 16px);
      }

      .pj-header__title {
        display: flex;
        flex-direction: column;
        gap: var(--sol-space-xs, 4px);
        min-width: 0;
      }

      .pj-title {
        margin: 0;
        font-size: var(--sol-font-size-xl, 1.25rem);
        color: var(--sol-color-text-primary);
      }

      .pj-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: var(--sol-space-sm, 8px);
        padding: var(--sol-space-lg, 24px) var(--sol-space-md, 16px);
        text-align: center;
        font-size: var(--sol-font-size-sm, 0.875rem);
        color: var(--sol-color-text-secondary);
      }

      @media (max-width: 767px) {
        .pj-header__action {
          width: 100%;
        }

        .pj-header__action ::ng-deep button {
          width: 100%;
          min-height: var(--sol-size-control-touch, 44px);
        }
      }
    `,
  ],
  template: `
    <section class="flex flex-col gap-6">
      <div class="pj-header">
        <div class="pj-header__title">
          <h1 class="pj-title sol-display">{{ text.title() }}</h1>
          <p class="text-sm text-muted" aria-live="polite">
            @if (!loading() && !loadError()) {
              {{ countText() }}
            } @else {
              {{ text.subtitle() }}
            }
          </p>
        </div>
        <sol-button
          class="pj-header__action"
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

      <sol-projects-filters
        [controls]="filterControls"
        [yearOptions]="yearOptions()"
        [methodologyOptions]="methodologyFilterOptions()"
        [yearsUnavailable]="yearsUnavailable()"
        [activeCount]="activeFilterCount()"
        (cleared)="clearFilters()"
      />

      <!-- Estados: cargando, error (con reintento), sin coincidencias por
           filtro, sin proyectos en el año y vacío legítimo. «Sin datos»
           nunca se muestra como «falló». -->
      @if (loading()) {
        <div class="pj-state" role="status" aria-live="polite">
          <sol-spinner size="md" />
          <p>{{ text.loading() }}</p>
        </div>
      } @else if (loadError()) {
        <div
          role="alert"
          class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          <span>{{ loadError() }}</span>
          <sol-button type="button" variant="secondary" size="sm" (click)="loadProjects()">
            {{ text.retry() }}
          </sol-button>
        </div>
      } @else if (visibleProjects().length === 0) {
        <sol-card>
          <div class="flex flex-col items-center gap-3 py-6 text-center">
            @if (activeFilterCount() > 0) {
              <p class="text-sm font-medium text-text" role="status">{{ text.noMatchTitle() }}</p>
              <p class="text-sm text-muted">{{ text.noMatchHint() }}</p>
              <sol-button type="button" variant="secondary" (click)="clearFilters()">
                {{ text.clearFilters() }}
              </sol-button>
            } @else if (selectedYear() !== null) {
              <p class="text-sm text-muted" role="status">{{ emptyForYearText() }}</p>
              <sol-button type="button" variant="secondary" (click)="yearControl.setValue('')">
                {{ text.showAllYears() }}
              </sol-button>
            } @else {
              <p class="text-base font-medium text-text" role="status">
                {{ text.emptyTitle() }}
              </p>
              <p class="text-sm text-muted">{{ text.emptySubtitle() }}</p>
              @if (!showForm()) {
                <sol-button type="button" variant="primary" (click)="toggleForm()">
                  {{ text.create() }}
                </sol-button>
              }
            }
          </div>
        </sol-card>
      } @else {
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          @for (project of visibleProjects(); track project.id) {
            <div class="relative">
              <a
                [routerLink]="['/projects', project.id]"
                [queryParams]="projectQueryParams()"
                class="block h-full rounded-xl transition-transform hover:-translate-y-0.5
                       focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
                [attr.aria-label]="cardAria(project.name)"
              >
              <sol-card class="block h-full">
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
                  @if (project.description) {
                    <p class="text-sm text-muted">{{ project.description }}</p>
                  }
                  <p class="mt-auto text-sm text-text">
                    <span class="font-medium">{{ tasksText(project) }}</span>
                    @if (project.task_count) {
                      <span class="text-muted"> · {{ openText(project) }}</span>
                    }
                  </p>
                  <div class="flex flex-wrap items-center gap-2 pr-9">
                    <span
                      class="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-2.5 py-0.5 text-xs font-medium text-success"
                    >
                      <span
                        class="h-1.5 w-1.5 rounded-full bg-success"
                        aria-hidden="true"
                      ></span>
                      {{ statusText(project.status) }}
                    </span>
                    @if (project.code) {
                      <span class="text-xs text-muted">{{ project.code }}</span>
                    }
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
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

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
    retry: this.i18n.t('projects.retry'),
    noMatchTitle: this.i18n.t('projects.noMatch.title'),
    noMatchHint: this.i18n.t('projects.noMatch.hint'),
    clearFilters: this.i18n.t('projects.filters.clear'),
    showAllYears: this.i18n.t('projects.showAllYears'),
  } as const;

  protected readonly methodologyOptions = METHODOLOGY_OPTIONS;

  /** Proyectos devueltos por el backend para el año elegido (sin los filtros locales). */
  protected readonly projects = signal<Project[]>([]);
  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);
  private projectsRequest?: Subscription;

  /**
   * Todos los proyectos (sin año) para el selector de «Proyecto padre»: con un
   * año elegido, `projects()` solo trae los que tienen tareas ese año. Se carga
   * al abrir el formulario o la edición; `null` mientras no haga falta.
   */
  private readonly allProjects = signal<Project[] | null>(null);
  private readonly parentSource = computed(() =>
    this.selectedYear() === null ? this.projects() : (this.allProjects() ?? this.projects()),
  );

  /* ---- Filtros (S05) -----------------------------------------------------
   * El año viaja al backend (`GET /projects?year=`): un proyecto «es de un
   * año» si tiene tareas creadas ese año en hora de Bogotá, igual que el
   * filtro de tareas. Metodología y búsqueda filtran en el cliente sobre la
   * lista ya cargada (es corta y no está paginada). */
  protected readonly yearControl = new FormControl<string>('', { nonNullable: true });
  protected readonly filterControls: ProjectsFilterControls = {
    year: this.yearControl,
    methodology: new FormControl<string>('', { nonNullable: true }),
    q: new FormControl<string>('', { nonNullable: true }),
  };
  protected readonly availableYears = signal<number[]>([]);
  protected readonly yearsUnavailable = signal(false);
  protected readonly selectedYear = signal<number | null>(null);
  /** Año preseleccionado al abrir (el que «Limpiar filtros» restaura). */
  private readonly defaultYear = signal<number | null>(null);
  private readonly filterMethodology = signal('');
  private readonly filterQ = signal('');

  protected readonly yearOptions = computed<SolSelectOption[]>(() =>
    this.availableYears().map((year) => ({ value: String(year), label: String(year) })),
  );

  /** Solo las metodologías presentes en la lista cargada (valores reales). */
  protected readonly methodologyFilterOptions = computed<SolSelectOption[]>(() => {
    const present = new Set(this.projects().map((project) => project.methodology));
    return METHODOLOGY_OPTIONS.filter((option) => present.has(option.value)).map((option) => ({
      value: option.value,
      label: option.label,
    }));
  });

  protected readonly activeFilterCount = computed(() => {
    const yearChanged = this.selectedYear() !== this.defaultYear() ? 1 : 0;
    return (
      yearChanged + [this.filterMethodology(), this.filterQ()].filter((value) => value !== '').length
    );
  });

  protected readonly visibleProjects = computed(() => {
    const methodology = this.filterMethodology();
    const needle = this.normalize(this.filterQ().trim());
    return this.projects().filter(
      (project) =>
        (!methodology || project.methodology === methodology) &&
        (!needle ||
          this.normalize(project.name).includes(needle) ||
          this.normalize(project.code ?? '').includes(needle)),
    );
  });

  /** `?year=` que se lleva al entrar a un proyecto: el workspace lo preselecciona. */
  protected readonly projectQueryParams = computed(() => ({
    year: this.selectedYear() ?? ALL_YEARS_PARAM,
  }));

  protected readonly countText = computed(() => {
    this.i18n.activeLang();
    const total = this.projects().length;
    const shown = this.visibleProjects().length;
    const year = this.selectedYear();
    if (total === 0) {
      return this.i18n.translate('projects.count.zero');
    }
    if (shown !== total) {
      return this.i18n.translate('projects.count.filtered', { shown, total });
    }
    if (year !== null) {
      return total === 1
        ? this.i18n.translate('projects.count.yearOne', { year })
        : this.i18n.translate('projects.count.yearOther', { count: total, year });
    }
    return total === 1
      ? this.i18n.translate('projects.count.one')
      : this.i18n.translate('projects.count.other', { count: total });
  });

  protected readonly emptyForYearText = computed(() => {
    this.i18n.activeLang();
    return this.i18n.translate('projects.emptyForYear', { year: this.selectedYear() });
  });

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
    ...this.parentSource().map((p) => ({ value: p.id, label: p.name })),
  ]);

  /** Opciones del select de padre al EDITAR: excluye el propio proyecto. */
  protected readonly editParentOptions = computed(() => {
    const editingId = this.editing()?.id;
    return [
      { value: '', label: this.text.parentNone() },
      ...this.parentSource()
        .filter((p) => p.id !== editingId)
        .map((p) => ({ value: p.id, label: p.name })),
    ];
  });

  constructor() {
    this.yearControl.valueChanges.pipe(takeUntilDestroyed()).subscribe((value) => {
      this.selectedYear.set(value ? Number(value) : null);
      this.syncYearParam();
      this.loadProjects();
    });
    this.filterControls.methodology.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe((value) => this.filterMethodology.set(value));
    this.filterControls.q.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe((value) => this.filterQ.set(value));
  }

  ngOnInit(): void {
    this.loadYearsThenProjects();
  }

  protected tasksText(project: Project): string {
    this.i18n.activeLang();
    const count = project.task_count ?? 0;
    const year = this.selectedYear();
    if (count === 0) {
      return this.i18n.translate('projects.card.tasksZero');
    }
    if (year !== null) {
      return count === 1
        ? this.i18n.translate('projects.card.tasksYearOne', { year })
        : this.i18n.translate('projects.card.tasksYearOther', { count, year });
    }
    return count === 1
      ? this.i18n.translate('projects.card.tasksOne')
      : this.i18n.translate('projects.card.tasksOther', { count });
  }

  protected openText(project: Project): string {
    const open = project.open_task_count ?? 0;
    if (open === 0) {
      return this.i18n.translate('projects.card.openZero');
    }
    return open === 1
      ? this.i18n.translate('projects.card.openOne')
      : this.i18n.translate('projects.card.openOther', { count: open });
  }

  /** Restaura el año preseleccionado y quita metodología y búsqueda (una sola consulta). */
  protected clearFilters(): void {
    const year = this.defaultYear();
    const yearChanged = this.selectedYear() !== year;
    this.filterControls.methodology.setValue('');
    this.filterControls.q.setValue('');
    if (yearChanged) {
      // valueChanges sincroniza la URL y recarga.
      this.yearControl.setValue(year === null ? '' : String(year));
    }
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
    if (this.showForm()) {
      this.ensureAllProjects();
    }
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
        next: (res) => {
          this.saving.set(false);
          this.showForm.set(false);
          this.allProjects.set(null);
          this.form.reset({
            name: '',
            description: '',
            methodology: 'planner',
            parent: '',
          });
          // Un proyecto nuevo no tiene tareas: con un año elegido no saldría
          // en la lista. Se abre directamente para agregar la primera tarea.
          if (this.selectedYear() !== null && res?.data?.id) {
            void this.router.navigate(['/projects', res.data.id], {
              queryParams: { year: ALL_YEARS_PARAM },
            });
            return;
          }
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
    this.ensureAllProjects();
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
      this.allProjects.set(null);
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

  /**
   * Carga los años con tareas y preselecciona el `?year=` de la URL si es
   * válido (`all` = todos); si no, el año actual cuando tiene datos, y si no
   * el más reciente. Si la consulta de años falla se listan todos los
   * proyectos y se avisa en línea: la vista nunca se queda vacía por eso.
   */
  private loadYearsThenProjects(): void {
    this.projectsService.years().subscribe({
      next: (res) => {
        const years = res.data ?? [];
        this.availableYears.set(years);
        this.yearsUnavailable.set(false);
        const fallback = this.naturalDefaultYear(years);
        this.applyInitialYear(fallback, this.requestedYear(years, fallback));
      },
      error: () => {
        this.availableYears.set([]);
        this.yearsUnavailable.set(true);
        this.applyInitialYear(null, null);
      },
    });
  }

  /** Año por defecto: el actual si tiene datos; si no, el más reciente. */
  private naturalDefaultYear(years: number[]): number | null {
    const current = new Date().getFullYear();
    return years.includes(current) ? current : (years[0] ?? null);
  }

  /** `?year=` de la URL si es válido (`all` = todos); si no, `fallback`. */
  private requestedYear(years: number[], fallback: number | null): number | null {
    const requested = this.route.snapshot.queryParamMap.get('year');
    if (requested === ALL_YEARS_PARAM) {
      return null;
    }
    if (requested !== null && years.includes(Number(requested))) {
      return Number(requested);
    }
    return fallback;
  }

  /**
   * `defaultYear` es el que restaura «Limpiar filtros» (el natural); el
   * seleccionado puede venir de la URL, y si difiere cuenta como filtro activo.
   */
  private applyInitialYear(defaultYear: number | null, year: number | null): void {
    this.defaultYear.set(defaultYear);
    this.selectedYear.set(year);
    this.yearControl.setValue(year === null ? '' : String(year), { emitEvent: false });
    this.loadProjects();
  }

  /** Refleja el año en la URL (sin nueva entrada de historial) para volver a él. */
  private syncYearParam(): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { year: this.selectedYear() ?? ALL_YEARS_PARAM },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  private ensureAllProjects(): void {
    if (this.selectedYear() === null || this.allProjects() !== null) {
      return;
    }
    this.projectsService.list().subscribe({
      next: (res) => this.allProjects.set(res.data ?? []),
      // Sin la lista completa el selector usa la del año: se puede elegir
      // padre entre los visibles, nunca se bloquea el formulario.
      error: () => this.allProjects.set(null),
    });
  }

  private normalize(value: string): string {
    return value
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase();
  }

  protected loadProjects(): void {
    this.loading.set(true);
    this.loadError.set(null);
    // Un cambio de año con otra carga en vuelo la cancela: la respuesta
    // tardía de otro año no puede pisar la vigente.
    this.projectsRequest?.unsubscribe();
    const year = this.selectedYear();

    this.projectsRequest = this.projectsService.list(year !== null ? { year } : {}).subscribe({
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
