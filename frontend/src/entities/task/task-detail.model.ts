import { Task } from '@entities/workspace/workspace.model';

/** Full task detail — extends workspace Task with fields from TaskRead API response. */
export interface TaskDetail extends Task {
  task_number: number | null;
  task_key: string | null;
  parent_task_id: string | null;
  subtask_progress: number | null; // 0.0–1.0, null = no subtasks
}

export interface Comment {
  id: string;
  task_id: string;
  author_id: string;
  body: string; // HTML
  mentioned_user_ids: string[];
  organization_id: string;
  created_at: string;
  updated_at: string;
}

export interface Attachment {
  id: string;
  target_type: string;
  target_id: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  uploaded_by: string;
  organization_id: string;
  created_at: string;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}
