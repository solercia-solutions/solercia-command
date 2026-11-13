import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { SolBadgeComponent, SolButtonComponent, SolCardComponent, SolSpinnerComponent } from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { readApiError } from '@shared/lib/api-error';
import { GitlabService } from '@entities/gitlab/gitlab.service';
import { TaskDevelopmentActivity } from '@entities/gitlab/gitlab.model';

type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral';

/**
 * Panel «Desarrollo» del detalle de una tarea: merge requests y commits de los
 * repositorios de GitLab vinculados al proyecto que mencionan la clave de la
 * tarea. Lectura en vivo y de solo lectura; cada estado (cargando, sin GitLab,
 * sin repositorios, sin coincidencias, error y éxito) tiene su propio mensaje.
 */
@Component({
  selector: 'sol-gitlab-development',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, SolBadgeComponent, SolButtonComponent, SolCardComponent, SolSpinnerComponent],
  template: `
    <sol-card>
      <div class="gd">
        <div class="gd__head">
          <h3 class="gd__title">{{ text.title() }}</h3>
          @if (state() === 'ready' || state() === 'noResults') {
            <sol-button type="button" variant="ghost" size="sm" (clicked)="load()">
              {{ text.refresh() }}
            </sol-button>
          }
        </div>

        @switch (state()) {
          @case ('loading') {
            <div class="gd__state" role="status" aria-live="polite">
              <sol-spinner size="md" />
              <p>{{ text.loading() }}</p>
            </div>
          }
          @case ('error') {
            <div class="gd__alert" role="alert">
              <span>{{ error() }}</span>
              <sol-button type="button" variant="secondary" size="sm" (clicked)="load()">
                {{ text.retry() }}
              </sol-button>
            </div>
          }
          @case ('notConnected') {
            <p class="gd__empty">{{ text.notConnected() }}</p>
          }
          @case ('noRepositories') {
            <p class="gd__empty">{{ text.noRepositories() }}</p>
          }
          @case ('noKey') {
            <p class="gd__empty">{{ text.noKey() }}</p>
          }
          @case ('noResults') {
            <p class="gd__empty">{{ noResultsText() }}</p>
            <p class="gd__muted">{{ repositoriesText() }}</p>
          }
          @case ('ready') {
            @if (activity(); as a) {
              <p class="gd__muted">{{ repositoriesText() }}</p>

              <section class="gd__section" [attr.aria-label]="text.mergeRequests()">
                <h4 class="gd__subtitle">{{ text.mergeRequests() }} ({{ a.merge_requests.length }})</h4>
                @if (a.merge_requests.length === 0) {
                  <p class="gd__muted">{{ text.noMergeRequests() }}</p>
                }
                <ul class="gd__list">
                  @for (mr of a.merge_requests; track mr.repository + mr.iid) {
                    <li class="gd__item">
                      <div class="gd__row">
                        <sol-badge [variant]="stateTone(mr.state)" size="sm">{{ stateLabel(mr.state) }}</sol-badge>
                        @if (mr.web_url) {
                          <a class="gd__link" [href]="mr.web_url" target="_blank" rel="noopener noreferrer">
                            !{{ mr.iid }} {{ mr.title }}
                          </a>
                        } @else {
                          <span>!{{ mr.iid }} {{ mr.title }}</span>
                        }
                      </div>
                      <p class="gd__meta">
                        {{ mr.repository }}
                        @if (mr.source_branch) { · {{ mr.source_branch }} }
                        @if (mr.author) { · {{ mr.author }} }
                        @if (mr.updated_at) { · {{ mr.updated_at | date: 'dd/MM/yyyy HH:mm' }} }
                      </p>
                    </li>
                  }
                </ul>
              </section>

              <section class="gd__section" [attr.aria-label]="text.commits()">
                <h4 class="gd__subtitle">{{ text.commits() }} ({{ a.commits.length }})</h4>
                @if (a.commits.length === 0) {
                  <p class="gd__muted">{{ text.noCommits() }}</p>
                }
                <ul class="gd__list">
                  @for (commit of a.commits; track commit.repository + commit.short_id) {
                    <li class="gd__item">
                      <div class="gd__row">
                        <code class="gd__sha">{{ commit.short_id }}</code>
                        @if (commit.web_url) {
                          <a class="gd__link" [href]="commit.web_url" target="_blank" rel="noopener noreferrer">
                            {{ commit.title }}
                          </a>
                        } @else {
                          <span>{{ commit.title }}</span>
                        }
                      </div>
                      <p class="gd__meta">
                        {{ commit.repository }}
                        @if (commit.author_name) { · {{ commit.author_name }} }
                        @if (commit.authored_at) { · {{ commit.authored_at | date: 'dd/MM/yyyy HH:mm' }} }
                      </p>
                    </li>
                  }
                </ul>
              </section>
            }
          }
        }
      </div>
    </sol-card>
  `,
  styles: `
    :host { display: block; }
    .gd { display: flex; flex-direction: column; gap: var(--sol-space-md); }
    .gd__head { display: flex; align-items: center; justify-content: space-between; gap: var(--sol-space-sm); }
    .gd__title { margin: 0; font-size: var(--sol-font-size-base); font-weight: 600; color: var(--sol-color-text); }
    .gd__subtitle { margin: 0 0 var(--sol-space-xs); font-size: var(--sol-font-size-sm); font-weight: 600; color: var(--sol-color-text); }
    .gd__state { display: flex; flex-direction: column; align-items: center; gap: var(--sol-space-sm); padding: var(--sol-space-lg) 0; color: var(--sol-color-text-muted); font-size: var(--sol-font-size-sm); }
    .gd__alert {
      display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--sol-space-sm);
      padding: var(--sol-space-sm) var(--sol-space-md);
      border: 1px solid color-mix(in srgb, var(--sol-color-danger) 40%, transparent);
      border-radius: var(--sol-border-radius-md);
      background: color-mix(in srgb, var(--sol-color-danger) 10%, transparent);
      color: var(--sol-color-danger); font-size: var(--sol-font-size-sm);
    }
    .gd__empty { margin: 0; color: var(--sol-color-text); font-size: var(--sol-font-size-sm); }
    .gd__muted, .gd__meta { margin: 0; color: var(--sol-color-text-muted); font-size: var(--sol-font-size-xs); overflow-wrap: anywhere; }
    .gd__section { display: flex; flex-direction: column; gap: var(--sol-space-xs); }
    .gd__list { display: flex; flex-direction: column; gap: var(--sol-space-sm); margin: 0; padding: 0; list-style: none; }
    .gd__item { display: flex; flex-direction: column; gap: 2px; padding: var(--sol-space-sm); border-radius: var(--sol-border-radius-md); background: var(--sol-color-surface-sunken, transparent); }
    .gd__row { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sol-space-sm); min-width: 0; font-size: var(--sol-font-size-sm); }
    .gd__link { color: var(--sol-color-brand); text-decoration: none; overflow-wrap: anywhere; }
    .gd__link:hover, .gd__link:focus-visible { text-decoration: underline; }
    .gd__sha { font-family: var(--sol-font-mono, monospace); font-size: var(--sol-font-size-xs); color: var(--sol-color-text-muted); }
  `,
})
export class GitlabDevelopmentComponent implements OnInit {
  readonly taskId = input.required<string>();

  private readonly gitlab = inject(GitlabService);
  private readonly i18n = inject(I18nService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly text = {
    title: this.i18n.t('gitlab.development.title'),
    loading: this.i18n.t('gitlab.development.loading'),
    retry: this.i18n.t('gitlab.development.retry'),
    refresh: this.i18n.t('gitlab.development.refresh'),
    notConnected: this.i18n.t('gitlab.development.notConnected'),
    noRepositories: this.i18n.t('gitlab.development.noRepositories'),
    noKey: this.i18n.t('gitlab.development.noKey'),
    mergeRequests: this.i18n.t('gitlab.development.mergeRequests'),
    commits: this.i18n.t('gitlab.development.commits'),
    noMergeRequests: this.i18n.t('gitlab.development.noMergeRequests'),
    noCommits: this.i18n.t('gitlab.development.noCommits'),
  } as const;

  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly activity = signal<TaskDevelopmentActivity | null>(null);

  protected readonly state = computed(() => {
    if (this.loading()) return 'loading';
    if (this.error()) return 'error';
    const a = this.activity();
    if (!a || !a.connected) return 'notConnected';
    if (a.repositories.length === 0) return 'noRepositories';
    if (!a.task_key) return 'noKey';
    if (a.merge_requests.length === 0 && a.commits.length === 0) return 'noResults';
    return 'ready';
  });

  protected readonly noResultsText = computed(() => {
    this.i18n.activeLang();
    return this.i18n.translate('gitlab.development.noResults', {
      key: this.activity()?.task_key ?? '',
    });
  });

  protected readonly repositoriesText = computed(() => {
    this.i18n.activeLang();
    return this.i18n.translate('gitlab.development.repositories', {
      list: (this.activity()?.repositories ?? []).join(', '),
    });
  });

  ngOnInit(): void {
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.gitlab
      .taskActivity(this.taskId())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.activity.set(res.data);
          this.loading.set(false);
        },
        error: (err: unknown) => {
          const api = readApiError(err);
          this.error.set(
            api.status === 0
              ? this.i18n.translate('gitlab.development.errorNetwork')
              : (api.detail ?? this.i18n.translate('gitlab.development.error')),
          );
          this.loading.set(false);
        },
      });
  }

  protected stateLabel(state: string): string {
    const known = ['opened', 'merged', 'closed', 'locked'];
    return known.includes(state)
      ? this.i18n.translate(`gitlab.development.states.${state}`)
      : state;
  }

  protected stateTone(state: string): BadgeTone {
    if (state === 'merged') return 'success';
    if (state === 'opened') return 'info';
    if (state === 'closed') return 'neutral';
    return 'warning';
  }
}
