import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  inject,
  output,
  signal,
} from '@angular/core';
import { Router } from '@angular/router';
import { NotificationsService } from '@entities/notification/notifications.service';
import { AppNotification, RULE_TYPE_LABELS } from '@entities/notification/notification.model';
import { SolBadgeComponent, SolSpinnerComponent } from '@shared/ui';
import { I18nService } from '@shared/i18n';

/**
 * Notification center dropdown panel.
 * Lists active notifications with actions (mark as read, resolve, navigate to task).
 * Emits `closed` when an action should dismiss the panel (e.g. task navigation).
 */
@Component({
  selector: 'sol-notification-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [SolBadgeComponent, SolSpinnerComponent],
  template: `
    <div
      role="dialog"
      [attr.aria-label]="text.dialogAria()"
      class="w-80 rounded-xl border border-border bg-elevated shadow-lg sm:w-96"
    >
      <!-- Header -->
      <div class="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 class="text-sm font-semibold text-text">{{ text.title() }}</h2>
        @if (notifications().length > 0) {
          <button
            type="button"
            (click)="markAllRead()"
            class="text-xs font-medium text-brand hover:underline
                   focus:outline-none focus-visible:ring-1 focus-visible:ring-ring/55"
          >
            {{ text.markAllRead() }}
          </button>
        }
      </div>

      <!-- Body -->
      <div class="max-h-[28rem] overflow-y-auto">
        @if (loading()) {
          <div class="flex items-center justify-center py-10">
            <sol-spinner size="md" />
          </div>
        } @else if (notifications().length === 0) {
          <p class="px-4 py-10 text-center text-sm text-muted">
            {{ text.empty() }}
          </p>
        } @else {
          <ul role="list" class="divide-y divide-border">
            @for (n of notifications(); track n.id) {
              <li class="px-4 py-3 transition-colors hover:bg-sunken">
                <!-- Content -->
                <p class="truncate text-sm font-medium text-text">{{ n.title }}</p>
                <p class="mt-0.5 line-clamp-2 text-xs text-muted">{{ n.body }}</p>

                <!-- Meta row -->
                <div class="mt-1.5 flex flex-wrap items-center gap-2">
                  <sol-badge variant="neutral" size="sm">{{ ruleLabel(n.rule_type) }}</sol-badge>
                  <span class="text-[11px] text-subtle">{{ relativeTime(n.created_at) }}</span>
                </div>

                <!-- Action row -->
                <div class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1">
                  @if (n.target_type === 'task' && n.target_id) {
                    <button
                      type="button"
                      (click)="openTask(n)"
                      class="text-xs font-medium text-brand hover:underline
                             focus:outline-none focus-visible:ring-1 focus-visible:ring-ring/55"
                    >
                      {{ text.viewTask() }}
                    </button>
                    <span class="text-subtle" aria-hidden="true">·</span>
                  }
                  <button
                    type="button"
                    (click)="markRead(n)"
                    class="text-xs text-muted transition-colors hover:text-text
                           focus:outline-none focus-visible:ring-1 focus-visible:ring-ring/55"
                  >
                    {{ text.markRead() }}
                  </button>
                  <span class="text-subtle" aria-hidden="true">·</span>
                  <button
                    type="button"
                    (click)="markResolved(n)"
                    class="text-xs text-muted transition-colors hover:text-text
                           focus:outline-none focus-visible:ring-1 focus-visible:ring-ring/55"
                  >
                    {{ text.resolve() }}
                  </button>
                </div>
              </li>
            }
          </ul>
        }
      </div>
    </div>
  `,
})
export class NotificationPanelComponent implements OnInit {
  private readonly notifService = inject(NotificationsService);
  private readonly router = inject(Router);
  private readonly i18n = inject(I18nService);

  /** Emitted when the panel should be closed (e.g. after navigating to a task). */
  readonly closed = output<void>();

  /** Static UI text resolved via i18n (reactive to language change). */
  protected readonly text = {
    dialogAria: this.i18n.t('notificationPanel.dialogAria'),
    title: this.i18n.t('notificationPanel.title'),
    markAllRead: this.i18n.t('notificationPanel.markAllRead'),
    empty: this.i18n.t('notificationPanel.empty'),
    viewTask: this.i18n.t('notificationPanel.viewTask'),
    markRead: this.i18n.t('notificationPanel.markRead'),
    resolve: this.i18n.t('notificationPanel.resolve'),
  } as const;

  protected readonly notifications = signal<AppNotification[]>([]);
  protected readonly loading = signal(false);

  /** Formats an ISO timestamp as a relative Spanish string ("hace 2 h"). */
  protected relativeTime(iso: string): string {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return this.i18n.translate('notificationPanel.relativeTime.now');
    if (mins < 60) {
      return this.i18n.translate('notificationPanel.relativeTime.minutes', {
        count: mins,
      });
    }
    const hours = Math.floor(mins / 60);
    if (hours < 24) {
      return this.i18n.translate('notificationPanel.relativeTime.hours', {
        count: hours,
      });
    }
    const days = Math.floor(hours / 24);
    return this.i18n.translate('notificationPanel.relativeTime.days', {
      count: days,
    });
  }

  protected ruleLabel(ruleType: string): string {
    return RULE_TYPE_LABELS[ruleType] ?? ruleType;
  }

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.notifService.list('active').subscribe({
      next: (res) => {
        this.notifications.set(res.data);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  protected markRead(n: AppNotification): void {
    this.notifService.updateStatus(n.id, 'read').subscribe({
      next: () => this.notifications.update((list) => list.filter((x) => x.id !== n.id)),
    });
  }

  protected markResolved(n: AppNotification): void {
    this.notifService.updateStatus(n.id, 'resolved').subscribe({
      next: () => this.notifications.update((list) => list.filter((x) => x.id !== n.id)),
    });
  }

  protected markAllRead(): void {
    const active = this.notifications();
    if (active.length === 0) return;
    this.notifService.markAllRead(active).subscribe({
      next: () => this.notifications.set([]),
    });
  }

  /**
   * For target_type='task': fetches the task by UUID to resolve its task_key,
   * then navigates to /task/{task_key}. If the key is unavailable, silently no-ops.
   */
  protected openTask(n: AppNotification): void {
    if (n.target_type !== 'task' || !n.target_id) return;
    this.notifService.resolveTaskKey(n.target_id).subscribe({
      next: (res) => {
        const key = res.data.task_key;
        if (key) {
          void this.router.navigate(['/task', key]);
          this.closed.emit();
        }
      },
      error: () => {
        // task not found or no task_key — silently ignore
      },
    });
  }
}
