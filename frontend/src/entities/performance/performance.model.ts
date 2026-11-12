/** Types for the per-collaborator performance dashboard ("Rendimiento"). */

export interface PerfUser {
  id: string;
  full_name: string;
}

/** Aggregated delivery metrics for a single collaborator. */
export interface PerfCollaborator {
  user: PerfUser;
  completed_tasks: number;
  completed_points: number;
  active_count: number;
  overdue_count: number;
  /**
   * Share of tasks completed on/before their due date, in [0, 1].
   * null when the collaborator has no completed task that had a due date.
   */
  on_time_rate: number | null;
}

export interface PerformanceData {
  collaborators: PerfCollaborator[];
  generated_at: string;
}

export interface PerformanceResponse {
  data: PerformanceData;
}
