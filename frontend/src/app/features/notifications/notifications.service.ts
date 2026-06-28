import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, forkJoin, tap } from 'rxjs';
import { apiBase } from '../../core/api.config';
import {
  AppNotification,
  NotificationListResponse,
  NotificationStatus,
  UnreadCountResponse,
} from './notification.model';

@Injectable({ providedIn: 'root' })
export class NotificationsService {
  private readonly http = inject(HttpClient);

  /** Reactive unread count — read by the header badge. Updated by refreshUnreadCount(). */
  readonly unreadCount = signal<number>(0);

  /** GET /notifications?status=… — returns wrapped list. */
  list(status?: NotificationStatus): Observable<NotificationListResponse> {
    const params: Record<string, string> = {};
    if (status) params['status'] = status;
    return this.http.get<NotificationListResponse>(`${apiBase}/notifications`, { params });
  }

  /** Fetches the current unread count and updates the signal. Fire-and-forget. */
  refreshUnreadCount(): void {
    this.http
      .get<UnreadCountResponse>(`${apiBase}/notifications/unread-count`)
      .subscribe({ next: (res) => this.unreadCount.set(res.data.count), error: () => {} });
  }

  /** PATCH /notifications/{id} — updates status, then refreshes the badge count. */
  updateStatus(id: string, status: NotificationStatus): Observable<unknown> {
    return this.http
      .patch<unknown>(`${apiBase}/notifications/${id}`, { status })
      .pipe(tap(() => this.refreshUnreadCount()));
  }

  /**
   * Marks all given notifications as read in parallel,
   * then refreshes the badge once when all complete.
   */
  markAllRead(notifications: AppNotification[]): Observable<unknown[]> {
    const requests = notifications.map((n) =>
      this.http.patch<unknown>(`${apiBase}/notifications/${n.id}`, { status: 'read' }),
    );
    return forkJoin(requests).pipe(tap(() => this.refreshUnreadCount()));
  }

  /**
   * Fetches a task by UUID to resolve its task_key for navigation.
   * The backend wraps the response in { data: Task }.
   */
  resolveTaskKey(taskId: string): Observable<{ data: { task_key?: string | null } }> {
    return this.http.get<{ data: { task_key?: string | null } }>(
      `${apiBase}/tasks/${taskId}`,
    );
  }
}
