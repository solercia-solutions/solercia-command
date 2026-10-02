/**
 * Types for institutional plans (change 45a API, consumed by 45c).
 *
 * Mirrors `backend/app/modules/plans/schemas.py` field by field. Two progress
 * figures that NEVER mix (45a D3/D-F):
 * - `calculated_progress`: ratio in [0, 1] from the activity's `primary`
 *   tasks; `null` means "no linked tasks" (no evidence), never 0.
 * - `reported_progress`: self-report of `reported_period`, 0..100. Pydantic
 *   serializes `Decimal` as a JSON string ("50.00"), so it may arrive as a
 *   string; use `toPercent()` from the page helpers to read it.
 */

/** Closed vocabularies (`vocabularies.py`). */
export type PlanType = 'pspi' | 'ptr' | 'pai' | 'ptep';
export type PlanStatus = 'active' | 'archived';
export type ReportPeriod = 'I' | 'II' | 'III' | 'ANUAL';
export type TaskLinkRole = 'primary' | 'contributes';
export type ActivityLinkType = 'contributes_to' | 'derives_from' | 'duplicates';
export type LinkResolution = 'exact' | 'by_external_code' | 'conflict' | 'manual';

/** Decimal fields arrive as strings (Pydantic v2) or numbers. */
export type ApiDecimal = string | number;

/** `PlanRead`. */
export interface Plan {
  id: string;
  code: string;
  name: string;
  plan_type: PlanType | string;
  period_year: number;
  version?: string | null;
  source_document?: string | null;
  status: PlanStatus | string;
  created_at: string;
}

/** `PlanActivityGroupCount`. */
export interface PlanActivityGroupCount {
  group_code: string | null;
  group_name: string | null;
  activity_count: number;
}

/** `PlanDetailRead` (`GET /plans/{id}`). */
export interface PlanDetail extends Plan {
  activity_count: number;
  groups: PlanActivityGroupCount[];
}

/** `PlanActivityReportRead`. */
export interface PlanActivityReport {
  id: string;
  period: ReportPeriod | string;
  reported_progress: ApiDecimal | null;
  qualitative_summary: string | null;
  evidence_refs: string[] | null;
  is_met: boolean | null;
  met_on_time: boolean | null;
  created_by?: string | null;
  updated_by?: string | null;
  updated_at?: string | null;
}

/** `PlanActivityLinkRead`. `is_confirmed` is the domain rule (D-I/H3). */
export interface PlanActivityLink {
  id: string;
  from_activity_id: string;
  to_activity_id: string;
  link_type: ActivityLinkType | string;
  source_reference: string | null;
  resolution: LinkResolution | string;
  is_confirmed: boolean;
}

/** `PlanActivityRead`. */
export interface PlanActivity {
  id: string;
  plan_id: string;
  code: string;
  group_code: string | null;
  group_name: string | null;
  name: string;
  deliverable: string | null;
  evidence_expected: string | null;
  responsible: string | null;
  is_mine: boolean;
  due_date: string | null;
  target_from: ApiDecimal | null;
  target_to: ApiDecimal | null;
  iso_controls: string[] | null;
  external_codes: string[] | null;
  scheduled_periods: string[] | null;
  sort_order: number;
  created_at: string;
  created_by?: string | null;
  updated_by?: string | null;
  // Derived by the backend service.
  activity_key: string | null;
  calculated_progress: number | null;
  primary_task_count: number;
  contributing_task_count: number;
  reported_progress: ApiDecimal | null;
  reported_period: ReportPeriod | string | null;
}

/** `PlanActivityDetailRead` (`GET /plans/activities/{id}`). */
export interface PlanActivityDetail extends PlanActivity {
  reports: PlanActivityReport[];
  links_out: PlanActivityLink[];
  links_in: PlanActivityLink[];
}

/** `ActivityTaskRead` (`GET /plans/activities/{id}/tasks`). */
export interface ActivityTask {
  task_id: string;
  task_key: string | null;
  title: string | null;
  project_code: string | null;
  project_name: string;
  status: string;
  role: TaskLinkRole | string;
  note: string | null;
  counts_toward_progress: boolean;
}

/** `ActivityConflictCountRead` (`GET /plans/activities/conflict-counts`). */
export interface ActivityConflictCount {
  activity_id: string;
  conflict_count: number;
}

/** Body of `PUT /plans/activities/{id}/reports/{period}` (replaces the row). */
export interface PlanActivityReportUpsert {
  reported_progress: number | null;
  qualitative_summary: string | null;
  evidence_refs: string[] | null;
  is_met: boolean | null;
  met_on_time: boolean | null;
}

/** Body of `POST /plans/activities/{id}/tasks`. */
export interface TaskLinkCreate {
  task_id: string;
  role: TaskLinkRole;
  note?: string | null;
}

/** Task row of the global search (`GET /search?types=task`). */
export interface TaskSearchResult {
  entity_type: string;
  id: string;
  title: string;
  snippet: string;
  project_id: string | null;
  project_name: string | null;
  task_key: string | null;
}

/** Query filters of `GET /plans/activities`. */
export interface ActivityFilters {
  plan_id?: string;
  plan_type?: PlanType;
  is_mine?: boolean;
  group_code?: string;
  task_id?: string;
  period?: ReportPeriod;
}

/** Envelopes (pagination is opt-in; unpaginated `meta = { total }`). */
export interface PlanListResponse<T> {
  data: T[];
  meta?: { total: number; page?: number; size?: number };
}

export interface PlanItemResponse<T> {
  data: T;
  message?: string;
}
