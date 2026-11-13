import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { forkJoin } from 'rxjs';
import { SolButtonComponent, SolSelectComponent, SolSpinnerComponent } from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { AlertService } from '@shared/lib/alerts';
import { readApiError } from '@shared/lib/api-error';
import { GitlabService } from '@entities/gitlab/gitlab.service';
import { GitlabRepository } from '@entities/gitlab/gitlab.model';
import { ProjectsService } from '@entities/project/projects.service';
import { Project } from '@entities/project/project.model';

/**
 * Vinculación de repositorios de GitLab con proyectos de Command, dentro de la
 * tarjeta del conector GitLab. La persona no escribe rutas: elige el proyecto
 * (el primero ya viene seleccionado) y marca los repositorios que el token
 * puede leer; los ya vinculados aparecen marcados.
 */
@Component({
  selector: 'sol-gitlab-repositories',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, SolButtonComponent, SolSelectComponent, SolSpinnerComponent],
  template: `
    <div class="gr">
      <h3 class="gr__title">{{ text.title() }}</h3>

      @if (loading()) {
        <div class="gr__state" role="status" aria-live="polite">
          <sol-spinner size="sm" />
          <span>{{ text.loading() }}</span>
        </div>
      } @else if (loadError(); as message) {
        <div class="gr__alert" role="alert">
          <span>{{ message }}</span>
          <sol-button type="button" variant="secondary" size="sm" (clicked)="load()">
            {{ text.retry() }}
          </sol-button>
        </div>
      } @else if (projects().length === 0) {
        <p class="gr__muted">{{ text.noProjects() }}</p>
      } @else if (repositories().length === 0) {
        <p class="gr__muted">{{ text.noRepositories() }}</p>
      } @else {
        <sol-select
          [label]="text.projectLabel()"
          [options]="projectOptions()"
          [ngModel]="projectId()"
          (ngModelChange)="selectProject($event)"
        />

        <input
          type="search"
          class="gr__search"
          [placeholder]="text.searchPlaceholder()"
          [attr.aria-label]="text.searchPlaceholder()"
          [ngModel]="query()"
          (ngModelChange)="query.set($event)"
        />

        @if (mappingLoading()) {
          <div class="gr__state" role="status" aria-live="polite">
            <sol-spinner size="sm" />
            <span>{{ text.loading() }}</span>
          </div>
        } @else if (filtered().length === 0) {
          <p class="gr__muted">{{ text.noMatches() }}</p>
        } @else {
          <fieldset class="gr__list" [disabled]="saving()">
            <legend class="sr-only">{{ text.repositoriesLegend() }}</legend>
            @for (repo of filtered(); track repo.path_with_namespace) {
              <label class="gr__option">
                <input
                  type="checkbox"
                  [checked]="selected().has(repo.path_with_namespace)"
                  (change)="toggle(repo.path_with_namespace)"
                />
                <span class="gr__path">{{ repo.path_with_namespace }}</span>
              </label>
            }
          </fieldset>
        }

        <p class="gr__muted">{{ selectionSummary() }}</p>
        @if (saveError(); as message) {
          <div class="gr__alert" role="alert"><span>{{ message }}</span></div>
        }
        <div>
          <sol-button
            type="button"
            variant="primary"
            size="touch"
            [loading]="saving()"
            [disabled]="!dirty() || mappingLoading()"
            (clicked)="save()"
          >
            {{ saving() ? text.saving() : text.save() }}
          </sol-button>
        </div>
      }
    </div>
  `,
  styles: `
    :host { display: block; }
    .gr { display: flex; flex-direction: column; gap: var(--sol-space-sm); }
    .gr__title { margin: 0; font-size: var(--sol-font-size-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--sol-color-text-muted); }
    .gr__state { display: flex; align-items: center; gap: var(--sol-space-sm); color: var(--sol-color-text-muted); font-size: var(--sol-font-size-sm); }
    .gr__muted { margin: 0; color: var(--sol-color-text-muted); font-size: var(--sol-font-size-sm); }
    .gr__alert {
      display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--sol-space-sm);
      padding: var(--sol-space-sm) var(--sol-space-md);
      border: 1px solid color-mix(in srgb, var(--sol-color-danger) 40%, transparent);
      border-radius: var(--sol-border-radius-md);
      background: color-mix(in srgb, var(--sol-color-danger) 10%, transparent);
      color: var(--sol-color-danger); font-size: var(--sol-font-size-sm);
    }
    .gr__search {
      min-height: 44px; padding: 0 var(--sol-space-sm);
      border: 1px solid var(--sol-color-border); border-radius: var(--sol-border-radius-md);
      background: var(--sol-color-surface); color: var(--sol-color-text); font-size: 16px;
    }
    .gr__list { display: flex; flex-direction: column; gap: 2px; max-height: 240px; overflow-y: auto; margin: 0; padding: 0; border: 0; }
    .gr__option { display: flex; align-items: center; gap: var(--sol-space-sm); min-height: 44px; padding: 0 var(--sol-space-sm); border-radius: var(--sol-border-radius-md); cursor: pointer; font-size: var(--sol-font-size-sm); color: var(--sol-color-text); }
    .gr__option:hover { background: color-mix(in srgb, var(--sol-color-brand) 8%, transparent); }
    .gr__option input { width: 18px; height: 18px; accent-color: var(--sol-color-brand); }
    .gr__path { overflow-wrap: anywhere; }
  `,
})
export class GitlabRepositoriesComponent implements OnInit {
  private readonly gitlab = inject(GitlabService);
  private readonly projectsService = inject(ProjectsService);
  private readonly i18n = inject(I18nService);
  private readonly alert = inject(AlertService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly text = {
    title: this.i18n.t('gitlab.repositories.title'),
    loading: this.i18n.t('gitlab.repositories.loading'),
    retry: this.i18n.t('gitlab.repositories.retry'),
    noProjects: this.i18n.t('gitlab.repositories.noProjects'),
    noRepositories: this.i18n.t('gitlab.repositories.noRepositories'),
    noMatches: this.i18n.t('gitlab.repositories.noMatches'),
    projectLabel: this.i18n.t('gitlab.repositories.projectLabel'),
    searchPlaceholder: this.i18n.t('gitlab.repositories.searchPlaceholder'),
    repositoriesLegend: this.i18n.t('gitlab.repositories.legend'),
    save: this.i18n.t('gitlab.repositories.save'),
    saving: this.i18n.t('gitlab.repositories.saving'),
  } as const;

  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);
  protected readonly projects = signal<Project[]>([]);
  protected readonly repositories = signal<GitlabRepository[]>([]);
  protected readonly projectId = signal<string>('');
  protected readonly query = signal('');

  protected readonly mappingLoading = signal(false);
  protected readonly saved = signal<ReadonlySet<string>>(new Set());
  protected readonly selected = signal<ReadonlySet<string>>(new Set());
  protected readonly saving = signal(false);
  protected readonly saveError = signal<string | null>(null);

  protected readonly projectOptions = computed(() =>
    this.projects().map((p) => ({ value: p.id, label: p.code ? `${p.code} · ${p.name}` : p.name })),
  );

  protected readonly filtered = computed(() => {
    const q = this.query().trim().toLowerCase();
    const repos = this.repositories();
    return q ? repos.filter((r) => r.path_with_namespace.toLowerCase().includes(q)) : repos;
  });

  protected readonly dirty = computed(() => {
    const a = this.saved();
    const b = this.selected();
    return a.size !== b.size || [...b].some((path) => !a.has(path));
  });

  protected readonly selectionSummary = computed(() => {
    this.i18n.activeLang();
    return this.i18n.translate('gitlab.repositories.selected', { count: this.selected().size });
  });

  ngOnInit(): void {
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.loadError.set(null);
    forkJoin({ projects: this.projectsService.list(), repos: this.gitlab.repositories() })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ projects, repos }) => {
          this.projects.set(projects.data ?? []);
          this.repositories.set(repos.data ?? []);
          this.loading.set(false);
          const first = this.projects()[0];
          if (first && this.repositories().length > 0) {
            this.selectProject(first.id);
          }
        },
        error: (err: unknown) => {
          this.loadError.set(this.errorMessage(err, 'gitlab.repositories.loadError'));
          this.loading.set(false);
        },
      });
  }

  protected selectProject(projectId: string): void {
    this.projectId.set(projectId);
    this.saveError.set(null);
    this.mappingLoading.set(true);
    this.gitlab
      .projectRepositories(projectId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          const current = new Set(res.data.repositories);
          this.saved.set(current);
          this.selected.set(new Set(current));
          this.mappingLoading.set(false);
        },
        error: (err: unknown) => {
          this.saveError.set(this.errorMessage(err, 'gitlab.repositories.loadError'));
          this.mappingLoading.set(false);
        },
      });
  }

  protected toggle(path: string): void {
    const next = new Set(this.selected());
    if (next.has(path)) {
      next.delete(path);
    } else {
      next.add(path);
    }
    this.selected.set(next);
  }

  protected save(): void {
    const projectId = this.projectId();
    if (!projectId || this.saving()) {
      return;
    }
    this.saving.set(true);
    this.saveError.set(null);
    this.gitlab
      .setProjectRepositories(projectId, [...this.selected()])
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          const current = new Set(res.data.repositories);
          this.saved.set(current);
          this.selected.set(new Set(current));
          this.saving.set(false);
          this.alert.showSuccess(this.i18n.translate('gitlab.repositories.saved'));
        },
        error: (err: unknown) => {
          this.saving.set(false);
          this.saveError.set(this.errorMessage(err, 'gitlab.repositories.saveError'));
        },
      });
  }

  private errorMessage(err: unknown, fallbackKey: string): string {
    const api = readApiError(err);
    if (api.status === 0) {
      return this.i18n.translate('gitlab.repositories.network');
    }
    return api.detail ?? this.i18n.translate(fallbackKey);
  }
}
