import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import { Member } from '@entities/workspace/workspace.model';
import { Attachment, Comment, TaskDetail } from './task-detail.model';

@Injectable({ providedIn: 'root' })
export class TaskDetailService {
  private readonly http = inject(HttpClient);

  getTaskByKey(key: string): Observable<{ data: TaskDetail }> {
    return this.http.get<{ data: TaskDetail }>(`${apiBase}/tasks/by-key/${key}`);
  }

  getSubtasks(taskId: string): Observable<{ data: TaskDetail[] }> {
    return this.http.get<{ data: TaskDetail[] }>(`${apiBase}/tasks/${taskId}/subtasks`);
  }

  updateTask(taskId: string, payload: object): Observable<{ data: TaskDetail }> {
    return this.http.patch<{ data: TaskDetail }>(`${apiBase}/tasks/${taskId}`, payload);
  }

  createSubtask(
    projectId: string,
    payload: { title: string; estimation_hours?: number | null; parent_task_id: string },
  ): Observable<{ data: TaskDetail }> {
    return this.http.post<{ data: TaskDetail }>(`${apiBase}/projects/${projectId}/tasks`, payload);
  }

  getMembers(projectId: string): Observable<{ data: Member[] }> {
    return this.http.get<{ data: Member[] }>(`${apiBase}/projects/${projectId}/members`);
  }

  getProjectTasks(projectId: string): Observable<{ data: TaskDetail[] }> {
    return this.http.get<{ data: TaskDetail[] }>(`${apiBase}/projects/${projectId}/tasks`);
  }

  getComments(taskId: string): Observable<{ data: Comment[] }> {
    return this.http.get<{ data: Comment[] }>(`${apiBase}/tasks/${taskId}/comments`);
  }

  createComment(taskId: string, body: string): Observable<{ data: Comment }> {
    return this.http.post<{ data: Comment }>(`${apiBase}/tasks/${taskId}/comments`, { body });
  }

  updateComment(commentId: string, body: string): Observable<{ data: Comment }> {
    return this.http.patch<{ data: Comment }>(`${apiBase}/comments/${commentId}`, { body });
  }

  deleteComment(commentId: string): Observable<void> {
    return this.http.delete<void>(`${apiBase}/comments/${commentId}`);
  }

  getTaskAttachments(taskId: string): Observable<{ data: Attachment[] }> {
    return this.http.get<{ data: Attachment[] }>(`${apiBase}/tasks/${taskId}/attachments`);
  }

  uploadTaskAttachment(taskId: string, file: File): Observable<{ data: Attachment }> {
    const fd = new FormData();
    fd.append('file', file);
    return this.http.post<{ data: Attachment }>(`${apiBase}/tasks/${taskId}/attachments`, fd);
  }

  getCommentAttachments(commentId: string): Observable<{ data: Attachment[] }> {
    return this.http.get<{ data: Attachment[] }>(`${apiBase}/comments/${commentId}/attachments`);
  }

  uploadCommentAttachment(commentId: string, file: File): Observable<{ data: Attachment }> {
    const fd = new FormData();
    fd.append('file', file);
    return this.http.post<{ data: Attachment }>(`${apiBase}/comments/${commentId}/attachments`, fd);
  }

  downloadAttachment(attachmentId: string): Observable<Blob> {
    return this.http.get<Blob>(`${apiBase}/attachments/${attachmentId}/download`, {
      responseType: 'blob' as 'json',
    });
  }
}
