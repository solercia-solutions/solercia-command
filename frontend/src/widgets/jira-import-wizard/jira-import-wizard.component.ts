import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import {
  SolBadgeComponent,
  SolButtonComponent,
  SolDrawerComponent,
  SolEmptyStateComponent,
  SolInputComponent,
  SolSkeletonComponent,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { readApiError } from '@shared/lib/api-error';
import { Connector } from '@entities/connector/connector.model';
import { JiraImportService } from '@entities/jira-import/jira-import.service';
import {
  JiraImportSummary,
  JiraPreviewResult,
  JiraProjectSummary,
} from '@entities/jira-import/jira-import.model';

type Step = 1 | 2 | 3;
type LoadState = 'idle' | 'loading' | 'error' | 'ready';

const CODE_RE = /^[A-Z0-9]{2,10}$/;
/** Above this many projects the list gets a search box (Hick). */
const SEARCH_THRESHOLD = 7;
/**
 * Error codes with their own wizard message (others fall back to the API detail).
 * `jira_project_too_large` stays out on purpose: its detail names the limit and
 * the JIRA_IMPORT_MAX_ISSUES setting, which a fixed message would lose.
 */
const KNOWN_ERRORS = new Set([
  'jira_credentials_missing',
  'jira_auth_error',
  'jira_project_unavailable',
  'jira_rate_limited',
  'jira_unavailable',
  'jira_config_invalid',
]);

/**
 * Three-step Jira project import: choose a project -> preview (name/code
 * editable, nothing persisted) -> import and show the final summary. Pure
 * orchestration over the `jira-import` endpoints; no business rule lives here.
 */
@Component({
  selector: 'sol-jira-import-wizard',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    SolBadgeComponent,
    SolButtonComponent,
    SolDrawerComponent,
    SolEmptyStateComponent,
    SolInputComponent,
    SolSkeletonComponent,
  ],
  template: `
    <sol-drawer
      [open]="connector() !== null"
      [title]="text.title()"
      size="lg"
      (closed)="close()"
    >
      <div class="flex flex-col gap-4">
        <!-- Progreso: los pasos ya hechos quedan marcados -->
        <ol class="flex flex-wrap gap-2 text-xs" [attr.aria-label]="stepAria()">
          @for (label of stepLabels(); track $index) {
            <li
              class="inline-flex items-center gap-1 rounded-full px-3 py-1"
              [class.bg-brand/10]="$index + 1 === step()"
              [class.text-brand]="$index + 1 === step()"
              [class.font-semibold]="$index + 1 === step()"
              [class.bg-sunken]="$index + 1 !== step()"
              [class.text-muted]="$index + 1 !== step()"
              [attr.aria-current]="$index + 1 === step() ? 'step' : null"
            >
              <span aria-hidden="true">{{ $index + 1 < step() ? '✓' : $index + 1 }}</span>
              {{ label }}
            </li>
          }
        </ol>

        @switch (step()) {
          <!-- Paso 1: elegir el proyecto de Jira -->
          @case (1) {
            @switch (projectsState()) {
              @case ('loading') {
                <div class="flex flex-col gap-2" [attr.aria-label]="text.loading()">
                  <sol-skeleton variant="text" />
                  <sol-skeleton variant="text" />
                  <sol-skeleton variant="text" />
                </div>
              }
              @case ('error') {
                <div role="alert" class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
                  {{ projectsError() }}
                </div>
                <div>
                  <sol-button type="button" variant="secondary" size="touch" (clicked)="loadProjects()">
                    {{ text.retry() }}
                  </sol-button>
                </div>
              }
              @case ('ready') {
                @if (projects().length === 0) {
                  <sol-empty-state
                    icon="folder"
                    titleKey="connectors.jiraProjectImport.empty.title"
                    descriptionKey="connectors.jiraProjectImport.empty.description"
                  />
                } @else {
                  <p class="text-sm text-muted">{{ text.chooseHint() }}</p>
                  @if (projects().length > searchThreshold) {
                    <sol-input
                      type="search"
                      [label]="text.searchLabel()"
                      [placeholder]="text.searchPlaceholder()"
                      [formControl]="searchControl"
                    ></sol-input>
                  }
                  @if (filteredProjects().length === 0) {
                    <div class="flex flex-col items-start gap-2 text-sm text-muted">
                      <p>{{ text.noResults() }}</p>
                      <sol-button type="button" variant="ghost" size="touch" (clicked)="searchControl.setValue('')">
                        {{ text.clearSearch() }}
                      </sol-button>
                    </div>
                  } @else {
                    <ul class="flex flex-col gap-2">
                      @for (project of filteredProjects(); track project.key) {
                        <li>
                          <button
                            type="button"
                            class="flex min-h-11 w-full items-center justify-between gap-3 rounded-lg border border-border
                                   px-3 py-2 text-left text-sm text-text hover:bg-sunken focus:outline-none
                                   focus-visible:ring-2 focus-visible:ring-brand/50"
                            (click)="choose(project)"
                          >
                            <span class="min-w-0">
                              <span class="block truncate font-medium">{{ project.name }}</span>
                              <span class="block text-xs text-muted">{{ project.key }}</span>
                            </span>
                            @if (project.imported_project) {
                              <sol-badge variant="neutral" size="sm">{{ text.alreadyImported() }}</sol-badge>
                            }
                          </button>
                        </li>
                      }
                    </ul>
                  }
                }
              }
            }
          }

          <!-- Paso 2: previsualizar (no escribe nada) -->
          @case (2) {
            <p class="text-sm text-text">
              <span class="font-semibold">{{ selected()?.name }}</span>
              <span class="text-muted"> · {{ selected()?.key }}</span>
            </p>
            @switch (previewState()) {
              @case ('loading') {
                <div class="flex flex-col gap-2" [attr.aria-label]="text.loading()">
                  <sol-skeleton variant="card" />
                  <sol-skeleton variant="text" />
                </div>
              }
              @case ('error') {
                <div role="alert" class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
                  {{ previewError() }}
                </div>
                <div class="flex flex-wrap gap-2">
                  <sol-button type="button" variant="secondary" size="touch" (clicked)="backToProjects()">
                    {{ text.chooseAnother() }}
                  </sol-button>
                  <sol-button type="button" variant="ghost" size="touch" (clicked)="loadPreview()">
                    {{ text.retry() }}
                  </sol-button>
                </div>
              }
              @case ('ready') {
                @if (preview(); as data) {
                  <p class="rounded-lg bg-sunken px-3 py-2 text-xs text-muted">{{ text.previewNote() }}</p>

                  @if (data.total === 0) {
                    <p class="text-sm text-muted">{{ text.previewEmpty() }}</p>
                  } @else {
                    <dl class="grid grid-cols-2 gap-2 sm:grid-cols-4">
                      @for (item of typeCounts(); track item.type) {
                        <div class="rounded-lg border border-border px-3 py-2">
                          <dt class="text-xs text-muted">{{ item.label }}</dt>
                          <dd class="text-lg font-semibold text-text">{{ item.count }}</dd>
                        </div>
                      }
                    </dl>
                    <p class="text-sm text-muted">{{ estimationLine() }}</p>

                    <section class="flex flex-col gap-1">
                      <h3 class="text-xs font-semibold uppercase tracking-wide text-muted">{{ text.sprintsHeading() }}</h3>
                      @if (data.sprints.length === 0) {
                        <p class="text-sm text-muted">{{ text.noSprints() }}</p>
                      } @else {
                        <ul class="flex flex-col gap-1 text-sm text-text">
                          @for (sprint of data.sprints; track sprint.name) {
                            <li class="flex items-center justify-between gap-2 rounded-md bg-sunken px-3 py-1.5">
                              <span class="truncate">{{ sprint.name }}</span>
                              <sol-badge variant="neutral" size="sm">{{ sprintStatusLabel(sprint.status) }}</sol-badge>
                            </li>
                          }
                        </ul>
                      }
                    </section>

                    <section class="flex flex-col gap-1">
                      <h3 class="text-xs font-semibold uppercase tracking-wide text-muted">{{ text.statusHeading() }}</h3>
                      <ul class="flex flex-col gap-1 text-sm text-text">
                        @for (row of data.status_mapping; track row.jira_status) {
                          <li class="flex items-center justify-between gap-2 rounded-md bg-sunken px-3 py-1.5">
                            <span class="truncate">{{ row.jira_status }} ({{ row.issues }})</span>
                            <span class="shrink-0 font-medium">→ {{ row.target_status }}</span>
                          </li>
                        }
                      </ul>
                    </section>
                  }

                  @if (data.existing_project; as existing) {
                    <p class="rounded-lg border border-border px-3 py-2 text-sm text-text">
                      {{ existingLine(existing.name, existing.code) }}
                    </p>
                  } @else {
                    <sol-input
                      [label]="text.nameLabel()"
                      [error]="nameError()"
                      [formControl]="nameControl"
                    ></sol-input>
                    <sol-input
                      [label]="text.codeLabel()"
                      [error]="codeError()"
                      [formControl]="codeControl"
                    ></sol-input>
                  }

                  <div class="flex flex-wrap items-center gap-2">
                    <sol-button type="button" variant="ghost" size="touch" (clicked)="backToProjects()">
                      {{ text.back() }}
                    </sol-button>
                    <sol-button
                      type="button"
                      variant="primary"
                      size="touch"
                      [disabled]="!canImport()"
                      (clicked)="runImport()"
                    >
                      {{ data.existing_project ? text.submitUpdate() : text.submit() }}
                    </sol-button>
                    @if (!canImport()) {
                      <span class="text-xs text-muted">{{ text.fixFields() }}</span>
                    }
                  </div>
                }
              }
            }
          }

          <!-- Paso 3: importar y ver el resumen -->
          @case (3) {
            @switch (importState()) {
              @case ('loading') {
                <div class="flex flex-col gap-2" role="status">
                  <p class="text-sm text-text">{{ text.importing() }}</p>
                  <sol-skeleton variant="card" />
                </div>
              }
              @case ('error') {
                <div role="alert" class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
                  {{ importError() }}
                </div>
                <p class="text-xs text-muted">{{ text.nothingSaved() }}</p>
                <div class="flex flex-wrap gap-2">
                  <sol-button type="button" variant="secondary" size="touch" (clicked)="step.set(2)">
                    {{ text.back() }}
                  </sol-button>
                  <sol-button type="button" variant="ghost" size="touch" (clicked)="runImport()">
                    {{ text.retry() }}
                  </sol-button>
                </div>
              }
              @case ('ready') {
                @if (summary(); as result) {
                  <div role="status" class="rounded-lg border border-success/40 bg-success/10 px-3 py-2 text-sm text-success">
                    {{ result.project_created ? text.successCreated() : text.successUpdated() }}
                  </div>
                  <dl class="grid grid-cols-3 gap-2">
                    <div class="rounded-lg border border-border px-3 py-2">
                      <dt class="text-xs text-muted">{{ text.created() }}</dt>
                      <dd class="text-lg font-semibold text-text">{{ result.tasks.created }}</dd>
                    </div>
                    <div class="rounded-lg border border-border px-3 py-2">
                      <dt class="text-xs text-muted">{{ text.updated() }}</dt>
                      <dd class="text-lg font-semibold text-text">{{ result.tasks.updated }}</dd>
                    </div>
                    <div class="rounded-lg border border-border px-3 py-2">
                      <dt class="text-xs text-muted">{{ text.unchanged() }}</dt>
                      <dd class="text-lg font-semibold text-text">{{ result.tasks.unchanged }}</dd>
                    </div>
                  </dl>
                  <ul class="flex flex-col gap-1 text-sm text-muted">
                    <li>{{ sprintsLine(result) }}</li>
                    @if (result.orphans.length > 0) {
                      <li>{{ listLine('connectors.jiraProjectImport.summary.orphans', result.orphans) }}</li>
                    }
                    @if (result.unassigned.length > 0) {
                      <li>{{ listLine('connectors.jiraProjectImport.summary.unassigned', result.unassigned) }}</li>
                    }
                    @if (unmappedStatuses(result).length > 0) {
                      <li>{{ listLine('connectors.jiraProjectImport.summary.unmapped', unmappedStatuses(result)) }}</li>
                    }
                    @if (result.errors.length > 0) {
                      <li>{{ listLine('connectors.jiraProjectImport.summary.errors', result.errors) }}</li>
                    }
                  </ul>
                  <div class="flex flex-wrap gap-2">
                    <sol-button type="button" variant="primary" size="touch" (clicked)="openProject(result.project_id)">
                      {{ text.openProject() }}
                    </sol-button>
                    <sol-button type="button" variant="ghost" size="touch" (clicked)="close()">
                      {{ text.close() }}
                    </sol-button>
                  </div>
                }
              }
            }
          }
        }
      </div>
    </sol-drawer>
  `,
})
export class JiraImportWizardComponent {
  private readonly service = inject(JiraImportService);
  private readonly i18n = inject(I18nService);
  private readonly router = inject(Router);

  /** Connector the wizard runs for; `null` keeps it closed. */
  readonly connector = input<Connector | null>(null);
  readonly closed = output<void>();
  readonly imported = output<JiraImportSummary>();

  protected readonly searchThreshold = SEARCH_THRESHOLD;

  protected readonly text = {
    title: this.i18n.t('connectors.jiraProjectImport.title'),
    loading: this.i18n.t('connectors.jiraProjectImport.loading'),
    retry: this.i18n.t('connectors.jiraProjectImport.retry'),
    chooseHint: this.i18n.t('connectors.jiraProjectImport.chooseHint'),
    searchLabel: this.i18n.t('connectors.jiraProjectImport.searchLabel'),
    searchPlaceholder: this.i18n.t('connectors.jiraProjectImport.searchPlaceholder'),
    noResults: this.i18n.t('connectors.jiraProjectImport.noResults'),
    clearSearch: this.i18n.t('connectors.jiraProjectImport.clearSearch'),
    alreadyImported: this.i18n.t('connectors.jiraProjectImport.alreadyImported'),
    chooseAnother: this.i18n.t('connectors.jiraProjectImport.chooseAnother'),
    previewNote: this.i18n.t('connectors.jiraProjectImport.previewNote'),
    previewEmpty: this.i18n.t('connectors.jiraProjectImport.previewEmpty'),
    sprintsHeading: this.i18n.t('connectors.jiraProjectImport.sprintsHeading'),
    noSprints: this.i18n.t('connectors.jiraProjectImport.noSprints'),
    statusHeading: this.i18n.t('connectors.jiraProjectImport.statusHeading'),
    nameLabel: this.i18n.t('connectors.jiraProjectImport.nameLabel'),
    codeLabel: this.i18n.t('connectors.jiraProjectImport.codeLabel'),
    back: this.i18n.t('connectors.jiraProjectImport.back'),
    submit: this.i18n.t('connectors.jiraProjectImport.submit'),
    submitUpdate: this.i18n.t('connectors.jiraProjectImport.submitUpdate'),
    fixFields: this.i18n.t('connectors.jiraProjectImport.fixFields'),
    importing: this.i18n.t('connectors.jiraProjectImport.importing'),
    nothingSaved: this.i18n.t('connectors.jiraProjectImport.nothingSaved'),
    successCreated: this.i18n.t('connectors.jiraProjectImport.successCreated'),
    successUpdated: this.i18n.t('connectors.jiraProjectImport.successUpdated'),
    created: this.i18n.t('connectors.jiraProjectImport.summary.created'),
    updated: this.i18n.t('connectors.jiraProjectImport.summary.updated'),
    unchanged: this.i18n.t('connectors.jiraProjectImport.summary.unchanged'),
    openProject: this.i18n.t('connectors.jiraProjectImport.openProject'),
    close: this.i18n.t('connectors.jiraProjectImport.close'),
  };

  protected readonly stepLabels = this.i18n.tMany([
    'connectors.jiraProjectImport.steps.choose',
    'connectors.jiraProjectImport.steps.preview',
    'connectors.jiraProjectImport.steps.import',
  ]);

  protected readonly step = signal<Step>(1);

  protected readonly projectsState = signal<LoadState>('idle');
  protected readonly projects = signal<JiraProjectSummary[]>([]);
  protected readonly projectsError = signal('');
  protected readonly searchControl = new FormControl('', { nonNullable: true });
  private readonly search = signal('');

  protected readonly selected = signal<JiraProjectSummary | null>(null);
  protected readonly previewState = signal<LoadState>('idle');
  protected readonly preview = signal<JiraPreviewResult | null>(null);
  protected readonly previewError = signal('');
  protected readonly nameControl = new FormControl('', { nonNullable: true });
  protected readonly codeControl = new FormControl('', { nonNullable: true });
  private readonly nameValue = signal('');
  private readonly codeValue = signal('');

  protected readonly importState = signal<LoadState>('idle');
  protected readonly summary = signal<JiraImportSummary | null>(null);
  protected readonly importError = signal('');

  protected readonly filteredProjects = computed(() => {
    const query = this.search().trim().toLowerCase();
    if (!query) {
      return this.projects();
    }
    return this.projects().filter(
      (p) => p.name.toLowerCase().includes(query) || p.key.toLowerCase().includes(query),
    );
  });

  protected readonly stepAria = computed(() => {
    this.i18n.activeLang();
    return this.i18n.translate('connectors.jiraProjectImport.stepAria', { step: this.step() });
  });

  protected readonly typeCounts = computed(() => {
    this.i18n.activeLang();
    const counts = this.preview()?.counts_by_type ?? {};
    return ['epic', 'story', 'task', 'subtask', 'bug']
      .filter((type) => (counts[type] ?? 0) > 0)
      .map((type) => ({
        type,
        count: counts[type],
        label: this.i18n.translate(`connectors.jiraProjectImport.types.${type}`),
      }));
  });

  protected readonly estimationLine = computed(() => {
    this.i18n.activeLang();
    const data = this.preview();
    if (!data) {
      return '';
    }
    return this.i18n.translate('connectors.jiraProjectImport.estimation', {
      hours: Number(data.estimated_hours).toLocaleString('es-CO', { maximumFractionDigits: 2 }),
      withEstimate: data.issues_with_estimate,
      points: data.story_points,
      withPoints: data.issues_with_points,
    });
  });

  protected readonly nameError = computed(() =>
    this.nameValue().trim() ? '' : this.i18n.translate('connectors.jiraProjectImport.nameRequired'),
  );

  protected readonly codeError = computed(() =>
    CODE_RE.test(this.codeValue().trim().toUpperCase())
      ? ''
      : this.i18n.translate('connectors.jiraProjectImport.codeInvalid'),
  );

  protected readonly canImport = computed(() => {
    const data = this.preview();
    if (!data || this.previewState() !== 'ready') {
      return false;
    }
    return data.existing_project !== null || (!this.nameError() && !this.codeError());
  });

  constructor() {
    this.searchControl.valueChanges.pipe(takeUntilDestroyed()).subscribe((v) => this.search.set(v));
    this.nameControl.valueChanges.pipe(takeUntilDestroyed()).subscribe((v) => this.nameValue.set(v));
    this.codeControl.valueChanges.pipe(takeUntilDestroyed()).subscribe((v) => this.codeValue.set(v));

    // Opening the wizard (a new connector) always restarts it at step 1.
    effect(() => {
      const connector = this.connector();
      untracked(() => {
        this.reset();
        if (connector) {
          this.loadProjects();
        }
      });
    });
  }

  // -- step 1 ------------------------------------------------------------------

  protected loadProjects(): void {
    const connector = this.connector();
    if (!connector) {
      return;
    }
    this.projectsState.set('loading');
    this.service.listJiraProjects(connector.id).subscribe({
      next: (res) => {
        this.projects.set(res.data ?? []);
        this.projectsState.set('ready');
      },
      error: (err: unknown) => {
        this.projectsError.set(this.errorMessage(err));
        this.projectsState.set('error');
      },
    });
  }

  protected choose(project: JiraProjectSummary): void {
    // Keep what the person already typed when coming back to the same project.
    if (this.selected()?.key !== project.key) {
      this.nameControl.setValue(project.name);
      this.codeControl.setValue('');
      this.preview.set(null);
    }
    this.selected.set(project);
    this.step.set(2);
    this.loadPreview();
  }

  protected backToProjects(): void {
    this.step.set(1);
    if (this.projectsState() !== 'ready') {
      this.loadProjects();
    }
  }

  // -- step 2 ------------------------------------------------------------------

  protected loadPreview(): void {
    const connector = this.connector();
    const project = this.selected();
    if (!connector || !project) {
      return;
    }
    this.previewState.set('loading');
    this.service.previewJiraProject(connector.id, project.key).subscribe({
      next: (res) => {
        this.preview.set(res.data);
        if (!this.codeControl.value) {
          this.codeControl.setValue(res.data.suggested_code);
        }
        this.previewState.set('ready');
      },
      error: (err: unknown) => {
        this.previewError.set(this.errorMessage(err));
        this.previewState.set('error');
      },
    });
  }

  protected sprintStatusLabel(status: string): string {
    return this.i18n.translate(`connectors.jiraProjectImport.sprintStatus.${status}`);
  }

  protected existingLine(name: string, code: string | null): string {
    return this.i18n.translate('connectors.jiraProjectImport.existing', {
      name,
      code: code ?? '—',
    });
  }

  // -- step 3 ------------------------------------------------------------------

  protected runImport(): void {
    const connector = this.connector();
    const project = this.selected();
    const data = this.preview();
    if (!connector || !project || !data || !this.canImport()) {
      return;
    }
    this.step.set(3);
    this.importState.set('loading');
    const creating = data.existing_project === null;
    this.service
      .importJiraProject(connector.id, {
        project_key: project.key,
        project_name: creating ? this.nameControl.value.trim() : null,
        project_code: creating ? this.codeControl.value.trim().toUpperCase() : null,
      })
      .subscribe({
        next: (res) => {
          this.summary.set(res.data);
          this.importState.set('ready');
          this.imported.emit(res.data);
        },
        error: (err: unknown) => {
          this.importError.set(this.errorMessage(err));
          this.importState.set('error');
        },
      });
  }

  protected sprintsLine(result: JiraImportSummary): string {
    return this.i18n.translate('connectors.jiraProjectImport.summary.sprints', {
      created: result.sprints.created,
      updated: result.sprints.updated,
    });
  }

  protected unmappedStatuses(result: JiraImportSummary): string[] {
    return Object.keys(result.unmapped_statuses ?? {});
  }

  protected listLine(key: string, items: string[]): string {
    const shown = items.slice(0, 10).join(', ');
    const rest = items.length > 10 ? ` (+${items.length - 10})` : '';
    return this.i18n.translate(key, { count: items.length, items: shown + rest });
  }

  protected openProject(projectId: string): void {
    this.close();
    void this.router.navigate(['/projects', projectId]);
  }

  protected close(): void {
    this.closed.emit();
  }

  // -- helpers -----------------------------------------------------------------

  private reset(): void {
    this.step.set(1);
    this.projectsState.set('idle');
    this.projects.set([]);
    this.searchControl.setValue('');
    this.selected.set(null);
    this.preview.set(null);
    this.previewState.set('idle');
    this.nameControl.setValue('');
    this.codeControl.setValue('');
    this.summary.set(null);
    this.importState.set('idle');
  }

  /** Wizard message for a known error code; otherwise the backend's own detail. */
  private errorMessage(err: unknown): string {
    const api = readApiError(err);
    if (api.status === 0) {
      return this.i18n.translate('connectors.jiraProjectImport.errors.network');
    }
    if (api.status === 403) {
      return this.i18n.translate('connectors.jiraProjectImport.errors.forbidden');
    }
    if (api.code && KNOWN_ERRORS.has(api.code)) {
      return this.i18n.translate(`connectors.jiraProjectImport.errors.${api.code}`);
    }
    return api.detail ?? this.i18n.translate('connectors.jiraProjectImport.errors.generic');
  }
}
