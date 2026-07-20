import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import {
  InstantiateResponse,
  OrgRoleTemplateDetailResponse,
  OrgRoleTemplateListResponse,
} from './org-role-template.model';

/** Thin HTTP client for the /org-role-templates resource. */
@Injectable({ providedIn: 'root' })
export class OrgRoleTemplatesService {
  private readonly http = inject(HttpClient);
  private readonly base = `${apiBase}/org-role-templates`;

  /** GET /org-role-templates — today, the 5 seeded system templates. */
  list(): Observable<OrgRoleTemplateListResponse> {
    return this.http.get<OrgRoleTemplateListResponse>(this.base);
  }

  /** GET /org-role-templates/:id — template detail with its node tree. */
  get(id: string): Observable<OrgRoleTemplateDetailResponse> {
    return this.http.get<OrgRoleTemplateDetailResponse>(`${this.base}/${id}`);
  }

  /**
   * POST /org-role-templates/:id/instantiate — generates (or reconciles,
   * idempotent) the template's project tree with the given lead. Requires
   * admin/manager (403 `forbidden`); 422 `lead_not_member` when the lead is
   * not an active member of the organization.
   */
  instantiate(
    id: string,
    leadUserId: string,
  ): Observable<InstantiateResponse> {
    return this.http.post<InstantiateResponse>(
      `${this.base}/${id}/instantiate`,
      { lead_user_id: leadUserId },
    );
  }
}
