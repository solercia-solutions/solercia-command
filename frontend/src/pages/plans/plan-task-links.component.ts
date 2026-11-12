import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { Subject, Subscription, debounceTime, distinctUntilChanged } from 'rxjs';
import {
  SolBadgeComponent,
  SolButtonComponent,
  SolFormFieldComponent,
  SolSkeletonComponent,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { readApiError } from '@shared/lib/api-error';
import { PlansService } from '@entities/plan/plans.service';
import { ActivityTask, TaskLinkRole, TaskSearchResult } from '@entities/plan/plan.model';
import { defaultLinkRole, externalCode } from './plans-view';

const MIN_QUERY = 2;

/**
 * Tasks linked to an activity (task N3). Everyone sees the list; admins and
 * managers (`canWrite`) can unlink (inline confirmation, no native dialog)
 * and link tasks from ANY project of the active organization through the
 * tenant-scoped global search.
 */
@Component({
  selector: 'sol-plan-task-links',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    SolBadgeComponent,
    SolButtonComponent,
    SolFormFieldComponent,
    SolSkeletonComponent,
  ],
  styles: [
    `
      /* Buscador con tokens --sol-* (patrón de formulario de PANDORA dentro del drawer). */
      .ptl-control {
        width: 100%;
        min-height: var(--sol-size-control-touch, 44px);
        padding: var(--sol-space-sm, 8px) var(--sol-space-md, 12px);
        border: 1px solid var(--sol-border-color-default);
        border-radius: var(--sol-border-radius-md, 8px);
        background: var(--sol-bg-surface);
        color: var(--sol-color-text-primary);
        font: inherit;
        font-size: var(--sol-font-size-sm, 0.875rem);
      }

      .ptl-control:focus-visible {
        outline: 2px solid var(--sol-color-primary);
        outline-offset: 1px;
      }
    `,
  ],
  template: `
    <section class="flex flex-col gap-2">
      <div class="flex items-center justify-between gap-2">
        <h3 class="text-sm font-semibold text-text">{{ t('plans.tasksSection.title') }}</h3>
        @if (canWrite() && !pickerOpen()) {
          <sol-button type="button" variant="secondary" size="sm" (clicked)="openPicker()">
            {{ t('plans.linker.open') }}
          </sol-button>
        }
      </div>

      @if (pickerOpen()) {
        <div class="flex flex-col gap-3 rounded-lg border border-brand/40 p-3">
          <sol-form-field [label]="t('plans.linker.role')" [hint]="t('plans.linker.roleHint.' + role())">
            <div class="flex flex-wrap gap-1.5" role="radiogroup" [attr.aria-label]="t('plans.linker.role')">
              @for (option of roles; track option) {
                <button
                  type="button"
                  role="radio"
                  class="min-h-11 rounded-full border px-3 text-sm transition-colors"
                  [class]="chipClass(role() === option)"
                  [attr.aria-checked]="role() === option"
                  (click)="role.set(option)"
                >
                  {{ t('plans.tasksSection.roles.' + option) }}
                </button>
              }
            </div>
          </sol-form-field>

          <sol-form-field [label]="t('plans.linker.search')">
            <input
              [id]="uid + '-q'"
              type="search"
              autocomplete="off"
              class="ptl-control"
              [attr.aria-label]="t('plans.linker.search')"
              [placeholder]="t('plans.linker.searchPlaceholder')"
              [value]="query()"
              (input)="onQuery($any($event.target).value)"
            />
          </sol-form-field>

          <div aria-live="polite">
            @if (query().trim().length < minQuery) {
              <p class="text-xs text-muted">{{ t('plans.linker.typeMore') }}</p>
            } @else if (searching()) {
              <sol-skeleton variant="row" [count]="3" />
            } @else if (searchError(); as message) {
              <div role="alert" class="flex flex-col gap-2 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
                <span>{{ message }}</span>
                <sol-button type="button" variant="secondary" size="sm" (clicked)="runSearch(query())">
                  {{ t('plans.retry') }}
                </sol-button>
              </div>
            } @else if (results().length === 0) {
              <p class="text-sm text-muted">{{ t('plans.linker.noResults') }}</p>
            } @else {
              <ul class="flex flex-col divide-y divide-border rounded-lg border border-border">
                @for (result of results(); track result.id) {
                  <li>
                    <button
                      type="button"
                      class="flex min-h-11 w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-muted/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
                      [disabled]="isLinked(result.id) || linkingId() !== null"
                      (click)="link(result)"
                    >
                      <span class="min-w-0">
                        @if (result.task_key) {
                          <span class="font-mono text-xs text-brand">{{ result.task_key }}</span>
                        }
                        <span class="block line-clamp-2 text-text">{{ result.title }}</span>
                        <span class="block text-xs text-muted">{{ result.project_name || '—' }}</span>
                      </span>
                      <span class="shrink-0 text-xs font-medium" [class.text-muted]="isLinked(result.id)" [class.text-brand]="!isLinked(result.id)">
                        @if (isLinked(result.id)) {
                          {{ t('plans.linker.alreadyLinked') }}
                        } @else if (linkingId() === result.id) {
                          {{ t('plans.linker.linking') }}
                        } @else {
                          {{ t('plans.linker.link') }}
                        }
                      </span>
                    </button>
                  </li>
                }
              </ul>
            }
          </div>

          @if (linkError(); as message) {
            <p role="alert" class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{{ message }}</p>
          }

          <div class="flex justify-end">
            <sol-button type="button" variant="ghost" size="sm" (clicked)="closePicker()">
              {{ t('plans.linker.close') }}
            </sol-button>
          </div>
        </div>
      }

      @if (tasks().length === 0) {
        <p class="text-sm text-muted">
          {{ t('plans.tasksSection.empty') }}
          @if (canWrite() && !pickerOpen()) {
            {{ t('plans.linker.emptyHint') }}
          }
        </p>
      } @else {
        <ul class="flex flex-col divide-y divide-border rounded-lg border border-border">
          @for (task of tasks(); track task.task_id) {
            <li class="flex flex-col gap-1 px-3 py-2 text-sm sm:flex-row sm:items-center sm:justify-between">
              <div class="min-w-0">
                @if (task.task_key) {
                  <a class="font-mono text-xs text-brand underline-offset-2 hover:underline" [routerLink]="['/task', task.task_key]">
                    @if (codeOf(task); as code) {
                      {{ code }} ·
                    }
                    {{ task.task_key }}
                  </a>
                }
                <p class="line-clamp-2 text-text">{{ task.title || '—' }}</p>
                <p class="text-xs text-muted">{{ task.project_name }} · {{ statusLabel(task.status) }}</p>
              </div>
              <div class="flex shrink-0 flex-wrap items-center gap-1.5">
                <sol-badge [variant]="task.role === 'primary' ? 'info' : 'neutral'" size="sm">
                  {{ labelOr('plans.tasksSection.roles.' + task.role, task.role) }}
                </sol-badge>
                @if (task.counts_toward_progress) {
                  <sol-badge variant="success" size="sm">{{ t('plans.tasksSection.counts') }}</sol-badge>
                }
                @if (canWrite()) {
                  @if (confirmingId() === task.task_id) {
                    <span class="text-xs text-text">{{ t('plans.linker.confirmUnlink') }}</span>
                    <sol-button type="button" variant="danger" size="sm" [loading]="unlinkingId() === task.task_id" (clicked)="unlink(task)">
                      {{ t('plans.linker.unlinkYes') }}
                    </sol-button>
                    <sol-button type="button" variant="ghost" size="sm" (clicked)="confirmingId.set(null)">
                      {{ t('plans.linker.cancel') }}
                    </sol-button>
                  } @else {
                    <button
                      type="button"
                      class="min-h-11 rounded-full px-3 text-xs text-muted hover:text-danger focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
                      [attr.aria-label]="t('plans.linker.unlinkAria', { key: task.task_key || task.title || '' })"
                      (click)="confirmingId.set(task.task_id)"
                    >
                      {{ t('plans.linker.unlink') }}
                    </button>
                  }
                }
              </div>
            </li>
          }
        </ul>
        @if (unlinkError(); as message) {
          <p role="alert" class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{{ message }}</p>
        }
      }
    </section>
  `,
})
export class PlanTaskLinksComponent implements OnInit {
  private readonly plansService = inject(PlansService);
  private readonly i18n = inject(I18nService);
  private readonly destroyRef = inject(DestroyRef);

  readonly activityId = input.required<string>();
  readonly tasks = input<ActivityTask[]>([]);
  readonly canWrite = input(false);

  /** Emitted after a successful link/unlink so the parent reloads. */
  readonly changed = output<'linked' | 'unlinked'>();

  protected readonly minQuery = MIN_QUERY;
  protected readonly roles: readonly TaskLinkRole[] = ['primary', 'contributes'];
  protected readonly uid = `plan-links-${Math.random().toString(36).slice(2, 9)}`;

  protected readonly pickerOpen = signal(false);
  protected readonly role = signal<TaskLinkRole>('primary');
  protected readonly query = signal('');
  protected readonly results = signal<TaskSearchResult[]>([]);
  protected readonly searching = signal(false);
  protected readonly searchError = signal<string | null>(null);
  protected readonly linkingId = signal<string | null>(null);
  protected readonly linkError = signal<string | null>(null);
  protected readonly confirmingId = signal<string | null>(null);
  protected readonly unlinkingId = signal<string | null>(null);
  protected readonly unlinkError = signal<string | null>(null);

  private readonly linkedIds = computed(() => new Set(this.tasks().map((task) => task.task_id)));
  private readonly primaryCount = computed(
    () => this.tasks().filter((task) => task.role === 'primary').length,
  );
  private readonly query$ = new Subject<string>();
  private searchSub: Subscription | null = null;

  ngOnInit(): void {
    this.query$
      .pipe(debounceTime(300), distinctUntilChanged(), takeUntilDestroyed(this.destroyRef))
      .subscribe((q) => this.runSearch(q));
  }

  protected t(key: string, params?: Record<string, unknown>): string {
    this.i18n.activeLang();
    return this.i18n.translate(key, params);
  }

  protected labelOr(key: string, fallback: string): string {
    const value = this.t(key);
    return value === key ? fallback : value;
  }

  /** Checklist code («T-07») or origin key of an imported task, if any. */
  protected codeOf(task: ActivityTask): string | null {
    return externalCode(task);
  }

  /** Only enum codes (`in_progress`) have a label; board names («En curso») show as they are. */
  protected statusLabel(status: string): string {
    return /^[a-z_]+$/.test(status) ? this.labelOr(`plans.taskStatus.${status}`, status) : status;
  }

  protected chipClass(active: boolean): string {
    return active
      ? 'border-brand bg-brand text-brand-fg'
      : 'border-border bg-surface text-text hover:border-brand';
  }

  protected isLinked(taskId: string): boolean {
    return this.linkedIds().has(taskId);
  }

  protected openPicker(): void {
    // Smart default: the first task of an activity without primaries is its primary.
    this.role.set(defaultLinkRole(this.primaryCount()));
    this.linkError.set(null);
    this.pickerOpen.set(true);
  }

  protected closePicker(): void {
    this.searchSub?.unsubscribe();
    this.pickerOpen.set(false);
    this.query.set('');
    this.results.set([]);
    this.searching.set(false);
    this.searchError.set(null);
    this.linkError.set(null);
  }

  protected onQuery(value: string): void {
    this.query.set(value);
    if (value.trim().length < MIN_QUERY) {
      this.searchSub?.unsubscribe();
      this.searching.set(false);
      this.results.set([]);
    } else {
      this.searching.set(true);
    }
    this.query$.next(value.trim());
  }

  protected runSearch(q: string): void {
    const text = q.trim();
    if (text.length < MIN_QUERY) {
      return;
    }
    this.searchSub?.unsubscribe();
    this.searching.set(true);
    this.searchError.set(null);
    this.searchSub = this.plansService
      .searchTasks(text)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.results.set(res.data.filter((row) => row.entity_type === 'task'));
          this.searching.set(false);
        },
        error: (err: unknown) => {
          this.searching.set(false);
          this.searchError.set(this.message(err, 'plans.linker.errors.searchFailed'));
        },
      });
  }

  protected link(result: TaskSearchResult): void {
    if (this.isLinked(result.id) || this.linkingId() !== null) {
      return;
    }
    this.linkingId.set(result.id);
    this.linkError.set(null);
    this.plansService
      .linkTask(this.activityId(), { task_id: result.id, role: this.role() })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.linkingId.set(null);
          // Next link of the same activity defaults to `contributes`.
          if (this.role() === 'primary') {
            this.role.set('contributes');
          }
          this.changed.emit('linked');
        },
        error: (err: unknown) => {
          this.linkingId.set(null);
          this.linkError.set(this.message(err, 'plans.linker.errors.linkFailed'));
        },
      });
  }

  protected unlink(task: ActivityTask): void {
    if (this.unlinkingId() !== null) {
      return;
    }
    this.unlinkingId.set(task.task_id);
    this.unlinkError.set(null);
    this.plansService
      .unlinkTask(this.activityId(), task.task_id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.unlinkingId.set(null);
          this.confirmingId.set(null);
          this.changed.emit('unlinked');
        },
        error: (err: unknown) => {
          this.unlinkingId.set(null);
          this.unlinkError.set(this.message(err, 'plans.linker.errors.unlinkFailed'));
        },
      });
  }

  private message(err: unknown, fallbackKey: string): string {
    const api = readApiError(err);
    if (api.status === 0) {
      return this.t('plans.errors.network');
    }
    if (api.status === 403) {
      return this.t('plans.linker.errors.forbidden');
    }
    return api.detail ?? this.t(fallbackKey);
  }
}
