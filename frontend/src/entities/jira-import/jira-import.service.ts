import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import { skipGlobalErrorHandling } from '@shared/api/error-handling.context';
import {
  JiraImportProjectPayload,
  JiraImportSummary,
  JiraPreviewResult,
  JiraProjectSummary,
} from './jira-import.model';

/**
 * Project import from a Jira connector. Every call opts out of the global
 * error handler: the wizard shows its own inline error on each step.
 */
@Injectable({ providedIn: 'root' })
export class JiraImportService {
  private readonly http = inject(HttpClient);

  listJiraProjects(connectorId: string): Observable<{ data: JiraProjectSummary[] }> {
    return this.http.get<{ data: JiraProjectSummary[] }>(
      `${apiBase}/connectors/${connectorId}/jira/projects`,
      { context: skipGlobalErrorHandling() },
    );
  }

  previewJiraProject(
    connectorId: string,
    projectKey: string,
  ): Observable<{ data: JiraPreviewResult }> {
    return this.http.post<{ data: JiraPreviewResult }>(
      `${apiBase}/connectors/${connectorId}/jira/preview`,
      { project_key: projectKey },
      { context: skipGlobalErrorHandling() },
    );
  }

  importJiraProject(
    connectorId: string,
    payload: JiraImportProjectPayload,
  ): Observable<{ data: JiraImportSummary; message?: string }> {
    return this.http.post<{ data: JiraImportSummary; message?: string }>(
      `${apiBase}/connectors/${connectorId}/jira/import-project`,
      payload,
      { context: skipGlobalErrorHandling() },
    );
  }
}
