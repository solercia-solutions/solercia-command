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
import { ButtonComponent } from '@shared/ui/button.component';
import { CardComponent } from '@shared/ui/card.component';
import { TextInputComponent } from '@shared/ui/text-input.component';
import { ProjectsService } from '@entities/project/projects.service';
import {
  METHODOLOGY_LABELS,
  METHODOLOGY_OPTIONS,
  Methodology,
  Project,
  statusLabel,
} from '@entities/project/project.model';

@Component({
  selector: 'bk-projects',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    ReactiveFormsModule,
    ButtonComponent,
    CardComponent,
    TextInputComponent,
  ],
  template: `
    <section class="flex flex-col gap-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 class="text-2xl font-semibold text-text">Proyectos</h1>
          <p class="text-sm text-muted">
            Administra los proyectos de tu organización.
          </p>
        </div>
        <bk-button
          type="button"
          variant="primary"
          (click)="toggleForm()"
          [ariaLabel]="showForm() ? 'Cierra el formulario' : 'Crea un proyecto'"
        >
          {{ showForm() ? 'Cerrar' : 'Crear proyecto' }}
        </bk-button>
      </div>

      @if (showForm()) {
        <bk-card>
          <h2 class="mb-4 text-lg font-semibold text-text">Crea tu proyecto</h2>
          <form
            [formGroup]="form"
            (ngSubmit)="onSubmit()"
            class="flex flex-col gap-4"
            novalidate
          >
            <div>
              <bk-text-input
                label="Nombre"
                placeholder="Ej. Plataforma de pagos"
                formControlName="name"
              ></bk-text-input>
              @if (showError('name')) {
                <p class="mt-1 text-xs text-danger">
                  El nombre es obligatorio.
                </p>
              }
            </div>

            <div>
              <bk-text-input
                label="Descripción"
                placeholder="Describe brevemente el objetivo (opcional)"
                formControlName="description"
              ></bk-text-input>
            </div>

            <div>
              <label class="block">
                <span class="mb-1.5 block text-sm font-medium text-text"
                  >Metodología</span
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
              <bk-button
                type="button"
                variant="ghost"
                (click)="toggleForm()"
              >
                Cancelar
              </bk-button>
              <bk-button
                type="submit"
                variant="primary"
                [disabled]="saving()"
              >
                {{ saving() ? 'Guardando…' : 'Guardar proyecto' }}
              </bk-button>
            </div>
          </form>
        </bk-card>
      }

      @if (loading()) {
        <p class="text-sm text-muted">Cargando proyectos…</p>
      } @else if (loadError()) {
        <div
          role="alert"
          class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {{ loadError() }}
        </div>
      } @else if (projects().length === 0) {
        <bk-card>
          <div class="py-8 text-center">
            <p class="text-base font-medium text-text">
              Todavía no tienes proyectos.
            </p>
            <p class="mt-1 text-sm text-muted">
              Crea tu primer proyecto para empezar a organizar el trabajo.
            </p>
          </div>
        </bk-card>
      } @else {
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          @for (project of projects(); track project.id) {
            <a
              [routerLink]="['/projects', project.id]"
              class="block rounded-xl transition-transform hover:-translate-y-0.5
                     focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
              [attr.aria-label]="'Abre el proyecto ' + project.name"
            >
            <bk-card>
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
                  {{ project.description || 'Sin descripción.' }}
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
            </bk-card>
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
              ? 'No fue posible conectar con el servidor. Inténtalo de nuevo.'
              : 'No se pudo crear el proyecto. Revisa los datos e inténtalo de nuevo.',
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
            ? 'No fue posible conectar con el servidor. Inténtalo de nuevo.'
            : 'No se pudieron cargar los proyectos. Inténtalo más tarde.',
        );
      },
    });
  }
}
