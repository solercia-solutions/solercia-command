import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import { skipGlobalErrorHandling } from '@shared/api/error-handling.context';
import {
  DependencyItemResponse,
  DependencyListResponse,
  DependencyPayload,
} from './dependency.model';

/**
 * Thin HTTP client for the /admin/dependencies resource.
 *
 * Every call opts out of the global error handler: the admin pages already
 * show their own inline error.
 */
@Injectable({ providedIn: 'root' })
export class DependenciesService {
  private readonly http = inject(HttpClient);
  private readonly base = `${apiBase}/admin/dependencies`;

  list(): Observable<DependencyListResponse> {
    return this.http.get<DependencyListResponse>(this.base, {
      context: skipGlobalErrorHandling(),
    });
  }

  get(id: string): Observable<DependencyItemResponse> {
    return this.http.get<DependencyItemResponse>(`${this.base}/${id}`, {
      context: skipGlobalErrorHandling(),
    });
  }

  create(payload: DependencyPayload): Observable<DependencyItemResponse> {
    return this.http.post<DependencyItemResponse>(this.base, payload, {
      context: skipGlobalErrorHandling(),
    });
  }

  update(
    id: string,
    payload: DependencyPayload,
  ): Observable<DependencyItemResponse> {
    return this.http.patch<DependencyItemResponse>(`${this.base}/${id}`, payload, {
      context: skipGlobalErrorHandling(),
    });
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`, {
      context: skipGlobalErrorHandling(),
    });
  }
}
