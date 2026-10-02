import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import { DailyDatePolicy, DailyResponse, ExecutiveResponse } from './executive.model';

/** Thin HTTP client for the executive dashboard. */
@Injectable({ providedIn: 'root' })
export class ExecutiveService {
  private readonly http = inject(HttpClient);

  daily(timezone: string, datePolicy: DailyDatePolicy): Observable<DailyResponse> {
    return this.http.get<DailyResponse>(`${apiBase}/dashboard/daily`, {
      params: { timezone, date_policy: datePolicy },
    });
  }

  dashboard(): Observable<ExecutiveResponse> {
    return this.http.get<ExecutiveResponse>(`${apiBase}/dashboard/executive`);
  }
}
