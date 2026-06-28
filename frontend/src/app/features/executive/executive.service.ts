import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '../../core/api.config';
import { ExecutiveResponse } from './executive.model';

/** Thin HTTP client for the executive dashboard. */
@Injectable({ providedIn: 'root' })
export class ExecutiveService {
  private readonly http = inject(HttpClient);

  dashboard(): Observable<ExecutiveResponse> {
    return this.http.get<ExecutiveResponse>(`${apiBase}/dashboard/executive`);
  }
}
