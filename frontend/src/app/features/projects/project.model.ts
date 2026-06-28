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
