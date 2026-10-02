import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import { ImportFormat, OptionCollection, OptionsResponse, PreviewResponse, ReviewRequest, ReviewResponse } from './task-import.model';

@Injectable({ providedIn: 'root' })
export class TaskImportService {
  private readonly http = inject(HttpClient);

  options(collection: OptionCollection, page: number, query: string): Observable<OptionsResponse> {
    return this.http.get<OptionsResponse>(`${apiBase}/task-import/options`, {
      params: { [`${collection}_page`]: page, [`${collection}_size`]: 20, [`${collection}_q`]: query },
    });
  }

  review(request: ReviewRequest): Observable<ReviewResponse> {
    return this.http.post<ReviewResponse>(`${apiBase}/task-import/review`, request);
  }

  /** Transient preview only. Auth and organization headers come from the interceptor. */
  preview(file: File, format: ImportFormat): Observable<PreviewResponse> {
    return this.http.post<PreviewResponse>(`${apiBase}/task-import/preview`, file, {
      params: { format, profile: 'checklist' },
      headers: { 'Content-Type': 'application/octet-stream' },
    });
  }
}
