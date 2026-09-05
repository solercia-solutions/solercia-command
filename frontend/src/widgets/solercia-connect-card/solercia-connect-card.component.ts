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
import { Subscription, exhaustMap, interval, timer } from 'rxjs';
import {
  SolBadgeComponent,
  SolButtonComponent,
  SolCardComponent,
  SolChipComponent,
  SolIconButtonComponent,
  SolIconComponent,
  SolProgressBarComponent,
  SolSkeletonComponent,
  SolTooltipComponent,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { ToastStore } from '@shared/lib/toast';
import { readApiError } from '@shared/lib/api-error';
import { ConnectorsService } from '@entities/connector/connectors.service';
import {
  Connector,
  SolerciaConnectSession,
  SolerciaConnectState,
  SolerciaConnectStatus,
  SolerciaConnectSyncError,
  SolerciaConnectSyncResult,
  providerIcon,
  providerLabel,
  solerciaConnectSettingsOf,
} from '@entities/connector/connector.model';

/** A supervised browser login being followed by this card. */
interface LoginSession {
  sessionId: string;
  startedAt: number;
  expiresAt: number;
}

interface SinceOption {
  days: number;
  /** Chip value (chips speak strings). */
  value: string;
  labelKey: string;
}

/** Poll cadence for `GET .../sessions/{id}` (UX spec: every 2 s). */
const POLL_INTERVAL_MS = 2000;
/** Hard stop when Connect does not say how long the login window lasts. */
const DEFAULT_LOGIN_WINDOW_S = 15 * 60;

const SINCE_OPTIONS: readonly SinceOption[] = [
  { days: 1, value: '1', labelKey: 'connectors.solerciaConnect.since.d1' },
  { days: 7, value: '7', labelKey: 'connectors.solerciaConnect.since.d7' },
  { days: 30, value: '30', labelKey: 'connectors.solerciaConnect.since.d30' },
];

const STATE_BADGE: Record<SolerciaConnectState, 'success' | 'warning' | 'danger'> = {
  connected: 'success',
  needs_login: 'warning',
  interactive_disabled: 'warning',
  runtime_unavailable: 'danger',
  runtime_unauthorized: 'danger',
  misconfigured: 'danger',
  error: 'danger',
};

/**
 * Card for ONE Solercia Connect connector: durable state (`/status`), the
 * supervised browser login (start + poll every 2 s with a visible countdown),
 * "test connection", mail sync into intake/tasks and the delete request.
 *
 * Rules honoured here (UX spec): `/status` is never called while a login
 * session is `running` (Connect's browser profile has a single owner); no
 * button is disabled without a tooltip saying why; every failure shows the
 * backend `detail` when there is one; polling stops on destroy.
 */
@Component({
  selector: 'sol-solercia-connect-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    SolBadgeComponent,
    SolButtonComponent,
    SolCardComponent,
    SolChipComponent,
    SolIconButtonComponent,
    SolIconComponent,
    SolProgressBarComponent,
    SolSkeletonComponent,
    SolTooltipComponent,
  ],
  template: `
    <sol-card>
      <div class="flex flex-col gap-4" [attr.aria-busy]="statusLoading()">
        <!-- Header: icon + name + state badge + delete (far from the primary action) -->
        <div class="flex items-start justify-between gap-2">
          <div class="flex min-w-0 items-center gap-3">
            <span
              class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand"
              aria-hidden="true"
            >
              <sol-icon [name]="icon" />
            </span>
            <div class="min-w-0">
              <h2 class="text-base font-semibold text-text">{{ label }}</h2>
              <div class="mt-1">
                @if (statusLoading() && !status()) {
                  <sol-skeleton variant="text" width="9rem" />
                } @else if (status(); as current) {
                  <sol-badge [variant]="badgeVariant(current.state)" size="sm">
                    {{ stateLabel(current.state) }}
                  </sol-badge>
                }
              </div>
            </div>
          </div>
          <sol-icon-button
            icon="trash"
            variant="danger"
            size="touch"
            [ariaLabel]="deleteAria()"
            (clicked)="deleteRequested.emit(connector())"
          />
        </div>

        <!-- Body: account, target, route, last check -->
        <dl class="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div class="flex min-w-0 flex-col">
            <dt class="text-xs font-semibold uppercase tracking-wide text-muted">
              {{ text.account() }}
            </dt>
            <dd class="truncate text-text" [title]="settings()?.account ?? ''">
              {{ settings()?.account ?? '—' }}
            </dd>
          </div>
          <div class="flex min-w-0 flex-col">
            <dt class="text-xs font-semibold uppercase tracking-wide text-muted">
              {{ text.target() }}
            </dt>
            <dd class="text-text">{{ targetLabel() }}</dd>
          </div>
          <div class="flex min-w-0 flex-col">
            <dt class="text-xs font-semibold uppercase tracking-wide text-muted">
              {{ text.route() }}
            </dt>
            <dd class="text-text">
              @if (statusLoading() && !status()) {
                <sol-skeleton variant="text" width="8rem" />
              } @else {
                {{ routeLabel() }}
              }
            </dd>
          </div>
          <div class="flex min-w-0 flex-col">
            <dt class="text-xs font-semibold uppercase tracking-wide text-muted">
              {{ text.checked() }}
            </dt>
            <dd class="text-text">
              @if (statusLoading() && !status()) {
                <sol-skeleton variant="text" width="7rem" />
              } @else if (status(); as current) {
                <time [attr.datetime]="current.checked_at" [title]="absoluteChecked()">
                  {{ relativeChecked() }}
                </time>
              } @else {
                —
              }
            </dd>
          </div>
        </dl>

        <!-- Durable state detail + remediation (only when there is something to say) -->
        @if (status(); as current) {
          @if (current.state === 'needs_login' && !loginSession()) {
            <p class="text-sm font-medium text-warning">{{ text.step2() }}</p>
          }
          @if (current.state !== 'connected' && current.detail) {
            <p class="text-sm text-muted">{{ current.detail }}</p>
          }
          @if (current.remediation.length > 0) {
            <div class="flex flex-col gap-2">
              <div class="flex items-center justify-between gap-2">
                <h3 class="text-xs font-semibold uppercase tracking-wide text-muted">
                  {{ text.remediationTitle() }}
                </h3>
                <sol-icon-button
                  icon="clipboard"
                  variant="ghost"
                  size="touch"
                  [ariaLabel]="text.copy()"
                  (clicked)="copyRemediation(current.remediation)"
                />
              </div>
              <pre
                class="overflow-x-auto whitespace-pre-wrap break-words rounded-md bg-sunken px-3 py-2 font-mono text-xs text-text"
              >{{ current.remediation.join('\\n') }}</pre>
            </div>
          }
        }

        <!-- Supervised login in progress -->
        @if (loginSession()) {
          <div class="flex flex-col gap-3 rounded-lg border border-border bg-sunken px-4 py-3">
            <sol-progress-bar
              mode="continuous"
              size="sm"
              [value]="remainingSeconds()"
              [max]="totalSeconds()"
              [variant]="remainingSeconds() < 60 ? 'warning' : 'primary'"
              [ariaLabel]="text.progressAria()"
            />
            <p class="text-sm text-text" aria-live="polite">{{ text.inProgress() }}</p>
            <p class="text-sm font-medium text-text tabular-nums" aria-live="off">
              {{ remainingLabel() }}
            </p>
            <div class="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
              <sol-button type="button" variant="ghost" size="touch" (clicked)="cancelTracking()">
                {{ text.cancelPolling() }}
              </sol-button>
              <span class="text-xs text-muted">{{ text.cancelHint() }}</span>
            </div>
          </div>
        }

        <!-- Sync detail (expanded from the warning toast) -->
        @if (showSyncDetail()) {
          @if (lastSync(); as sync) {
            <div class="flex flex-col gap-2 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3">
              <div class="flex items-center justify-between gap-2">
                <h3 class="text-xs font-semibold uppercase tracking-wide text-muted">
                  {{ text.syncDetailTitle() }}
                </h3>
                <button
                  type="button"
                  class="text-xs font-medium text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/55"
                  (click)="showSyncDetail.set(false)"
                >
                  {{ text.hideDetail() }}
                </button>
              </div>
              <p class="text-sm text-text">{{ syncSummary(sync) }}</p>
              <ul class="flex flex-col gap-1 text-sm text-text">
                @for (error of sync.errors; track $index) {
                  <li class="flex gap-2">
                    <code class="shrink-0 rounded bg-sunken px-1 font-mono text-xs">{{ error.code }}</code>
                    <span>{{ error.detail }}</span>
                  </li>
                }
              </ul>
            </div>
          }
        }

        <!-- Actions: primary first and large; stack under 640 px -->
        @if (!loginSession()) {
          <div class="flex flex-col gap-3">
            @if (status()?.state === 'connected') {
              <div
                role="radiogroup"
                class="flex flex-wrap items-center gap-2"
                [attr.aria-label]="text.sinceLabel()"
              >
                <span class="text-xs font-semibold uppercase tracking-wide text-muted">
                  {{ text.sinceLabel() }}
                </span>
                @for (option of sinceOptions; track option.value) {
                  <sol-chip
                    [role]="'radio'"
                    size="sm"
                    [value]="option.value"
                    [label]="sinceLabel(option)"
                    [selected]="sinceDays() === option.days"
                    [disabled]="syncing()"
                    (toggled)="sinceDays.set(option.days)"
                  />
                }
              </div>
            }
            <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
              @switch (primaryAction()) {
                @case ('sync') {
                  <sol-button
                    type="button"
                    variant="primary"
                    size="touch"
                    [loading]="syncing()"
                    (clicked)="sync()"
                  >
                    {{ text.sync() }}
                  </sol-button>
                  <sol-button
                    type="button"
                    variant="secondary"
                    size="touch"
                    [loading]="loginStarting()"
                    (clicked)="startLogin()"
                  >
                    {{ text.refresh() }}
                  </sol-button>
                }
                @case ('login') {
                  <sol-button
                    type="button"
                    variant="primary"
                    size="touch"
                    [loading]="loginStarting()"
                    (clicked)="startLogin()"
                  >
                    {{ text.login() }}
                  </sol-button>
                }
                @case ('retry') {
                  <sol-button
                    type="button"
                    variant="primary"
                    size="touch"
                    [loading]="statusLoading()"
                    (clicked)="refreshStatus()"
                  >
                    {{ text.retry() }}
                  </sol-button>
                }
              }
              @if (primaryAction() !== 'retry') {
                <sol-button
                  type="button"
                  variant="ghost"
                  size="touch"
                  [loading]="statusLoading()"
                  (clicked)="refreshStatus()"
                >
                  {{ text.test() }}
                </sol-button>
              }
            </div>
          </div>
        } @else {
          <!-- While the login runs, test/sync are disabled WITH the reason (tooltip). -->
          <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
            <sol-tooltip [text]="text.waitLogin()">
              <sol-button type="button" variant="ghost" size="touch" [disabled]="true">
                {{ text.test() }}
              </sol-button>
            </sol-tooltip>
            <sol-tooltip [text]="text.waitLogin()">
              <sol-button type="button" variant="secondary" size="touch" [disabled]="true">
                {{ text.sync() }}
              </sol-button>
            </sol-tooltip>
          </div>
        }
      </div>
    </sol-card>
  `,
})
export class SolerciaConnectCardComponent implements OnInit {
  private readonly connectorsService = inject(ConnectorsService);
  private readonly i18n = inject(I18nService);
  private readonly toast = inject(ToastStore);
  private readonly destroyRef = inject(DestroyRef);

  readonly connector = input.required<Connector>();
  readonly deleteRequested = output<Connector>();

  protected readonly label = providerLabel('solercia_connect');
  protected readonly icon = providerIcon('solercia_connect');
  protected readonly sinceOptions = SINCE_OPTIONS;

  protected readonly text = {
    account: this.i18n.t('connectors.solerciaConnect.fields.account'),
    target: this.i18n.t('connectors.solerciaConnect.fields.target'),
    route: this.i18n.t('connectors.solerciaConnect.fields.route'),
    checked: this.i18n.t('connectors.solerciaConnect.fields.checked'),
    step2: this.i18n.t('connectors.solerciaConnect.step2'),
    remediationTitle: this.i18n.t('connectors.solerciaConnect.remediationTitle'),
    copy: this.i18n.t('connectors.solerciaConnect.actions.copy'),
    login: this.i18n.t('connectors.solerciaConnect.actions.login'),
    refresh: this.i18n.t('connectors.solerciaConnect.actions.refresh'),
    retry: this.i18n.t('connectors.solerciaConnect.actions.retry'),
    test: this.i18n.t('connectors.solerciaConnect.actions.test'),
    sync: this.i18n.t('connectors.solerciaConnect.actions.sync'),
    cancelPolling: this.i18n.t('connectors.solerciaConnect.actions.cancelPolling'),
    hideDetail: this.i18n.t('connectors.solerciaConnect.actions.hideDetail'),
    waitLogin: this.i18n.t('connectors.solerciaConnect.waitLogin'),
    sinceLabel: this.i18n.t('connectors.solerciaConnect.sinceLabel'),
    inProgress: this.i18n.t('connectors.solerciaConnect.session.inProgress'),
    cancelHint: this.i18n.t('connectors.solerciaConnect.session.cancelHint'),
    progressAria: this.i18n.t('connectors.solerciaConnect.session.progressAria'),
    syncDetailTitle: this.i18n.t('connectors.solerciaConnect.sync.detailTitle'),
  } as const;

  // -- durable state -----------------------------------------------------------
  protected readonly status = signal<SolerciaConnectStatus | null>(null);
  protected readonly statusLoading = signal(false);
  protected readonly settings = computed(() => solerciaConnectSettingsOf(this.connector()));

  // -- supervised login ---------------------------------------------------------
  protected readonly loginStarting = signal(false);
  protected readonly loginSession = signal<LoginSession | null>(null);
  private readonly now = signal(Date.now());
  private pollSubscription: Subscription | null = null;
  private tickSubscription: Subscription | null = null;

  protected readonly remainingSeconds = computed(() => {
    const session = this.loginSession();
    if (!session) {
      return 0;
    }
    return Math.max(0, Math.ceil((session.expiresAt - this.now()) / 1000));
  });

  protected readonly totalSeconds = computed(() => {
    const session = this.loginSession();
    return session ? Math.max(1, Math.round((session.expiresAt - session.startedAt) / 1000)) : 1;
  });

  protected readonly remainingLabel = computed(() => {
    this.i18n.activeLang();
    const total = this.remainingSeconds();
    const minutes = String(Math.floor(total / 60)).padStart(2, '0');
    const seconds = String(total % 60).padStart(2, '0');
    return this.i18n.translate('connectors.solerciaConnect.session.remaining', {
      time: `${minutes}:${seconds}`,
    });
  });

  // -- sync --------------------------------------------------------------------
  protected readonly sinceDays = signal(7);
  protected readonly syncing = signal(false);
  protected readonly lastSync = signal<SolerciaConnectSyncResult | null>(null);
  protected readonly showSyncDetail = signal(false);

  /** Which button leads the action row for the current state. */
  protected readonly primaryAction = computed<'sync' | 'login' | 'retry' | 'none'>(() => {
    const state = this.status()?.state;
    switch (state) {
      case 'connected':
        return 'sync';
      case 'needs_login':
        return 'login';
      case 'runtime_unavailable':
      case 'error':
        return 'retry';
      case undefined:
        return this.statusLoading() ? 'none' : 'retry';
      default:
        return 'none';
    }
  });

  protected readonly targetLabel = computed(() => {
    this.i18n.activeLang();
    const target = this.settings()?.target;
    return target ? this.i18n.translate(`connectors.create.targets.${target}`) : '—';
  });

  protected readonly routeLabel = computed(() => {
    this.i18n.activeLang();
    const route = this.status()?.route;
    const key = route === 'browser' ? 'browser' : route ? 'official' : 'unknown';
    return this.i18n.translate(`connectors.solerciaConnect.routes.${key}`);
  });

  protected readonly absoluteChecked = computed(() => {
    const iso = this.status()?.checked_at;
    if (!iso) {
      return '';
    }
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
  });

  protected readonly relativeChecked = computed(() => {
    this.i18n.activeLang();
    const iso = this.status()?.checked_at;
    if (!iso) {
      return '—';
    }
    const elapsedMs = this.now() - new Date(iso).getTime();
    if (!Number.isFinite(elapsedMs) || elapsedMs < 60_000) {
      return this.i18n.translate('connectors.solerciaConnect.relative.now');
    }
    const minutes = Math.floor(elapsedMs / 60_000);
    if (minutes < 60) {
      return this.i18n.translate('connectors.solerciaConnect.relative.minutes', { count: minutes });
    }
    const hours = Math.floor(minutes / 60);
    if (hours < 24) {
      return this.i18n.translate('connectors.solerciaConnect.relative.hours', { count: hours });
    }
    return this.i18n.translate('connectors.solerciaConnect.relative.days', {
      count: Math.floor(hours / 24),
    });
  });

  ngOnInit(): void {
    this.refreshStatus();
    // Keeps "Verificado hace X min" honest without re-querying the backend.
    interval(60_000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.now.set(Date.now()));
  }

  // -- presentation helpers -------------------------------------------------------

  protected badgeVariant(state: SolerciaConnectState): 'success' | 'warning' | 'danger' {
    return STATE_BADGE[state] ?? 'danger';
  }

  protected stateLabel(state: SolerciaConnectState): string {
    return this.i18n.translate(`connectors.solerciaConnect.states.${state}`);
  }

  protected deleteAria(): string {
    return this.i18n.translate('connectors.delete.ariaLabel', { provider: this.label });
  }

  protected sinceLabel(option: SinceOption): string {
    return this.i18n.translate(option.labelKey);
  }

  protected syncSummary(sync: SolerciaConnectSyncResult): string {
    return this.i18n.translate('connectors.solerciaConnect.sync.summary', {
      new: sync.items_new,
      duplicated: sync.items_duplicated,
      tasks: sync.tasks_created,
    });
  }

  // -- status --------------------------------------------------------------------

  /** `GET .../status`. Never while a login session is running (single-owner profile). */
  protected refreshStatus(): void {
    if (this.loginSession() || this.statusLoading()) {
      return;
    }
    this.statusLoading.set(true);
    this.connectorsService.solerciaConnectStatus(this.connector().id).subscribe({
      next: (res) => {
        this.status.set(res.data);
        this.now.set(Date.now());
        this.statusLoading.set(false);
      },
      error: (err: unknown) => {
        this.statusLoading.set(false);
        this.patchStatus('error', this.errorMessage(err, 'connectors.solerciaConnect.status.error'));
      },
    });
  }

  /** Local, optimistic update of the badge/detail from a write's outcome. */
  private patchStatus(
    state: SolerciaConnectState,
    detail: string | null,
    remediation: string[] = [],
  ): void {
    const current = this.status();
    this.status.set({
      state,
      route: current?.route ?? null,
      account: current?.account ?? this.settings()?.account ?? null,
      checked_at: new Date().toISOString(),
      detail,
      remediation,
      runtime: current?.runtime ?? { reachable: null },
    });
    this.now.set(Date.now());
  }

  // -- supervised login -------------------------------------------------------------

  protected startLogin(): void {
    if (this.loginStarting() || this.loginSession()) {
      return;
    }
    this.loginStarting.set(true);
    this.connectorsService.startSolerciaConnectLogin(this.connector().id).subscribe({
      next: (res) => {
        this.loginStarting.set(false);
        this.track(res.data.session_id, res.data.expires_in_seconds ?? DEFAULT_LOGIN_WINDOW_S);
      },
      error: (err: unknown) => {
        this.loginStarting.set(false);
        this.onStartError(err);
      },
    });
  }

  private onStartError(err: unknown): void {
    const api = readApiError(err);
    if (api.status === 409 && api.code === 'solercia_connect_busy') {
      const running = api.meta?.['session_id'];
      const sessionId = typeof running === 'string' && running.length > 0 ? running : null;
      this.toast.warning(
        this.i18n.translate('connectors.solerciaConnect.session.busy'),
        sessionId
          ? {
              durationMs: 0,
              action: {
                label: this.i18n.translate('connectors.solerciaConnect.actions.followSession'),
                run: () => this.track(sessionId, DEFAULT_LOGIN_WINDOW_S),
              },
            }
          : undefined,
      );
      return;
    }
    if (api.status === 409 && api.code === 'solercia_connect_interactive_disabled') {
      this.patchStatus('interactive_disabled', api.detail, api.detail ? [api.detail] : []);
      return;
    }
    this.toast.error(this.errorMessage(err, 'connectors.solerciaConnect.session.startError'));
  }

  /** Follows one session: countdown every second, poll every 2 s, hard stop at expiry. */
  private track(sessionId: string, windowSeconds: number): void {
    this.stopTracking();
    const startedAt = Date.now();
    this.now.set(startedAt);
    this.loginSession.set({
      sessionId,
      startedAt,
      expiresAt: startedAt + Math.max(1, windowSeconds) * 1000,
    });

    this.tickSubscription = interval(1000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.now.set(Date.now());
        if (this.remainingSeconds() <= 0) {
          this.onExpired();
        }
      });

    this.pollSubscription = timer(0, POLL_INTERVAL_MS)
      .pipe(
        exhaustMap(() =>
          this.connectorsService.solerciaConnectSession(this.connector().id, sessionId),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (res) => this.onSessionUpdate(res.data),
        error: (err: unknown) => {
          this.stopTracking();
          this.toast.error(this.errorMessage(err, 'connectors.solerciaConnect.session.pollError'));
        },
      });
  }

  private onSessionUpdate(session: SolerciaConnectSession): void {
    if (session.state === 'running') {
      return;
    }
    this.stopTracking();
    const account = this.settings()?.account ?? '';
    switch (session.state) {
      case 'connected':
        this.toast.success(
          this.i18n.translate('connectors.solerciaConnect.session.connected', { account }),
        );
        break;
      case 'failed':
        this.toast.error(this.failedMessage(session, account));
        break;
      case 'not_found':
        this.toast.error(this.i18n.translate('connectors.solerciaConnect.session.notFound'));
        break;
    }
    this.refreshStatus();
  }

  private failedMessage(session: SolerciaConnectSession, account: string): string {
    const code = session.error_code;
    if (
      code === 'browser_login_required' ||
      code === 'browser_mfa_required' ||
      code === 'browser_account_mismatch'
    ) {
      return this.i18n.translate(`connectors.solerciaConnect.session.failed.${code}`, { account });
    }
    return session.detail || this.i18n.translate('connectors.solerciaConnect.session.failedDefault');
  }

  private onExpired(): void {
    this.stopTracking();
    this.toast.warning(this.i18n.translate('connectors.solerciaConnect.session.expired'));
    this.refreshStatus();
  }

  /** Stops polling only; the browser Connect opened stays open on the machine. */
  protected cancelTracking(): void {
    this.stopTracking();
    this.toast.info(this.i18n.translate('connectors.solerciaConnect.session.cancelled'));
  }

  private stopTracking(): void {
    this.pollSubscription?.unsubscribe();
    this.tickSubscription?.unsubscribe();
    this.pollSubscription = null;
    this.tickSubscription = null;
    this.loginSession.set(null);
  }

  // -- sync ------------------------------------------------------------------------

  protected sync(): void {
    if (this.syncing() || this.loginSession()) {
      return;
    }
    this.syncing.set(true);
    this.showSyncDetail.set(false);
    this.connectorsService.syncSolerciaConnect(this.connector().id, this.sinceDays()).subscribe({
      next: (res) => {
        this.syncing.set(false);
        this.onSyncResult(res.data);
      },
      error: (err: unknown) => {
        this.syncing.set(false);
        const api = readApiError(err);
        if (api.status === 409 && api.code === 'solercia_connect_needs_login') {
          const detail =
            api.detail ?? this.i18n.translate('connectors.solerciaConnect.sync.needsLogin');
          this.patchStatus('needs_login', detail);
          this.toast.warning(detail);
          return;
        }
        this.toast.error(this.errorMessage(err, 'connectors.solerciaConnect.sync.error'));
      },
    });
  }

  private onSyncResult(result: SolerciaConnectSyncResult): void {
    this.lastSync.set(result);
    const first: SolerciaConnectSyncError | undefined = result.errors[0];
    if (first) {
      this.toast.warning(
        this.i18n.translate('connectors.solerciaConnect.sync.partial', { first: first.detail }),
        {
          action: {
            label: this.i18n.translate('connectors.solerciaConnect.actions.viewDetail'),
            run: () => this.showSyncDetail.set(true),
          },
        },
      );
      return;
    }
    this.toast.success(
      this.i18n.translate('connectors.solerciaConnect.sync.success', {
        new: result.items_new,
        duplicated: result.items_duplicated,
        tasks: result.tasks_created,
      }),
    );
  }

  // -- remediation -------------------------------------------------------------------

  protected copyRemediation(lines: string[]): void {
    const payload = lines.join('\n');
    const clipboard = typeof navigator !== 'undefined' ? navigator.clipboard : undefined;
    if (!clipboard) {
      this.toast.error(this.i18n.translate('connectors.solerciaConnect.actions.copyError'));
      return;
    }
    clipboard.writeText(payload).then(
      () => this.toast.success(this.i18n.translate('connectors.solerciaConnect.actions.copied')),
      () => this.toast.error(this.i18n.translate('connectors.solerciaConnect.actions.copyError')),
    );
  }

  // -- errors -------------------------------------------------------------------------

  /** Backend `detail` when present; network fallback; otherwise the given key. */
  private errorMessage(err: unknown, fallbackKey: string): string {
    const api = readApiError(err);
    if (api.status === 0) {
      return this.i18n.translate('connectors.errors.network');
    }
    return api.detail ?? this.i18n.translate(fallbackKey);
  }
}
