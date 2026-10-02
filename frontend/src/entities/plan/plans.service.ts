import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import {
  ActivityConflictCount,
  ActivityFilters,
  ActivityTask,
  Plan,
  PlanActivity,
  PlanActivityDetail,
  PlanDetail,
  PlanItemResponse,
  PlanActivityReport,
  PlanActivityReportUpsert,
  PlanListResponse,
  PlanType,
  ReportPeriod,
  TaskLinkCreate,
  TaskSearchResult,
} from './plan.model';

/**
 * Thin HTTP client for `/plans`.
 *
 * Reads are open to any member. Writes (`PUT .../reports/{period}`,
 * `POST/DELETE .../tasks`) are admin/manager only in the backend; the view
 * gates them with the caller's role in the active organization. Activity
 * links (`POST/DELETE .../links`) stay unexposed: they come from the sources.
 */
@Injectable({ providedIn: 'root' })
export class PlansService {
  private readonly http = inject(HttpClient);

  /** GET /plans — every plan of the active organization, unpaginated. */
  list(filters: { plan_type?: PlanType; period_year?: number } = {}): Observable<
    PlanListResponse<Plan>
  > {
    return this.http.get<PlanListResponse<Plan>>(`${apiBase}/plans`, {
      params: toParams(filters),
    });
  }

  /** GET /plans/:id — plan plus activity count per group. */
  get(id: string): Observable<PlanItemResponse<PlanDetail>> {
    return this.http.get<PlanItemResponse<PlanDetail>>(`${apiBase}/plans/${id}`);
  }

  /**
   * GET /plans/activities — activities across plans with both progress
   * figures; `period` selects which reported progress is exposed.
   */
  activities(filters: ActivityFilters = {}): Observable<PlanListResponse<PlanActivity>> {
    return this.http.get<PlanListResponse<PlanActivity>>(`${apiBase}/plans/activities`, {
      params: toParams(filters),
    });
  }

  /** GET /plans/activities/:id — reports and incoming/outgoing links. */
  activity(id: string, period?: ReportPeriod): Observable<PlanItemResponse<PlanActivityDetail>> {
    return this.http.get<PlanItemResponse<PlanActivityDetail>>(
      `${apiBase}/plans/activities/${id}`,
      { params: toParams({ period }) },
    );
  }

  /** GET /plans/activities/:id/tasks — linked tasks with their role. */
  activityTasks(id: string): Observable<PlanListResponse<ActivityTask>> {
    return this.http.get<PlanListResponse<ActivityTask>>(
      `${apiBase}/plans/activities/${id}/tasks`,
    );
  }

  /** GET /plans/activities/conflict-counts — activities with conflict links. */
  conflictCounts(): Observable<PlanListResponse<ActivityConflictCount>> {
    return this.http.get<PlanListResponse<ActivityConflictCount>>(
      `${apiBase}/plans/activities/conflict-counts`,
    );
  }

  /** PUT /plans/activities/:id/reports/:period — create or replace (admin/manager). */
  saveReport(
    id: string,
    period: ReportPeriod,
    body: PlanActivityReportUpsert,
  ): Observable<PlanItemResponse<PlanActivityReport>> {
    return this.http.put<PlanItemResponse<PlanActivityReport>>(
      `${apiBase}/plans/activities/${id}/reports/${period}`,
      body,
    );
  }

  /** POST /plans/activities/:id/tasks — link a task with a role (admin/manager). */
  linkTask(id: string, body: TaskLinkCreate): Observable<PlanItemResponse<ActivityTask>> {
    return this.http.post<PlanItemResponse<ActivityTask>>(
      `${apiBase}/plans/activities/${id}/tasks`,
      body,
    );
  }

  /** DELETE /plans/activities/:id/tasks/:taskId (admin/manager). */
  unlinkTask(id: string, taskId: string): Observable<void> {
    return this.http.delete<void>(`${apiBase}/plans/activities/${id}/tasks/${taskId}`);
  }

  /**
   * GET /search?types=task — tasks of EVERY project of the active
   * organization (the global search is tenant-scoped). `q` needs 2+ chars.
   */
  searchTasks(q: string, size = 10): Observable<PlanListResponse<TaskSearchResult>> {
    return this.http.get<PlanListResponse<TaskSearchResult>>(`${apiBase}/search`, {
      params: toParams({ q, types: 'task', size }),
    });
  }
}

/** Drops `undefined`/`null` so absent filters never reach the query string. */
function toParams(values: object): HttpParams {
  let params = new HttpParams();
  for (const [key, value] of Object.entries(values) as [string, unknown][]) {
    if (value !== undefined && value !== null && value !== '') {
      params = params.set(key, String(value));
    }
  }
  return params;
}
