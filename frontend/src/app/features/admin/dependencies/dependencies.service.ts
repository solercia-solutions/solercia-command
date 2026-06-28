import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '../../../core/api.config';
import {
  DependencyItemResponse,
  DependencyListResponse,
  DependencyPayload,
} from './dependency.model';

/** Thin HTTP client for the /admin/dependencies resource. */
@Injectable({ providedIn: 'root' })
export class DependenciesService {
  private readonly http = inject(HttpClient);
  private readonly base = `${apiBase}/admin/dependencies`;

  list(): Observable<DependencyListResponse> {
    return this.http.get<DependencyListResponse>(this.base);
  }

  get(id: string): Observable<DependencyItemResponse> {
    return this.http.get<DependencyItemResponse>(`${this.base}/${id}`);
  }

  create(payload: DependencyPayload): Observable<DependencyItemResponse> {
    return this.http.post<DependencyItemResponse>(this.base, payload);
  }

  update(
    id: string,
    payload: DependencyPayload,
  ): Observable<DependencyItemResponse> {
    return this.http.patch<DependencyItemResponse>(`${this.base}/${id}`, payload);
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }
}
