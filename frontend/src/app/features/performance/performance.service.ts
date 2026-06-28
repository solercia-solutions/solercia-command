import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '../../core/api.config';
import { PerformanceResponse } from './performance.model';

/** Thin HTTP client for the collaborator performance dashboard. */
@Injectable({ providedIn: 'root' })
export class PerformanceService {
  private readonly http = inject(HttpClient);

  /** Org-wide performance; optionally restricted to a single sprint. */
  performance(sprintId?: string | null): Observable<PerformanceResponse> {
    let params = new HttpParams();
    if (sprintId) {
      params = params.set('sprint_id', sprintId);
    }
    return this.http.get<PerformanceResponse>(
      `${apiBase}/dashboard/performance`,
      { params },
    );
  }
}
