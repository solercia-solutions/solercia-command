import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import { skipGlobalErrorHandling } from '@shared/api/error-handling.context';
import { Member } from '@entities/workspace/workspace.model';
import { Attachment, Comment, TaskDetail } from './task-detail.model';

/**
 * Every call opts out of the global error handler: the task panel shows its
 * own inline error, and an error page would discard an open draft (comment,
 * subtask) over a secondary request such as an attachment list.
 */
@Injectable({ providedIn: 'root' })
export class TaskDetailService {
  private readonly http = inject(HttpClient);

  getTaskByKey(key: string): Observable<{ data: TaskDetail }> {
    return this.http.get<{ data: TaskDetail }>(`${apiBase}/tasks/by-key/${key}`, {
      context: skipGlobalErrorHandling(),
    });
  }

  getSubtasks(taskId: string): Observable<{ data: TaskDetail[] }> {
    return this.http.get<{ data: TaskDetail[] }>(`${apiBase}/tasks/${taskId}/subtasks`, {
      context: skipGlobalErrorHandling(),
    });
  }

  updateTask(taskId: string, payload: object): Observable<{ data: TaskDetail }> {
    return this.http.patch<{ data: TaskDetail }>(`${apiBase}/tasks/${taskId}`, payload, {
      context: skipGlobalErrorHandling(),
    });
  }

  createSubtask(
    projectId: string,
    payload: { title: string; estimation_hours?: number | null; parent_task_id: string },
  ): Observable<{ data: TaskDetail }> {
    return this.http.post<{ data: TaskDetail }>(`${apiBase}/projects/${projectId}/tasks`, payload, {
      context: skipGlobalErrorHandling(),
    });
  }

  getMembers(projectId: string): Observable<{ data: Member[] }> {
    return this.http.get<{ data: Member[] }>(`${apiBase}/projects/${projectId}/members`, {
      context: skipGlobalErrorHandling(),
    });
  }

  getProjectTasks(projectId: string): Observable<{ data: TaskDetail[] }> {
    return this.http.get<{ data: TaskDetail[] }>(`${apiBase}/projects/${projectId}/tasks`, {
      context: skipGlobalErrorHandling(),
    });
  }

  getComments(taskId: string): Observable<{ data: Comment[] }> {
    return this.http.get<{ data: Comment[] }>(`${apiBase}/tasks/${taskId}/comments`, {
      context: skipGlobalErrorHandling(),
    });
  }

  createComment(taskId: string, body: string): Observable<{ data: Comment }> {
    return this.http.post<{ data: Comment }>(
      `${apiBase}/tasks/${taskId}/comments`,
      { body },
      { context: skipGlobalErrorHandling() },
    );
  }

  updateComment(commentId: string, body: string): Observable<{ data: Comment }> {
    return this.http.patch<{ data: Comment }>(
      `${apiBase}/comments/${commentId}`,
      { body },
      { context: skipGlobalErrorHandling() },
    );
  }

  deleteComment(commentId: string): Observable<void> {
    return this.http.delete<void>(`${apiBase}/comments/${commentId}`, {
      context: skipGlobalErrorHandling(),
    });
  }

  getTaskAttachments(taskId: string): Observable<{ data: Attachment[] }> {
    return this.http.get<{ data: Attachment[] }>(`${apiBase}/tasks/${taskId}/attachments`, {
      context: skipGlobalErrorHandling(),
    });
  }

  uploadTaskAttachment(taskId: string, file: File): Observable<{ data: Attachment }> {
    const fd = new FormData();
    fd.append('file', file);
    return this.http.post<{ data: Attachment }>(`${apiBase}/tasks/${taskId}/attachments`, fd, {
      context: skipGlobalErrorHandling(),
    });
  }

  getCommentAttachments(commentId: string): Observable<{ data: Attachment[] }> {
    return this.http.get<{ data: Attachment[] }>(`${apiBase}/comments/${commentId}/attachments`, {
      context: skipGlobalErrorHandling(),
    });
  }

  uploadCommentAttachment(commentId: string, file: File): Observable<{ data: Attachment }> {
    const fd = new FormData();
    fd.append('file', file);
    return this.http.post<{ data: Attachment }>(`${apiBase}/comments/${commentId}/attachments`, fd, {
      context: skipGlobalErrorHandling(),
    });
  }

  downloadAttachment(attachmentId: string): Observable<Blob> {
    return this.http.get<Blob>(`${apiBase}/attachments/${attachmentId}/download`, {
      responseType: 'blob' as 'json',
      context: skipGlobalErrorHandling(),
    });
  }
}
