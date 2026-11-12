import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import { skipGlobalErrorHandling } from '@shared/api/error-handling.context';
import { DailyDatePolicy, DailyResponse, ExecutiveResponse } from './executive.model';

/**
 * Thin HTTP client for the executive dashboard.
 *
 * Both calls opt out of the global error handler: the executive page already
 * shows its own inline error per block.
 */
@Injectable({ providedIn: 'root' })
export class ExecutiveService {
  private readonly http = inject(HttpClient);

  daily(timezone: string, datePolicy: DailyDatePolicy): Observable<DailyResponse> {
    return this.http.get<DailyResponse>(`${apiBase}/dashboard/daily`, {
      params: { timezone, date_policy: datePolicy },
      context: skipGlobalErrorHandling(),
    });
  }

  dashboard(): Observable<ExecutiveResponse> {
    return this.http.get<ExecutiveResponse>(`${apiBase}/dashboard/executive`, {
      context: skipGlobalErrorHandling(),
    });
  }
}
