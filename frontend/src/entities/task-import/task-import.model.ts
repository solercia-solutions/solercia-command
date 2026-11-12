export type ImportFormat = 'csv' | 'xlsx';

/** Mirrors the server-owned ParseLimits default; server validation remains authoritative. */
export const MAX_PREVIEW_BYTES = 5 * 1024 * 1024;

export interface PreviewIssue {
  code: string;
  severity: 'error' | 'warning' | 'info';
  row: number | null;
  column: number | null;
}

export const MAX_REVIEW_DECISIONS = 9999;
export const MAX_ENCODED_SOURCE = 4 * Math.ceil(MAX_PREVIEW_BYTES / 3);
export const MAX_REVIEW_BODY_BYTES = MAX_ENCODED_SOURCE + MAX_REVIEW_DECISIONS * 4096 + 4096;

export interface RowKey {
  source_hash: string;
  sheet: string | null;
  row: number;
}

export interface PreviewRow {
  key: RowKey;
  number: number;
  disposition: 'candidate' | 'blank_skipped' | 'rejected';
  due_date: string | null;
  fields: { name: string; value: string | number | boolean | null }[];
  issues: PreviewIssue[];
}

export interface TaskImportPreview {
  source_hash: string;
  profile_version: string;
  complete: boolean;
  rows: PreviewRow[];
  issues: PreviewIssue[];
  counts: {
    candidate: number;
    rejected: number;
    blank_skipped: number;
    total: number;
  } | null;
}

export interface PreviewResponse {
  data: TaskImportPreview;
  message: string;
}

export interface OptionItem { id: string; label: string }
export interface OptionPage {
  items: OptionItem[];
  meta: { page: number; size: number; total: number };
}
export type OptionCollection = 'projects' | 'members';
export interface OptionsResponse {
  data: { projects: OptionPage; members: OptionPage; default_project: OptionItem | null };
  message: string;
}
export type ReviewDecision =
  | { key: RowKey; action: 'include'; project_id: string; assignee_id: string; corrections?: { due_date: string | null } }
  | { key: RowKey; action: 'exclude'; reason: string };
export interface ReviewRequest {
  format: ImportFormat;
  profile: 'checklist';
  source_base64: string;
  source_hash: string;
  profile_version: string;
  decisions: ReviewDecision[];
}
export interface ReviewRow {
  key: RowKey;
  action: 'include' | 'exclude' | 'blank_skipped' | 'unresolved';
  project_id: string | null;
  assignee_id: string | null;
  effective_due_date: string | null;
  effective_status: string | null;
  issues: string[];
}
export interface ReviewData {
  status: 'blocked' | 'validated_for_review';
  source_hash: string;
  profile_version: string;
  counts: TaskImportPreview['counts'];
  issues: string[];
  rows: ReviewRow[];
}
export interface ReviewResponse { data: ReviewData; message: string }

export function previewFormat(name: string): ImportFormat | null {
  const extension = name.split('.').pop()?.toLowerCase();
  return extension === 'csv' || extension === 'xlsx' ? extension : null;
}
