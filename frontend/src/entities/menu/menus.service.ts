import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import { skipGlobalErrorHandling } from '@shared/api/error-handling.context';
import {
  AdminMenuItemResponse,
  AdminMenuListResponse,
  AdminMenuPayload,
} from './menu-admin.model';

/**
 * Thin HTTP client for the /admin/menus resource.
 *
 * Every call opts out of the global error handler: the admin pages already
 * show their own inline error.
 */
@Injectable({ providedIn: 'root' })
export class MenusService {
  private readonly http = inject(HttpClient);
  private readonly base = `${apiBase}/admin/menus`;

  /** GET /admin/menus — flat list (each item carries `parent_id`). */
  list(): Observable<AdminMenuListResponse> {
    return this.http.get<AdminMenuListResponse>(this.base, {
      context: skipGlobalErrorHandling(),
    });
  }

  get(id: string): Observable<AdminMenuItemResponse> {
    return this.http.get<AdminMenuItemResponse>(`${this.base}/${id}`, {
      context: skipGlobalErrorHandling(),
    });
  }

  create(payload: AdminMenuPayload): Observable<AdminMenuItemResponse> {
    return this.http.post<AdminMenuItemResponse>(this.base, payload, {
      context: skipGlobalErrorHandling(),
    });
  }

  update(
    id: string,
    payload: AdminMenuPayload,
  ): Observable<AdminMenuItemResponse> {
    return this.http.patch<AdminMenuItemResponse>(`${this.base}/${id}`, payload, {
      context: skipGlobalErrorHandling(),
    });
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`, {
      context: skipGlobalErrorHandling(),
    });
  }
}
