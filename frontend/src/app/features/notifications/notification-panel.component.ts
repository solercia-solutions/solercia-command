import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  OnInit,
  Output,
  inject,
  signal,
} from '@angular/core';
import { Router } from '@angular/router';
import { NotificationsService } from './notifications.service';
import { AppNotification, RULE_TYPE_LABELS } from './notification.model';

/** Formats an ISO timestamp as a relative Spanish string ("hace 2 h"). */
function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return 'ahora mismo';
  if (mins < 60) return `hace ${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.floor(hours / 24);
  return `hace ${days} d`;
}

/**
 * Notification center dropdown panel.
 * Lists active notifications with actions (mark as read, resolve, navigate to task).
 * Emits `closed` when an action should dismiss the panel (e.g. task navigation).
 */
@Component({
  selector: 'bk-notification-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [],
  template: `
    <div
      role="dialog"
      aria-label="Centro de notificaciones"
      class="w-80 rounded-xl border border-border bg-elevated shadow-lg sm:w-96"
    >
      <!-- Header -->
      <div class="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 class="text-sm font-semibold text-text">Notificaciones</h2>
        @if (notifications().length > 0) {
          <button
            type="button"
            (click)="markAllRead()"
            class="text-xs font-medium text-brand hover:underline
                   focus:outline-none focus-visible:ring-1 focus-visible:ring-ring/55"
          >
            Marcar todas como leídas
          </button>
        }
      </div>

      <!-- Body -->
      <div class="max-h-[28rem] overflow-y-auto">
        @if (loading()) {
          <div class="flex items-center justify-center py-10">
            <svg
              class="h-5 w-5 animate-spin text-muted"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          </div>
        } @else if (notifications().length === 0) {
          <p class="px-4 py-10 text-center text-sm text-muted">
            No tienes notificaciones pendientes.
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
                  <span
                    class="inline-flex rounded-full bg-sunken px-2 py-0.5
                           text-[10px] font-semibold uppercase tracking-wide text-subtle"
                  >
                    {{ ruleLabel(n.rule_type) }}
                  </span>
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
                      Ver tarea
                    </button>
                    <span class="text-subtle" aria-hidden="true">·</span>
                  }
                  <button
                    type="button"
                    (click)="markRead(n)"
                    class="text-xs text-muted transition-colors hover:text-text
                           focus:outline-none focus-visible:ring-1 focus-visible:ring-ring/55"
                  >
                    Marcar como leída
                  </button>
                  <span class="text-subtle" aria-hidden="true">·</span>
                  <button
                    type="button"
                    (click)="markResolved(n)"
                    class="text-xs text-muted transition-colors hover:text-text
                           focus:outline-none focus-visible:ring-1 focus-visible:ring-ring/55"
                  >
                    Resolver
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

  /** Emitted when the panel should be closed (e.g. after navigating to a task). */
  @Output() readonly closed = new EventEmitter<void>();

  protected readonly notifications = signal<AppNotification[]>([]);
  protected readonly loading = signal(false);

  protected readonly relativeTime = relativeTime;

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
