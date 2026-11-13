/** Mirror of `backend/app/modules/jira_import/schemas.py` (project import). */

export interface ImportedProjectRef {
  id: string;
  name: string;
  code: string | null;
}

export interface JiraProjectSummary {
  key: string;
  name: string;
  imported_project: ImportedProjectRef | null;
}

export interface JiraSprintPreview {
  name: string;
  jira_state: string | null;
  status: string;
  start_date: string | null;
  end_date: string | null;
  issues: number;
}

export interface JiraStatusMapping {
  jira_status: string;
  bucket: string;
  target_status: string;
  issues: number;
}

export interface JiraPreviewResult {
  project_key: string;
  suggested_code: string;
  methodology: string;
  existing_project: ImportedProjectRef | null;
  total: number;
  counts_by_type: Record<string, number>;
  sprints: JiraSprintPreview[];
  status_mapping: JiraStatusMapping[];
  target_statuses: string[];
  /** Decimal serialized as a string by the API. */
  estimated_hours: string | number;
  issues_with_estimate: number;
  story_points: number;
  issues_with_points: number;
  unmapped_types: Record<string, number>;
  unmapped_statuses: Record<string, number>;
  unmapped_priorities: Record<string, number>;
  skipped_malformed: number;
}

export interface JiraImportProjectPayload {
  project_key: string;
  project_name?: string | null;
  project_code?: string | null;
  status_overrides?: Record<string, string>;
}

export interface EntityCounts {
  created: number;
  updated: number;
  unchanged: number;
}

export interface JiraImportSummary {
  project_id: string;
  project_code: string | null;
  project_name: string;
  project_created: boolean;
  tasks: EntityCounts;
  sprints: EntityCounts;
  parents_linked: number;
  orphans: string[];
  unassigned: string[];
  unmapped_types: Record<string, number>;
  unmapped_statuses: Record<string, number>;
  unmapped_priorities: Record<string, number>;
  errors: string[];
}
