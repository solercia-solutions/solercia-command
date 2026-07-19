/** Methodology drives board columns, statuses, sprints and estimation. */
export type Methodology = 'planner' | 'kanban' | 'scrum' | 'custom';

/** How a methodology lets work be estimated. */
export type EstimationMode = 'none' | 'points' | 'hours' | 'both';

/**
 * Strategy-derived configuration the backend attaches to every project.
 * The board columns ARE `allowed_statuses`; the frontend derives all
 * methodology-specific behaviour from this payload (no per-methodology ifs).
 */
export interface MethodologyInfo {
  methodology: Methodology;
  default_columns: string[];
  allowed_statuses: string[];
  sprints_enabled: boolean;
  estimation_mode: EstimationMode;
  has_backlog: boolean;
}

export interface Project {
  id: string;
  name: string;
  description?: string | null;
  methodology: Methodology;
  status: string;
  organization_id: string;
  created_at: string;
  /** Parent in the hierarchy (change 21-project-hierarchy); null = root. */
  parent_project_id: string | null;
  /** Present on GET /projects and GET /projects/:id responses. */
  methodology_info?: MethodologyInfo;
}

/** A project whose methodology configuration is guaranteed to be present. */
export interface ProjectDetail extends Project {
  methodology_info: MethodologyInfo;
}

/** Single-item envelope for GET /projects/:id. */
export interface ProjectDetailResponse {
  data: ProjectDetail;
}

/** Backend list envelope: { data: [...], meta: { total } }. */
export interface ProjectListResponse {
  data: Project[];
  meta: { total: number };
}

/** Backend single-item envelope: { data: {...} }. */
export interface ProjectItemResponse {
  data: Project;
}

export interface CreateProjectPayload {
  name: string;
  description?: string | null;
  methodology: Methodology;
}

/** Spanish (Colombian formal) labels for each methodology. */
export const METHODOLOGY_LABELS: Record<Methodology, string> = {
  planner: 'Planificador',
  kanban: 'Kanban',
  scrum: 'Scrum',
  custom: 'Personalizado',
};

export const METHODOLOGY_OPTIONS: ReadonlyArray<{
  value: Methodology;
  label: string;
}> = [
  { value: 'planner', label: METHODOLOGY_LABELS.planner },
  { value: 'kanban', label: METHODOLOGY_LABELS.kanban },
  { value: 'scrum', label: METHODOLOGY_LABELS.scrum },
  { value: 'custom', label: METHODOLOGY_LABELS.custom },
];

/** Human-readable Spanish label for an arbitrary backend status code. */
export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    active: 'Activo',
    archived: 'Archivado',
    draft: 'Borrador',
    paused: 'En pausa',
    completed: 'Completado',
  };
  return map[status] ?? status;
}

/** Badge variant used by `project-tree-node` to color each methodology chip. */
export const METHODOLOGY_BADGE_VARIANT: Record<
  Methodology,
  'info' | 'success' | 'warning' | 'neutral'
> = {
  planner: 'info',
  kanban: 'success',
  scrum: 'warning',
  custom: 'neutral',
};

/** A node of `GET /projects/:id/tree` — structural fallback (design.md Decision 1). */
export interface ProjectTreeNode {
  id: string;
  name: string;
  code: string | null;
  methodology: Methodology;
  status: string;
  children: ProjectTreeNode[];
}

/** `{done, total, percent_done}` — shared shape for `self`/`rollup` counts. */
export interface ProjectProgressCounts {
  done: number;
  total: number;
  percent_done: number;
}

/** A node of `GET /projects/:id/progress` — own vs. consolidated subtree counts. */
export interface ProjectProgressNode {
  project_id: string;
  name: string;
  self: ProjectProgressCounts;
  rollup: ProjectProgressCounts;
  children: ProjectProgressNode[];
}

/** Envelope for `GET /projects/:id/tree`. */
export interface ProjectTreeResponse {
  data: ProjectTreeNode;
}

/** Envelope for `GET /projects/:id/progress`. */
export interface ProjectProgressResponse {
  data: ProjectProgressNode;
}

/**
 * View-model of a forest node, composed client-side in `hierarchy.component`
 * from `list()` (structure, grouped by `parent_project_id`) plus `progress()`
 * (roll-up numbers, one call per root — design.md Decision 1).
 */
export interface TreeNodeVM {
  id: string;
  name: string;
  methodology: Methodology;
  /** Undefined when the owning root's `/progress` call failed (R7). */
  rollup?: { done: number; total: number };
  /** Set only on the root of a branch whose `/progress` call failed (R7). */
  rollupError?: string;
  children: TreeNodeVM[];
}
