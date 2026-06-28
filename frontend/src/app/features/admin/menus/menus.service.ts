import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '../../../core/api.config';
import {
  AdminMenuItemResponse,
  AdminMenuListResponse,
  AdminMenuPayload,
} from './menu-admin.model';

/** Thin HTTP client for the /admin/menus resource. */
@Injectable({ providedIn: 'root' })
export class MenusService {
  private readonly http = inject(HttpClient);
  private readonly base = `${apiBase}/admin/menus`;

  /** GET /admin/menus — flat list (each item carries `parent_id`). */
  list(): Observable<AdminMenuListResponse> {
    return this.http.get<AdminMenuListResponse>(this.base);
  }

  get(id: string): Observable<AdminMenuItemResponse> {
    return this.http.get<AdminMenuItemResponse>(`${this.base}/${id}`);
  }

  create(payload: AdminMenuPayload): Observable<AdminMenuItemResponse> {
    return this.http.post<AdminMenuItemResponse>(this.base, payload);
  }

  update(
    id: string,
    payload: AdminMenuPayload,
  ): Observable<AdminMenuItemResponse> {
    return this.http.patch<AdminMenuItemResponse>(`${this.base}/${id}`, payload);
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }
}
