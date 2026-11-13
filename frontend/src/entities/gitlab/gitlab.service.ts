import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import { skipGlobalErrorHandling } from '@shared/api/error-handling.context';
import {
  GitlabRepository,
  ProjectRepositories,
  TaskDevelopmentActivity,
} from './gitlab.model';

/**
 * Integración de solo lectura con GitLab. Las vistas que la usan muestran su
 * propio estado de error, por eso se excluyen del manejador global.
 */
@Injectable({ providedIn: 'root' })
export class GitlabService {
  private readonly http = inject(HttpClient);

  repositories(): Observable<{ data: GitlabRepository[] }> {
    return this.http.get<{ data: GitlabRepository[] }>(`${apiBase}/gitlab/repositories`, {
      context: skipGlobalErrorHandling(),
    });
  }

  projectRepositories(projectId: string): Observable<{ data: ProjectRepositories }> {
    return this.http.get<{ data: ProjectRepositories }>(
      `${apiBase}/gitlab/projects/${projectId}/repositories`,
      { context: skipGlobalErrorHandling() },
    );
  }

  setProjectRepositories(
    projectId: string,
    repositories: string[],
  ): Observable<{ data: ProjectRepositories }> {
    return this.http.put<{ data: ProjectRepositories }>(
      `${apiBase}/gitlab/projects/${projectId}/repositories`,
      { repositories },
      { context: skipGlobalErrorHandling() },
    );
  }

  taskActivity(taskId: string): Observable<{ data: TaskDevelopmentActivity }> {
    return this.http.get<{ data: TaskDevelopmentActivity }>(
      `${apiBase}/tasks/${taskId}/gitlab/activity`,
      { context: skipGlobalErrorHandling() },
    );
  }
}
