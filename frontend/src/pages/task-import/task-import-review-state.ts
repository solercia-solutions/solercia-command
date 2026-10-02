import { MAX_REVIEW_DECISIONS, OptionItem, OptionPage, PreviewRow, ReviewDecision, RowKey, TaskImportPreview } from '@entities/task-import/task-import.model';

export interface RowDraft {
  action: 'include' | 'exclude';
  project: OptionItem | null;
  projectTouched: boolean;
  member: OptionItem | null;
  dateMode: 'unchanged' | 'date' | 'none';
  date: string;
  reason: string;
}
export interface OptionsState {
  status: 'loading' | 'empty' | 'filteredEmpty' | 'error' | 'success';
  query: string;
  page: OptionPage;
  error: string | null;
}
export const ROW_PAGE_SIZE = 25;
export function rowId(key: RowKey): string { return JSON.stringify([key.source_hash, key.sheet, key.row]); }
export function emptyOptions(): OptionsState {
  return { status: 'loading', query: '', page: { items: [], meta: { page: 1, size: 20, total: 0 } }, error: null };
}
export function newDrafts(preview: TaskImportPreview, project: OptionItem | null): Record<string, RowDraft> {
  return Object.fromEntries(preview.rows.filter(row => row.disposition !== 'blank_skipped').map(row => [rowId(row.key), {
    action: 'include', project, projectTouched: false, member: null,
    dateMode: 'unchanged', date: '', reason: '',
  }]));
}
/** Pydantic trims before enforcing 2–100 Unicode characters. */
export function validQuery(query: string): boolean {
  const length = Array.from(query.trim()).length;
  return length === 0 || (length >= 2 && length <= 100);
}
export function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000')) return false;
  const date = new Date(value + 'T00:00:00Z');
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}
export function decisionFor(row: PreviewRow, draft: RowDraft | undefined): ReviewDecision | null {
  if (!draft || row.disposition === 'blank_skipped') return null;
  if (draft.action === 'exclude') {
    return draft.reason.trim() && Array.from(draft.reason).length <= 512
      ? { key: row.key, action: 'exclude', reason: draft.reason } : null;
  }
  if (!draft.project || !draft.member || draft.project.id.length > 36 || draft.member.id.length > 36) return null;
  if (draft.dateMode === 'date' && !validDate(draft.date)) return null;
  return {
    key: row.key, action: 'include', project_id: draft.project.id, assignee_id: draft.member.id,
    ...(draft.dateMode === 'unchanged' ? {} : { corrections: { due_date: draft.dateMode === 'none' ? null : draft.date } }),
  };
}
/** Missing decisions stay unresolved on the server; never silently exclude. */
export function reviewDecisions(preview: TaskImportPreview, drafts: Record<string, RowDraft>): ReviewDecision[] {
  return preview.rows.map(row => decisionFor(row, drafts[rowId(row.key)]))
    .filter((decision): decision is ReviewDecision => decision !== null);
}
export function withinReviewLimits(preview: TaskImportPreview, decisions: ReviewDecision[]): boolean {
  return preview.rows.length <= MAX_REVIEW_DECISIONS && decisions.length <= MAX_REVIEW_DECISIONS &&
    preview.profile_version.length > 0 && preview.profile_version.length <= 64 &&
    /^[0-9a-f]{64}$/.test(preview.source_hash) && preview.rows.every(row =>
      row.key.source_hash === preview.source_hash && Number.isInteger(row.key.row) &&
      row.key.row >= 1 && row.key.row <= 10000 && (row.key.sheet === null || Array.from(row.key.sheet).length <= 128)) &&
    new Set(decisions.filter(d => d.action === 'include').map(d => d.project_id)).size <= 1000 &&
    new Set(decisions.filter(d => d.action === 'include').map(d => d.assignee_id)).size <= 1000;
}
export function visibleOptions(page: OptionPage, selected: OptionItem | null): OptionItem[] {
  return selected && !page.items.some(item => item.id === selected.id) ? [selected, ...page.items] : page.items;
}
