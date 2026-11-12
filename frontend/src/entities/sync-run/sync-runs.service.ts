import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import { skipGlobalErrorHandling } from '@shared/api/error-handling.context';
import { SyncRun, SyncRunPage } from './sync-run.model';

/** `/sync/*`: solo admin. 409 `SYNC_ALREADY_RUNNING` si ya hay una corrida en curso. */
@Injectable({ providedIn: 'root' })
export class SyncRunsService {
  private readonly http = inject(HttpClient);
  private readonly base = `${apiBase}/sync`;

  list(page: number, size: number): Observable<SyncRunPage> {
    const params = new HttpParams().set('page', page).set('size', size);
    return this.http.get<SyncRunPage>(`${this.base}/runs`, {
      params,
      context: skipGlobalErrorHandling(),
    });
  }

  runNow(): Observable<{ data: SyncRun }> {
    return this.http.post<{ data: SyncRun }>(`${this.base}/run`, null, {
      context: skipGlobalErrorHandling(),
    });
  }
}
