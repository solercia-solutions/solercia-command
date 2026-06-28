/** Domain types for the project workspace (tasks, sprints, members). */
import { Methodology } from '../project.model';

export type Priority = 'critical' | 'high' | 'medium' | 'low';
export type SprintStatus = 'active' | 'closed';
export type TaskType = 'task' | 'bug' | 'story' | 'epic';

/** A work item. `status` is a free string validated against the methodology. */
export interface Task {
  id: string;
  project_id: string;
  sprint_id: string | null;
  title: string;
  description?: string | null;
  task_type?: TaskType | string | null;
  status: string;
  priority: Priority;
  assignee_id?: string | null;
  assignee_name?: string | null;
  estimation_points?: number | null;
  estimation_hours?: number | null;
  due_date?: string | null;
  start_date?: string | null;
  /** Set when the task entered the done column; cleared when it leaves it. */
  completed_at?: string | null;
  order?: number | null;
  risk_flag?: boolean;
  risk_reason?: string | null;
  created_at: string;
}

export interface Sprint {
  id: string;
  project_id: string;
  name: string;
  goal?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  status: SprintStatus;
  created_at: string;
}

/** An assignable organization member (as exposed for a project). */
export interface Member {
  user_id: string;
  full_name: string;
  email: string;
  role: string;
}

/** Payload to create a task. Status defaults server-side to first allowed. */
export interface CreateTaskPayload {
  title: string;
  description?: string | null;
  status?: string;
  priority?: Priority;
  assignee_id?: string | null;
  estimation_points?: number | null;
  estimation_hours?: number | null;
  due_date?: string | null;
  sprint_id?: string | null;
  task_type?: TaskType | string;
}

/** Partial patch for a task (move column, reassign, edit, flag risk, etc.). */
export interface UpdateTaskPayload {
  title?: string;
  description?: string | null;
  status?: string;
  priority?: Priority;
  assignee_id?: string | null;
  estimation_points?: number | null;
  estimation_hours?: number | null;
  due_date?: string | null;
  risk_flag?: boolean;
  risk_reason?: string | null;
  sprint_id?: string | null;
  order?: number;
}

export interface CreateSprintPayload {
  name: string;
  goal?: string | null;
  start_date?: string | null;
  end_date?: string | null;
}

export interface UpdateSprintPayload {
  name?: string;
  goal?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  status?: SprintStatus;
}

/* ---- Response envelopes ({ data, meta }) ---------------------------------- */

export interface TaskListResponse {
  data: Task[];
  meta: { total: number };
}
export interface TaskItemResponse {
  data: Task;
}
export interface MemberListResponse {
  data: Member[];
}
export interface SprintListResponse {
  data: Sprint[];
}
export interface SprintItemResponse {
  data: Sprint;
}

/* ---- Burndown ------------------------------------------------------------- */

/** Unit the burndown is measured in (story points or task count). */
export type BurndownUnit = 'points' | 'tasks';

/** A single day on the burndown timeline. `actual` is null for future dates. */
export interface BurndownDay {
  date: string; // YYYY-MM-DD
  ideal: number;
  actual: number | null;
}

/** Lightweight sprint reference embedded in the burndown payload. */
export interface BurndownSprintRef {
  id: string;
  name: string;
  start_date: string | null;
  end_date: string | null;
  status: SprintStatus;
}

export interface BurndownData {
  sprint: BurndownSprintRef;
  total_points: number;
  total_tasks: number;
  completed_tasks: number;
  unit: BurndownUnit;
  days: BurndownDay[];
}

export interface BurndownResponse {
  data: BurndownData;
}

/* ---- Spanish (Colombian formal) labels ------------------------------------ */

export const PRIORITY_LABELS: Record<Priority, string> = {
  critical: 'Crítica',
  high: 'Alta',
  medium: 'Media',
  low: 'Baja',
};

export const PRIORITY_OPTIONS: ReadonlyArray<{ value: Priority; label: string }> = [
  { value: 'critical', label: PRIORITY_LABELS.critical },
  { value: 'high', label: PRIORITY_LABELS.high },
  { value: 'medium', label: PRIORITY_LABELS.medium },
  { value: 'low', label: PRIORITY_LABELS.low },
];

/** Tailwind classes for the priority chip (token-driven, light + dark). */
export const PRIORITY_CHIP_CLASS: Record<Priority, string> = {
  critical: 'bg-danger/10 text-danger',
  high: 'bg-warning/10 text-warning',
  medium: 'bg-brand/10 text-brand',
  low: 'bg-muted/10 text-muted',
};

export const TASK_TYPE_LABELS: Record<TaskType, string> = {
  task: 'Tarea',
  bug: 'Error',
  story: 'Historia',
  epic: 'Épica',
};

export const TASK_TYPE_OPTIONS: ReadonlyArray<{ value: TaskType; label: string }> = [
  { value: 'task', label: TASK_TYPE_LABELS.task },
  { value: 'story', label: TASK_TYPE_LABELS.story },
  { value: 'bug', label: TASK_TYPE_LABELS.bug },
  { value: 'epic', label: TASK_TYPE_LABELS.epic },
];

/**
 * Display label for a status/column. The stored value is kept intact for
 * PATCH; this only translates well-known English column names to Spanish.
 */
export function statusDisplay(status: string): string {
  const map: Record<string, string> = {
    'To Do': 'Por hacer',
    'In Progress': 'En progreso',
    'In Review': 'En revisión',
    Done: 'Hecho',
    Doing: 'En curso',
    Backlog: 'Backlog',
  };
  return map[status] ?? status;
}

/** Short Spanish label for the methodology (mirrors project.model labels). */
export const METHODOLOGY_BADGE: Record<Methodology, string> = {
  planner: 'Planificador',
  kanban: 'Kanban',
  scrum: 'Scrum',
  custom: 'Personalizado',
};

/** A task is overdue when its due date passed and it is not in the done column. */
export function isOverdue(task: Task, doneStatus: string | null): boolean {
  if (!task.due_date) {
    return false;
  }
  if (doneStatus && task.status === doneStatus) {
    return false;
  }
  return new Date(task.due_date).getTime() < Date.now();
}

/** Compact Spanish date (e.g. "5 jun"). Returns '' for empty input. */
export function formatShortDate(value: string | null | undefined): string {
  if (!value) {
    return '';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return date.toLocaleDateString('es-CO', { day: 'numeric', month: 'short' });
}
