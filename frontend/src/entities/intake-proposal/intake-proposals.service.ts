import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import { skipGlobalErrorHandling } from '@shared/api/error-handling.context';
import { IntakeProposal, ProposalPage, ProposalQuery } from './intake-proposal.model';

/** `/intake/proposals`: admin y manager. La bandeja pinta sus propios errores. */
@Injectable({ providedIn: 'root' })
export class IntakeProposalsService {
  private readonly http = inject(HttpClient);
  private readonly base = `${apiBase}/intake/proposals`;

  list(query: ProposalQuery): Observable<ProposalPage> {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== null && value !== undefined && value !== '') {
        params = params.set(key, String(value));
      }
    }
    return this.http.get<ProposalPage>(this.base, {
      params,
      context: skipGlobalErrorHandling(),
    });
  }

  get(id: string): Observable<{ data: IntakeProposal }> {
    return this.http.get<{ data: IntakeProposal }>(`${this.base}/${id}`, {
      context: skipGlobalErrorHandling(),
    });
  }

  /** Vincula el hilo a la tarea; el estado de la tarea cambia SOLO si se envía `status`. */
  accept(
    id: string,
    body: { task_id?: string | null; status?: string | null },
  ): Observable<{ data: IntakeProposal }> {
    const payload: Record<string, string> = {};
    if (body.task_id) {
      payload['task_id'] = body.task_id;
    }
    if (body.status) {
      payload['status'] = body.status;
    }
    return this.http.post<{ data: IntakeProposal }>(`${this.base}/${id}/accept`, payload, {
      context: skipGlobalErrorHandling(),
    });
  }

  dismiss(id: string): Observable<{ data: IntakeProposal }> {
    return this.http.post<{ data: IntakeProposal }>(`${this.base}/${id}/dismiss`, null, {
      context: skipGlobalErrorHandling(),
    });
  }

  createTask(id: string): Observable<{ data: IntakeProposal }> {
    return this.http.post<{ data: IntakeProposal }>(`${this.base}/${id}/create-task`, {}, {
      context: skipGlobalErrorHandling(),
    });
  }
}
