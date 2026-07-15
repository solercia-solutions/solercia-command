import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import {
  BurndownResponse,
  CreateSprintPayload,
  CreateTaskPayload,
  MemberListResponse,
  SprintClosePayload,
  SprintCloseResponse,
  SprintItemResponse,
  SprintListResponse,
  TaskItemResponse,
  TaskListResponse,
  UpdateSprintPayload,
  UpdateTaskPayload,
  VelocityResponse,
} from './workspace.model';

/** Optional filters for the project task list. */
export interface TaskQuery {
  sprint_id?: string;
  status?: string;
  assignee_id?: string;
}

/**
 * Thin HTTP client for the project workspace resources: members, tasks and
 * sprints. All endpoints are tenant-scoped server-side via the bearer token.
 */
@Injectable({ providedIn: 'root' })
export class WorkspaceService {
  private readonly http = inject(HttpClient);

  /* ---- Members ----------------------------------------------------------- */

  members(projectId: string): Observable<MemberListResponse> {
    return this.http.get<MemberListResponse>(
      `${apiBase}/projects/${projectId}/members`,
    );
  }

  /* ---- Tasks ------------------------------------------------------------- */

  tasks(projectId: string, query: TaskQuery = {}): Observable<TaskListResponse> {
    let params = new HttpParams();
    if (query.sprint_id) {
      params = params.set('sprint_id', query.sprint_id);
    }
    if (query.status) {
      params = params.set('status', query.status);
    }
    if (query.assignee_id) {
      params = params.set('assignee_id', query.assignee_id);
    }
    return this.http.get<TaskListResponse>(
      `${apiBase}/projects/${projectId}/tasks`,
      { params },
    );
  }

  createTask(
    projectId: string,
    payload: CreateTaskPayload,
  ): Observable<TaskItemResponse> {
    return this.http.post<TaskItemResponse>(
      `${apiBase}/projects/${projectId}/tasks`,
      payload,
    );
  }

  getTask(taskId: string): Observable<TaskItemResponse> {
    return this.http.get<TaskItemResponse>(`${apiBase}/tasks/${taskId}`);
  }

  updateTask(
    taskId: string,
    payload: UpdateTaskPayload,
  ): Observable<TaskItemResponse> {
    return this.http.patch<TaskItemResponse>(
      `${apiBase}/tasks/${taskId}`,
      payload,
    );
  }

  deleteTask(taskId: string): Observable<void> {
    return this.http.delete<void>(`${apiBase}/tasks/${taskId}`);
  }

  /* ---- Sprints ----------------------------------------------------------- */

  sprints(projectId: string): Observable<SprintListResponse> {
    return this.http.get<SprintListResponse>(
      `${apiBase}/projects/${projectId}/sprints`,
    );
  }

  createSprint(
    projectId: string,
    payload: CreateSprintPayload,
  ): Observable<SprintItemResponse> {
    return this.http.post<SprintItemResponse>(
      `${apiBase}/projects/${projectId}/sprints`,
      payload,
    );
  }

  updateSprint(
    sprintId: string,
    payload: UpdateSprintPayload,
  ): Observable<SprintItemResponse> {
    return this.http.patch<SprintItemResponse>(
      `${apiBase}/sprints/${sprintId}`,
      payload,
    );
  }

  /** Burndown series for a sprint (ideal vs actual remaining work). */
  burndown(
    projectId: string,
    sprintId: string,
  ): Observable<BurndownResponse> {
    return this.http.get<BurndownResponse>(
      `${apiBase}/projects/${projectId}/sprints/${sprintId}/burndown`,
    );
  }

  /**
   * Close a sprint via the dedicated close endpoint. Computes completed_points
   * and moves incomplete tasks to the backlog or a target sprint.
   */
  closeSprint(
    sprintId: string,
    payload: SprintClosePayload = {},
  ): Observable<SprintCloseResponse> {
    return this.http.post<SprintCloseResponse>(
      `${apiBase}/sprints/${sprintId}/close`,
      payload,
    );
  }

  /** Velocity report: completed points per closed sprint + projections. */
  velocity(projectId: string): Observable<VelocityResponse> {
    return this.http.get<VelocityResponse>(
      `${apiBase}/projects/${projectId}/velocity`,
    );
  }
}
