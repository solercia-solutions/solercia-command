import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  OnDestroy,
  effect,
  untracked,
  computed,
  inject,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { AuthService } from '@features/auth/auth.service';
import { ActiveOrgStore } from '@features/organizations/active-org.store';
import { HttpErrorResponse } from '@angular/common/http';
import { SolCardComponent, SolIconComponent } from '@shared/ui';
import { I18nService } from '@shared/i18n';
import {
  PRIORITY_CHIP_CLASS,
  PRIORITY_LABELS,
  Priority,
  formatShortDate,
} from '@entities/workspace/workspace.model';
import { METHODOLOGY_LABELS, Methodology } from '@entities/project/project.model';
import { ExecutiveService } from '@entities/executive/executive.service';
import { DailyDashboard, DailyDatePolicy, ExecutiveDashboard } from '@entities/executive/executive.model';

/**
 * Executive ("vista de jefe") dashboard: one scannable screen with team
 * workload, what each person is doing, risks and per-project progress.
 */
@Component({
  selector: 'sol-executive',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [SolCardComponent, SolIconComponent, RouterLink],
  template: `
    <section class="flex flex-col gap-6">
      <div>
        <h1 class="font-display text-2xl font-bold tracking-tight text-text">
          {{ text.title() }}
        </h1>
        <p class="text-sm text-muted">
          {{ text.subtitle() }}
        </p>
      </div>

      <section aria-labelledby="daily-heading" class="flex min-w-0 flex-col gap-3">
        <h2 id="daily-heading" class="font-display text-lg font-bold text-text">{{ dailyText('title') }}</h2>
        <sol-card>
          <p class="text-sm text-muted">{{ dailyText('scope') }}</p>
          <div class="mt-3 grid gap-3 md:grid-cols-2">
            <label class="flex min-w-0 flex-col gap-1 text-sm text-text">
              {{ dailyText('timezone') }}
              <select class="min-h-11 w-full rounded-lg border border-border bg-sunken px-3 text-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
                [value]="dailyTimezone()" (change)="changeDailyTimezone($any($event.target).value)">
                <option value="America/Bogota">{{ dailyText('bogota') }}</option>
                <option value="UTC">{{ dailyText('utc') }}</option>
              </select>
            </label>
            <label class="flex min-w-0 flex-col gap-1 text-sm text-text">
              {{ dailyText('policy') }}
              <select required aria-describedby="daily-policy-help" class="min-h-11 w-full rounded-lg border border-border bg-sunken px-3 text-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
                [value]="dailyPolicy()" (change)="changeDailyPolicy($any($event.target).value)">
                <option value="">{{ dailyText('choose') }}</option>
                <option value="stored_calendar_date">{{ dailyText('stored_calendar_date') }}</option>
                <option value="instant">{{ dailyText('instant') }}</option>
              </select>
            </label>
          </div>
          <p id="daily-policy-help" class="mt-2 text-sm text-muted">{{ dailyText('policyHelp') }}</p>
          <button type="button" class="mt-3 min-h-11 rounded-lg bg-brand px-4 py-2 text-brand-fg focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand disabled:opacity-50"
            [disabled]="!dailyPolicy() || !dailyContext()" (click)="queryDaily()">
            {{ dailyText(dailyError() ? 'retry' : 'query') }}
          </button>
          <div class="mt-3 text-sm" aria-live="polite" [attr.aria-busy]="dailyLoading()">
            @if (!dailyContext()) {
              <p class="text-muted">{{ dailyText('context') }}</p>
            } @else if (!dailyPolicy()) {
              <p class="text-muted">{{ dailyText('configure') }}</p>
            } @else if (dailyLoading()) {
              <p class="text-muted" role="status">{{ dailyText('loading') }}</p>
            } @else if (dailyError()) {
              <p class="text-danger" role="alert">{{ dailyError() }}</p>
            } @else if (dailyData(); as daily) {
              <p class="font-medium text-text">{{ dailyText('success') }} · {{ daily.timezone }} · {{ dailyText(daily.date_policy) }}</p>
              <p class="text-muted">{{ dailyText('generated') }} {{ dailyGenerated(daily) }}</p>
              <p class="mt-2 text-muted">{{ dailyText('freshness') }}</p>
              <p class="mt-2 text-muted">{{ dailyText('overlap') }}</p>
              @if (daily.coverage_warnings.length) {
                <h3 class="mt-3 font-semibold text-text">{{ dailyText('warningsTitle') }}</h3>
                <ul class="list-disc pl-5 text-muted">
                  @for (warning of daily.coverage_warnings; track warning) {
                    <li>{{ dailyWarning(warning) }}</li>
                  }
                </ul>
              }
              @if (dailyEmpty()) { <p class="mt-3 text-muted">{{ dailyText('empty') }}</p> }
              <div class="mt-4 grid min-w-0 gap-4 md:grid-cols-2">
                @for (group of dailyGroups; track group) {
                  <div class="min-w-0 rounded-lg border border-border p-3">
                    <h3 class="font-semibold text-text">{{ dailyText(group) }} ({{ daily[group].count }})
                      @if (group === 'today') { · {{ daily.today_date }} }
                      @if (group === 'tomorrow') { · {{ daily.tomorrow_date }} }
                    </h3>
                    @if (!daily[group].items.length) { <p class="mt-2 text-muted">{{ dailyText('groupEmpty') }}</p> }
                    <ul class="divide-y divide-border">
                      @for (item of daily[group].items; track item.id) {
                        <li class="py-2 break-words">
                          @if (item.task_key !== null) {
                            <a class="inline-flex min-h-11 items-center text-brand underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand" [routerLink]="['/task', item.task_key]">{{ item.title }}</a>
                          } @else {
                            <p class="font-medium text-text">{{ item.title }}</p>
                            <p class="text-xs text-muted">{{ dailyText('noKey') }}</p>
                          }
                          <p class="text-xs text-muted">{{ dailyText('due') }}: {{ item.due_date ?? dailyText('noDue') }}</p>
                        </li>
                      }
                    </ul>
                  </div>
                }
              </div>
            } @else {
              <p class="text-muted">{{ dailyText('ready') }}</p>
            }
          </div>
        </sol-card>
      </section>

      @if (loading()) {
        <p class="text-sm text-muted">{{ text.loading() }}</p>
      } @else if (loadError()) {
        <div
          role="alert"
          class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {{ loadError() }}
        </div>
      } @else if (data(); as dash) {
        <!-- Totals -->
        <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <sol-card>
            <p class="text-sm text-muted">{{ text.totalProjects() }}</p>
            <p class="mt-1 text-3xl font-bold tracking-tight tnum text-text">
              {{ dash.totals.projects }}
            </p>
          </sol-card>
          <sol-card>
            <p class="text-sm text-muted">{{ text.totalTasks() }}</p>
            <p class="mt-1 text-3xl font-bold tracking-tight tnum text-text">
              {{ dash.totals.tasks }}
            </p>
          </sol-card>
          <sol-card>
            <p class="text-sm text-muted">{{ text.totalOverdue() }}</p>
            <p
              class="mt-1 text-3xl font-bold tracking-tight tnum"
              [class.text-danger]="dash.totals.overdue > 0"
              [class.text-text]="dash.totals.overdue === 0"
            >
              {{ dash.totals.overdue }}
            </p>
          </sol-card>
          <sol-card>
            <p class="text-sm text-muted">{{ text.totalAtRisk() }}</p>
            <p
              class="mt-1 text-3xl font-bold tracking-tight tnum"
              [class.text-warning]="dash.totals.at_risk > 0"
              [class.text-text]="dash.totals.at_risk === 0"
            >
              {{ dash.totals.at_risk }}
            </p>
          </sol-card>
        </div>

        <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <!-- En qué anda cada uno -->
          <div class="flex flex-col gap-3">
            <h2 class="font-display text-lg font-bold tracking-tight text-text">{{ text.byAssigneeTitle() }}</h2>
            @if (dash.by_assignee.length === 0) {
              <sol-card>
                <p class="py-4 text-center text-sm text-muted">
                  {{ text.byAssigneeEmpty() }}
                </p>
              </sol-card>
            } @else {
              @for (person of dash.by_assignee; track person.user.id) {
                <sol-card>
                  <div class="flex items-center justify-between gap-2">
                    <div class="flex items-center gap-2">
                      <span
                        class="grid h-7 w-7 place-items-center rounded-full bg-brand-soft text-xs font-semibold text-brand-soft-fg"
                        aria-hidden="true"
                      >
                        {{ initial(person.user.full_name) }}
                      </span>
                      <span class="text-sm font-medium text-text">
                        {{ person.user.full_name }}
                      </span>
                    </div>
                    <span
                      class="rounded-full bg-sunken px-2 py-0.5 text-xs font-medium text-muted"
                    >
                      {{ activeCountLabel(person.active_count) }}
                    </span>
                  </div>
                  @if (person.in_progress.length > 0) {
                    <ul class="mt-3 flex flex-col gap-1.5">
                      @for (task of person.in_progress; track task.id) {
                        <li class="flex items-center gap-2 text-sm text-text">
                          <span
                            class="h-1.5 w-1.5 shrink-0 rounded-full bg-brand"
                            aria-hidden="true"
                          ></span>
                          <span class="truncate">{{ task.title }}</span>
                          <span
                            class="ml-auto shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium"
                            [class]="priorityChip(task.priority)"
                          >
                            {{ priorityLabel(task.priority) }}
                          </span>
                        </li>
                      }
                    </ul>
                  } @else {
                    <p class="mt-2 text-xs text-muted">{{ text.noInProgress() }}</p>
                  }
                </sol-card>
              }
            }
          </div>

          <!-- Riesgos -->
          <div class="flex flex-col gap-3">
            <h2 class="font-display text-lg font-bold tracking-tight text-text">{{ text.risksTitle() }}</h2>
            @if (dash.at_risk.length === 0) {
              <sol-card>
                <p class="py-4 text-center text-sm text-muted">
                  {{ text.risksEmpty() }}
                </p>
              </sol-card>
            } @else {
              <sol-card>
                <ul class="flex flex-col divide-y divide-border">
                  @for (task of dash.at_risk; track task.id) {
                    <li class="flex items-center gap-3 py-2 first:pt-0 last:pb-0">
                      <span class="shrink-0 text-danger" aria-hidden="true">
                        <sol-icon name="exclamation-triangle" size="sm" />
                      </span>
                      <div class="min-w-0 flex-1">
                        <p class="truncate text-sm font-medium text-text">
                          {{ task.title }}
                        </p>
                        <p class="text-xs text-muted">
                          {{ task.assignee_name || text.noAssignee() }}
                          @if (task.due_date) {
                            · {{ dueOnLabel(task.due_date) }}
                          }
                        </p>
                      </div>
                      <span
                        class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium"
                        [class]="priorityChip(task.priority)"
                      >
                        {{ priorityLabel(task.priority) }}
                      </span>
                    </li>
                  }
                </ul>
              </sol-card>
            }
          </div>
        </div>

        <!-- Carga del equipo -->
        <div class="flex flex-col gap-3">
          <h2 class="font-display text-lg font-bold tracking-tight text-text">{{ text.workloadTitle() }}</h2>
          <sol-card>
            @if (dash.workload.length === 0) {
              <p class="py-4 text-center text-sm text-muted">
                {{ text.workloadEmpty() }}
              </p>
            } @else {
              <ul class="flex flex-col gap-3">
                @for (item of dash.workload; track item.user.id) {
                  <li class="flex items-center gap-3">
                    <span class="w-40 shrink-0 truncate text-sm text-text">
                      {{ item.user.full_name }}
                    </span>
                    <div
                      class="h-2.5 flex-1 overflow-hidden rounded-full bg-sunken"
                      role="img"
                      [attr.aria-label]="
                        workloadAria(item.user.full_name, item.active_count)
                      "
                    >
                      <div
                        class="h-full rounded-full bg-brand transition-all"
                        [style.width.%]="barWidth(item.active_count)"
                      ></div>
                    </div>
                    <span
                      class="w-8 shrink-0 text-right text-sm font-medium text-text"
                    >
                      {{ item.active_count }}
                    </span>
                  </li>
                }
              </ul>
            }
          </sol-card>
        </div>

        <!-- Avance por proyecto -->
        <div class="flex flex-col gap-3">
          <h2 class="font-display text-lg font-bold tracking-tight text-text">{{ text.progressTitle() }}</h2>
          @if (dash.projects_progress.length === 0) {
            <sol-card>
              <p class="py-4 text-center text-sm text-muted">
                {{ text.progressEmpty() }}
              </p>
            </sol-card>
          } @else {
            <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
              @for (
                progress of dash.projects_progress;
                track progress.project.id
              ) {
                <sol-card>
                  <div class="flex items-center justify-between gap-2">
                    <h3 class="text-base font-semibold text-text">
                      {{ progress.project.name }}
                    </h3>
                    <span
                      class="rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-medium text-brand-soft-fg"
                    >
                      {{ methodologyLabel(progress.project.methodology) }}
                    </span>
                  </div>
                  <div class="mt-3">
                    <div class="flex items-center justify-between text-xs text-muted">
                      <span>{{ doneOfTotalLabel(progress.done, progress.total) }}</span>
                      <span class="font-medium text-text"
                        >{{ progress.percent_done }}%</span
                      >
                    </div>
                    <div
                      class="mt-1.5 h-2.5 overflow-hidden rounded-full bg-sunken"
                      role="img"
                      [attr.aria-label]="percentAria(progress.percent_done)"
                    >
                      <div
                        class="h-full rounded-full bg-success transition-all"
                        [style.width.%]="progress.percent_done"
                      ></div>
                    </div>
                  </div>
                </sol-card>
              }
            </div>
          }
        </div>
      }
    </section>
  `,
})
export class ExecutiveComponent implements OnInit, OnDestroy {
  private readonly executiveService = inject(ExecutiveService);
  private readonly i18n = inject(I18nService);

  private readonly auth = inject(AuthService);
  private readonly activeOrg = inject(ActiveOrgStore);
  protected readonly dailyTimezone = signal('America/Bogota');
  protected readonly dailyPolicy = signal<DailyDatePolicy | ''>('');
  protected readonly dailyData = signal<DailyDashboard | null>(null);
  protected readonly dailyLoading = signal(false);
  protected readonly dailyError = signal<string | null>(null);
  protected readonly dailyGroups = ['today', 'tomorrow', 'overdue', 'blocked'] as const;
  protected readonly dailyEmpty = computed(() => {
    const data = this.dailyData();
    return data !== null && this.dailyGroups.every(group => data[group].count === 0);
  });
  protected readonly dailyContext = computed(() => {
    const user = this.auth.user();
    const org = this.activeOrg.activeOrgId() ?? user?.organization_id;
    return this.auth.isAuthenticated() && user && org ? `${user.id}:${org}` : null;
  });
  private dailyRequest?: Subscription;
  private dailyGeneration = 0;
  private destroyed = false;
  private readonly dailyContextReset = effect(() => {
    this.dailyContext();
    untracked(() => this.clearDaily());
  });

  protected dailyText(key: string): string {
    return this.i18n.translate(`daily.${key}`);
  }

  protected changeDailyTimezone(value: string): void {
    if (value !== 'America/Bogota' && value !== 'UTC') return;
    this.clearDaily();
    this.dailyTimezone.set(value);
  }

  protected changeDailyPolicy(value: string): void {
    if (value !== '' && value !== 'stored_calendar_date' && value !== 'instant') return;
    this.clearDaily();
    this.dailyPolicy.set(value);
  }

  private clearDaily(): void {
    this.dailyGeneration++;
    this.dailyRequest?.unsubscribe();
    this.dailyData.set(null);
    this.dailyLoading.set(false);
    this.dailyError.set(null);
  }

  protected queryDaily(): void {
    this.clearDaily();
    const context = this.dailyContext();
    const policy = this.dailyPolicy();
    if (!context || !policy || this.destroyed) return;
    const generation = this.dailyGeneration;
    const timezone = this.dailyTimezone();
    const current = () => !this.destroyed && generation === this.dailyGeneration && context === this.dailyContext();
    this.dailyLoading.set(true);
    this.dailyRequest = this.executiveService.daily(timezone, policy).subscribe({
      next: res => {
        if (!current()) return;
        this.dailyData.set(res.data);
        this.dailyLoading.set(false);
      },
      error: (error: HttpErrorResponse) => {
        if (!current()) return;
        this.dailyLoading.set(false);
        const code = error.error?.code;
        const known = ['daily_disabled', 'organization_unavailable', 'invalid_daily_parameters', 'input_limit', 'timeout', 'daily_unavailable'];
        this.dailyError.set(this.dailyText(`errors.${error.status === 0 ? 'network' : known.includes(code) ? code : 'load'}`));
      },
    });
  }

  protected dailyWarning(code: string): string {
    const known = ['cancellation_unsupported', 'unknown_board', 'unknown_status', 'completion_conflict', 'missing_due_date', 'naive_due_date', 'naive_updated_at', 'groups_overlap', 'missing_task_key'];
    return this.dailyText(`warnings.${known.includes(code) ? code : 'unknown'}`);
  }

  protected dailyGenerated(data: DailyDashboard): string {
    return new Intl.DateTimeFormat('es-CO', {
      timeZone: data.timezone, dateStyle: 'medium', timeStyle: 'short',
    }).format(new Date(data.generated_at));
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    this.clearDaily();
  }

  /** Textos estáticos de la vista resueltos por i18n (reactivos al idioma). */
  protected readonly text = {
    title: this.i18n.t('executive.title'),
    subtitle: this.i18n.t('executive.subtitle'),
    loading: this.i18n.t('executive.loading'),
    totalProjects: this.i18n.t('executive.totals.projects'),
    totalTasks: this.i18n.t('executive.totals.tasks'),
    totalOverdue: this.i18n.t('executive.totals.overdue'),
    totalAtRisk: this.i18n.t('executive.totals.atRisk'),
    byAssigneeTitle: this.i18n.t('executive.byAssignee.title'),
    byAssigneeEmpty: this.i18n.t('executive.byAssignee.empty'),
    noInProgress: this.i18n.t('executive.byAssignee.noInProgress'),
    risksTitle: this.i18n.t('executive.risks.title'),
    risksEmpty: this.i18n.t('executive.risks.empty'),
    noAssignee: this.i18n.t('executive.risks.noAssignee'),
    workloadTitle: this.i18n.t('executive.workload.title'),
    workloadEmpty: this.i18n.t('executive.workload.empty'),
    progressTitle: this.i18n.t('executive.progress.title'),
    progressEmpty: this.i18n.t('executive.progress.empty'),
  } as const;

  protected readonly data = signal<ExecutiveDashboard | null>(null);
  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);

  private readonly maxWorkload = computed<number>(() => {
    const workload = this.data()?.workload ?? [];
    return workload.reduce((max, item) => Math.max(max, item.active_count), 0);
  });

  ngOnInit(): void {
    this.load();
  }

  protected barWidth(count: number): number {
    const max = this.maxWorkload();
    if (max <= 0) {
      return 0;
    }
    return Math.round((count / max) * 100);
  }

  protected initial(name: string): string {
    const trimmed = name?.trim();
    return trimmed ? trimmed.charAt(0).toUpperCase() : '?';
  }

  protected priorityChip(priority: Priority): string {
    return PRIORITY_CHIP_CLASS[priority] ?? PRIORITY_CHIP_CLASS.medium;
  }

  protected priorityLabel(priority: Priority): string {
    return PRIORITY_LABELS[priority] ?? priority;
  }

  protected methodologyLabel(methodology: Methodology): string {
    return METHODOLOGY_LABELS[methodology] ?? methodology;
  }

  protected shortDate(value: string | null | undefined): string {
    return formatShortDate(value);
  }

  protected activeCountLabel(count: number): string {
    return this.i18n.translate('executive.byAssignee.activeCount', { count });
  }

  protected dueOnLabel(due: string | null | undefined): string {
    return this.i18n.translate('executive.risks.dueOn', {
      date: this.shortDate(due),
    });
  }

  protected workloadAria(name: string, count: number): string {
    return this.i18n.translate('executive.workload.barAria', { name, count });
  }

  protected doneOfTotalLabel(done: number, total: number): string {
    return this.i18n.translate('executive.progress.doneOfTotal', {
      done,
      total,
    });
  }

  protected percentAria(percent: number): string {
    return this.i18n.translate('executive.progress.percentAria', { percent });
  }

  private load(): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.executiveService.dashboard().subscribe({
      next: (res) => {
        this.data.set(res.data);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.loadError.set(
          err.status === 0
            ? this.i18n.translate('executive.errors.network')
            : this.i18n.translate('executive.errors.load'),
        );
      },
    });
  }
}
