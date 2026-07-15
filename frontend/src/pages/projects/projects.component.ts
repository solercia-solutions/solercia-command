import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
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
import { SolButtonComponent } from '@shared/ui';
import { SolCardComponent } from '@shared/ui';
import { SolInputComponent } from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { ProjectsService } from '@entities/project/projects.service';
import {
  METHODOLOGY_LABELS,
  METHODOLOGY_OPTIONS,
  Methodology,
  Project,
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
    SolInputComponent,
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
                <div class="flex items-center gap-2 pt-1">
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
          }
        </div>
      }
    </section>
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
    cancel: this.i18n.t('projects.actions.cancel'),
    save: this.i18n.t('projects.actions.save'),
    saving: this.i18n.t('projects.actions.saving'),
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

  protected readonly form = this.fb.nonNullable.group({
    name: ['', [Validators.required]],
    description: [''],
    methodology: ['planner' as Methodology, [Validators.required]],
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

  protected toggleForm(): void {
    this.formError.set(null);
    this.showForm.update((open) => !open);
    if (!this.showForm()) {
      this.form.reset({
        name: '',
        description: '',
        methodology: 'planner',
      });
    }
  }

  protected showError(control: 'name'): boolean {
    const c = this.form.controls[control];
    return c.invalid && (c.touched || c.dirty);
  }

  protected onSubmit(): void {
    this.formError.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const { name, description, methodology } = this.form.getRawValue();
    this.saving.set(true);

    this.projectsService
      .create({
        name: name.trim(),
        description: description.trim() || null,
        methodology,
      })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.showForm.set(false);
          this.form.reset({
            name: '',
            description: '',
            methodology: 'planner',
          });
          this.loadProjects();
        },
        error: (err: HttpErrorResponse) => {
          this.saving.set(false);
          this.formError.set(
            err.status === 0
              ? this.i18n.translate('projects.errors.network')
              : this.i18n.translate('projects.errors.create'),
          );
        },
      });
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
