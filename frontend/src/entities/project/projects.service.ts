import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import {
  CreateProjectPayload,
  ProjectDetailResponse,
  ProjectItemResponse,
  ProjectListResponse,
} from './project.model';

/** Thin HTTP client for the /projects resource. */
@Injectable({ providedIn: 'root' })
export class ProjectsService {
  private readonly http = inject(HttpClient);

  list(): Observable<ProjectListResponse> {
    return this.http.get<ProjectListResponse>(`${apiBase}/projects`);
  }

  /** GET /projects/:id — single project including methodology_info. */
  get(id: string): Observable<ProjectDetailResponse> {
    return this.http.get<ProjectDetailResponse>(`${apiBase}/projects/${id}`);
  }

  create(payload: CreateProjectPayload): Observable<ProjectItemResponse> {
    return this.http.post<ProjectItemResponse>(
      `${apiBase}/projects`,
      payload,
    );
  }
}
