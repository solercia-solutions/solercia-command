/** Types for the executive ("vista de jefe") dashboard. */
import { Methodology } from '@entities/project/project.model';
import { Task } from '@entities/workspace/workspace.model';

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

export type DailyDatePolicy = 'stored_calendar_date' | 'instant';

export interface DailyItem {
  id: string;
  project_id: string;
  task_key: string | null;
  title: string;
  status: string;
  /** Calendar date already interpreted by the API; never convert to an instant. */
  due_date: string | null;
  updated_at: string | null;
  blocked_count: number;
}

export interface DailyGroup {
  count: number;
  items: DailyItem[];
}

export interface DailyDashboard {
  timezone: string;
  date_policy: DailyDatePolicy;
  generated_at: string;
  today_date: string;
  tomorrow_date: string;
  today: DailyGroup;
  tomorrow: DailyGroup;
  overdue: DailyGroup;
  blocked: DailyGroup;
  coverage_warnings: string[];
  provider_freshness: 'unknown';
}

export interface DailyResponse {
  data: DailyDashboard;
}

export interface ExecutiveResponse {
  data: ExecutiveDashboard;
}
