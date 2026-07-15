import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import {
  AdminUserItemResponse,
  AdminUserListResponse,
  CreateUserPayload,
  UpdateUserPayload,
  UserRolesPayload,
} from './user-admin.model';

/** Thin HTTP client for the /admin/users resource. */
@Injectable({ providedIn: 'root' })
export class UsersService {
  private readonly http = inject(HttpClient);
  private readonly base = `${apiBase}/admin/users`;

  list(): Observable<AdminUserListResponse> {
    return this.http.get<AdminUserListResponse>(this.base);
  }

  get(id: string): Observable<AdminUserItemResponse> {
    return this.http.get<AdminUserItemResponse>(`${this.base}/${id}`);
  }

  create(payload: CreateUserPayload): Observable<AdminUserItemResponse> {
    return this.http.post<AdminUserItemResponse>(this.base, payload);
  }

  update(
    id: string,
    payload: UpdateUserPayload,
  ): Observable<AdminUserItemResponse> {
    return this.http.patch<AdminUserItemResponse>(`${this.base}/${id}`, payload);
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }

  /** PUT /admin/users/{id}/roles — replace the role set assigned to a user. */
  setRoles(
    id: string,
    payload: UserRolesPayload,
  ): Observable<AdminUserItemResponse> {
    return this.http.put<AdminUserItemResponse>(
      `${this.base}/${id}/roles`,
      payload,
    );
  }
}
