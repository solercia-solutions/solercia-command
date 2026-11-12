import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { apiBase } from '@shared/api/api.config';
import { skipGlobalErrorHandling } from '@shared/api/error-handling.context';
import {
  MemberCreatePayload,
  MemberRole,
  Organization,
  OrganizationCreatePayload,
  OrganizationItemResponse,
  OrganizationListResponse,
  OrganizationMember,
  OrganizationMembership,
  OrganizationUpdatePayload,
} from './organization.model';

/**
 * Thin HTTP client for CRUD + membership on /organizations (organizations-admin).
 *
 * Every call opts out of the global error handler: the admin page, the
 * organization switcher and the plans page already show their own inline error.
 */
@Injectable({ providedIn: 'root' })
export class OrganizationsService {
  private readonly http = inject(HttpClient);
  private readonly base = `${apiBase}/organizations`;

  /** GET /organizations/mine — every organization the caller belongs to. */
  mine(): Observable<OrganizationListResponse<OrganizationMembership>> {
    return this.http.get<OrganizationListResponse<OrganizationMembership>>(
      `${this.base}/mine`,
      { context: skipGlobalErrorHandling() },
    );
  }

  /** POST /organizations — bootstrap; the creator becomes its sole admin. */
  create(
    payload: OrganizationCreatePayload,
  ): Observable<OrganizationItemResponse<Organization>> {
    return this.http.post<OrganizationItemResponse<Organization>>(
      this.base,
      payload,
      { context: skipGlobalErrorHandling() },
    );
  }

  get(id: string): Observable<OrganizationItemResponse<Organization>> {
    return this.http.get<OrganizationItemResponse<Organization>>(
      `${this.base}/${id}`,
      { context: skipGlobalErrorHandling() },
    );
  }

  update(
    id: string,
    payload: OrganizationUpdatePayload,
  ): Observable<OrganizationItemResponse<Organization>> {
    return this.http.patch<OrganizationItemResponse<Organization>>(
      `${this.base}/${id}`,
      payload,
      { context: skipGlobalErrorHandling() },
    );
  }

  remove(id: string): Observable<OrganizationItemResponse<null>> {
    return this.http.delete<OrganizationItemResponse<null>>(
      `${this.base}/${id}`,
      { context: skipGlobalErrorHandling() },
    );
  }

  listMembers(
    id: string,
  ): Observable<OrganizationListResponse<OrganizationMember>> {
    return this.http.get<OrganizationListResponse<OrganizationMember>>(
      `${this.base}/${id}/members`,
      { context: skipGlobalErrorHandling() },
    );
  }

  addMember(
    id: string,
    payload: MemberCreatePayload,
  ): Observable<OrganizationItemResponse<OrganizationMember>> {
    return this.http.post<OrganizationItemResponse<OrganizationMember>>(
      `${this.base}/${id}/members`,
      payload,
      { context: skipGlobalErrorHandling() },
    );
  }

  updateMemberRole(
    id: string,
    memberId: string,
    role: MemberRole,
  ): Observable<OrganizationItemResponse<OrganizationMember>> {
    return this.http.patch<OrganizationItemResponse<OrganizationMember>>(
      `${this.base}/${id}/members/${memberId}`,
      { role },
      { context: skipGlobalErrorHandling() },
    );
  }

  removeMember(
    id: string,
    memberId: string,
  ): Observable<OrganizationItemResponse<null>> {
    return this.http.delete<OrganizationItemResponse<null>>(
      `${this.base}/${id}/members/${memberId}`,
      { context: skipGlobalErrorHandling() },
    );
  }
}
