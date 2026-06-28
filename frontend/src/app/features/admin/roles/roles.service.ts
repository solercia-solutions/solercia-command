import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '../../../core/api.config';
import {
  RoleItemResponse,
  RoleListResponse,
  RoleMenusPayload,
  RolePayload,
} from './role.model';

/** Thin HTTP client for the /admin/roles resource. */
@Injectable({ providedIn: 'root' })
export class RolesService {
  private readonly http = inject(HttpClient);
  private readonly base = `${apiBase}/admin/roles`;

  list(): Observable<RoleListResponse> {
    return this.http.get<RoleListResponse>(this.base);
  }

  get(id: string): Observable<RoleItemResponse> {
    return this.http.get<RoleItemResponse>(`${this.base}/${id}`);
  }

  create(payload: RolePayload): Observable<RoleItemResponse> {
    return this.http.post<RoleItemResponse>(this.base, payload);
  }

  update(id: string, payload: RolePayload): Observable<RoleItemResponse> {
    return this.http.patch<RoleItemResponse>(`${this.base}/${id}`, payload);
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }

  /** PUT /admin/roles/{id}/menus — replace the menu set assigned to a role. */
  setMenus(
    id: string,
    payload: RoleMenusPayload,
  ): Observable<RoleItemResponse> {
    return this.http.put<RoleItemResponse>(`${this.base}/${id}/menus`, payload);
  }
}
