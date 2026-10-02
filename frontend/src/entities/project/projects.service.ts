import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import { skipGlobalErrorHandling } from '@shared/api/error-handling.context';
import {
  CreateProjectPayload,
  ProjectDetailResponse,
  ProjectItemResponse,
  ProjectListResponse,
  ProjectProgressResponse,
  ProjectTreeResponse,
  UpdateProjectPayload,
} from './project.model';

/**
 * Thin HTTP client for the /projects resource.
 *
 * Every call opts out of the global error handler: the projects, hierarchy
 * and teams pages, the workspace and the task panel already show their own
 * inline error.
 */
@Injectable({ providedIn: 'root' })
export class ProjectsService {
  private readonly http = inject(HttpClient);

  list(): Observable<ProjectListResponse> {
    return this.http.get<ProjectListResponse>(`${apiBase}/projects`, {
      context: skipGlobalErrorHandling(),
    });
  }

  /** GET /projects/:id — single project including methodology_info. */
  get(id: string): Observable<ProjectDetailResponse> {
    return this.http.get<ProjectDetailResponse>(`${apiBase}/projects/${id}`, {
      context: skipGlobalErrorHandling(),
    });
  }

  create(payload: CreateProjectPayload): Observable<ProjectItemResponse> {
    return this.http.post<ProjectItemResponse>(
      `${apiBase}/projects`,
      payload,
      { context: skipGlobalErrorHandling() },
    );
  }

  /**
   * PATCH /projects/:id — partial edit (name/description/code). Domain
   * errors: 409 `project_code_taken`, 422 `methodology_not_editable`.
   */
  update(
    id: string,
    payload: UpdateProjectPayload,
  ): Observable<ProjectItemResponse> {
    return this.http.patch<ProjectItemResponse>(
      `${apiBase}/projects/${id}`,
      payload,
      { context: skipGlobalErrorHandling() },
    );
  }

  /**
   * PATCH /projects/:id/parent — re-link in the hierarchy (`null` = root).
   * Domain errors: 422 `self_parent` / `max_depth_exceeded`,
   * 404 `parent_not_found`, 409 `project_cycle`.
   */
  reparent(
    id: string,
    parentProjectId: string | null,
  ): Observable<ProjectItemResponse> {
    return this.http.patch<ProjectItemResponse>(
      `${apiBase}/projects/${id}/parent`,
      { parent_project_id: parentProjectId },
      { context: skipGlobalErrorHandling() },
    );
  }

  /**
   * GET /projects/:id/tree — nested structure fallback (design.md Decision
   * 1), used only when `list()` omits `parent_project_id`.
   */
  tree(id: string): Observable<ProjectTreeResponse> {
    return this.http.get<ProjectTreeResponse>(
      `${apiBase}/projects/${id}/tree`,
      { context: skipGlobalErrorHandling() },
    );
  }

  /** GET /projects/:id/progress — consolidated roll-up of the subtree. */
  progress(id: string): Observable<ProjectProgressResponse> {
    return this.http.get<ProjectProgressResponse>(
      `${apiBase}/projects/${id}/progress`,
      { context: skipGlobalErrorHandling() },
    );
  }
}
