/** Types for the executive ("vista de jefe") dashboard. */
import { Methodology } from '../projects/project.model';
import { Task } from '../projects/workspace/workspace.model';

export interface ExecUser {
  id: string;
  full_name: string;
}

/** What each person is currently working on. */
export interface ExecByAssignee {
  user: ExecUser;
  in_progress: Task[];
  active_count: number;
}

/** Active workload per person (for the bar chart). */
export interface ExecWorkload {
  user: ExecUser;
  active_count: number;
}

/** Progress roll-up per project. */
export interface ExecProjectProgress {
  project: { id: string; name: string; methodology: Methodology };
  total: number;
  done: number;
  in_progress: number;
  percent_done: number;
}

export interface ExecTotals {
  projects: number;
  tasks: number;
  overdue: number;
  at_risk: number;
}

export interface ExecutiveDashboard {
  by_assignee: ExecByAssignee[];
  at_risk: Task[];
  workload: ExecWorkload[];
  projects_progress: ExecProjectProgress[];
  totals: ExecTotals;
}

export interface ExecutiveResponse {
  data: ExecutiveDashboard;
}
